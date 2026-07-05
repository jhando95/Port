"""PowerPC instruction decoder.

Instructions are 32-bit, big-endian, fixed width. PowerPC numbers bits from
the MSB (bit 0 = 0x80000000). The primary opcode is bits 0-5; the remaining
fields depend on the instruction form (D, XO, X, M, I, B, XL).

`decode(word, address)` returns an Instruction with both the raw decoded
fields and a normalized semantic role for destination/source registers, so the
recompiler can emit C uniformly regardless of the underlying encoding quirk
(e.g. arithmetic puts the destination in bits 6-10, logical ops in bits 11-15).
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _sign_extend(value: int, bits: int) -> int:
    mask = 1 << (bits - 1)
    return (value ^ mask) - mask


@dataclass
class Instruction:
    address: int
    raw: int
    mnemonic: str = ".word"

    # Semantic register roles (None when unused). `dest` is the written GPR.
    dest: int | None = None
    src_a: int | None = None
    src_b: int | None = None

    # Immediates.
    simm: int | None = None      # sign-extended
    uimm: int | None = None      # zero-extended
    disp: int | None = None      # load/store displacement (signed)

    # rlwinm rotate/mask.
    sh: int | None = None
    mb: int | None = None
    me: int | None = None

    # Compare.
    crf: int | None = None

    # Branch.
    target: int | None = None    # absolute target address, if computable
    bo: int | None = None
    bi: int | None = None
    lk: bool = False             # branch-with-link (call)
    aa: bool = False             # absolute addressing
    rc: bool = False             # record bit (updates CR0)

    # Control-flow classification.
    is_branch: bool = False
    is_conditional: bool = False
    is_call: bool = False
    is_return: bool = False
    ends_block: bool = False     # unconditional transfer / return

    operands: list[str] = field(default_factory=list)  # rendered for disasm

    @property
    def disasm(self) -> str:
        if self.operands:
            return f"{self.mnemonic} {', '.join(self.operands)}"
        return self.mnemonic


def _reg(n: int) -> str:
    return f"r{n}"


def decode(word: int, address: int = 0) -> Instruction:
    word &= 0xFFFFFFFF
    opcode = word >> 26
    insn = Instruction(address=address, raw=word)

    f1 = (word >> 21) & 0x1F  # bits 6-10
    f2 = (word >> 16) & 0x1F  # bits 11-15
    f3 = (word >> 11) & 0x1F  # bits 16-20
    rc = bool(word & 1)

    # --- D-form arithmetic (dest = f1, srcA = f2) ------------------------
    if opcode in (7, 12, 13, 14, 15):
        simm = _sign_extend(word & 0xFFFF, 16)
        insn.dest, insn.src_a, insn.simm = f1, f2, simm
        if opcode == 14 and f2 == 0:  # addi rD, 0, x -> li
            insn.mnemonic = "li"
            insn.src_a = None
            insn.operands = [_reg(f1), str(simm)]
        elif opcode == 15 and f2 == 0:  # addis rD, 0, x -> lis
            insn.mnemonic = "lis"
            insn.src_a = None
            insn.uimm = word & 0xFFFF
            insn.operands = [_reg(f1), hex(word & 0xFFFF)]
        else:
            insn.mnemonic = {7: "mulli", 12: "addic", 13: "addic.",
                             14: "addi", 15: "addis"}[opcode]
            insn.operands = [_reg(f1), _reg(f2), str(simm)]
        return insn

    if opcode in (8, 10, 11):  # subfic, cmpli, cmpi
        simm = _sign_extend(word & 0xFFFF, 16)
        if opcode == 8:
            insn.mnemonic = "subfic"
            insn.dest, insn.src_a, insn.simm = f1, f2, simm
            insn.operands = [_reg(f1), _reg(f2), str(simm)]
        else:
            crf = (word >> 23) & 0x7
            ra = f2  # cmpi rA is bits 11-15
            insn.crf, insn.src_a = crf, ra
            if opcode == 11:  # cmpi -> cmpwi
                insn.mnemonic = "cmpwi"
                insn.simm = simm
                insn.operands = ([_reg(ra), str(simm)] if crf == 0
                                 else [f"cr{crf}", _reg(ra), str(simm)])
            else:  # cmpli -> cmplwi
                insn.mnemonic = "cmplwi"
                insn.uimm = word & 0xFFFF
                insn.operands = ([_reg(ra), hex(word & 0xFFFF)] if crf == 0
                                 else [f"cr{crf}", _reg(ra), hex(word & 0xFFFF)])
        return insn

    # --- D-form logical (dest = f2/rA, srcS = f1/rS) ----------------------
    if opcode in (24, 25, 26, 27, 28, 29):
        uimm = word & 0xFFFF
        insn.dest, insn.src_a, insn.uimm = f2, f1, uimm
        insn.rc = opcode in (28, 29)
        names = {24: "ori", 25: "oris", 26: "xori", 27: "xoris",
                 28: "andi.", 29: "andis."}
        if opcode == 24 and f1 == 0 and f2 == 0 and uimm == 0:
            insn.mnemonic = "nop"
            insn.dest = insn.src_a = None
            insn.operands = []
        else:
            insn.mnemonic = names[opcode]
            insn.operands = [_reg(f2), _reg(f1), hex(uimm)]
        return insn

    # --- D-form load/store ------------------------------------------------
    load_store = {
        32: ("lwz", False), 33: ("lwzu", False), 34: ("lbz", False),
        35: ("lbzu", False), 36: ("stw", True), 37: ("stwu", True),
        38: ("stb", True), 39: ("stbu", True), 40: ("lhz", False),
        41: ("lhzu", False), 42: ("lha", False), 43: ("lhau", False),
        44: ("sth", True), 45: ("sthu", True),
    }
    if opcode in load_store:
        name, is_store = load_store[opcode]
        disp = _sign_extend(word & 0xFFFF, 16)
        insn.mnemonic = name
        insn.disp = disp
        insn.src_a = f2  # base register (rA); 0 means literal 0
        if is_store:
            insn.src_b = f1  # value register (rS)
        else:
            insn.dest = f1   # loaded into rD
        insn.operands = [_reg(f1), f"{disp}({_reg(f2)})"]
        return insn

    # --- rlwinm (M-form) --------------------------------------------------
    if opcode == 21:
        insn.mnemonic = "rlwinm"
        insn.dest, insn.src_a = f2, f1
        insn.sh = f3
        insn.mb = (word >> 6) & 0x1F
        insn.me = (word >> 1) & 0x1F
        insn.rc = rc
        insn.operands = [_reg(f2), _reg(f1), str(insn.sh),
                         str(insn.mb), str(insn.me)]
        return insn

    # --- branch (I-form) --------------------------------------------------
    if opcode == 18:
        li = _sign_extend(word & 0x03FFFFFC, 26)
        aa = bool((word >> 1) & 1)
        lk = bool(word & 1)
        insn.aa, insn.lk = aa, lk
        insn.target = li if aa else (address + li) & 0xFFFFFFFF
        insn.is_branch = True
        insn.is_call = lk
        insn.ends_block = not lk  # bl continues to the return address
        insn.mnemonic = "b" + ("l" if lk else "") + ("a" if aa else "")
        insn.operands = [f"0x{insn.target:08x}"]
        return insn

    # --- conditional branch (B-form) --------------------------------------
    if opcode == 16:
        bd = _sign_extend(word & 0xFFFC, 16)
        aa = bool((word >> 1) & 1)
        lk = bool(word & 1)
        bo = (word >> 21) & 0x1F
        bi = (word >> 16) & 0x1F
        insn.bo, insn.bi, insn.aa, insn.lk = bo, bi, aa, lk
        insn.target = bd if aa else (address + bd) & 0xFFFFFFFF
        insn.is_branch = True
        insn.is_conditional = True
        insn.is_call = lk
        insn.mnemonic = _bc_mnemonic(bo, bi, lk)
        insn.operands = _bc_operands(bo, bi, insn.target)
        return insn

    # --- XL-form (opcode 19): bclr / bcctr / CR ops -----------------------
    if opcode == 19:
        xo = (word >> 1) & 0x3FF
        lk = bool(word & 1)
        bo = (word >> 21) & 0x1F
        if xo == 16:  # bclr
            insn.mnemonic = "blr" + ("l" if lk else "")
            insn.is_branch = True
            insn.is_return = not lk
            insn.is_call = lk
            insn.ends_block = not lk
            insn.bo = bo
            insn.is_conditional = not (bo & 0x14 == 0x14)
            return insn
        if xo == 528:  # bcctr
            insn.mnemonic = "bctr" + ("l" if lk else "")
            insn.is_branch = True
            insn.is_call = lk
            insn.ends_block = not lk
            insn.bo = bo
            return insn
        insn.mnemonic = ".word"  # other CR logical ops: not yet handled
        insn.operands = [f"0x{word:08x}"]
        return insn

    # --- XO / X-form (opcode 31): register ALU ops ------------------------
    if opcode == 31:
        return _decode_x_form(word, address, f1, f2, f3, rc)

    insn.mnemonic = ".word"
    insn.operands = [f"0x{word:08x}"]
    return insn


# Extended-opcode table for opcode 31. Value: (mnemonic, kind) where kind is
# "arith" (dest=f1, a=f2, b=f3), "logic" (dest=f2, a=f1, b=f3), or "special".
_X_OPS = {
    266: ("add", "arith"), 40: ("subf", "arith"), 10: ("addc", "arith"),
    138: ("adde", "arith"), 235: ("mullw", "arith"), 75: ("mulhw", "arith"),
    11: ("mulhwu", "arith"), 491: ("divw", "arith"), 459: ("divwu", "arith"),
    104: ("neg", "arith"),
    28: ("and", "logic"), 444: ("or", "logic"), 316: ("xor", "logic"),
    476: ("nand", "logic"), 124: ("nor", "logic"), 60: ("andc", "logic"),
    412: ("orc", "logic"), 284: ("eqv", "logic"),
    24: ("slw", "logic"), 536: ("srw", "logic"), 792: ("sraw", "logic"),
    954: ("extsb", "logic"), 922: ("extsh", "logic"), 26: ("cntlzw", "logic"),
    0: ("cmpw", "cmp"), 32: ("cmplw", "cmp"),
    339: ("mfspr", "special"), 467: ("mtspr", "special"),
    824: ("srawi", "special"),
}


def _decode_x_form(word, address, f1, f2, f3, rc) -> Instruction:
    insn = Instruction(address=address, raw=word)
    xo = (word >> 1) & 0x3FF
    entry = _X_OPS.get(xo)
    if entry is None:
        insn.mnemonic = ".word"
        insn.operands = [f"0x{word:08x}"]
        return insn
    name, kind = entry
    insn.rc = rc

    if kind == "arith":
        insn.dest, insn.src_a, insn.src_b = f1, f2, f3
        insn.mnemonic = name + (".") * rc
        if name == "neg":
            insn.src_b = None
            insn.operands = [_reg(f1), _reg(f2)]
        else:
            insn.operands = [_reg(f1), _reg(f2), _reg(f3)]
        return insn

    if kind == "logic":
        insn.dest, insn.src_a, insn.src_b = f2, f1, f3
        # or rA, rS, rS -> mr rA, rS
        if name == "or" and f1 == f3:
            insn.mnemonic = "mr" + (".") * rc
            insn.operands = [_reg(f2), _reg(f1)]
        elif name in ("extsb", "extsh", "cntlzw"):
            insn.src_b = None
            insn.mnemonic = name + (".") * rc
            insn.operands = [_reg(f2), _reg(f1)]
        else:
            insn.mnemonic = name + (".") * rc
            insn.operands = [_reg(f2), _reg(f1), _reg(f3)]
        return insn

    if kind == "cmp":
        crf = (word >> 23) & 0x7
        insn.crf, insn.src_a, insn.src_b = crf, f2, f3
        insn.mnemonic = name
        insn.operands = ([_reg(f2), _reg(f3)] if crf == 0
                         else [f"cr{crf}", _reg(f2), _reg(f3)])
        return insn

    # special
    if name == "srawi":
        insn.mnemonic = "srawi" + (".") * rc
        insn.dest, insn.src_a, insn.sh = f2, f1, f3
        insn.operands = [_reg(f2), _reg(f1), str(f3)]
        return insn
    # SPR number is split across two 5-bit fields and stored high-half first.
    spr = ((word >> 16) & 0x1F) | (((word >> 11) & 0x1F) << 5)
    spr_name = {8: "lr", 9: "ctr", 1: "xer"}.get(spr, f"spr{spr}")
    if name == "mfspr":
        insn.mnemonic = {"lr": "mflr", "ctr": "mfctr"}.get(spr_name, "mfspr")
        insn.dest = f1
        insn.operands = ([_reg(f1)] if insn.mnemonic != "mfspr"
                         else [_reg(f1), str(spr)])
        insn.simm = spr
    else:  # mtspr
        insn.mnemonic = {"lr": "mtlr", "ctr": "mtctr"}.get(spr_name, "mtspr")
        insn.src_a = f1
        insn.operands = ([_reg(f1)] if insn.mnemonic != "mtspr"
                         else [str(spr), _reg(f1)])
        insn.simm = spr
    return insn


def _bc_mnemonic(bo: int, bi: int, lk: bool) -> str:
    suffix = "l" if lk else ""
    cond = bi & 3
    # BO=12: branch if true; BO=4: branch if false (condition-only forms)
    if bo == 12:
        base = {0: "blt", 1: "bgt", 2: "beq", 3: "bso"}[cond]
    elif bo == 4:
        base = {0: "bge", 1: "ble", 2: "bne", 3: "bns"}[cond]
    else:
        return "bc" + suffix
    return base + suffix


def _bc_operands(bo: int, bi: int, target: int) -> list[str]:
    if bo in (4, 12):
        crf = bi >> 2
        prefix = [] if crf == 0 else [f"cr{crf}"]
        return prefix + [f"0x{target:08x}"]
    return [str(bo), str(bi), f"0x{target:08x}"]


def disassemble(word: int, address: int = 0) -> str:
    return decode(word, address).disasm
