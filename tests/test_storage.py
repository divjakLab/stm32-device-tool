from devicetool.core.storage import Settings, load_json, save_json


def test_json_round_trip(tmp_path):
    p = tmp_path / "a" / "b.json"
    save_json(p, {"x": [1, "č"]})
    assert load_json(p, None) == {"x": [1, "č"]}
    assert not (tmp_path / "a" / "b.json.tmp").exists()


def test_load_json_missing_or_corrupt_returns_default(tmp_path):
    assert load_json(tmp_path / "nope.json", 42) == 42
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_json(bad, 42) == 42


def test_settings_persist(tmp_path):
    p = tmp_path / "settings.json"
    s = Settings(p)
    s.set("baud", 921600)
    assert Settings(p).get("baud") == 921600


def test_settings_corrupt_or_wrong_type_starts_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert Settings(p).data == {}
    p.write_text("garbage", encoding="utf-8")
    assert Settings(p).get("x", "d") == "d"
