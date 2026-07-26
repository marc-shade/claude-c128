/*
 * claude-c128 client.
 *
 * Renders the bridge's wire protocol onto the C128's 80-column VDC screen and
 * sends keystrokes back. The C128 does no layout of its own: the Linux side
 * already decided what every cell should contain, so this is a thin, fast
 * applier of cell runs.
 *
 * The protocol is decoded by a resumable state machine because bytes arrive
 * from the NMI ring buffer in arbitrary chunks, and a command can be split
 * across two reads.
 */
#include <c128.h>
#include <conio.h>
#include <stdint.h>

/* --- hardware, implemented in c128hw.s ---------------------------------- */
extern unsigned char vdcRow, vdcCol, vdcAttr, vdcLen, vdcChar;
extern unsigned char vdcBuf[256];

void vdc_init(void);
void vdc_run(void);
void vdc_fill(void);
void vdc_clear(void);
void vdc_place_cursor(void);
void vdc_setglyph(void);

void acia_init(void);
void acia_shutdown(void);
unsigned char acia_avail(void);
unsigned char acia_get(void);
void acia_put(unsigned char b);
unsigned char kb_get(void);       /* KERNAL GETIN: PETSCII key, 0 if none */
void vdc_mirror(void);            /* copy a VDC plane into mirrorBuf */
extern unsigned char mirrorBuf[2048];

/* --- protocol ----------------------------------------------------------- */
#define CMD_CLEAR   0x01
#define CMD_RUN     0x02
#define CMD_FILL    0x03
#define CMD_CURSOR  0x04
#define CMD_FRAME   0x05
#define CMD_BELL    0x06
#define CMD_PANEL   0x07
#define CMD_HELLO   0x08
#define CMD_BYE     0x09
#define CMD_GLYPH   0x0A

#define CURSOR_HIDE 0xFF

/* Parser states. Each command collects a fixed header, then a payload. */
enum {
    S_OPCODE,
    S_ARGS,
    S_PAYLOAD,
    S_PANEL_PAYLOAD,
    S_GLYPH_PAYLOAD
};

static unsigned char state = S_OPCODE;
static unsigned char opcode;
static unsigned char args[4];
static unsigned char argsNeeded;
static unsigned char argsGot;
static unsigned char payloadNeeded;
static unsigned char payloadGot;
static unsigned char panelRow;
static unsigned char running = 1;
static unsigned char framesSeen;

/* Exported for the emulator harness: proves the main loop is alive. */
unsigned int loopCount;
static unsigned char consumed;
/* Host-settable: write 1 for characters or 2 for attributes and the main loop
   copies that VDC plane into mirrorBuf, then clears this back to 0. */
unsigned char mirrorReq;
static unsigned int retry;

/* The 40-column VIC-II companion screen is written directly; it is small and
   updated rarely, so it does not need the VDC fast path. */
#define VIC_SCREEN ((unsigned char *)0x0400)
#define VIC_COLOR  ((unsigned char *)0xD800)

static void panel_write(unsigned char row, unsigned char col, unsigned char code)
{
    unsigned int off = (unsigned int)row * 40u + col;
    if (row < 25 && col < 40) {
        VIC_SCREEN[off] = code;
        VIC_COLOR[off] = COLOR_GRAY2;
    }
}

static void bell(void)
{
    /* A short blip on SID voice 3 rather than the KERNAL bell, which would
       write to the 40-column screen we are using as a status panel. */
    unsigned char i;
    SID.v3.freq = 0x2000;
    SID.v3.ad = 0x09;
    SID.v3.sr = 0x00;
    SID.amp = 0x0F;
    SID.v3.ctrl = 0x21;
    for (i = 0; i < 120; ++i) {
        /* deliberate short spin: the blip must not stall the receive loop */
    }
    SID.v3.ctrl = 0x20;
}

/*
 * Ultimate II+ modem answering.
 *
 * The Ultimate presents a Hayes modem in front of the ACIA. When the bridge
 * dials in, it sends "\rRING\r" and waits for "ATA". Its replies are printable
 * ASCII plus CR, and protocol opcodes are $01-$09, so the two streams cannot
 * be confused: every byte can be offered to this watcher and to the protocol
 * decoder, and each ignores what belongs to the other.
 *
 * On a machine with no modem in front of the ACIA (VICE, or a real RS-232
 * cartridge) no RING ever arrives and this simply never fires.
 */
/* Explicit ASCII, not char literals: cc65 maps 'R' to PETSCII $D2 for CBM
   targets, which could never match the $52 the modem actually sends. */
static const unsigned char RING[4] = { 0x52, 0x49, 0x4E, 0x47 };   /* "RING" */
static unsigned char ringMatch;
static unsigned char answered;

static void modem_watch(unsigned char b)
{
    if (answered)
        return;
    if (b == RING[ringMatch]) {
        if (++ringMatch == 4) {
            static const unsigned char ata[4] = { 0x41, 0x54, 0x41, 0x0D };  /* "ATA" */
            unsigned char i;
            for (i = 0; i < 4; ++i)
                acia_put(ata[i]);
            answered = 1;
            ringMatch = 0;
        }
    } else {
        ringMatch = (b == RING[0]) ? 1 : 0;
    }
}

static void handle_byte(unsigned char b)
{
    switch (state) {
    case S_OPCODE:
        opcode = b;
        argsGot = 0;
        payloadGot = 0;
        switch (opcode) {
        case CMD_CLEAR:  argsNeeded = 1; break;
        case CMD_RUN:    argsNeeded = 4; break;
        case CMD_FILL:   argsNeeded = 5; break;
        case CMD_CURSOR: argsNeeded = 2; break;
        case CMD_PANEL:  argsNeeded = 2; break;
        case CMD_HELLO:  argsNeeded = 2; break;
        case CMD_GLYPH:  argsNeeded = 1; break;
        case CMD_FRAME:  framesSeen = 1; return;
        case CMD_BELL:   bell(); return;
        case CMD_BYE:    running = 0; return;
        default:
            /* Desynchronised: ignore until something parses again. */
            return;
        }
        state = S_ARGS;
        return;

    case S_ARGS:
        if (argsGot < sizeof(args))
            args[argsGot] = b;
        ++argsGot;
        if (argsGot < argsNeeded)
            return;

        switch (opcode) {
        case CMD_CLEAR:
            vdcAttr = args[0];
            vdc_clear();
            state = S_OPCODE;
            return;

        case CMD_RUN:
            vdcRow = args[0];
            vdcCol = args[1];
            vdcAttr = args[2];
            payloadNeeded = args[3];
            if (payloadNeeded == 0) {
                state = S_OPCODE;
                return;
            }
            state = S_PAYLOAD;
            return;

        case CMD_FILL:
            /* args: row, col, attr, len, char - the char is the 5th byte, and
               args[] only holds four, so it arrives in `b`. */
            vdcRow = args[0];
            vdcCol = args[1];
            vdcAttr = args[2];
            vdcLen = args[3];
            vdcChar = b;
            vdc_fill();
            state = S_OPCODE;
            return;

        case CMD_CURSOR:
            if (args[0] == CURSOR_HIDE) {
                /* Park the cursor off-screen; the VDC has no hide bit here. */
                vdcRow = 24;
                vdcCol = 79;
            } else {
                vdcRow = args[0];
                vdcCol = args[1];
            }
            vdc_place_cursor();
            state = S_OPCODE;
            return;

        case CMD_GLYPH:
            /* args[0] is the character code; the 8 bitmap rows follow. */
            vdcChar = args[0];
            payloadNeeded = 8;
            state = S_GLYPH_PAYLOAD;
            return;

        case CMD_PANEL:
            panelRow = args[0];
            payloadNeeded = args[1];
            if (payloadNeeded == 0) {
                state = S_OPCODE;
                return;
            }
            state = S_PANEL_PAYLOAD;
            return;

        case CMD_HELLO:
        default:
            state = S_OPCODE;
            return;
        }

    case S_PAYLOAD:
        vdcBuf[payloadGot] = b;
        ++payloadGot;
        if (payloadGot >= payloadNeeded) {
            vdcLen = payloadNeeded;
            vdc_run();
            state = S_OPCODE;
        }
        return;

    case S_PANEL_PAYLOAD:
        panel_write(panelRow, payloadGot, b);
        ++payloadGot;
        if (payloadGot >= payloadNeeded)
            state = S_OPCODE;
        return;

    case S_GLYPH_PAYLOAD:
        vdcBuf[payloadGot] = b;
        ++payloadGot;
        if (payloadGot >= 8) {
            vdc_setglyph();
            state = S_OPCODE;
        }
        return;
    }
}

/* --- client -> server control ------------------------------------------- */
#define CLIENT_ESCAPE 0x00
#define CLIENT_RESYNC 0x01
#define CLIENT_BYE    0x02
#define CLIENT_CREDIT 0x03
/* Must match CREDIT_UNIT in server/protocol.py. */
#define CREDIT_UNIT   64

#define KEY_HELP      0x84      /* C128 HELP key */

static void send_control(unsigned char code)
{
    acia_put(CLIENT_ESCAPE);
    acia_put(code);
}

/* --- keyboard ----------------------------------------------------------- */
static void pump_keyboard(void)
{
    unsigned char k;
    /* GETIN returns PETSCII straight from the KERNAL buffer, or 0 when empty.
       Translation to terminal input happens on the Linux side. */
    while ((k = kb_get()) != 0) {
        if (k == KEY_HELP) {
            /* Repaint from scratch, and re-arm the modem watcher so a bridge
               that has been restarted can ring us again. */
            state = S_OPCODE;
            framesSeen = 0;
            answered = 0;
            ringMatch = 0;
            retry = 0;
            send_control(CLIENT_RESYNC);
        } else if (k == CLIENT_ESCAPE) {
            continue;           /* $00 is reserved as the control escape */
        } else {
            acia_put(k);
        }
    }
}

/*
 * cc65 translates string literals to PETSCII for CBM targets, so text arriving
 * from C is PETSCII, not ASCII. The VDC stores screen codes, which are a
 * different encoding again; this is the standard PETSCII -> screen code fold.
 */
static unsigned char petscii_to_screen(unsigned char c)
{
    if (c < 0x20) return c + 0x80;
    if (c < 0x40) return c;                 /* space .. ?            */
    if (c < 0x60) return c - 0x40;          /* @A-Z  -> $00-$1F      */
    if (c < 0x80) return c - 0x20;          /* graphics              */
    if (c < 0xA0) return c + 0x40;
    if (c < 0xC0) return c - 0x40;
    if (c < 0xFF) return c - 0x80;
    return 0x5E;
}

static void splash(void)
{
    static const char *msg = "claude code / c128 - connecting";
    unsigned char i;
    for (i = 0; msg[i]; ++i)
        vdcBuf[i] = petscii_to_screen((unsigned char)msg[i]);
    vdcRow = 0;
    vdcCol = 0;
    vdcAttr = 0x0E;
    vdcLen = i;
    vdc_run();
}

int main(void)
{
    unsigned char budget;

    /* Deliberately stay at 1MHz. fast() would double VDC throughput but blanks
       the VIC-II, and the 40-column screen is the companion status display on
       the second monitor. At 38400 baud a byte arrives every ~260 cycles and
       the NMI handler costs about 30, so 1MHz has ample headroom.

       Put the editor on the 40-column screen as well, so KERNAL output cannot
       scribble on the VDC surface we are painting. */
    videomode(VIDEOMODE_40COL);
    clrscr();
    cputs("claude code / c128 bridge client\r\n");
    cputs("80-column screen is the terminal.\r\n");
    cputs("RUN/STOP + RESTORE to quit.\r\n");

    vdcAttr = 0x0E;
    vdc_init();
    splash();
    acia_init();

    /* Only now is the NMI handler live. Anything the bridge sent while this
       machine was still loading is gone, so ask for the screen from scratch
       instead of starting from a partial picture. */
    consumed = 0;
    retry = 0;
    send_control(CLIENT_RESYNC);

    while (running) {
        ++loopCount;
        /* Re-announce until the server replies with a frame. The first attempt
           is lost whenever a modem is still in command mode, and on real
           hardware the operator may start this before the bridge exists. */
        if (!framesSeen && ++retry == 0)
            send_control(CLIENT_RESYNC);
        /* Drain a bounded number of bytes before checking the keyboard, so a
           fast sender cannot starve input, and a burst still gets applied in
           one go rather than one byte per outer iteration. */
        if (mirrorReq) {
            if (mirrorReq == 4) {
                /* Diagnostic: run a full clear on demand, so the host can test
                   vdc_clear in isolation from the protocol path. */
                vdcAttr = 0x0E;
                vdc_clear();
            } else {
                vdcChar = mirrorReq - 1;  /* 0 = characters, 1 = attributes */
                vdc_mirror();
            }
            mirrorReq = 0;
        }
        budget = 255;
        while (budget-- && acia_avail()) {
            unsigned char b = acia_get();
            /* Every byte taken out of the ring is room the server may reuse.
               Acknowledging in units keeps the return traffic negligible while
               never letting the server run further ahead than the ring holds. */
            if (++consumed >= CREDIT_UNIT) {
                consumed = 0;
                send_control(CLIENT_CREDIT);
            }
            modem_watch(b);
            handle_byte(b);
            if (answered == 1) {
                /* Just answered the call. The modem is still parsing "ATA" and
                   has not gone transparent, so anything sent now is swallowed;
                   the retry below is what actually gets through. */
                answered = 2;
                state = S_OPCODE;
                retry = 0;
            }
        }
        pump_keyboard();
    }

    send_control(CLIENT_BYE);
    acia_shutdown();
    videomode(VIDEOMODE_40COL);
    clrscr();
    cputs("disconnected.\r\n");
    return 0;
}
