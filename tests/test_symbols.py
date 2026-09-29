import shutil
import subprocess

import pytest

from devicetool.core.symbols import Symbolizer

SRC = "int add(int a, int b) { return a + b; }\nint mul(int a, int b) { return a * b; }\n"


@pytest.fixture(scope="module")
def elf(tmp_path_factory):
    if shutil.which("clang") is None:
        pytest.skip("clang not available")
    d = tmp_path_factory.mktemp("elf")
    (d / "f.c").write_text(SRC)
    subprocess.run(["clang", "--target=thumbv8m.main-none-eabi", "-g", "-O1", "-c",
                    str(d / "f.c"), "-o", str(d / "f.o")], check=True)
    return Symbolizer(d / "f.o")


def test_functions_found(elf):
    names = {name for _, _, name in elf.functions()}
    assert {"add", "mul"} <= names


def test_describe_with_offset_and_line(elf):
    starts = {name: start for start, _, name in elf.functions()}
    mul = starts["mul"]
    assert elf.function_at(mul + 2) == ("mul", 2)
    assert elf.function_at(mul + 3) == ("mul", 2)        # thumb bit ignored
    assert elf.describe(mul) == "mul+0x0 (f.c:2)"
    assert elf.describe(starts["add"]).startswith("add+0x0 (f.c:1)")


def test_address_outside_functions(elf):
    assert elf.function_at(0x08000000) is None


def test_not_an_elf(tmp_path):
    p = tmp_path / "x.elf"
    p.write_bytes(b"hello")
    with pytest.raises(ValueError):
        Symbolizer(p)
