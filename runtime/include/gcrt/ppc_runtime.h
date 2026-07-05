/* gcrt PowerPC recompiler runtime contract (generated). */
#ifndef GCRT_PPC_RUNTIME_H
#define GCRT_PPC_RUNTIME_H
#include <stdint.h>

/* An FPR holds a double for scalar ops; the u64 view gives bit-accurate
   access for the integer-convert instructions (fctiw/fctiwz + stfiwx). */
typedef union PpcFpr {
    double   f64;
    uint64_t u64;
} PpcFpr;

typedef struct PpcContext {
    uint32_t gpr[32];
    PpcFpr   fpr[32];   /* singles round via (double)(float) casts */
    uint32_t lr;
    uint32_t ctr;
    uint32_t cr;   /* 8 condition fields, PowerPC bit order (bit0 = MSB) */
    uint32_t xer;
} PpcContext;

/* Condition register helpers. Field f occupies bits [f*4 .. f*4+3];
   sub-bit 0=LT 1=GT 2=EQ 3=SO, addressed MSB-first. */
static inline int ppc_cr_bit(const PpcContext* c, int bi) {
    return (c->cr >> (31 - bi)) & 1;
}
static inline void ppc_cmp_signed(PpcContext* c, int f, int32_t a, int32_t b) {
    uint32_t lt = a < b, gt = a > b, eq = a == b;
    int base = f * 4;
    uint32_t clear = ~(0xFu << (28 - base));
    c->cr = (c->cr & clear) |
            ((lt << 3 | gt << 2 | eq << 1) << (28 - base));
}
static inline void ppc_cmp_unsigned(PpcContext* c, int f, uint32_t a, uint32_t b) {
    uint32_t lt = a < b, gt = a > b, eq = a == b;
    int base = f * 4;
    uint32_t clear = ~(0xFu << (28 - base));
    c->cr = (c->cr & clear) |
            ((lt << 3 | gt << 2 | eq << 1) << (28 - base));
}
static inline void ppc_fcmp(PpcContext* c, int f, double a, double b) {
    uint32_t lt = 0, gt = 0, eq = 0, un = 0;
    if (a != a || b != b) un = 1;   /* NaN -> unordered */
    else if (a < b) lt = 1;
    else if (a > b) gt = 1;
    else eq = 1;
    int base = f * 4;
    uint32_t clear = ~(0xFu << (28 - base));
    c->cr = (c->cr & clear) |
            ((lt << 3 | gt << 2 | eq << 1 | un) << (28 - base));
}

/* Double -> 32-bit integer conversions for fctiwz (truncate) and fctiw
   (round to nearest), with the out-of-range/NaN clamping PowerPC specifies. */
static inline uint32_t ppc_d2iz(double v) {
    if (v != v) return 0x80000000u;             /* NaN */
    if (v >= 2147483647.0) return 0x7fffffffu;
    if (v <= -2147483648.0) return 0x80000000u;
    return (uint32_t)(int32_t)v;                /* truncate toward zero */
}
static inline uint32_t ppc_d2i(double v) {
    return ppc_d2iz(__builtin_nearbyint(v));    /* current rounding (nearest) */
}

/* Memory + control hooks the host runtime implements (backed by gcrt::Memory
   and the recompiled function table). Declared with C linkage so the C++
   runtime bridge and the C recompiled code agree on symbols. */
#ifdef __cplusplus
extern "C" {
#endif
uint8_t  ppc_read_u8 (PpcContext*, uint32_t ea);
uint16_t ppc_read_u16(PpcContext*, uint32_t ea);
uint32_t ppc_read_u32(PpcContext*, uint32_t ea);
void ppc_write_u8 (PpcContext*, uint32_t ea, uint8_t v);
void ppc_write_u16(PpcContext*, uint32_t ea, uint16_t v);
void ppc_write_u32(PpcContext*, uint32_t ea, uint32_t v);
float  ppc_read_float (PpcContext*, uint32_t ea);
double ppc_read_double(PpcContext*, uint32_t ea);
void ppc_write_float (PpcContext*, uint32_t ea, float v);
void ppc_write_double(PpcContext*, uint32_t ea, double v);
void ppc_call(PpcContext*, uint32_t target);
void ppc_unimplemented(PpcContext*, uint32_t address, uint32_t raw);

/* Recompiled translation units call this (via their generated
   ppc_register_all) to register each function at its guest address so
   ppc_call() can dispatch between them. Implemented by the runtime bridge. */
typedef void (*PpcFunctionPtr)(PpcContext*);
void ppc_register_function(uint32_t address, PpcFunctionPtr fn);
#ifdef __cplusplus
}
#endif

#endif
