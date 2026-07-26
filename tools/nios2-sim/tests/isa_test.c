/* Checks the simulator's instruction semantics against values computed by the
 * host compiler. Anything the interpreter gets wrong here would silently
 * corrupt the crypto measurements, so this runs first.
 *
 * The expected values are not written by hand: build.sh compiles this same file
 * for the host as well, runs both, and diffs the output. A discrepancy means the
 * simulator and a real compiler disagree about what the C means.
 */
#include <stdio.h>
#include <stdint.h>

/* volatile everywhere so the compiler emits real instructions rather than
 * folding these into constants at compile time. */
static volatile int32_t  a32, b32;
static volatile uint32_t ua, ub;
static volatile int16_t  s16;
static volatile int8_t   s8;
static volatile uint64_t u64a, u64b;
static volatile int64_t  i64a, i64b;

int main(void)
{
    /* signed and unsigned arithmetic, including the wrap cases */
    a32 = -2147483647 - 1; b32 = -1;
    printf("add  %d\n",  (int) (a32 + b32));
    printf("sub  %d\n",  (int) (a32 - b32));
    a32 = 1234567; b32 = -7654321;
    printf("mul  %d\n",  (int) (a32 * b32));
    printf("div  %d\n",  (int) (b32 / a32));
    printf("mod  %d\n",  (int) (b32 % a32));

    ua = 0xFFFFFFFFu; ub = 0x80000001u;
    printf("uadd %u\n",  (unsigned) (ua + ub));
    printf("umul %u\n",  (unsigned) (ua * ub));
    printf("udiv %u\n",  (unsigned) (ua / ub));
    printf("umod %u\n",  (unsigned) (ua % ub));

    /* shifts: variable and constant, signed right shift must be arithmetic */
    ua = 0xDEADBEEFu;
    for (int i = 0; i < 33; i += 8)
        printf("shl%02d %08x\n", i, (unsigned) (ua << (i & 31)));
    for (int i = 0; i < 33; i += 8)
        printf("shr%02d %08x\n", i, (unsigned) (ua >> (i & 31)));
    a32 = -1234567890;
    for (int i = 0; i < 33; i += 8)
        printf("sar%02d %d\n", i, (int) (a32 >> (i & 31)));
    printf("shlc %08x\n", (unsigned) (ua << 13));
    printf("shrc %08x\n", (unsigned) (ua >> 13));
    printf("sarc %d\n",   (int) (a32 >> 13));

/* Split 64-bit values into halves: printf's %ll support is not what is under
 * test here, and newlib's may differ from the host's. */
#define P64(tag, v) do { uint64_t _t = (uint64_t)(v); \
    printf("%s %08x:%08x\n", tag, (unsigned)(_t >> 32), (unsigned)(_t & 0xffffffffu)); \
} while (0)

    /* 64-bit: exercises __muldi3, __divdi3, and the shift helpers */
    u64a = 0x0123456789ABCDEFull; u64b = 0xFEDCBA9876543210ull;
    P64("u64mul", u64a * u64b);
    P64("u64div", u64b / u64a);
    P64("u64shl", u64a << 17);
    P64("u64shr", u64b >> 17);
    i64a = -1234567890123LL; i64b = 987654321LL;
    P64("i64mul", i64a * i64b);
    P64("i64div", i64a / i64b);
    P64("i64sar", i64a >> 13);

    /* the 32x32->64 widening multiply, which is the crypto hot path */
    ua = 0xFEDCBA98u; ub = 0x76543210u;
    P64("widen", (uint64_t) ua * (uint64_t) ub);

    /* sign extension on narrow loads */
    s16 = -12345; s8 = -123;
    printf("sext16 %d\n", (int) s16);
    printf("sext8  %d\n", (int) s8);
    printf("zext16 %u\n", (unsigned) (uint16_t) s16);
    printf("zext8  %u\n", (unsigned) (uint8_t) s8);

    /* comparisons across the signed/unsigned boundary */
    a32 = -1; ua = 0xFFFFFFFFu; ub = 1;
    printf("cmps %d %d %d\n", a32 < 0, a32 >= 0, a32 < 1);
    printf("cmpu %d %d %d\n", ua > ub, ua < ub, ua >= ub);

    /* byte-wise memory traffic, to catch endianness and narrow-store bugs */
    static volatile uint8_t buf[16];
    for (int i = 0; i < 16; i++) buf[i] = (uint8_t) (i * 17);
    uint32_t acc = 0;
    for (int i = 0; i < 16; i++) acc = acc * 31 + buf[i];
    printf("bytes %08x\n", (unsigned) acc);

    static volatile uint32_t w[4] = { 0x11223344, 0x55667788, 0x99AABBCC, 0xDDEEFF00 };
    printf("words %08x %08x\n", (unsigned) w[1], (unsigned) (w[0] ^ w[3]));
    volatile uint16_t *h = (volatile uint16_t *) w;
    printf("halfs %04x %04x\n", (unsigned) h[0], (unsigned) h[1]);

    printf("done\n");
    return 0;
}
