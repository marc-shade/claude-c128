; ---------------------------------------------------------------------------
; claude-c128 client: VDC screen writes and 6551 ACIA receive.
;
; Both are performance-critical, so they live in assembly and take their
; arguments through fixed zero-page-free globals rather than the C stack.
;
; The VDC is a separate chip with private RAM reached through a two-register
; window at $D600/$D601: write a register number to $D600, wait for bit 7 of
; $D600 to go high, then read or write $D601. Register 31 is a data port that
; auto-increments the update address, so a run of cells costs one address
; setup plus one guarded store per byte.
;
; The ACIA has a one-byte receive buffer. At 38400 baud a byte lands every
; ~260 cycles, which the KERNAL's own interrupts would routinely overrun, so
; reception is driven from NMI (unmaskable) into a 256-byte ring buffer whose
; head and tail wrap for free as single bytes.
; ---------------------------------------------------------------------------

        .export _vdc_init, _vdc_run, _vdc_fill, _vdc_clear, _vdc_place_cursor
        .export _acia_init, _acia_get, _acia_avail, _acia_put, _acia_shutdown
        .export _kb_get, _kbCount
        .export _vdc_mirror, _mirrorBuf, _lastAttr
        .export _vdcRow, _vdcCol, _vdcAttr, _vdcLen, _vdcChar, _vdcBuf
        ; Link diagnostics: exported so the emulator harness and the on-screen
        ; status panel can see whether bytes are actually arriving.
        .export _rxHead, _rxTail, _rxCount, _nmiCount, _rxOverruns, _rxDropped

VDC_ADDR        = $D600         ; register select / status
VDC_DATA        = $D601         ; register data

VDC_R_HSTART    = 18            ; update address high
VDC_R_LSTART    = 19            ; update address low
VDC_R_VSCROLL   = 24            ; bit 7 selects block copy (1) or fill (0)
VDC_R_COUNT     = 30            ; block word count: triggers the block operation
VDC_R_DATA      = 31            ; data port, auto-incrementing

; Largest block fill issued at once. The count register is 8-bit, and keeping
; each burst short bounds how long the main loop goes without draining the
; receive ring.
FILL_CHUNK      = 250

SCREEN_BASE     = $0000         ; VDC RAM: character cells
ATTR_BASE       = $0800         ; VDC RAM: attribute cells
COLS            = 80

ACIA_DATA       = $DE00
ACIA_STATUS     = $DE01
ACIA_CMD        = $DE02
ACIA_CTRL       = $DE03

; SwiftLink runs a doubled crystal, so the 6551 baud codes all double:
;   $1C = 9600   $1D = 14400   $1E = 19200   $1F = 38400   (8N1, internal clock)
; The binding limit is not the wire, it is how fast the C128 can parse a frame
; and push it through the VDC at 1MHz. Measured in VICE: 38400 overruns the
; receive ring during a full repaint; 19200 does not.
ACIA_CTRL_VAL   = $1F
; DTR on, receiver interrupt enabled, RTS asserted, transmit interrupt off.
ACIA_CMD_VAL    = $09

NMI_VECTOR      = $0318
; The C128 ROM NMI stub at $FF05 pushes A, X, Y *and* the MMU configuration
; register before dispatching through $0318, then banks in ROM. That differs
; from the C64, where nothing is saved. A handler that pushes its own registers
; and returns with a bare RTI therefore unbalances the stack and returns to a
; garbage address. $FF33 is the KERNAL's matching unwind:
;   PLA / STA $FF00 / PLA / TAY / PLA / TAX / PLA / RTI
NMI_EXIT        = $FF33

        .bss
_vdcRow:        .res 1
_vdcCol:        .res 1
_vdcAttr:       .res 1
_vdcLen:        .res 1
_vdcChar:       .res 1
_vdcBuf:        .res 256

offsetLo:       .res 1
offsetHi:       .res 1
fillByte:       .res 1
fillCount:      .res 1
fillLeft:       .res 2
oldNmi:         .res 2
_rxHead:        .res 1
_rxTail:        .res 1
_rxCount:       .res 2          ; bytes accepted from the ACIA
_nmiCount:      .res 2          ; NMIs seen, ours or not
_rxOverruns:    .res 1          ; ACIA reported a dropped byte
_rxDropped:     .res 1          ; receive ring was full; byte discarded
_kbCount:       .res 2          ; keys read from the keyboard, for diagnostics

; The VDC keeps its screen in private RAM that the cartridge bus cannot reach,
; so a host debugging over the network is blind to the 80-column display. The
; C128 itself can read it, so it copies a plane here on request and the host
; reads it back out of ordinary memory.
_lastAttr:      .res 1          ; last attribute byte vdc_run wrote
_mirrorBuf:     .res 2048

rxHead          = _rxHead
rxTail          = _rxTail

; 256 contiguous bytes indexed by a byte, so head/tail wrap on their own.
; Page alignment would only save the indexed page-crossing cycle, and the
; c128 config cannot guarantee it for BSS, so it is not requested.
rxBuf:          .res 256

        .code

; ---------------------------------------------------------------------------
; vdc_reg_write: A = value, X = register number
; ---------------------------------------------------------------------------
vdcRegWrite:
        stx VDC_ADDR
@wait:  bit VDC_ADDR
        bpl @wait
        sta VDC_DATA
        rts

; ---------------------------------------------------------------------------
; vdcSetAddr: point the VDC update address at offsetHi/offsetLo
; ---------------------------------------------------------------------------
vdcSetAddr:
        lda offsetHi
        ldx #VDC_R_HSTART
        jsr vdcRegWrite
        lda offsetLo
        ldx #VDC_R_LSTART
        jsr vdcRegWrite
        ldx #VDC_R_DATA         ; leave the data port selected
        stx VDC_ADDR
        ; vdcRegWrite waits *before* each store, so on return the write to the
        ; address-low register may still be in flight. Without this wait the
        ; very first data write can be issued against the previous update
        ; address, which lost cell 0 of every full-screen clear.
@settle:
        bit VDC_ADDR
        bpl @settle
        rts

; ---------------------------------------------------------------------------
; vdcPut: A = byte -> data port (address auto-increments)
; ---------------------------------------------------------------------------
vdcPut:
@wait:  bit VDC_ADDR
        bpl @wait
        sta VDC_DATA
        rts

; ---------------------------------------------------------------------------
; attrToVdc: protocol attribute -> VDC attribute byte.
;
; The VDC attribute is  bit7 alternate charset | bit6 reverse | bit5 underline |
; bit4 blink | bits3-0 colour.
;
; Bit 7 must be set: the C128 keeps 512 character definitions at the base in R28,
; the first 256 being the uppercase/graphics set and the second 256 the
; lowercase set. Everything the bridge sends is encoded as lowercase-set screen
; codes, so without this bit the VDC draws them from the wrong half and text
; comes out as graphics symbols.
;
; Underline and reverse are carried through unchanged; the protocol already
; uses the VDC's own bit positions for them.
; ---------------------------------------------------------------------------
attrToVdc:
        and #$6F                ; colour (3-0), underline (5), reverse (6)
        ora #$80                ; select the lowercase character set
        rts

; ---------------------------------------------------------------------------
; vdcRegRead: X = register number -> A
; ---------------------------------------------------------------------------
vdcRegRead:
        stx VDC_ADDR
@wait:  bit VDC_ADDR
        bpl @wait
        lda VDC_DATA
        rts

; ---------------------------------------------------------------------------
; fillChunk: A = byte, X = count (1..255), at the current update address.
;
; Uses the VDC's block-fill: write the byte once through the data port, then
; write the remaining count to register 30 and the VDC repeats it at memory
; speed. Writing 2000 cells one at a time takes ~80ms at 1MHz, long enough for
; a 38400-baud sender to overrun a 256-byte receive ring; this takes a fraction
; of that.
; ---------------------------------------------------------------------------
fillChunk:
        sta fillByte
        stx fillCount
        ldy #VDC_R_DATA
        sty VDC_ADDR
@w1:    bit VDC_ADDR
        bpl @w1
        lda fillByte
        sta VDC_DATA            ; first copy, address auto-increments
        ldx fillCount
        dex
        beq @done
        ldy #VDC_R_COUNT
        sty VDC_ADDR
@w2:    bit VDC_ADDR
        bpl @w2
        txa
        sta VDC_DATA            ; block-fill the remainder
@done:  rts

; ---------------------------------------------------------------------------
; fillSpan: fill fillLeft bytes with A from the current update address,
;           in FILL_CHUNK-sized bursts.
; ---------------------------------------------------------------------------
fillSpan:
        sta fillByte
@loop:  lda fillLeft
        ora fillLeft+1
        beq @done
        lda fillLeft+1
        bne @full               ; more than 255 left
        lda fillLeft
        cmp #FILL_CHUNK
        bcc @last
@full:  ldx #FILL_CHUNK
        lda fillLeft
        sec
        sbc #FILL_CHUNK
        sta fillLeft
        lda fillLeft+1
        sbc #0
        sta fillLeft+1
        lda fillByte
        jsr fillChunk
        jmp @loop
@last:  ldx fillLeft
        lda #0
        sta fillLeft
        sta fillLeft+1
        lda fillByte
        jsr fillChunk
@done:  rts

; ---------------------------------------------------------------------------
; calcOffset: offset = vdcRow * 80 + vdcCol, into offsetHi/offsetLo
; row*80 == row*64 + row*16, which is cheaper than a multiply loop.
; ---------------------------------------------------------------------------
calcOffset:
        lda #0
        sta offsetHi
        lda _vdcRow
        asl a                   ; row*2
        asl a                   ; row*4
        rol offsetHi
        asl a                   ; row*8
        rol offsetHi
        asl a                   ; row*16
        rol offsetHi
        sta offsetLo            ; offset = row*16
        lda offsetHi
        pha
        lda offsetLo
        pha                     ; save row*16
        asl a                   ; row*32
        rol offsetHi
        asl a                   ; row*64
        rol offsetHi
        sta offsetLo
        pla
        clc
        adc offsetLo            ; row*64 + row*16 = row*80
        sta offsetLo
        pla
        adc offsetHi
        sta offsetHi
        lda offsetLo
        clc
        adc _vdcCol
        sta offsetLo
        lda offsetHi
        adc #0
        sta offsetHi
        rts

; ---------------------------------------------------------------------------
; _vdc_run: write vdcLen screen codes from vdcBuf at (vdcRow,vdcCol),
;           then the same span in attribute RAM with vdcAttr.
; ---------------------------------------------------------------------------
_vdc_run:
        lda _vdcLen
        bne @go
        rts
@go:    jsr calcOffset
        jsr vdcSetAddr
        ldy #0
@chars: lda _vdcBuf,y
        jsr vdcPut
        iny
        cpy _vdcLen
        bne @chars

        jsr calcOffset          ; same span in attribute RAM
        lda offsetHi
        clc
        adc #>ATTR_BASE
        sta offsetHi
        jsr vdcSetAddr
        lda _vdcAttr
        jsr attrToVdc
        sta _lastAttr           ; the VDC-format byte we actually store
        ldy #0
@attrs: lda _lastAttr
        jsr vdcPut
        iny
        cpy _vdcLen
        bne @attrs
        rts

; ---------------------------------------------------------------------------
; _vdc_fill: vdcLen copies of vdcChar at (vdcRow,vdcCol) with vdcAttr
; ---------------------------------------------------------------------------
_vdc_fill:
        lda _vdcLen
        bne @go
        rts
@go:    jsr calcOffset
        jsr vdcSetAddr
        ldx _vdcLen
        lda _vdcChar
        jsr fillChunk

        jsr calcOffset
        lda offsetHi
        clc
        adc #>ATTR_BASE
        sta offsetHi
        jsr vdcSetAddr
        ldx _vdcLen
        lda _vdcAttr
        jsr attrToVdc
        jsr fillChunk
        rts

; ---------------------------------------------------------------------------
; _vdc_clear: blank all 2000 cells and set all 2000 attributes, using the
; VDC block fill rather than a per-cell loop.
; ---------------------------------------------------------------------------
_vdc_clear:
        lda #0
        sta offsetLo
        sta offsetHi
        jsr vdcSetAddr
        lda #<2000
        sta fillLeft
        lda #>2000
        sta fillLeft+1
        lda #$20
        jsr fillSpan

        lda #<SCREEN_BASE
        sta offsetLo
        lda #>ATTR_BASE
        sta offsetHi
        jsr vdcSetAddr
        lda #<2000
        sta fillLeft
        lda #>2000
        sta fillLeft+1
        lda _vdcAttr
        jsr attrToVdc
        jsr fillSpan
        rts

; ---------------------------------------------------------------------------
; _vdc_place_cursor: VDC registers 14/15 hold the cursor position
; ---------------------------------------------------------------------------
_vdc_place_cursor:
        jsr calcOffset
        lda offsetHi
        ldx #14
        jsr vdcRegWrite
        lda offsetLo
        ldx #15
        jsr vdcRegWrite
        rts

; ---------------------------------------------------------------------------
; _vdc_init: leave the KERNAL's 80-column setup in place and just clear.
; ---------------------------------------------------------------------------
_vdc_init:
        ; Register 24 bit 7 chooses block COPY (1) or block FILL (0). The
        ; KERNAL may leave either set, and every fill below depends on it.
        ldx #VDC_R_VSCROLL
        jsr vdcRegRead
        and #$7F
        ldx #VDC_R_VSCROLL
        jsr vdcRegWrite
        jsr _vdc_clear
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
; nmiHandler: entered from the ROM stub at $FF05, which has already saved
; A, X, Y and the MMU config and banked in ROM. So registers are free to
; clobber and we must leave through NMI_EXIT, never a bare RTI.
;
; Anything that is not our ACIA byte is handed to the previous handler with the
; stack exactly as we found it, so RESTORE keeps working.
; ---------------------------------------------------------------------------
nmiHandler:
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
        bne @nooc2
        inc _rxCount+1
@nooc2:
        jmp NMI_EXIT
@ringfull:
        ; Dropping here would corrupt the screen silently, so it is counted.
        ; The byte is discarded rather than overwriting unread data; the client
        ; can recover the whole picture with a resync.
        inc _rxDropped
        jmp NMI_EXIT
@chain: jmp (oldNmi)

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
; Calls the KERNAL's GETIN ($FFE4) rather than cc65's kbhit()/cgetc(). GETIN is
; the documented non-blocking read and it takes the C128's keyboard buffer and
; its count ($034A/$D0) into account itself, which conio did not appear to do
; here: keys placed in that buffer were never returned, so nothing was ever
; transmitted while the receive direction worked perfectly.
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
; _vdc_mirror: copy one VDC plane into _mirrorBuf.
;   _vdcChar = 0 -> character cells at VDC $0000
;   _vdcChar = 1 -> attribute cells at VDC $0800
; Copies 2048 bytes, which covers the 2000 used by an 80x25 screen.
; ---------------------------------------------------------------------------
        .importzp ptr1

; _vdcChar = 2 additionally means "dump VDC registers 0..36 into mirrorBuf",
; which is the only way for a host on the far side of the cartridge bus to see
; how the VDC is actually configured (where the screen and attribute RAM live,
; and whether attributes are enabled at all).
_vdc_mirror:
        lda _vdcChar
        cmp #2
        bne @plane
        ldx #0
@reg:   txa
        pha
        jsr vdcRegRead          ; X = register number -> A
        sta _mirrorBuf,x
        pla
        tax
        inx
        cpx #37
        bne @reg
        rts
@plane:
        lda #<_mirrorBuf
        sta ptr1
        lda #>_mirrorBuf
        sta ptr1+1
        lda #0
        sta offsetLo
        ldx _vdcChar
        beq @chars
        lda #>ATTR_BASE
        .byte $2C                       ; skip the next two bytes (BIT abs)
@chars: lda #>SCREEN_BASE
        sta offsetHi
        jsr vdcSetAddr                  ; leaves the data port selected
        ; The VDC data port is pipelined: the first read after setting the
        ; update address returns the previously latched byte, not the one at
        ; the new address. Throw it away, then re-point and read for real.
@pre:   bit VDC_ADDR
        bpl @pre
        lda VDC_DATA
        jsr vdcSetAddr
        ldx #8                          ; 8 pages = 2048 bytes
@page:  ldy #0
@byte:  bit VDC_ADDR
        bpl @byte
        lda VDC_DATA
        sta (ptr1),y
        iny
        bne @byte
        inc ptr1+1
        dex
        bne @page
        rts
