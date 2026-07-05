"""Decoder tests against known-good PowerPC encodings (verified by hand and
against standard assembler output)."""

from gcport.ppc import decode, disassemble


def d(word, addr=0):
    return decode(word, addr)


def test_li_and_lis():
    assert disassemble(0x38600005) == "li r3, 5"
    assert disassemble(0x38800007) == "li r4, 7"
    # lis r5, 0x8000
    assert d(0x3CA08000).mnemonic == "lis"
    assert d(0x3CA08000).operands == ["r5", "0x8000"]


def test_addi_negative_simm():
    ins = d(0x3863FFFF)  # addi r3, r3, -1
    assert ins.mnemonic == "addi"
    assert ins.dest == 3 and ins.src_a == 3 and ins.simm == -1


def test_add_subf():
    ins = d(0x7C632214)  # add r3, r3, r4
    assert ins.mnemonic == "add"
    assert (ins.dest, ins.src_a, ins.src_b) == (3, 3, 4)
    ins = d(0x7C642850)  # subf r3, r4, r5  -> r5 - r4
    assert ins.mnemonic == "subf"
    assert (ins.dest, ins.src_a, ins.src_b) == (3, 4, 5)


def test_mr_is_simplified_or():
    ins = d(0x7C651B78)  # or r5, r3, r3
    assert ins.mnemonic == "mr"
    assert ins.dest == 5 and ins.src_a == 3


def test_or_and_xor():
    # or r5, r3, r4 (not mr since rS != rB)
    ins = d(0x7C652378)
    assert ins.mnemonic == "or"
    assert (ins.dest, ins.src_a, ins.src_b) == (5, 3, 4)


def test_nop():
    assert d(0x60000000).mnemonic == "nop"


def test_ori():
    ins = d(0x60650001)  # ori r5, r3, 1
    assert ins.mnemonic == "ori"
    assert ins.dest == 5 and ins.src_a == 3 and ins.uimm == 1


def test_loads_stores():
    ins = d(0x80640008)  # lwz r3, 8(r4)
    assert ins.mnemonic == "lwz"
    assert ins.dest == 3 and ins.src_a == 4 and ins.disp == 8
    ins = d(0x90610004)  # stw r3, 4(r1)
    assert ins.mnemonic == "stw"
    assert ins.src_b == 3 and ins.src_a == 1 and ins.disp == 4
    assert d(0x88640000).mnemonic == "lbz"
    assert d(0x98640000).mnemonic == "stb"


def test_cmpwi():
    ins = d(0x2C040005)  # cmpwi r4, 5
    assert ins.mnemonic == "cmpwi"
    assert ins.src_a == 4 and ins.simm == 5 and ins.crf == 0


def test_unconditional_branch():
    ins = d(0x48000010, addr=0x100)  # b 0x110
    assert ins.mnemonic == "b"
    assert ins.target == 0x110
    assert ins.ends_block and not ins.is_call
    # bl sets the call flag
    ins = d(0x48000011, addr=0x100)
    assert ins.mnemonic == "bl" and ins.is_call


def test_backward_branch():
    ins = d(0x4BFFFFF0, addr=0x18)  # b -16 -> 0x08
    assert ins.target == 0x08


def test_conditional_branch():
    ins = d(0x40800010, addr=0x0C)  # bge 0x1C
    assert ins.mnemonic == "bge"
    assert ins.target == 0x1C
    assert ins.is_conditional and ins.bo == 4 and ins.bi == 0
    ins = d(0x41820010, addr=0x0C)  # beq 0x1C (BO=12, BI=2)
    assert ins.mnemonic == "beq"
    assert ins.bo == 12 and ins.bi == 2


def test_blr_and_bctr():
    ins = d(0x4E800020)
    assert ins.mnemonic == "blr" and ins.is_return and ins.ends_block
    ins = d(0x4E800420)
    assert ins.mnemonic == "bctr"


def test_mflr_mtlr():
    assert d(0x7C0802A6).mnemonic == "mflr"   # mflr r0
    assert d(0x7C0803A6).mnemonic == "mtlr"   # mtlr r0


def test_rlwinm():
    ins = d(0x5463103A)  # rlwinm r3, r3, 2, 0, 29 (slwi r3,r3,2)
    assert ins.mnemonic == "rlwinm"
    assert ins.dest == 3 and ins.src_a == 3 and ins.sh == 2


def test_fp_load_store():
    ins = d(0xC0230000)  # lfs f1, 0(r3)
    assert ins.mnemonic == "lfs" and ins.is_float
    assert ins.dest == 1 and ins.src_a == 3 and ins.disp == 0
    ins = d(0xC8230000)  # lfd f1, 0(r3)
    assert ins.mnemonic == "lfd"
    ins = d(0xD0230008)  # stfs f1, 8(r3)
    assert ins.mnemonic == "stfs"
    assert ins.src_b == 1 and ins.src_a == 3 and ins.disp == 8


def test_fp_arith():
    ins = d(0xEC21102A)  # fadds f1, f1, f2
    assert ins.mnemonic == "fadds" and ins.is_float
    assert (ins.dest, ins.src_a, ins.src_b) == (1, 1, 2)
    ins = d(0xEC2200F2)  # fmuls f1, f2, f3  (uses frA, frC)
    assert ins.mnemonic == "fmuls"
    assert ins.dest == 1 and ins.src_a == 2 and ins.src_c == 3
    ins = d(0xEC2220FA)  # fmadds f1, f2, f3, f4  -> D = A*C + B
    assert ins.mnemonic == "fmadds"
    assert (ins.dest, ins.src_a, ins.src_c, ins.src_b) == (1, 2, 3, 4)


def test_fp_unary_and_compare():
    ins = d(0xFC201090)  # fmr f1, f2
    assert ins.mnemonic == "fmr" and ins.dest == 1 and ins.src_b == 2
    ins = d(0xFC201050)  # fneg f1, f2
    assert ins.mnemonic == "fneg"
    ins = d(0xFC011000)  # fcmpu cr0, f1, f2
    assert ins.mnemonic == "fcmpu"
    assert ins.src_a == 1 and ins.src_b == 2 and ins.crf == 0


def test_fp_convert():
    ins = d(0xFC40081E)  # fctiwz f2, f1
    assert ins.mnemonic == "fctiwz" and ins.is_float
    assert ins.dest == 2 and ins.src_b == 1


def test_indexed_memory():
    ins = d(0x7CC3202E)  # lwzx r6, r3, r4
    assert ins.mnemonic == "lwzx"
    assert ins.dest == 6 and ins.src_a == 3 and ins.index == 4
    ins = d(0x7CA3212E)  # stwx r5, r3, r4
    assert ins.mnemonic == "stwx"
    assert ins.src_b == 5 and ins.src_a == 3 and ins.index == 4
    ins = d(0x7C432FAE)  # stfiwx f2, r3, r5
    assert ins.mnemonic == "stfiwx" and ins.is_float
    assert ins.src_b == 2 and ins.src_a == 3 and ins.index == 5


def test_paired_single_disassembles():
    # ps_add f1, f2, f3 (opcode 4, xo 21) -> decoded but emission is a trap
    word = (4 << 26) | (1 << 21) | (2 << 16) | (3 << 11) | (21 << 1)
    ins = d(word)
    assert ins.mnemonic == "ps_add"


def test_unknown_is_word():
    ins = d(0x00000000)
    assert ins.mnemonic == ".word"
