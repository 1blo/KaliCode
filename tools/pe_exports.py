"""Print the export table of a PE file."""
from __future__ import annotations

import struct
import sys


def exports(path: str) -> list[str]:
    data = open(path, "rb").read()

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    assert data[e_lfanew:e_lfanew + 4] == b"PE\0\0", "not a PE"
    coff = e_lfanew + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    pe32_plus = magic == 0x20B

    dd_off = opt + (112 if pe32_plus else 96)
    export_rva, export_size = struct.unpack_from("<II", data, dd_off)

    sections = []
    sec_off = opt + opt_size
    for i in range(n_sections):
        o = sec_off + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("latin-1")
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        sections.append((name, vaddr, vsize, raddr, rsize))

    def to_off(rva: int) -> int:
        for name, vaddr, vsize, raddr, rsize in sections:
            if vaddr <= rva < vaddr + max(vsize, rsize):
                return raddr + (rva - vaddr)
        return None

    if not export_rva:
        return []
    eo = to_off(export_rva)
    if eo is None:
        return []
    (flags, ts, maj, minor, name_rva, ordinal_base, n_funcs, n_names,
     func_rva, names_rva, ords_rva) = struct.unpack_from("<IIHHIIIIIII", data, eo)

    names_off = to_off(names_rva)
    out = []
    for i in range(n_names):
        nrva = struct.unpack_from("<I", data, names_off + i * 4)[0]
        no = to_off(nrva)
        end = data.index(b"\0", no)
        out.append(data[no:end].decode("latin-1"))
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"=== {p} ===")
        try:
            for n in exports(p):
                print("  ", n)
        except Exception as e:
            print("   error:", e)
