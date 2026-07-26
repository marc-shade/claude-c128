; ---------------------------------------------------------------------------
; claude-c128 client: C64 hardware layer.
;
; Implements the same interface as c128hw.s against the VIC-II's 40x25 screen
; instead of the C128's 80-column VDC. main.c is shared; everything that differs
; between the machines is here or behind __C64__ in main.c.
;
; Four things are genuinely different, and each one is a trap:
;
;  1. NMI. The C128 ROM stub at $FF05 saves A/X/Y and the MMU before dispatching
;     through $0318, so a handler there must leave via $FF33. The C64 saves
;     NOTHING before $0318 - the CPU has pushed only P and PC. So this handler
;     pushes its own registers and returns with RTI, and restores them before
;     chaining so the ROM handler sees the stack it expects.
;
;  2. Attributes. Colour RAM holds four bits of colour and nothing else: there is
;     no reverse, underline or blink bit. Reverse video on a C64 is a different
;     glyph - screen code with bit 7 set - so the protocol's reverse bit has to
;     be folded into the character, not the colour. Underline cannot be rendered
;     at all and is dropped; see the note on attrToColour.
;
;  3. Character set. The bridge sends lowercase-set screen codes, and the C64
;     powers up in the uppercase/graphics set. The custom glyphs the bridge
;     uploads also have to live somewhere writable. Both are solved by copying
;     the ROM's lowercase set into RAM at CHARSET and pointing the VIC there.
;
;  4. No hardware cursor. The VDC has one; the VIC-II does not. Drawn by
;     inverting the cell, with the original byte saved so it can be put back.
; ---------------------------------------------------------------------------

        .export _scr_init, _scr_run, _scr_fill, _scr_clear, _scr_place_cursor
        .export _acia_init, _acia_get, _acia_avail, _acia_put, _acia_shutdown
        .export _kb_get, _kbCount
        .export _scr_mirror, _mirrorBuf, _lastAttr, _scr_setglyph
        .export _scrRow, _scrCol, _scrAttr, _scrLen, _scrChar, _scrBuf
        .export _rxHead, _rxTail, _rxCount, _nmiCount, _rxOverruns, _rxDropped

        .importzp ptr1, ptr2

SCREEN          = $0400         ; VIC-II text matrix, 1000 cells
COLORRAM        = $D800         ; four bits of colour per cell
CHARSET         = $3000         ; our copy of the lowercase set, 2 KB

; VIC-II memory pointers: bits 7-4 select the screen base within the 16 KB VIC
; bank (SCREEN/$0400 = 1), bits 3-1 the character base (CHARSET/$0800 = 6).
VIC_MEMPTR      = $D018
VIC_MEMPTR_VAL  = (1 << 4) | (6 << 1)

; Character ROM as the CPU sees it with CHAREN low. The lowercase set is the
; second half; its upper 1 KB is the reversed forms, which is exactly what the
; VIC uses for screen codes $80-$FF, so a straight 2 KB copy gives both.
CHARROM_LOWER   = $D800
CPU_PORT        = $01

COLS            = 40
ROWS            = 25
CELLS           = COLS * ROWS   ; 1000

ACIA_DATA       = $DE00
ACIA_STATUS     = $DE01
ACIA_CMD        = $DE02
ACIA_CTRL       = $DE03

; Same SwiftLink doubled-crystal codes as the C128. The C64 has an easier job
; here - 1000 cells to repaint instead of 2000, written straight to RAM rather
; than through the VDC's handshaked port - so the receive ring is under less
; pressure at a given baud rate, not more.
ACIA_CTRL_VAL   = $1F
ACIA_CMD_VAL    = $09

NMI_VECTOR      = $0318

        .bss

_scrRow:        .res 1
_scrCol:        .res 1
_scrAttr:       .res 1
_scrLen:        .res 1
_scrChar:       .res 1
_scrBuf:        .res 256

_rxHead:        .res 1
_rxTail:        .res 1
_rxCount:       .res 2          ; bytes accepted from the ACIA
_nmiCount:      .res 2          ; NMIs seen, ours or not
_rxOverruns:    .res 1          ; ACIA reported a dropped byte
_rxDropped:     .res 1          ; receive ring was full; byte discarded
_kbCount:       .res 2          ; keys read, for diagnostics

_lastAttr:      .res 1          ; last colour nibble scr_run wrote
_mirrorBuf:     .res 2048

oldNmi:         .res 2
offsetLo:       .res 1
offsetHi:       .res 1
revMask:        .res 1          ; $80 when the run is reverse video, else $00
colourVal:      .res 1
tmp:            .res 1

; Software cursor: where it is, and what was underneath it.
curOffLo:       .res 1
curOffHi:       .res 1
curSaved:       .res 1
curActive:      .res 1

rxHead          = _rxHead
rxTail          = _rxTail
rxBuf:          .res 256

        .rodata

; Row start offsets, computed by the assembler. A hand-written table is exactly
; the kind of thing that is wrong in one entry and produces a bug that looks
; like a protocol fault.
rowLo:  .repeat ROWS, I
        .byte <(I * COLS)
        .endrepeat
rowHi:  .repeat ROWS, I
        .byte >(I * COLS)
        .endrepeat

        .code

; ---------------------------------------------------------------------------
; calcOffset: offsetHi/Lo = scrRow * 40 + scrCol
; ---------------------------------------------------------------------------
calcOffset:
        ldx _scrRow
        cpx #ROWS
        bcc @ok
        ldx #ROWS-1             ; clamp rather than write off the end
@ok:    lda rowLo,x
        clc
        adc _scrCol
        sta offsetLo
        lda rowHi,x
        adc #0
        sta offsetHi
        rts

; ---------------------------------------------------------------------------
; setPointers: ptr1 -> screen cell, ptr2 -> colour cell, both at offsetHi/Lo
; ---------------------------------------------------------------------------
setPointers:
        lda offsetLo
        clc
        adc #<SCREEN
        sta ptr1
        lda offsetHi
        adc #>SCREEN
        sta ptr1+1
        lda offsetLo
        clc
        adc #<COLORRAM
        sta ptr2
        lda offsetHi
        adc #>COLORRAM
        sta ptr2+1
        rts

; ---------------------------------------------------------------------------
; attrToColour: protocol attribute -> colour nibble in colourVal, and the
; reverse-video mask in revMask.
;
; The protocol attribute is the VDC's own layout: bit7 alt charset | bit6 reverse
; | bit5 underline | bit4 blink | bits3-0 colour. Of those the VIC-II can express
; only the colour and, by using a different glyph, the reverse.
;
; Underline is dropped. That is a real loss - Claude Code underlines links - but
; the alternative would be to spend one of the 256 character slots per underlined
; glyph, and the bridge is already using free slots for its box-drawing set.
; Blink is dropped for the same reason; the VIC-II has no blink attribute.
; ---------------------------------------------------------------------------
attrToColour:
        lda _scrAttr
        and #$0F
        sta colourVal
        sta _lastAttr
        lda _scrAttr
        and #$40                ; reverse
        beq @norev
        lda #$80
@norev: sta revMask
        rts

; ---------------------------------------------------------------------------
; _scr_run: write scrLen screen codes from scrBuf at (scrRow,scrCol) and set
;           the matching colour cells.
; ---------------------------------------------------------------------------
_scr_run:
        lda _scrLen
        bne @go
        rts
@go:    jsr calcOffset
        jsr setPointers
        jsr attrToColour
        ldy #0
@loop:  lda _scrBuf,y
        ora revMask
        sta (ptr1),y
        lda colourVal
        sta (ptr2),y
        iny
        cpy _scrLen
        bne @loop
        ; A run may have painted over the cursor cell. Leaving curActive set
        ; would make the next place_cursor restore a stale byte on top of the
        ; new text, so the saved cell is only trusted if it still looks like our
        ; inverted copy - see _scr_place_cursor.
        rts

; ---------------------------------------------------------------------------
; _scr_fill: scrLen copies of scrChar at (scrRow,scrCol)
; ---------------------------------------------------------------------------
_scr_fill:
        lda _scrLen
        bne @go
        rts
@go:    jsr calcOffset
        jsr setPointers
        jsr attrToColour
        lda _scrChar
        ora revMask
        sta tmp
        ldy #0
@loop:  lda tmp
        sta (ptr1),y
        lda colourVal
        sta (ptr2),y
        iny
        cpy _scrLen
        bne @loop
        rts

; ---------------------------------------------------------------------------
; _scr_clear: blank all 1000 cells and set all 1000 colour bytes.
;
; Four 250-byte strips rather than a 16-bit loop: one X register covers the lot
; and it is roughly twice as fast, which matters because a clear arrives at the
; start of every full repaint and the receive ring keeps filling meanwhile.
; ---------------------------------------------------------------------------
_scr_clear:
        jsr attrToColour
        lda #0
        sta curActive           ; whatever was under the cursor is gone
        ldx #0
@loop:  lda #$20                ; screen code for space
        sta SCREEN + 0,x
        sta SCREEN + 250,x
        sta SCREEN + 500,x
        sta SCREEN + 750,x
        lda colourVal
        sta COLORRAM + 0,x
        sta COLORRAM + 250,x
        sta COLORRAM + 500,x
        sta COLORRAM + 750,x
        inx
        cpx #250
        bne @loop
        rts

; ---------------------------------------------------------------------------
; _scr_place_cursor: software cursor.
;
; Restores the previous cell first, but only if it still holds the inverted copy
; this routine wrote. If a run has repainted that cell since, the saved byte is
; stale and writing it back would corrupt one character - which is exactly the
; sort of fault that looks like a protocol bug.
; ---------------------------------------------------------------------------
_scr_place_cursor:
        lda curActive
        beq @place
        lda curOffLo
        clc
        adc #<SCREEN
        sta ptr1
        lda curOffHi
        adc #>SCREEN
        sta ptr1+1
        ldy #0
        lda (ptr1),y
        cmp curSaved            ; unchanged since we inverted it?
        bne @stale
        ; It matches what we wrote, so it is ours to put back.
        lda curSaved
        and #$7F
        sta (ptr1),y
@stale: lda #0
        sta curActive

@place: jsr calcOffset
        jsr setPointers
        ldy #0
        lda (ptr1),y
        ora #$80                ; reverse the glyph
        sta (ptr1),y
        sta curSaved            ; remember the inverted form, to detect repaints
        lda offsetLo
        sta curOffLo
        lda offsetHi
        sta curOffHi
        lda #1
        sta curActive
        rts

; ---------------------------------------------------------------------------
; _scr_setglyph: 8 bitmap rows from scrBuf into CHARSET + scrChar * 8
; ---------------------------------------------------------------------------
_scr_setglyph:
        lda _scrChar
        sta ptr1
        lda #0
        sta ptr1+1
        asl ptr1
        rol ptr1+1
        asl ptr1
        rol ptr1+1
        asl ptr1
        rol ptr1+1              ; ptr1 = code * 8
        lda ptr1
        clc
        adc #<CHARSET
        sta ptr1
        lda ptr1+1
        adc #>CHARSET
        sta ptr1+1
        ldy #0
@loop:  lda _scrBuf,y
        sta (ptr1),y
        iny
        cpy #8
        bne @loop
        rts

; ---------------------------------------------------------------------------
; _scr_init: copy the ROM lowercase set into RAM, point the VIC at it, clear.
;
; The copy runs with the character ROM banked in over the I/O area, so no
; interrupt may fire: the KERNAL's IRQ would touch $D000-$DFFF and find character
; data. IRQs are masked here. An NMI in this window would do the same damage, but
; ours is not hooked yet and RESTORE during startup is the operator's choice.
; ---------------------------------------------------------------------------
_scr_init:
        sei
        lda CPU_PORT
        pha
        and #$FB                ; CHAREN low: character ROM visible at $D000
        sta CPU_PORT

        lda #<CHARROM_LOWER
        sta ptr1
        lda #>CHARROM_LOWER
        sta ptr1+1
        lda #<CHARSET
        sta ptr2
        lda #>CHARSET
        sta ptr2+1
        ldx #8                  ; 8 pages = 2 KB = 256 glyphs
@page:  ldy #0
@byte:  lda (ptr1),y
        sta (ptr2),y
        iny
        bne @byte
        inc ptr1+1
        inc ptr2+1
        dex
        bne @page

        pla
        sta CPU_PORT            ; I/O back
        cli

        lda #VIC_MEMPTR_VAL
        sta VIC_MEMPTR

        lda #0
        sta curActive
        jsr _scr_clear
        rts

; ---------------------------------------------------------------------------
; _acia_init: configure the ACIA and hook NMI
; ---------------------------------------------------------------------------
_acia_init:
        sei
        lda #0
        sta rxHead
        sta rxTail

        lda NMI_VECTOR
        sta oldNmi
        lda NMI_VECTOR+1
        sta oldNmi+1
        lda #<nmiHandler
        sta NMI_VECTOR
        lda #>nmiHandler
        sta NMI_VECTOR+1

        lda ACIA_STATUS         ; clear any pending interrupt
        lda #ACIA_CTRL_VAL
        sta ACIA_CTRL
        lda #ACIA_CMD_VAL
        sta ACIA_CMD
        cli
        rts

; ---------------------------------------------------------------------------
; _acia_shutdown: drop DTR and restore the original NMI vector
; ---------------------------------------------------------------------------
_acia_shutdown:
        sei
        lda #$00                ; DTR low -> the Ultimate drops the connection
        sta ACIA_CMD
        lda oldNmi
        sta NMI_VECTOR
        lda oldNmi+1
        sta NMI_VECTOR+1
        cli
        rts

; ---------------------------------------------------------------------------
; nmiHandler: entered from $FE43 via $0318 with NOTHING saved but P and PC.
;
; This is the opposite of the C128, whose ROM stub saves A/X/Y and the MMU first
; and requires an exit through $FF33. Here we save and restore our own registers
; and leave by RTI - and before chaining to the previous handler we unwind those
; pushes, because that handler expects the stack the CPU left it.
; ---------------------------------------------------------------------------
nmiHandler:
        pha
        txa
        pha
        tya
        pha

        inc _nmiCount
        bne @nooc1
        inc _nmiCount+1
@nooc1:
        lda ACIA_STATUS         ; reading clears the ACIA interrupt flag
        tax                     ; keep the full status for the overrun check
        and #$08                ; receiver data register full?
        beq @chain
        txa
        and #$04                ; overrun: a byte was lost before we read it
        beq @store
        inc _rxOverruns
@store:
        lda ACIA_DATA           ; reading clears RDRF and re-arms the NMI line
        ldx rxHead
        inx
        cpx rxTail              ; would this write lap the unread tail?
        beq @ringfull
        dex
        sta rxBuf,x
        inx
        stx rxHead              ; 256-byte ring: wraps on its own
        inc _rxCount
        bne @exit
        inc _rxCount+1
@exit:
        pla
        tay
        pla
        tax
        pla
        rti
@ringfull:
        ; Counted, not silently overwritten: the client can recover the whole
        ; picture with a resync, but only if it knows it lost something.
        inc _rxDropped
        jmp @exit
@chain:
        pla
        tay
        pla
        tax
        pla
        jmp (oldNmi)

; ---------------------------------------------------------------------------
; _acia_avail: A = 1 when a byte is waiting
; ---------------------------------------------------------------------------
_acia_avail:
        ldx #0
        lda rxHead
        cmp rxTail
        beq @empty
        lda #1
        rts
@empty: lda #0
        rts

; ---------------------------------------------------------------------------
; _acia_get: A = next byte (call only when _acia_avail returned 1)
; ---------------------------------------------------------------------------
_acia_get:
        ldx #0
        ldy rxTail
        lda rxBuf,y
        iny
        sty rxTail
        rts

; ---------------------------------------------------------------------------
; _acia_put: transmit A, waiting for the transmitter to drain
; ---------------------------------------------------------------------------
_acia_put:
        pha
@wait:  lda ACIA_STATUS
        and #$10                ; transmitter data register empty
        beq @wait
        pla
        sta ACIA_DATA
        rts

; ---------------------------------------------------------------------------
; _kb_get: next key in PETSCII, or 0 if none.
;
; The KERNAL's GETIN, as on the C128. It reads the C64's own buffer at $0277 with
; the count at $C6, so the address difference between the machines never has to
; appear here.
; ---------------------------------------------------------------------------
_kb_get:
        jsr $FFE4               ; KERNAL GETIN
        cmp #0
        beq @none
        inc _kbCount
        bne @none
        inc _kbCount+1
@none:  ldx #0
        rts

; ---------------------------------------------------------------------------
; _scr_mirror: copy the screen into _mirrorBuf for host-side inspection.
;   _scrChar = 0 -> the 1000 character cells
;   _scrChar = 1 -> the 1000 colour cells
;
; Less essential than on the C128, where the VDC's private RAM is invisible from
; the cartridge bus: here the Ultimate can read $0400 directly. Kept so the same
; host tools work against both machines.
; ---------------------------------------------------------------------------
_scr_mirror:
        lda #<_mirrorBuf
        sta ptr2
        lda #>_mirrorBuf
        sta ptr2+1
        lda _scrChar
        beq @chars
        lda #<COLORRAM
        sta ptr1
        lda #>COLORRAM
        sta ptr1+1
        bne @copy               ; >COLORRAM is non-zero, so this always taken
@chars:
        lda #<SCREEN
        sta ptr1
        lda #>SCREEN
        sta ptr1+1
@copy:
        ; 1000 bytes: three whole pages then 232 bytes.
        ldx #3
@page:  ldy #0
@byte:  lda (ptr1),y
        sta (ptr2),y
        iny
        bne @byte
        inc ptr1+1
        inc ptr2+1
        dex
        bne @page
        ldy #0
@tail:  lda (ptr1),y
        sta (ptr2),y
        iny
        cpy #<(CELLS - 768)
        bne @tail
        rts
