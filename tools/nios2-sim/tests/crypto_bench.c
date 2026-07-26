/* Runs the public-key half of a TLS 1.3 handshake and reports the instruction
 * count for each phase, measured by the simulator rather than derived by hand.
 *
 * Two jobs:
 *
 *  1. VALIDATION. Every scalar is fixed, so the results are deterministic. The
 *     same source is compiled for the host and both outputs are diffed. If a
 *     P-256 shared secret computed by ~50 million simulated instructions matches
 *     the host's byte for byte, the simulator's arithmetic is right and mbedTLS
 *     works on this target. A wrong carry anywhere would change the answer.
 *
 *  2. MEASUREMENT. sim_icount() reads the simulator's counter through MMIO, so
 *     the program brackets its own phases and the host does not have to guess
 *     where each one starts.
 *
 * The host build has no counter, so it prints only the results; the diff covers
 * the result lines and the counts are read from the simulator run.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "mbedtls/ecp.h"
#include "mbedtls/ecdh.h"
#include "mbedtls/ecdsa.h"
#include "mbedtls/sha256.h"
#include "mbedtls/bignum.h"

#ifdef NIOS2_SIM
unsigned sim_icount(void);
#else
static unsigned sim_icount(void) { return 0; }
#endif

/* Fixed "random" stream. Both builds get the same bytes, so both compute the
 * same keys - which is the whole point. This is not a key generator. */
static int fixed_rng(void *ctx, unsigned char *out, size_t len)
{
    static uint32_t s = 0x12345678u;
    (void) ctx;
    for (size_t i = 0; i < len; i++) {
        s = s * 1664525u + 1013904223u;
        out[i] = (unsigned char) (s >> 24);
    }
    return 0;
}

static void dump(const char *tag, const unsigned char *p, size_t n)
{
    printf("%s ", tag);
    for (size_t i = 0; i < n; i++) printf("%02x", p[i]);
    printf("\n");
}

static void phase(const char *tag, unsigned start)
{
    unsigned end = sim_icount();
    if (end) printf("# %-28s %10u instructions\n", tag, end - start);
}

int main(void)
{
    mbedtls_ecp_group grp;
    mbedtls_mpi d_a, d_b, z;
    mbedtls_ecp_point Q_a, Q_b;
    unsigned char buf[32];
    unsigned t;
    int ret;

    mbedtls_ecp_group_init(&grp);
    mbedtls_mpi_init(&d_a); mbedtls_mpi_init(&d_b); mbedtls_mpi_init(&z);
    mbedtls_ecp_point_init(&Q_a); mbedtls_ecp_point_init(&Q_b);

    t = sim_icount();
    ret = mbedtls_ecp_group_load(&grp, MBEDTLS_ECP_DP_SECP256R1);
    if (ret) { printf("FAIL group_load -0x%04x\n", -ret); return 1; }
    phase("group load", t);

    /* 1. our ephemeral keypair */
    t = sim_icount();
    ret = mbedtls_ecp_gen_keypair(&grp, &d_a, &Q_a, fixed_rng, NULL);
    if (ret) { printf("FAIL gen_keypair -0x%04x\n", -ret); return 1; }
    phase("ephemeral keygen", t);
    {   /* point coordinates are private in 3.x, so go through the public
           serialisation instead of reaching into the struct */
        unsigned char pt[65]; size_t ptlen = 0;
        ret = mbedtls_ecp_point_write_binary(&grp, &Q_a,
                  MBEDTLS_ECP_PF_UNCOMPRESSED, &ptlen, pt, sizeof pt);
        if (ret) { printf("FAIL write Qa -0x%04x\n", -ret); return 1; }
        dump("Qa", pt, ptlen);
    }

    /* 2. the peer's keypair, so there is something to agree with */
    ret = mbedtls_ecp_gen_keypair(&grp, &d_b, &Q_b, fixed_rng, NULL);
    if (ret) { printf("FAIL peer gen_keypair -0x%04x\n", -ret); return 1; }

    /* 3. ECDH shared secret */
    t = sim_icount();
    ret = mbedtls_ecdh_compute_shared(&grp, &z, &Q_b, &d_a, fixed_rng, NULL);
    if (ret) { printf("FAIL ecdh -0x%04x\n", -ret); return 1; }
    phase("ECDH shared secret", t);
    ret = mbedtls_mpi_write_binary(&z, buf, sizeof buf);
    if (ret) { printf("FAIL write z -0x%04x\n", -ret); return 1; }
    dump("ECDH", buf, sizeof buf);

    /* Both sides must agree, or the arithmetic is wrong somewhere. */
    {
        mbedtls_mpi z2;
        mbedtls_mpi_init(&z2);
        ret = mbedtls_ecdh_compute_shared(&grp, &z2, &Q_a, &d_b, fixed_rng, NULL);
        if (ret) { printf("FAIL ecdh reverse -0x%04x\n", -ret); return 1; }
        printf("AGREE %d\n", mbedtls_mpi_cmp_mpi(&z, &z2) == 0);
        mbedtls_mpi_free(&z2);
    }

    /* 4. ECDSA over a fixed digest, as a certificate signature would be */
    unsigned char hash[32];
    ret = mbedtls_sha256((const unsigned char *) "certificate tbs", 15, hash, 0);
    if (ret) { printf("FAIL sha256 -0x%04x\n", -ret); return 1; }
    dump("HASH", hash, sizeof hash);

    mbedtls_mpi r, s;
    mbedtls_mpi_init(&r); mbedtls_mpi_init(&s);
    t = sim_icount();
    ret = mbedtls_ecdsa_sign(&grp, &r, &s, &d_a, hash, sizeof hash, fixed_rng, NULL);
    if (ret) { printf("FAIL ecdsa_sign -0x%04x\n", -ret); return 1; }
    phase("ECDSA sign", t);

    t = sim_icount();
    ret = mbedtls_ecdsa_verify(&grp, hash, sizeof hash, &Q_a, &r, &s);
    phase("ECDSA verify", t);
    printf("VERIFY %d\n", ret == 0);

    /* A tampered digest must NOT verify. Without this the verify above could be
     * returning 0 for the wrong reason. */
    hash[0] ^= 0x01;
    ret = mbedtls_ecdsa_verify(&grp, hash, sizeof hash, &Q_a, &r, &s);
    printf("REJECT %d\n", ret != 0);

    printf("done\n");
    return 0;
}
