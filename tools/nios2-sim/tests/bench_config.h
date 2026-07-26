/* Minimal mbedTLS config for the ECP benchmark. The SSL, PSA and X.509 layers
 * are omitted - they are not part of the arithmetic being measured - but every
 * setting that affects the elliptic-curve math is identical to the firmware's
 * modem_mbedtls_config.h, because those are what the instruction counts depend
 * on. If you change one there, change it here. */
#define MBEDTLS_BIGNUM_C
#define MBEDTLS_ECP_C
#define MBEDTLS_ECDH_C
#define MBEDTLS_ECDSA_C
#define MBEDTLS_ASN1_PARSE_C
#define MBEDTLS_ASN1_WRITE_C
#define MBEDTLS_MD_C
#define MBEDTLS_SHA256_C
#define MBEDTLS_SHA224_C
#define MBEDTLS_PLATFORM_C
#define MBEDTLS_NO_PLATFORM_ENTROPY

#define MBEDTLS_ECP_DP_SECP256R1_ENABLED

/* These two are the ones that matter for cost, and they match the firmware. */
#define MBEDTLS_ECP_WINDOW_SIZE        2
#define MBEDTLS_ECP_FIXED_POINT_OPTIM  0

#define MBEDTLS_AES_FEWER_TABLES
#define MBEDTLS_SHA256_SMALLER
