from pathlib import Path

from devicetool import config


def test_pack_is_found():
    pack = config.find_pack_file()
    assert pack is not None and pack.name.endswith(".pack")


def test_user_dirs_on_macos(monkeypatch):
    monkeypatch.setattr(config.sys, "platform", "darwin")
    assert config.support_dir().parts[-2:] == ("Application Support", "STM32 Device Tool")
    assert config.logs_dir().parts[-2:] == ("Logs", "STM32 Device Tool")


def test_user_dirs_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert config.support_dir() == tmp_path / "Roaming" / "STM32 Device Tool"
    assert config.logs_dir() == tmp_path / "Local" / "STM32 Device Tool" / "Logs"


def test_user_dirs_on_windows_without_env(monkeypatch):
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert config.support_dir() == Path.home() / "AppData" / "Roaming" / "STM32 Device Tool"
    assert config.logs_dir() == Path.home() / "AppData" / "Local" / "STM32 Device Tool" / "Logs"
