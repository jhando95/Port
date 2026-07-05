"""Static recompiler back-end: PowerPC instructions -> C.

Emits a C function per recompiled routine operating on a `PpcContext` (the
guest register file) and calling memory/branch hooks the runtime provides.
The emitted code references the contract in RUNTIME_HEADER.

This is a first, verifiable slice: the integer/compare/branch/load-store
subset the decoder recognizes. Instructions outside that subset emit an
explicit `ppc_unimplemented(...)` call so gaps fail loudly instead of
silently producing wrong results.
"""

from __future__ import annotations

from .decode import Instruction, decode

RUNTIME_HEADER = r"""/* gcrt PowerPC recompiler runtime contract (generated). */
#ifndef GCRT_PPC_RUNTIME_H
#define GCRT_PPC_RUNTIME_H
#include <stdint.h>

typedef struct PpcContext {
    uint32_t gpr[32];
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

/* Memory + control hooks the host runtime implements (backed by gcrt::Memory
   and the recompiled function table). */
uint8_t  ppc_read_u8 (PpcContext*, uint32_t ea);
uint16_t ppc_read_u16(PpcContext*, uint32_t ea);
uint32_t ppc_read_u32(PpcContext*, uint32_t ea);
void ppc_write_u8 (PpcContext*, uint32_t ea, uint8_t v);
void ppc_write_u16(PpcContext*, uint32_t ea, uint16_t v);
void ppc_write_u32(PpcContext*, uint32_t ea, uint32_t v);
void ppc_call(PpcContext*, uint32_t target);
void ppc_unimplemented(PpcContext*, uint32_t address, uint32_t raw);

#endif
"""


def _label(address: int) -> str:
    return f"L_{address:08x}"


def _gpr(n: int) -> str:
    return f"c->gpr[{n}]"


def _base_expr(reg: int | None, disp: int) -> str:
    """Effective address: (rA|0) + disp, honoring rA=0 meaning literal 0."""
    if not reg:  # rA == 0 -> base is 0
        return f"{disp & 0xFFFFFFFF}u"
    if disp == 0:
        return _gpr(reg)
    return f"({_gpr(reg)} + {disp})"


def _emit_one(insn: Instruction) -> list[str]:
    """Return the C statements implementing a single instruction."""
    m = insn.mnemonic.rstrip(".")  # record-bit handling is separate
    d, a, b = insn.dest, insn.src_a, insn.src_b

    def src(reg: int | None) -> str:
        # For arithmetic with rA, a register value; 0 stays literal only for
        # addi/load base which are handled via _base_expr.
        return _gpr(reg)

    stmts: list[str] = []

    if m == "nop":
        return ["/* nop */"]
    if m == "li":
        stmts = [f"{_gpr(d)} = (uint32_t){insn.simm};"]
    elif m == "lis":
        stmts = [f"{_gpr(d)} = (uint32_t)({insn.uimm} << 16);"]
    elif m == "addi":
        stmts = [f"{_gpr(d)} = {_base_expr(a, insn.simm)};"]
    elif m == "addis":
        val = (insn.simm << 16) & 0xFFFFFFFF
        base = "0u" if not a else _gpr(a)
        stmts = [f"{_gpr(d)} = {base} + {val}u;"]
    elif m in ("addic", "addc"):
        stmts = [f"{_gpr(d)} = {src(a)} + (uint32_t){insn.simm};"]
    elif m == "mulli":
        stmts = [f"{_gpr(d)} = (uint32_t)((int32_t){src(a)} * {insn.simm});"]
    elif m == "subfic":
        stmts = [f"{_gpr(d)} = (uint32_t){insn.simm} - {src(a)};"]
    elif m == "add":
        stmts = [f"{_gpr(d)} = {src(a)} + {src(b)};"]
    elif m == "subf":
        stmts = [f"{_gpr(d)} = {src(b)} - {src(a)};"]
    elif m == "neg":
        stmts = [f"{_gpr(d)} = (uint32_t)(-(int32_t){src(a)});"]
    elif m == "mullw":
        stmts = [f"{_gpr(d)} = (uint32_t)((int32_t){src(a)} * (int32_t){src(b)});"]
    elif m == "divw":
        stmts = [f"{_gpr(d)} = (uint32_t)((int32_t){src(a)} / (int32_t){src(b)});"]
    elif m == "divwu":
        stmts = [f"{_gpr(d)} = {src(a)} / {src(b)};"]
    elif m == "and":
        stmts = [f"{_gpr(d)} = {src(a)} & {src(b)};"]
    elif m == "or":
        stmts = [f"{_gpr(d)} = {src(a)} | {src(b)};"]
    elif m == "xor":
        stmts = [f"{_gpr(d)} = {src(a)} ^ {src(b)};"]
    elif m == "nand":
        stmts = [f"{_gpr(d)} = ~({src(a)} & {src(b)});"]
    elif m == "nor":
        stmts = [f"{_gpr(d)} = ~({src(a)} | {src(b)});"]
    elif m == "andc":
        stmts = [f"{_gpr(d)} = {src(a)} & ~{src(b)};"]
    elif m == "orc":
        stmts = [f"{_gpr(d)} = {src(a)} | ~{src(b)};"]
    elif m == "eqv":
        stmts = [f"{_gpr(d)} = ~({src(a)} ^ {src(b)});"]
    elif m == "mr":
        stmts = [f"{_gpr(d)} = {src(a)};"]
    elif m == "slw":
        stmts = [f"{_gpr(d)} = ({src(a)} << ({src(b)} & 0x3f)) "
                 f"& (({src(b)} & 0x20) ? 0u : 0xffffffffu);"]
    elif m == "srw":
        stmts = [f"{_gpr(d)} = ({src(b)} & 0x20) ? 0u : "
                 f"({src(a)} >> ({src(b)} & 0x1f));"]
    elif m == "sraw":
        stmts = [f"{_gpr(d)} = (uint32_t)((int32_t){src(a)} >> "
                 f"(({src(b)} & 0x20) ? 31 : ({src(b)} & 0x1f)));"]
    elif m == "srawi":
        stmts = [f"{_gpr(d)} = (uint32_t)((int32_t){src(a)} >> {insn.sh});"]
    elif m == "extsb":
        stmts = [f"{_gpr(d)} = (uint32_t)(int32_t)(int8_t){src(a)};"]
    elif m == "extsh":
        stmts = [f"{_gpr(d)} = (uint32_t)(int32_t)(int16_t){src(a)};"]
    elif m == "cntlzw":
        stmts = [f"{_gpr(d)} = {src(a)} ? (uint32_t)__builtin_clz({src(a)}) : 32u;"]
    elif m in ("ori", "oris", "xori", "xoris", "andi", "andis"):
        shift = 16 if m.endswith("s") else 0
        op = {"ori": "|", "oris": "|", "xori": "^", "xoris": "^",
              "andi": "&", "andis": "&"}[m]
        stmts = [f"{_gpr(d)} = {src(a)} {op} ({insn.uimm}u << {shift});"]
    elif m == "rlwinm":
        stmts = _emit_rlwinm(insn)
    elif m in ("lwz", "lwzu"):
        stmts = [f"{_gpr(d)} = ppc_read_u32(c, {_base_expr(a, insn.disp)});"]
    elif m in ("lhz", "lhzu"):
        stmts = [f"{_gpr(d)} = ppc_read_u16(c, {_base_expr(a, insn.disp)});"]
    elif m in ("lha", "lhau"):
        stmts = [f"{_gpr(d)} = (uint32_t)(int32_t)(int16_t)"
                 f"ppc_read_u16(c, {_base_expr(a, insn.disp)});"]
    elif m in ("lbz", "lbzu"):
        stmts = [f"{_gpr(d)} = ppc_read_u8(c, {_base_expr(a, insn.disp)});"]
    elif m in ("stw", "stwu"):
        stmts = [f"ppc_write_u32(c, {_base_expr(a, insn.disp)}, {_gpr(b)});"]
    elif m in ("sth", "sthu"):
        stmts = [f"ppc_write_u16(c, {_base_expr(a, insn.disp)}, "
                 f"(uint16_t){_gpr(b)});"]
    elif m in ("stb", "stbu"):
        stmts = [f"ppc_write_u8(c, {_base_expr(a, insn.disp)}, "
                 f"(uint8_t){_gpr(b)});"]
    elif m in ("cmpwi", "cmpw"):
        rhs = f"(int32_t){insn.simm}" if m == "cmpwi" else f"(int32_t){_gpr(b)}"
        stmts = [f"ppc_cmp_signed(c, {insn.crf or 0}, (int32_t){_gpr(a)}, {rhs});"]
    elif m in ("cmplwi", "cmplw"):
        rhs = f"{insn.uimm}u" if m == "cmplwi" else _gpr(b)
        stmts = [f"ppc_cmp_unsigned(c, {insn.crf or 0}, {_gpr(a)}, {rhs});"]
    elif m == "mflr":
        stmts = [f"{_gpr(d)} = c->lr;"]
    elif m == "mtlr":
        stmts = [f"c->lr = {_gpr(a)};"]
    elif m == "mfctr":
        stmts = [f"{_gpr(d)} = c->ctr;"]
    elif m == "mtctr":
        stmts = [f"c->ctr = {_gpr(a)};"]
    else:
        return [f"ppc_unimplemented(c, 0x{insn.address:08x}u, "
                f"0x{insn.raw:08x}u); /* {insn.disasm} */"]

    if insn.rc:  # record bit: reflect the (signed) result in CR0
        stmts.append(f"ppc_cmp_signed(c, 0, (int32_t){_gpr(d)}, 0);")
    return stmts


def _emit_rlwinm(insn: Instruction) -> list[str]:
    sh, mb, me = insn.sh, insn.mb, insn.me
    # mask with bits mb..me set (PowerPC MSB-order, wrapping when mb > me)
    if mb <= me:
        mask = 0
        for bit in range(mb, me + 1):
            mask |= 1 << (31 - bit)
    else:
        mask = 0xFFFFFFFF
        for bit in range(me + 1, mb):
            mask &= ~(1 << (31 - bit))
    rot = (f"(({_gpr(insn.src_a)} << {sh}) | ({_gpr(insn.src_a)} >> {32 - sh}))"
           if sh else _gpr(insn.src_a))
    return [f"{_gpr(insn.dest)} = {rot} & 0x{mask:08x}u;"]


def recompile_function(code: bytes, base_address: int, name: str) -> str:
    """Recompile a contiguous code blob into a C function named `name`.

    Branches whose target lies inside the blob become gotos; targets outside
    become ppc_call() (calls) or a call+return (tail branches). blr returns.
    """
    if len(code) % 4 != 0:
        raise ValueError("code length must be a multiple of 4")
    count = len(code) // 4
    instrs = [decode(int.from_bytes(code[i * 4:i * 4 + 4], "big"),
                     base_address + i * 4) for i in range(count)]
    end_address = base_address + len(code)

    # Labels only for internal branch targets, to avoid unused-label warnings.
    targets: set[int] = set()
    for ins in instrs:
        if ins.is_branch and ins.target is not None and not ins.is_call:
            if base_address <= ins.target < end_address:
                targets.add(ins.target)

    lines = [f"void {name}(PpcContext* c) {{"]
    for ins in instrs:
        if ins.address in targets:
            lines.append(f"{_label(ins.address)}:;")
        for stmt in _emit_branch(ins, base_address, end_address, targets) \
                if ins.is_branch else _emit_one(ins):
            lines.append(f"    {stmt}")
    lines.append("}")
    return "\n".join(lines)


def _emit_branch(insn: Instruction, base: int, end: int,
                 targets: set[int]) -> list[str]:
    if insn.is_return:
        return ["return;"]
    if insn.mnemonic.startswith("bctr"):
        if insn.is_call:
            return ["ppc_call(c, c->ctr);"]
        return ["ppc_call(c, c->ctr);", "return;"]

    target = insn.target
    internal = target is not None and base <= target < end

    if insn.is_conditional:
        # BO=12 branch-if-true, BO=4 branch-if-false (condition-only forms).
        cond = None
        if insn.bo == 12:
            cond = f"ppc_cr_bit(c, {insn.bi})"
        elif insn.bo == 4:
            cond = f"!ppc_cr_bit(c, {insn.bi})"
        if cond is None:
            return [f"ppc_unimplemented(c, 0x{insn.address:08x}u, "
                    f"0x{insn.raw:08x}u); /* {insn.disasm} */"]
        if internal:
            return [f"if ({cond}) goto {_label(target)};"]
        return [f"if ({cond}) {{ ppc_call(c, 0x{target:08x}u); return; }}"]

    # unconditional
    if insn.is_call:  # bl
        return [f"ppc_call(c, 0x{target:08x}u);"]
    if internal:
        return [f"goto {_label(target)};"]
    return [f"ppc_call(c, 0x{target:08x}u);", "return;"]
