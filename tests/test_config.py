"""設定檔：版本遷移、舊版沿用、壞檔處理、寫入"""
import json
import os

from cafe_desk import config, paths


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


def test_missing_config_gives_current_schema(cfg_path):
    assert config.load() == {"schema": config.SCHEMA}


def test_v0_is_migrated(cfg_path):
    _write(cfg_path, {"x": 5, "cups": [1, 2], "drink": "latte"})
    cfg = config.load()
    assert cfg["schema"] == config.SCHEMA
    assert "cups" not in cfg
    assert cfg["x"] == 5 and cfg["drink"] == "latte"


def test_newer_schema_is_not_downgraded(cfg_path):
    _write(cfg_path, {"schema": 99, "future": True})
    cfg = config.load()
    assert cfg["schema"] == 99 and cfg["future"]


def test_old_espresso_desk_config_is_used(cfg_path):
    _write(paths.OLD_CONFIG_PATHS[0], {"drink": "mocha", "cups": []})
    cfg = config.load()
    assert cfg["drink"] == "mocha" and "cups" not in cfg
    assert not os.path.exists(cfg_path), "讀舊檔不應該自動寫新檔"


def test_broken_config_is_kept_aside(cfg_path):
    _write(cfg_path, "{ not json")
    assert config.load() == {"schema": config.SCHEMA}
    assert os.path.exists(cfg_path + ".bad")
    _write(cfg_path, "[1, 2]")
    assert config.load() == {"schema": config.SCHEMA}


def test_save_roundtrip(cfg_path):
    config.save({"schema": 1, "lang": "en", "名稱": "中文"})
    assert config.load()["名稱"] == "中文"
    assert not os.path.exists(cfg_path + ".tmp")


def test_desk_saves_schema(desk, cfg_path):
    desk.save_config()
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["schema"] == config.SCHEMA
    assert cfg["machine"] == desk.machine.key
