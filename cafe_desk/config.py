"""設定檔 cafe_desk.json：讀取、版本遷移、寫入

設定檔有 "schema" 欄位記錄格式版本。讀進來之後一律先經過 migrate()，把舊格式逐版升到 SCHEMA，
其他程式只需要處理最新格式。之後要改欄位時：SCHEMA 加一，在 _MIGRATIONS 加一個函式。
    schema 0：1.0.0 Beta 以前（含 Espresso Desk 時期）沒有版本號的設定檔
    schema 1：1.0.0
    schema 2：拿掉「手動沖煮使用完整流程」選項（full_flow），沖煮一律跑完整流程
    schema 3：清潔保養計數改成每台咖啡機各自計算：maintenance 從 {項目: 數值} 變成 {咖啡機: {項目: 數值}}
比目前程式還新的設定檔（用舊版程式開新版設定）不降級，未知欄位照原樣保留。
"""
import json
import time
import os

from . import errlog, paths

SCHEMA = 3


def _v0_to_v1(cfg):
    cfg.pop("cups", None)                   # 溫杯架的杯子（v3.5 已移除）
    return cfg


def _v1_to_v2(cfg):
    cfg.pop("full_flow", None)              # 完整流程不再是選項
    return cfg


def _v2_to_v3(cfg):
    m = cfg.get("maintenance")
    if isinstance(m, dict) and m and not all(isinstance(v, dict) for v in m.values()):
        cfg["maintenance"] = {cfg.get("machine") or "desk01": m}     # 舊的共用計數算給當時用的那台
    return cfg


_MIGRATIONS = {0: _v0_to_v1, 1: _v1_to_v2, 2: _v2_to_v3}  # 從 schema n 升到 n+1


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

_last_fail = -1e9                           # 上次記下「設定檔寫入失敗」的時間（time.monotonic）


def save(cfg):
    """先寫暫存檔再取代，寫到一半當掉也不會留下半個設定檔"""
    path = paths.CONFIG_PATH
    tmp = path + ".tmp"
    text = json.dumps(cfg, ensure_ascii=False, indent=1)
    err = None
    for attempt in range(3):                # Windows：檔案剛好被防毒、同步軟體或別的程式開著時 replace 會被拒，等一下再試
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
            return
        except Exception as e:
            err = e
            time.sleep(0.03 * (attempt + 1))
    try:                                    # 還是不行：直接寫（不如放棄存檔）
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return
    except Exception as e:
        err = e
    global _last_fail
    now = time.monotonic()
    if now - _last_fail > 60.0:             # 失敗的訊息一分鐘最多一則（不要洗版）
        _last_fail = now
        errlog.write(f"設定檔寫入失敗：{path}：{err!r}")
