"""Address → 'function+offset (file:line)' from an .elf built with debug info."""

from __future__ import annotations

import os
from bisect import bisect_right
from pathlib import Path
from typing import Optional

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection


class Symbolizer:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            with open(self.path, "rb") as f:
                elf = ELFFile(f)
                self._funcs = self._load_functions(elf)
                self._lines = self._load_lines(elf)
        except (ELFError, OSError) as exc:
            raise ValueError(f"Not a readable .elf file: {exc}") from exc
        self._starts = [s for s, _, _ in self._funcs]
        self._line_addrs = [a for a, _, _ in self._lines]

    @staticmethod
    def _load_functions(elf: ELFFile) -> list[tuple[int, int, str]]:
        out = []
        for sec in elf.iter_sections():
            if isinstance(sec, SymbolTableSection):
                for sym in sec.iter_symbols():
                    if sym["st_info"]["type"] == "STT_FUNC" and sym.name:
                        out.append((sym["st_value"] & ~1, sym["st_size"], sym.name))
        return sorted(out)

    @staticmethod
    def _load_lines(elf: ELFFile) -> list[tuple[int, str, int]]:
        if not elf.has_dwarf_info():
            return []
        dwarf = elf.get_dwarf_info()
        out = []
        for cu in dwarf.iter_CUs():
            lp = dwarf.line_program_for_CU(cu)
            if lp is None:
                continue
            files = lp["file_entry"]
            base = 0 if lp.header["version"] >= 5 else 1
            for entry in lp.get_entries():
                st = entry.state
                if st is None or st.end_sequence:
                    continue
                idx = st.file - base
                name = files[idx].name.decode(errors="replace") if 0 <= idx < len(files) else "?"
                out.append((st.address, name, st.line))
        return sorted(out)

    def functions(self) -> list[tuple[int, int, str]]:
        return list(self._funcs)

    def function_at(self, addr: int) -> Optional[tuple[str, int]]:
        addr &= ~1
        i = bisect_right(self._starts, addr) - 1
        if i < 0:
            return None
        start, size, name = self._funcs[i]
        if size and addr >= start + size:
            return None
        return name, addr - start

    def line_at(self, addr: int) -> Optional[tuple[str, int]]:
        addr &= ~1
        i = bisect_right(self._line_addrs, addr) - 1
        if i < 0:
            return None
        _, name, line = self._lines[i]
        return name, line

    def describe(self, addr: int) -> Optional[str]:
        func = self.function_at(addr)
        if func is None:
            return None
        text = f"{func[0]}+0x{func[1]:X}"
        line = self.line_at(addr)
        if line is not None:
            text += f" ({os.path.basename(line[0])}:{line[1]})"
        return text
