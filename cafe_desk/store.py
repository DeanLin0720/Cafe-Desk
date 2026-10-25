"""商店：用營業額買咖啡機升級（一次性）與精品咖啡豆（消耗品，品項在 beans.PREMIUM）

錢包餘額＝累積營業額 − 已經花掉的錢；店鋪等級照樣看累積營業額，花錢不會掉級。
每筆購買都記在紀錄資料庫的 events（kind "purchase"，有簽章），所以改設定檔加不了錢、刪不掉購買紀錄。
"""
from dataclasses import replace

# key：(對象, 名稱, 說明, 價格, 改變的特性)
# 對象是咖啡機 key 的 tuple（一次升級可以影響好幾台），或 STATION（沖煮台的手沖用磨豆機）。
# 改變的特性：機器 Traits 的欄位＝新的值；channel_delta＝通道效應加減；
# fines＝沖煮台萃取不均的倍率（brew.FINES_K）；clarity＝沖煮台的甜感加成（brew.CLARITY）
STATION = ("station",)
EXTERNAL = ("desk01", "lever", "compact")           # 用獨立磨豆機的咖啡機
UPGRADES = {
    "desk01_frother": (("desk01",), "專業奶泡機", "換成專業奶泡機：奶泡更細，拉花更容易成功", 18000, {"frother_q": 0.72}),
    "lever_collar": (("lever",), "沖煮頭恆溫套環", "沖煮頭水溫更穩：每杯飄動從 ±0.5°C 降到 ±0.2°C", 12000, {"temp_noise": 0.2}),
    "compact_pid": (("compact",), "PID 溫控套件", "單鍋爐加裝 PID：每杯水溫飄動從 ±1.4°C 降到 ±0.4°C", 25000, {"temp_noise": 0.4}),
    "allinone_burr": (("allinone",), "精密刀盤", "內建磨豆機換成精密刀盤：研磨均勻，通道效應跟獨立磨豆機一樣", 20000,
                      {"channel_add": 0.0}),
    "grinder_flat": (EXTERNAL, "平刀盤", "獨立磨豆機換成平刀盤：研磨更均勻、通道效應更少，三台用獨立磨豆機的咖啡機都受惠", 15000,
                     {"channel_delta": -0.04}),
    # 營業用雙頭機（店鋪 Lv.9 解鎖）：四項可以一起買，效果疊加
    "duo_burr": (("duo",), "營業級平刀盤", "雙頭機內建磨豆機換成大平刀盤：研磨更均勻，通道效應更少", 30000,
                 {"channel_delta": -0.04}),
    "duo_steam": (("duo",), "自動打奶蒸氣管", "雙頭機蒸氣管換成大孔徑自動款：蒸氣更強（1.5 → 1.9），打奶更快、奶泡更細", 35000,
                  {"steam_power": 1.9}),
    "duo_preinfuse": (("duo",), "壓力曲線（預浸）", "萃取前先低壓預浸，粉餅吸飽水再加壓：甜感更好，通道效應再少一點", 40000,
                      {"sweet_add": 0.3, "channel_delta": -0.02}),
    "duo_boiler": (("duo",), "雙鍋爐快速回溫", "加大加熱器：鍋爐回溫更快，兩杯一起萃取時水溫幾乎不掉", 25000,
                   {"boiler_heat": 1.0, "boiler_draw": 0.05}),
    "station_ghost": (STATION, "鬼齒刀盤", "手沖用磨豆機換成鬼齒刀盤：細粉更少，手沖、冰滴、摩卡壺、虹吸壺喝起來更乾淨、更甜，研磨偏細也比較不會萃取不均", 12000,
                      {"fines": 0.6, "clarity": 0.8}),
}
# 商店卡片的圖示（render/icons.py 的 upgrade_icon）
UPGRADE_ICONS = {"desk01_frother": "frother", "lever_collar": "collar", "compact_pid": "pid", "allinone_burr": "conical",
                 "duo_burr": "flat", "duo_steam": "steam", "duo_preinfuse": "preinfuse", "duo_boiler": "boiler",
                 "grinder_flat": "flat", "station_ghost": "ghost"}
TARGET_NAMES = {EXTERNAL: "獨立磨豆機", STATION: "手沖用磨豆機"}


def balance(stats):
    """錢包餘額"""
    return stats.data["revenue_total"] - stats.data["spent"]


def apply_upgrades(owned):
    """依已購買的升級重設每台咖啡機的特性與沖煮台的磨豆機（MACHINES 是共用的實例，一律從類別的原始特性重算）"""
    from . import brew
    from .machines import MACHINES
    for key, m in MACHINES.items():
        base = type(m).traits
        mods = {}
        for up, (targets, *_rest, change) in UPGRADES.items():
            if key in targets and up in owned:
                for field, value in change.items():
                    if field == "channel_delta":
                        mods["channel_add"] = mods.get("channel_add", base.channel_add) + value
                    else:
                        mods[field] = value
        m.traits = replace(base, **mods)
    brew.FINES_K, brew.CLARITY = 1.0, 0.0
    for up, (targets, *_rest, change) in UPGRADES.items():
        if targets == STATION and up in owned:
            brew.FINES_K *= change.get("fines", 1.0)
            brew.CLARITY += change.get("clarity", 0.0)


def upgraded(machine_key, owned):
    return bool(upgrade_names(machine_key, owned))


def upgrade_names(machine_key, owned):
    """這台咖啡機身上已經有的升級名稱（含共用的獨立磨豆機）"""
    return [name for k, (targets, name, *_r) in UPGRADES.items() if machine_key in targets and k in owned]


def target_name(key):
    """升級的對象顯示名稱（中文原文；顯示時再 T()）"""
    from .machines import MACHINES
    targets = UPGRADES[key][0]
    return TARGET_NAMES.get(targets) or MACHINES[targets[0]].name
