/* A615-family OOB protocol, including A618. No MMIO in this header.
 * Reference: MiCode surya-q-oss kgsl_gmu_core.h, kgsl_hfi.h,
 * adreno.h and adreno_a6xx_gmu.c (a6xx_gmu_oob_set/clear).
 */
#ifndef SURYA_GMU_PROTOCOL_H
#define SURYA_GMU_PROTOCOL_H
#include <stdint.h>

#define SGMU_BOOT_REQUEST 6u
#define SGMU_BOOT_SET (1u << (SGMU_BOOT_REQUEST + 16u))
#define SGMU_BOOT_ACK (1u << (SGMU_BOOT_REQUEST + 24u))
#define SGMU_BOOT_RELEASE SGMU_BOOT_ACK
#define SGMU_CM3_FAULT (1u << 15)

enum sgmu_reply { SGMU_PENDING, SGMU_ACKNOWLEDGED, SGMU_FAULT };

static inline enum sgmu_reply
sgmu_boot_reply(uint32_t status)
{
    /* Never accept an ACK accompanied by a firmware fault. */
    if (status & SGMU_CM3_FAULT) return SGMU_FAULT;
    if (status & SGMU_BOOT_ACK) return SGMU_ACKNOWLEDGED;
    return SGMU_PENDING;
}
#endif
