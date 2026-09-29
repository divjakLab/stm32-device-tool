import json

import pytest

from devicetool.core.commands import (EXAMPLES, Command, CommandLibrary, History, fill,
                                      placeholders)


def test_placeholders_in_order_unique():
    assert placeholders("wifi set {ssid} {password} {ssid}") == ["ssid", "password"]
    assert placeholders("reboot") == []


def test_json_braces_are_not_placeholders():
    text = 'cfg {"on": true, "n": 1}'
    assert placeholders(text) == []
    assert fill(text, {}) == text


def test_fill():
    assert fill("set {key} {value}", {"key": "led", "value": "1"}) == "set led 1"
    assert fill("x {a}", {"a": "{b}"}) == "x {b}"      # values are not re-expanded
    with pytest.raises(KeyError):
        fill("set {key}", {})


def test_default_library_has_examples():
    lib = CommandLibrary()
    assert lib.groups() == ["Examples"]
    assert [c.text for c in lib.commands] == [c.text for c in EXAMPLES]


def test_save_load_round_trip(tmp_path):
    p = tmp_path / "commands.json"
    lib = CommandLibrary([Command("Scan", "wifi scan", "Wi-Fi"), Command("V", "version")])
    lib.save(p)
    again = CommandLibrary.load(p)
    assert again.commands == lib.commands
    assert again.groups() == ["Wi-Fi", "General"]


def test_corrupt_file_gives_defaults_and_is_kept(tmp_path):
    p = tmp_path / "commands.json"
    p.write_text("{broken", encoding="utf-8")
    lib = CommandLibrary.load(p)
    assert lib.groups() == ["Examples"]
    assert (tmp_path / "commands.json.bad").read_text(encoding="utf-8") == "{broken"


def test_missing_file_gives_defaults(tmp_path):
    assert CommandLibrary.load(tmp_path / "none.json").groups() == ["Examples"]


def test_import_merges_and_skips_duplicates(tmp_path):
    lib = CommandLibrary([Command("V", "version")])
    f = tmp_path / "share.json"
    f.write_text(json.dumps({"version": 1, "commands": [
        {"name": "V", "text": "version", "group": "General"},
        {"name": "Scan", "text": "wifi scan", "group": "Wi-Fi"}]}), encoding="utf-8")
    assert lib.import_file(f) == 1
    assert [c.name for c in lib.commands] == ["V", "Scan"]


@pytest.mark.parametrize("content", ["[1,2]", '{"commands": "x"}',
                                     '{"commands": [{"name": 1, "text": "a"}]}',
                                     '{"commands": [{"name": "a", "text": ""}]}', "nope"])
def test_import_rejects_malformed(tmp_path, content):
    f = tmp_path / "bad.json"
    f.write_text(content, encoding="utf-8")
    lib = CommandLibrary([])
    with pytest.raises(ValueError):
        lib.import_file(f)
    assert lib.commands == []


def test_export(tmp_path):
    lib = CommandLibrary([Command("a", "b", "G")])
    f = tmp_path / "out.json"
    lib.export_file(f)
    assert json.loads(f.read_text(encoding="utf-8"))["commands"] == [
        {"name": "a", "text": "b", "group": "G"}]


def test_history_navigation(tmp_path):
    h = History(max_items=3)
    for t in ["a", "b", "b", "c", "d"]:
        h.add(t)
    assert h.items == ["b", "c", "d"]
    assert h.previous() == "d"
    assert h.previous() == "c"
    assert h.previous() == "b"
    assert h.previous() == "b"          # stays at the oldest
    assert h.next() == "c"
    assert h.next() == "d"
    assert h.next() == ""               # past the newest: empty input
    h.add("")                           # empty is ignored
    assert h.items == ["b", "c", "d"]
    p = tmp_path / "h.json"
    h.save(p)
    assert History.load(p, max_items=3).items == ["b", "c", "d"]
    p.write_text('{"x": 1}', encoding="utf-8")
    assert History.load(p).items == []
