import struct

from devicetool import selftest


def test_qt_platform_plugin_name(monkeypatch):
    monkeypatch.setattr(selftest.sys, "platform", "darwin")
    assert selftest.qt_platform_plugin() == "libqcocoa.dylib"
    monkeypatch.setattr(selftest.sys, "platform", "win32")
    assert selftest.qt_platform_plugin() == "qwindows.dll"


def test_ico_writer_makes_valid_icon(tmp_path):
    from tools.make_icon import write_ico
    pngs = {16: b"\x89PNG-16", 256: b"\x89PNG-256"}
    p = tmp_path / "i.ico"
    write_ico(p, pngs)
    data = p.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind, count) == (0, 1, 2)
    w0, h0 = data[6], data[7]
    size0, off0 = struct.unpack_from("<II", data, 6 + 8)
    assert (w0, h0) == (16, 16) and data[off0:off0 + size0] == b"\x89PNG-16"
    w1 = data[6 + 16]
    size1, off1 = struct.unpack_from("<II", data, 6 + 16 + 8)
    assert w1 == 0 and data[off1:off1 + size1] == b"\x89PNG-256"   # 0 means 256
