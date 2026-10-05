import os

from app import config_files


def test_load_yaml_rereads_when_mtime_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(config_files, "CONFIG_DIR", tmp_path)
    f = tmp_path / "x.yaml"
    f.write_text("a: 1\n")
    assert config_files.load_yaml("x.yaml") == {"a": 1}
    f.write_text("a: 2\n")
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    assert config_files.load_yaml("x.yaml") == {"a": 2}


def test_load_yaml_missing_file_is_empty_and_warns(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config_files, "CONFIG_DIR", tmp_path)
    assert config_files.load_yaml("nope.yaml") == {}
    assert "nope.yaml" in caplog.text
