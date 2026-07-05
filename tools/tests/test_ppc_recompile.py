"""Recompiler tests: emitted-C string checks plus a real end-to-end run where
the recompiled code is compiled by cc and executed to verify semantics."""

import shutil
import struct
import subprocess

import pytest

from gcport.ppc import RUNTIME_HEADER, recompile_function


def assemble(words):
    return b"".join(struct.pack(">I", w) for w in words)


def test_emits_expected_c_for_arithmetic():
    code = assemble([0x38600005, 0x38800007, 0x7C632214, 0x4E800020])
    c = recompile_function(code, 0, "f")
    assert "c->gpr[3] = (uint32_t)5;" in c
    assert "c->gpr[4] = (uint32_t)7;" in c
    assert "c->gpr[3] = c->gpr[3] + c->gpr[4];" in c
    assert "return;" in c


def test_internal_branch_becomes_goto():
    # b -4 (infinite self-loop) at address 0 -> goto its own label
    code = assemble([0x48000000 | ((-0) & 0x03FFFFFC), 0x4E800020])
    # use a real backward branch: at addr 4, b -4 -> target 0
    code = assemble([0x60000000, 0x4BFFFFFC, 0x4E800020])
    c = recompile_function(code, 0, "f")
    assert "goto L_00000000;" in c
    assert "L_00000000:" in c


def test_call_becomes_hook():
    code = assemble([0x48000011, 0x4E800020])  # bl +0x10... actually bl to 0x10
    c = recompile_function(code, 0, "f")
    assert "ppc_call(c, 0x00000010u);" in c


def test_unimplemented_is_explicit():
    # fsqrt needs a bit-accurate FPR model we don't have yet -> trap, not wrong
    code = assemble([0xFC20102C, 0x4E800020])  # fsqrt f1, f2
    c = recompile_function(code, 0, "f")
    assert "ppc_unimplemented(c" in c


def _cc():
    return shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.mark.skipif(_cc() is None, reason="no C compiler available")
def test_end_to_end_loop_sum(tmp_path):
    """Recompile a loop summing 1..4, compile the C, run it, check r3 == 10.

    Exercises li, cmpwi, conditional branch (bge), add, addi, unconditional
    backward branch, and blr — the whole front-to-back pipeline.
    """
    program = assemble([
        0x38600000,  # 0x00  li   r3, 0      ; sum
        0x38800001,  # 0x04  li   r4, 1      ; i
        0x2C040005,  # 0x08  cmpwi r4, 5     ; loop:
        0x40800010,  # 0x0C  bge  0x1C       ; if i >= 5 -> end
        0x7C632214,  # 0x10  add  r3, r3, r4
        0x38840001,  # 0x14  addi r4, r4, 1
        0x4BFFFFF0,  # 0x18  b    0x08       ; loop
        0x4E800020,  # 0x1C  blr             ; end
    ])
    func = recompile_function(program, 0, "run")

    (tmp_path / "ppc_runtime.h").write_text(RUNTIME_HEADER)
    harness = f"""
#include "ppc_runtime.h"
{func}
/* Unused by this program, but define the hooks so linking always succeeds. */
uint8_t  ppc_read_u8 (PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
uint16_t ppc_read_u16(PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
uint32_t ppc_read_u32(PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
void ppc_write_u8 (PpcContext* c, uint32_t e, uint8_t v)  {{ (void)c;(void)e;(void)v; }}
void ppc_write_u16(PpcContext* c, uint32_t e, uint16_t v) {{ (void)c;(void)e;(void)v; }}
void ppc_write_u32(PpcContext* c, uint32_t e, uint32_t v) {{ (void)c;(void)e;(void)v; }}
void ppc_call(PpcContext* c, uint32_t t) {{ (void)c;(void)t; }}
void ppc_unimplemented(PpcContext* c, uint32_t a, uint32_t r) {{ (void)c;(void)a;(void)r; }}
#include <stdio.h>
int main(void) {{
    PpcContext c;
    for (int i = 0; i < 32; ++i) c.gpr[i] = 0;
    c.lr = c.ctr = c.cr = c.xer = 0;
    run(&c);
    printf("%u\\n", c.gpr[3]);
    return c.gpr[3] == 10 ? 0 : 1;
}}
"""
    src = tmp_path / "harness.c"
    src.write_text(harness)
    exe = tmp_path / "harness"
    compile_res = subprocess.run(
        [_cc(), "-std=c11", "-Wall", "-I", str(tmp_path), str(src),
         "-o", str(exe)],
        capture_output=True, text=True)
    assert compile_res.returncode == 0, compile_res.stderr
    run_res = subprocess.run([str(exe)], capture_output=True, text=True)
    assert run_res.stdout.strip() == "10", run_res.stdout
    assert run_res.returncode == 0


@pytest.mark.skipif(_cc() is None, reason="no C compiler available")
def test_end_to_end_float(tmp_path):
    """Recompile lfs/fadds/stfs and verify a real float sum (1.5 + 2.25)."""
    program = assemble([
        0xC0230000,  # lfs  f1, 0(r3)
        0xC0430004,  # lfs  f2, 4(r3)
        0xEC21102A,  # fadds f1, f1, f2
        0xD0230008,  # stfs f1, 8(r3)
        0x4E800020,  # blr
    ])
    func = recompile_function(program, 0, "run")
    (tmp_path / "ppc_runtime.h").write_text(RUNTIME_HEADER)
    harness = f"""
#include "ppc_runtime.h"
#include <string.h>
static uint8_t MEM[0x1000];
{func}
float ppc_read_float(PpcContext* c, uint32_t e) {{ (void)c; e&=0xfff;
    uint32_t b=((uint32_t)MEM[e]<<24)|((uint32_t)MEM[e+1]<<16)|
              ((uint32_t)MEM[e+2]<<8)|MEM[e+3]; float f; memcpy(&f,&b,4); return f; }}
double ppc_read_double(PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
void ppc_write_float(PpcContext* c, uint32_t e, float v) {{ (void)c; e&=0xfff;
    uint32_t b; memcpy(&b,&v,4);
    MEM[e]=b>>24; MEM[e+1]=b>>16; MEM[e+2]=b>>8; MEM[e+3]=b; }}
void ppc_write_double(PpcContext* c, uint32_t e, double v) {{ (void)c;(void)e;(void)v; }}
uint8_t  ppc_read_u8 (PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
uint16_t ppc_read_u16(PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
uint32_t ppc_read_u32(PpcContext* c, uint32_t e) {{ (void)c;(void)e; return 0; }}
void ppc_write_u8 (PpcContext* c, uint32_t e, uint8_t v)  {{ (void)c;(void)e;(void)v; }}
void ppc_write_u16(PpcContext* c, uint32_t e, uint16_t v) {{ (void)c;(void)e;(void)v; }}
void ppc_write_u32(PpcContext* c, uint32_t e, uint32_t v) {{ (void)c;(void)e;(void)v; }}
void ppc_call(PpcContext* c, uint32_t t) {{ (void)c;(void)t; }}
void ppc_unimplemented(PpcContext* c, uint32_t a, uint32_t r) {{ (void)c;(void)a;(void)r; }}
int main(void) {{
    PpcContext c; for (int i=0;i<32;++i){{c.gpr[i]=0;c.fpr[i]=0;}}
    c.lr=c.ctr=c.cr=c.xer=0;
    c.gpr[3] = 0x100;
    ppc_write_float(&c, 0x100, 1.5f);
    ppc_write_float(&c, 0x104, 2.25f);
    run(&c);
    float result = ppc_read_float(&c, 0x108);
    return result == 3.75f ? 0 : 1;
}}
"""
    src = tmp_path / "harness.c"
    src.write_text(harness)
    exe = tmp_path / "harness"
    r = subprocess.run([_cc(), "-std=c11", "-I", str(tmp_path), str(src),
                        "-o", str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(exe)]).returncode == 0


@pytest.mark.skipif(_cc() is None, reason="no C compiler available")
def test_end_to_end_memory(tmp_path):
    """Recompile store-then-load and verify it round-trips through the hooks."""
    # li r3, 0x1234 ; li r4, 0x100 ; stw r3, 0(r4) ; lwz r5, 0(r4) ; blr
    program = assemble([
        0x38601234,  # li r3, 0x1234
        0x38800100,  # li r4, 0x100
        0x90640000,  # stw r3, 0(r4)
        0x80A40000,  # lwz r5, 0(r4)
        0x4E800020,  # blr
    ])
    func = recompile_function(program, 0, "run")
    (tmp_path / "ppc_runtime.h").write_text(RUNTIME_HEADER)
    harness = f"""
#include "ppc_runtime.h"
#include <stdio.h>
static uint8_t MEM[0x10000];
{func}
uint8_t  ppc_read_u8 (PpcContext* c, uint32_t e) {{ (void)c; return MEM[e & 0xffff]; }}
uint16_t ppc_read_u16(PpcContext* c, uint32_t e) {{ (void)c; e&=0xffff;
    return (uint16_t)((MEM[e]<<8)|MEM[e+1]); }}
uint32_t ppc_read_u32(PpcContext* c, uint32_t e) {{ (void)c; e&=0xffff;
    return ((uint32_t)MEM[e]<<24)|((uint32_t)MEM[e+1]<<16)|
           ((uint32_t)MEM[e+2]<<8)|MEM[e+3]; }}
void ppc_write_u8 (PpcContext* c, uint32_t e, uint8_t v)  {{ (void)c; MEM[e&0xffff]=v; }}
void ppc_write_u16(PpcContext* c, uint32_t e, uint16_t v) {{ (void)c; e&=0xffff;
    MEM[e]=v>>8; MEM[e+1]=v; }}
void ppc_write_u32(PpcContext* c, uint32_t e, uint32_t v) {{ (void)c; e&=0xffff;
    MEM[e]=v>>24; MEM[e+1]=v>>16; MEM[e+2]=v>>8; MEM[e+3]=v; }}
void ppc_call(PpcContext* c, uint32_t t) {{ (void)c;(void)t; }}
void ppc_unimplemented(PpcContext* c, uint32_t a, uint32_t r) {{ (void)c;(void)a;(void)r; }}
int main(void) {{
    PpcContext c; for (int i=0;i<32;++i) c.gpr[i]=0; c.lr=c.ctr=c.cr=c.xer=0;
    run(&c);
    return c.gpr[5] == 0x1234 ? 0 : 1;
}}
"""
    src = tmp_path / "harness.c"
    src.write_text(harness)
    exe = tmp_path / "harness"
    r = subprocess.run([_cc(), "-std=c11", "-I", str(tmp_path), str(src),
                        "-o", str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert subprocess.run([str(exe)]).returncode == 0
