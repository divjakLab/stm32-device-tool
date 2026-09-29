import pytest
from intelhex import IntelHex

from devicetool.core.hexfile import HexFileError, load_hex


def make_hex(path, start=0x08000000, data=b"\x01\x02\x03\x04"):
    ih = IntelHex()
    ih.puts(start, data)
    ih.write_hex_file(str(path))


def test_valid_hex(tmp_path):
    p = tmp_path / "fw with space.hex"
    make_hex(p)
    ih, info = load_hex(p)
    assert (info.size, info.start, info.end) == (4, 0x08000000, 0x08000004)
    assert info.segments == [(0x08000000, 0x08000004)]


def test_missing_garbage_empty(tmp_path):
    with pytest.raises(HexFileError, match="not found"):
        load_hex(tmp_path / "none.hex")
    g = tmp_path / "g.hex"
    g.write_text("hello world")
    with pytest.raises(HexFileError, match="not a valid"):
        load_hex(g)
    e = tmp_path / "e.hex"
    e.write_text(":00000001FF\n")
    with pytest.raises(HexFileError, match="no data"):
        load_hex(e)
