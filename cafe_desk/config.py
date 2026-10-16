"""設定檔 cafe_desk.json：讀取、版本遷移、寫入

設定檔有 "schema" 欄位記錄格式版本。讀進來之後一律先經過 migrate()，把舊格式逐版升到 SCHEMA，
其他程式只需要處理最新格式。之後要改欄位時：SCHEMA 加一，在 _MIGRATIONS 加一個函式。
    schema 0：1.0.0 Beta 以前（含 Espresso Desk 時期）沒有版本號的設定檔
    schema 1：1.0.0
比目前程式還新的設定檔（用舊版程式開新版設定）不降級，未知欄位照原樣保留。
"""
import json
import os

from . import errlog, paths

SCHEMA = 1


def _v0_to_v1(cfg):
    cfg.pop("cups", None)                   # 溫杯架的杯子（v3.5 已移除）
    return cfg


_MIGRATIONS = {0: _v0_to_v1}               # 從 schema n 升到 n+1


def migrate(cfg):
    v = cfg.get("schema", 0)
    if not isinstance(v, int) or v < 0:
        v = 0
    while v < SCHEMA:
        cfg = _MIGRATIONS[v](cfg)
        v += 1
    cfg["schema"] = v                       # 比 SCHEMA 新的維持原值
    return cfg


def _read(path):
    with open(path, encoding="utf-8-sig") as f:         # 記事本等工具存檔可能加上 BOM
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError("設定檔不是 JSON 物件")
    return cfg


def load():
    """讀設定檔並升級到最新格式。新設定檔不存在時沿用舊版（Espresso Desk）的設定；
    設定檔壞掉時改名成 .bad 保留下來（不要被預設值蓋掉），從預設值開始"""
    path = paths.CONFIG_PATH
    if os.path.exists(path):
        try:
            return migrate(_read(path))
        except Exception as e:
            errlog.write(f"設定檔讀取失敗，改用預設值：{path}：{e!r}")
            try:
                os.replace(path, path + ".bad")
            except OSError:
                pass
            return migrate({})
    for old in paths.OLD_CONFIG_PATHS:      # 第一次使用新版：沿用舊版的設定（只讀不寫）
        try:
            return migrate(_read(old))
        except Exception:
            pass
    return migrate({})


def save(cfg):
    """先寫暫存檔再取代，寫到一半當掉也不會留下半個設定檔"""
    path = paths.CONFIG_PATH
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        errlog.write(f"設定檔寫入失敗：{path}：{e!r}")
