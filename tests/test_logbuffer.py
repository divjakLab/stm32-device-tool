import time

from devicetool.core.logbuffer import (Level, LineAssembler, LogLine, LogStore, SessionLog,
                                       classify, format_ts, make_marker, matches, prune_logs)


def texts(lines):
    return [l.text for l in lines]


def test_split_on_all_line_endings():
    a = LineAssembler()
    assert texts(a.feed(b"one\r\ntwo\nthree\rfour", 1.0)) == ["one", "two", "three"]
    assert texts(a.flush_if_idle(1.1)) == []
    assert texts(a.flush_if_idle(1.3)) == ["four"]


def test_crlf_split_across_reads_gives_one_line():
    a = LineAssembler()
    assert texts(a.feed(b"hello\r", 1.0)) == ["hello"]
    assert texts(a.feed(b"\nworld\r\n", 1.01)) == ["world"]


def test_blank_lines_are_kept():
    a = LineAssembler()
    assert texts(a.feed(b"a\r\n\r\nb\r\n", 1.0)) == ["a", "", "b"]


def test_partial_line_waits_for_rest():
    a = LineAssembler()
    assert a.feed(b"Wi-Fi in", 1.0) == []
    assert texts(a.feed(b"it is done\r\n", 1.05)) == ["Wi-Fi init is done"]


def test_garbage_bytes_do_not_crash_and_are_replaced():
    a = LineAssembler()
    out = a.feed(bytes(range(256)) + b"\n", 1.0)
    joined = "".join(texts(out))
    assert "�" in joined
    assert "\x1b" not in joined and "\x00" not in joined


def test_ansi_colors_are_stripped():
    a = LineAssembler()
    assert texts(a.feed(b"\x1b[31mERROR\x1b[0m x\n", 1.0)) == ["ERROR x"]


def test_long_line_without_newline_is_force_split():
    a = LineAssembler(max_line_bytes=4096)
    out = a.feed(b"x" * 10000, 1.0)
    assert [len(t) for t in texts(out)] == [4096, 4096]
    assert len(texts(a.flush_if_idle(2.0))[0]) == 10000 - 8192


def test_big_burst_is_fast():
    a = LineAssembler()
    data = b"BLE advertising is started, value=12345\r\n" * 25000  # ~1 MB
    t0 = time.perf_counter()
    out = a.feed(data, 1.0)
    assert len(out) == 25000
    assert time.perf_counter() - t0 < 1.0


def test_utf8_char_split_across_reads():
    a = LineAssembler()
    s = "čšž\n".encode()
    assert a.feed(s[:1], 1.0) == []
    assert texts(a.feed(s[1:], 1.01)) == ["čšž"]


def test_classify():
    assert classify("failed to start advertising, -3") is Level.ERROR
    assert classify("MQTT_ERROR_CONNECT") is Level.ERROR
    assert classify("HardFault!") is Level.ERROR
    assert classify("ASSERT at x") is Level.ERROR
    assert classify("Warning: low RSSI") is Level.WARN
    assert classify("Wi-Fi init is done") is Level.NORMAL


def test_marker_and_format():
    m = make_marker("board reset", 0.0)
    assert m.level is Level.MARKER and m.text == "── board reset ──"
    assert len(format_ts(time.time())) == len("12:34:56.789")


def test_store_filter_and_limit(tmp_path):
    s = LogStore(max_lines=3)
    s.extend([LogLine(1.0, t, Level.NORMAL) for t in ["a BLE", "b wifi", "c ble", "d"]])
    assert texts(s.lines) == ["b wifi", "c ble", "d"]
    assert texts(s.filtered("BLE")) == ["c ble"]
    assert texts(s.filtered("  ")) == ["b wifi", "c ble", "d"]
    assert matches(LogLine(0, "Hello", Level.NORMAL), "hell")
    p = tmp_path / "out.txt"
    s.save(p)
    assert p.read_text(encoding="utf-8").splitlines()[0].endswith("  b wifi")


def test_session_log_writes_and_prunes(tmp_path):
    for i in range(5):
        (tmp_path / f"2020-01-0{i + 1}_00-00-00.txt").write_text("x")
    log = SessionLog(tmp_path, keep=3)
    log.write([LogLine(1.0, "hello", Level.NORMAL)])
    log.close()
    assert "hello" in log.path.read_text(encoding="utf-8")
    assert len(list(tmp_path.glob("*.txt"))) == 3
    assert log.path.exists()
    prune_logs(tmp_path, 1)
    assert list(tmp_path.glob("*.txt")) == [log.path]
