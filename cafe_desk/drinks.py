"""飲品：定義、牛奶與拉花模型、評分、分階段流程

一杯飲品由多個階段組成，例如熱拿鐵＝（備粉）→ 萃取 →（單鍋爐加熱）→ 打奶 → 倒奶拉花。
這裡只算時間軸、位置與事件，不碰繪圖；位置都是場景座標。
"""
import math
import random
from dataclasses import dataclass, asdict

from .i18n import T
from .util import clamp, lerp
from .workflow import Workflow, ease, arc_move

# base：流程與畫面家族（espresso／americano／iced：冰飲／milk：熱牛奶飲品）
# shot：這杯濃縮的預設（ratio＝液重/粉量、grind＝研磨微調 µm、dose/basket＝指定粉量與粉碗、style＝評分基準）
DRINKS = {
    "espresso": {"name": "濃縮", "cup": "espresso", "hot": True, "base": "espresso"},
    "ristretto": {"name": "Ristretto", "cup": "espresso", "hot": True, "base": "espresso",
                  "shot": {"ratio": 1.3, "grind": -10, "style": "ristretto"}},
    "lungo": {"name": "Lungo", "cup": "espresso", "hot": True, "base": "espresso",
              "shot": {"ratio": 3.0, "grind": 15, "style": "lungo"}},
    "doppio": {"name": "雙份濃縮", "cup": "espresso", "hot": True, "base": "espresso",
               "shot": {"dose": 21.0, "basket": 22.0, "ratio": 2.0, "grind": 12}},
    "americano": {"name": "美式", "cup": "americano", "hot": True, "base": "americano"},
    "iced_americano": {"name": "冰美式", "cup": "iced", "hot": False, "base": "iced"},
    "latte": {"name": "熱拿鐵", "cup": "latte", "hot": True, "base": "milk"},
    "cappuccino": {"name": "卡布奇諾", "cup": "cappuccino", "hot": True, "base": "milk"},
    "flat_white": {"name": "馥列白", "cup": "flat_white", "hot": True, "base": "milk",
                   "shot": {"ratio": 1.5, "style": "ristretto"}},
    "cortado": {"name": "可塔朵", "cup": "cortado", "hot": True, "base": "milk"},
    "macchiato": {"name": "瑪奇朵", "cup": "espresso", "hot": True, "base": "milk"},
    "iced_latte": {"name": "冰拿鐵", "cup": "iced", "hot": False, "base": "iced"},
    "mocha": {"name": "摩卡", "cup": "latte", "hot": True, "base": "milk",
              "syrup": "choc", "syrup_g": "choc_g", "whip": "opt", "dust": "cocoa"},
    "caramel_macchiato": {"name": "焦糖瑪奇朵", "cup": "latte", "hot": True, "base": "milk"},
    "espresso_tonic": {"name": "濃縮通寧", "cup": "iced", "hot": False, "base": "iced"},
    "affogato": {"name": "阿芙佳朵", "cup": "affogato", "hot": True, "base": "affogato"},
    # 季節限定（只在節日期間出現，見 festivals.py）
    "pumpkin_latte": {"name": "南瓜香料拿鐵", "cup": "latte", "hot": True, "base": "milk", "festival": "halloween",
                      "syrup": "pumpkin", "syrup_g": 18.0, "whip": True, "dust": "cinnamon"},
    "gingerbread_latte": {"name": "薑餅拿鐵", "cup": "latte", "hot": True, "base": "milk", "festival": "christmas",
                          "syrup": "ginger", "syrup_g": 16.0, "whip": True, "dust": "cinnamon"},
    "rose_latte": {"name": "玫瑰拿鐵", "cup": "latte", "hot": True, "base": "milk", "festival": "valentine",
                   "syrup": "rose", "syrup_g": 14.0},
}
FESTIVAL_DRINKS = tuple(k for k, v in DRINKS.items() if v.get("festival"))
# 選單分組（None＝分隔線）
DRINK_ORDER = ("espresso", "ristretto", "lungo", "doppio", None, "americano", "iced_americano", "espresso_tonic",
               None, "latte", "cappuccino", "flat_white", "cortado", "macchiato", "mocha", "caramel_macchiato",
               "iced_latte", None, "affogato")
DRINK_KEYS = tuple(k for k in DRINK_ORDER if k)
AUTO_WEIGHTS = {"espresso": 0.12, "ristretto": 0.04, "lungo": 0.04, "doppio": 0.05, "americano": 0.12,
                "iced_americano": 0.1, "latte": 0.17, "cappuccino": 0.11, "flat_white": 0.08,
                "cortado": 0.05, "macchiato": 0.04, "iced_latte": 0.1, "mocha": 0.08, "caramel_macchiato": 0.08,
                "espresso_tonic": 0.06, "affogato": 0.06}

ART_NAMES = {"heart": "愛心", "tulip": "鬱金香", "rosetta": "葉子", "blob": "白點（沒拉成）", "dot": "奶泡點",
             "mark": "焦糖格紋", "whip": "鮮奶油"}
ART_CHOICES = (("auto", "自動（看奶泡狀況）"), ("heart", "愛心"), ("tulip", "鬱金香"), ("rosetta", "葉子"))
ART_NEED = {"heart": 0.42, "tulip": 0.58, "rosetta": 0.72}      # 指定圖案需要的奶泡細緻度
ART_BONUS = {"heart": 0, "tulip": 4, "rosetta": 8}              # 指定較難的圖案拉成功的加分
# 牛奶種類：texture＝奶泡細緻度倍率、foam＝奶泡穩定度（倒出後剩多少）、color＝顏色、prefix＝點單品名前綴
MILK_KINDS = {
    "dairy": {"name": "牛奶", "texture": 1.0, "foam": 1.0, "color": "#f4eee4", "prefix": ""},
    "oat": {"name": "燕麥奶", "texture": 0.95, "foam": 0.94, "color": "#efe3cc", "prefix": "燕麥"},
    "soy": {"name": "豆奶", "texture": 0.88, "foam": 0.88, "color": "#f3ead2", "prefix": "豆奶"},
    "almond": {"name": "杏仁奶", "texture": 0.76, "foam": 0.7, "color": "#ebe2d5", "prefix": "杏仁"},
}
MILK_NAMES = {k: v["name"] for k, v in MILK_KINDS.items()}
SYRUPS = {
    "choc": {"name": "巧克力醬", "color": "#3a1a0c", "label": "CHOCO"},
    "vanilla": {"name": "香草糖漿", "color": "#e2b878", "label": "VANILLA"},
    "pumpkin": {"name": "南瓜香料醬", "color": "#d9822b", "label": "PUMPKIN"},
    "ginger": {"name": "薑餅糖漿", "color": "#8a4a20", "label": "GINGER"},
    "rose": {"name": "玫瑰糖漿", "color": "#d0607a", "label": "ROSE"},
}
# 撒在杯面上的粉：(顏色, 畫成小花)
DUSTS = {"cocoa": ("#5a321a", False), "cinnamon": ("#8a4a22", False)}


def whip_on(drink, dp):
    """這杯有沒有擠鮮奶油"""
    w = DRINKS.get(drink, {}).get("whip")
    return w is True or (w == "opt" and dp.whip)
ICE_VOL = 15.0             # 每顆冰塊佔的體積（g）
FOAM_EXPANSION = 1.0       # 奶泡量 100% 時體積變兩倍


def base_of(drink):
    return DRINKS[drink]["base"] if drink in DRINKS else "espresso"


def is_milk(drink):
    return base_of(drink) == "milk"


@dataclass
class DrinkParams:
    milk_g: float = 150.0          # 熱拿鐵牛奶量
    milk_temp: float = 60.0        # 打奶溫度（所有熱牛奶飲品共用）
    foam: float = 30.0             # 熱拿鐵奶泡量（體積增加 %）
    water_g: float = 120.0         # 美式熱水量
    ice: float = 5.0               # 冰塊數（冰拿鐵、冰美式）
    iced_milk_g: float = 150.0     # 冰拿鐵牛奶量
    iced_water_g: float = 140.0    # 冰美式冷水量
    capp_milk_g: float = 100.0     # 卡布奇諾牛奶量
    capp_foam: float = 70.0        # 卡布奇諾奶泡量
    cocoa: bool = True             # 卡布奇諾撒可可粉
    flat_milk_g: float = 110.0     # 馥列白牛奶量
    flat_foam: float = 12.0        # 馥列白奶泡量（薄）
    cortado_milk_g: float = 40.0   # 可塔朵牛奶量（約與濃縮 1:1）
    mac_milk_g: float = 16.0       # 瑪奇朵的一匙奶泡
    mocha_milk_g: float = 140.0    # 摩卡牛奶量
    choc_g: float = 20.0           # 摩卡巧克力醬
    whip: bool = True              # 摩卡擠鮮奶油（＋可可粉）
    cm_milk_g: float = 150.0       # 焦糖瑪奇朵牛奶量
    vanilla_g: float = 12.0        # 焦糖瑪奇朵香草糖漿
    tonic_g: float = 150.0         # 濃縮通寧的通寧水
    scoop_g: float = 70.0          # 阿芙佳朵的冰淇淋
    art: str = "auto"              # 指定拉花圖案：auto／heart／tulip／rosetta
    milk_kind: str = "dairy"       # 牛奶種類：dairy／oat／soy／almond

    def copy(self):
        return DrinkParams(**asdict(self))


# 熱牛奶飲品：(牛奶量欄位, 奶泡量欄位或固定值, 理想奶泡量, 容許範圍)
MILK_SPEC = {
    "latte": ("milk_g", "foam", 30, 35),
    "cappuccino": ("capp_milk_g", "capp_foam", 70, 24),
    "flat_white": ("flat_milk_g", "flat_foam", 12, 14),
    "cortado": ("cortado_milk_g", 15.0, 15, 22),
    "macchiato": ("mac_milk_g", 100.0, 100, 50),
    "mocha": ("mocha_milk_g", "foam", 30, 35),
    "caramel_macchiato": ("cm_milk_g", 35.0, 35, 30),
}
for _k in FESTIVAL_DRINKS:
    MILK_SPEC[_k] = ("milk_g", "foam", 30, 35)


def milk_plan(drink, dp):
    """(牛奶量 g, 奶泡量 %, 理想奶泡量, 容許範圍)"""
    g_attr, foam, target, tol = MILK_SPEC.get(drink, MILK_SPEC["latte"])
    foam = getattr(dp, foam) if isinstance(foam, str) else foam
    return getattr(dp, g_attr), foam, target, tol


def shot_params(drink, params):
    """依飲品的濃縮預設改這一杯的沖煮參數（回傳新物件，style）"""
    p = params.copy()
    sp = DRINKS[drink].get("shot")
    if not sp:
        return p, None, False
    if "basket" in sp:
        p.basket = sp["basket"]
    if "dose" in sp:
        p.dose = sp["dose"]
    p.grind_um = clamp(p.grind_um + sp.get("grind", 0), 150, 500)
    p.yield_g = round(p.dose * sp["ratio"])
    return p, sp.get("style"), True


@dataclass
class MilkResult:
    temp: float
    foam: float
    texture: float                 # 0–1：奶泡細緻度（決定拉花品質）
    art: str
    art_q: float
    score: float
    comment: str
    wanted: str = "auto"           # 指定的圖案
    art_note: str = ""             # 指定圖案沒拉好的說明
    milk_score: float = 0.0        # 只看牛奶（溫度、奶泡量）的分數


@dataclass
class DrinkResult:
    drink: str
    score: float
    comment: str
    milk: MilkResult = None
    title: str = ""                # 點單模式：訂單上的品名（例如燕麥拿鐵）


def steam_time(dp, traits, device, drink="latte"):
    """打奶所需時間（秒）"""
    grams = milk_plan(drink, dp)[0]
    amount = max(0.25, grams / 150.0)
    if device == "frother":
        return 30.0 * amount + 4.0
    heat = max(0.2, (dp.milk_temp - 5) / 55.0)
    return 22.0 * amount * heat / max(0.3, traits.steam_power) + 3.0


def evaluate_milk(dp, traits, device, rnd=random, drink="latte"):
    """依打奶溫度、奶泡量、設備、指定圖案，算出奶泡細緻度與拉花結果"""
    _, foam, target, tol = milk_plan(drink, dp)
    t = dp.milk_temp
    tf = 1 - clamp(abs(t - 60) / 16, 0, 1) ** 1.4
    if t > 68:
        tf -= (t - 68) * 0.05                      # 燙到：甜感流失、奶泡變粗
    ff = 1 - clamp(abs(foam - target) / tol, 0, 1)
    if device == "frother":
        base = 0.62
    else:
        base = clamp(0.72 + 0.14 * (traits.steam_power - 1), 0.5, 0.95)
    base *= MILK_KINDS.get(dp.milk_kind, MILK_KINDS["dairy"])["texture"]    # 植物奶較難打出細緻奶泡
    texture = clamp(base * (0.55 + 0.45 * ff) * (0.62 + 0.38 * clamp(tf, 0, 1)) * 1.12
                    + rnd.gauss(0, 0.06), 0, 1)
    # 卡布奇諾奶泡厚，拉花難度較高；馥列白奶泡薄，最好拉葉子
    eff = texture - {"cappuccino": 0.1, "cortado": 0.05}.get(drink, 0.0)
    wanted = dp.art if dp.art in ART_NEED else "auto"
    note = ""
    if drink in ("macchiato", "caramel_macchiato") or whip_on(drink, dp):
        # 瑪奇朵：奶泡點；焦糖瑪奇朵：奶泡上濃縮的印子＋焦糖格紋；摩卡加鮮奶油：看不到拉花
        art = {"macchiato": "dot", "caramel_macchiato": "mark"}.get(drink, "whip")
        wanted = "auto"
        art_q = clamp(texture + rnd.gauss(0, 0.07), 0.05, 1)
    elif wanted == "auto" and drink == "rose_latte" and eff >= 0.42:
        art = "heart"                              # 玫瑰拿鐵：情人節一律拉愛心
        art_q = clamp(eff + rnd.gauss(0, 0.07), 0.05, 1)
    elif wanted == "auto":
        if eff < 0.42:
            art = "blob"
        elif eff < 0.58:
            art = "heart"
        elif eff < 0.76:
            art = rnd.choice(("heart", "tulip", "rosetta") if drink == "flat_white" else ("heart", "tulip"))
        else:
            art = rnd.choice(("rosetta", "rosetta", "tulip") if drink == "flat_white"
                             else ("heart", "tulip", "rosetta", "rosetta"))
        art_q = clamp(eff + rnd.gauss(0, 0.07), 0.05, 1)
    else:
        need = ART_NEED[wanted]
        name = T(ART_NAMES[wanted])
        if eff >= need:
            art = wanted
            art_q = clamp(eff + rnd.gauss(0, 0.06), 0.05, 1)
        elif eff >= need - 0.14:                   # 差一點：圖案出來了但糊糊的
            art = wanted
            art_q = clamp(eff - 0.3 + rnd.gauss(0, 0.04), 0.05, 0.4)
            note = T("{name}有點糊", name=name)
        else:                                      # 差太多：變成一坨白點
            art = "blob"
            art_q = clamp(eff + rnd.gauss(0, 0.05), 0.05, 1)
            note = T("想拉{name}，奶泡不夠細", name=name)
    milk_score = 100 * clamp(0.5 * clamp(tf, 0, 1) + 0.5 * ff, 0, 1)
    if art == "blob":
        art_score = 35
    else:
        art_score = 45 + 55 * art_q
        if wanted != "auto" and not note:
            art_score = min(100, art_score + ART_BONUS[wanted])
    if t > 70:
        c = T("奶溫過高，甜感流失")
    elif t < 50:
        c = T("奶溫偏低")
    elif foam > target + tol * 0.8:
        c = T("奶泡太厚")
    elif foam < target - tol * 0.6:
        c = T("奶泡太薄")
    elif texture > 0.78:
        c = T("奶泡細緻如絲")
    elif texture > 0.55:
        c = T("奶泡尚可")
    else:
        c = T("奶泡偏粗")
    if art in ("dot", "mark", "whip"):
        art_score = 50 + 50 * art_q                # 沒有拉花：只看奶泡是否細緻
    if dp.milk_kind == "almond" and texture < 0.55:
        c = T("杏仁奶奶泡很快就消了")
    return MilkResult(t, foam, texture, art, art_q, 0.6 * milk_score + 0.4 * art_score, c, wanted, note, milk_score)


def band_score(x, lo, hi, slope):
    if x < lo:
        return max(0.0, 100 - (lo - x) * slope)
    if x > hi:
        return max(0.0, 100 - (x - hi) * slope)
    return 100.0


def score_drink(drink, shot, dp, milk=None, comment_fn=None):
    """飲品總分：濃縮為主，再依飲品加上比例、牛奶、拉花"""
    base = shot.res.score
    shot_c = comment_fn(shot.res, shot.p, shot.style) if comment_fn else ""
    family = base_of(drink)
    if family == "espresso":
        return DrinkResult(drink, base, shot_c)
    if drink == "americano":
        ratio = dp.water_g / max(1.0, shot.weight)
        rs = band_score(ratio, 2.5, 4.5, 30)
        c = T("比例剛好" if rs > 90 else ("偏淡" if ratio > 4.5 else "偏濃"))
        return DrinkResult(drink, 0.75 * base + 0.25 * rs, f"{c} · {shot_c}")
    if drink == "iced_americano":
        ratio = dp.iced_water_g / max(1.0, shot.weight)
        rs = band_score(ratio, 3.0, 5.0, 25)
        c = T("比例剛好" if rs > 90 else ("偏淡" if ratio > 5 else "偏濃"))
        return DrinkResult(drink, 0.7 * base + 0.3 * rs, f"{c} · {shot_c}")
    if drink == "espresso_tonic":
        ratio = dp.tonic_g / max(1.0, shot.weight)
        rs = band_score(ratio, 3.0, 5.0, 25)
        c = T("分層漂亮、比例剛好" if rs > 90 else ("通寧水偏多" if ratio > 5 else "咖啡偏濃"))
        return DrinkResult(drink, 0.7 * base + 0.3 * rs, f"{c} · {shot_c}")
    if drink == "affogato":
        ratio = dp.scoop_g / max(1.0, shot.weight)
        rs = band_score(ratio, 1.4, 2.6, 50)
        c = T("冰淇淋與濃縮剛好" if rs > 90 else ("冰淇淋太多" if ratio > 2.6 else "濃縮蓋過冰淇淋"))
        return DrinkResult(drink, 0.8 * base + 0.2 * rs, f"{c} · {shot_c}")
    if drink == "iced_latte":
        ratio = dp.iced_milk_g / max(1.0, shot.weight)
        rs = band_score(ratio, 3.0, 5.0, 25)
        c = T("奶咖比例剛好" if rs > 90 else ("奶味偏重" if ratio > 5 else "咖啡偏濃"))
        return DrinkResult(drink, 0.7 * base + 0.3 * rs, f"{c} · {shot_c}")
    # 熱牛奶飲品
    art = T(ART_NAMES[milk.art].split("（")[0])
    art_c = milk.art_note or (T("拉花：{art}", art=art) if milk.art != "blob" else T("拉花沒成形"))
    if drink == "macchiato":
        return DrinkResult(drink, 0.8 * base + 0.2 * milk.score, f"{milk.comment} · {shot_c}", milk)
    if drink == "caramel_macchiato":
        return DrinkResult(drink, 0.5 * base + 0.5 * milk.milk_score, T("焦糖格紋 · {comment}", comment=milk.comment), milk)
    if milk.art == "whip":
        return DrinkResult(drink, 0.5 * base + 0.5 * milk.milk_score, T("鮮奶油 · {comment}", comment=milk.comment), milk)
    if drink == "cortado":
        ratio = milk_plan(drink, dp)[0] / max(1.0, shot.weight)
        rs = band_score(ratio, 0.8, 1.4, 60)
        c = T("奶咖 1:1 剛好" if rs > 90 else ("奶味偏重" if ratio > 1.4 else "咖啡偏濃"))
        return DrinkResult(drink, 0.6 * base + 0.2 * milk.score + 0.2 * rs, f"{art_c} · {c}", milk)
    w = 0.55 if drink == "flat_white" else 0.5
    return DrinkResult(drink, w * base + (1 - w) * milk.score, f"{art_c} · {milk.comment}", milk)


# ═══════════════════════════ 階段 ═══════════════════════════

class Stage:
    name = ""
    done = False

    def start(self, s):
        pass

    def update(self, s, dt):
        pass

    def status(self, s):
        return ""


class PrepStage(Stage):
    """完整流程的備粉：取把手、敲渣、磨豆、布粉、填壓、扣回（沿用 Workflow）"""
    name = "prep"

    def start(self, s):
        s.app.workflow = Workflow(s.params.copy(), s.app.pf_used, s.app.machine)

    def update(self, s, dt):
        wf = s.app.workflow
        if wf is None or wf.done:
            s.app.workflow = None
            s.app.pf_used = False
            self.done = True

    def status(self, s):
        wf = s.app.workflow
        return wf.status() if wf else ""


class BrewStage(Stage):
    name = "brew"

    def start(self, s):
        s.app.start_brew(s.params, s.style, s.preset)

    def update(self, s, dt):
        sh = s.app.shot
        if sh is not None and sh.phase == "done":
            self.done = True

    def status(self, s):
        sh = s.app.shot
        return (sh.stage() or "") if sh else ""


class CoolStage(Stage):
    """單鍋爐：上一杯打過奶，鍋爐還在蒸氣溫度，先降溫到沖煮溫度"""
    name = "cool"

    def start(self, s):
        s.boiler_mode = "cool"
        self.puff = 0.0

    def update(self, s, dt):
        b = s.app.boiler
        b.temp -= 3.5 * dt
        self.puff -= dt
        if self.puff <= 0:
            self.puff = 0.9
            s.events.append("vent")
        if b.temp <= s.params.temp + 0.5:
            b.temp = min(b.temp, s.params.temp + 0.5)
            s.boiler_mode = "brew"
            self.done = True

    def status(self, s):
        return T("鍋爐降溫中…  {t:.0f}°C", t=s.app.boiler.temp)


class HeatStage(Stage):
    """單鍋爐：切換到蒸氣模式，鍋爐加熱到蒸氣溫度"""
    name = "heat"

    def start(self, s):
        s.boiler_mode = "steam"

    def update(self, s, dt):
        b, target = s.app.boiler, s.app.machine.traits.steam_temp
        b.temp = min(target, b.temp + 2.6 * dt)
        if b.temp >= target - 0.2:
            self.done = True

    def status(self, s):
        return T("切換蒸氣模式，加熱中…  {t:.0f}°C", t=s.app.boiler.temp)


class IceStage(Stage):
    """一顆顆丟冰塊：落下、撞擊杯底或其他冰塊後停住"""
    name = "ice"

    def start(self, s):
        cup = s.app.cup
        n = int(round(s.dp.ice))
        self.queue = []
        inner_l, inner_r = cup.cup_x(cup.B - 10)
        width = inner_r - inner_l
        per_row = 3
        for i in range(n):
            row, col = divmod(i, per_row)
            size = random.uniform(15, 18)
            x = inner_l + width * (col + 0.5) / per_row + random.uniform(-3, 3)
            rest = cup.B - 8 - size * 0.5 - row * (size * 0.82)
            self.queue.append({"x": x, "y": cup.T - 50 - random.uniform(0, 10), "vy": 0.0, "size": size,
                               "rot": random.uniform(-25, 25), "vr": random.uniform(-120, 120),
                               "rest": rest, "landed": False, "bob": random.uniform(0, 6.28)})
        self.clock = 0.0

    def update(self, s, dt):
        self.clock += dt
        while self.queue and self.clock >= 0.32:
            self.clock -= 0.32
            s.app.ice.append(self.queue.pop(0))
        if not self.queue and all(c["landed"] for c in s.app.ice):
            self.done = True

    def status(self, s):
        return T("加入冰塊…")


class PourStage(Stage):
    """容器入場 → 傾倒 → 回正 → 離場；art=True 時後段是拉花"""
    name = "pour"
    LABEL = {"water": "注入熱水…", "cold_water": "倒入冷水…", "cold_milk": "倒入冰牛奶…",
             "hot_milk": "注入牛奶融合…", "tonic": "倒入通寧水…", "choc": "擠入巧克力醬…",
             "vanilla": "加入香草糖漿…", "pumpkin": "加入南瓜香料醬…", "ginger": "加入薑餅糖漿…",
             "rose": "加入玫瑰糖漿…"}

    def __init__(self, vessel, liquid, grams, rate, start=None, home=None, art=False, foam_vol=0.0,
                 label=None, art_label="拉花中…"):
        self.vessel, self.liquid, self.grams, self.rate = vessel, liquid, grams, rate
        self.start_pos, self.home, self.art, self.foam_vol = start, home, art, foam_vol
        self.label, self.art_label = label, art_label

    def start(self, s):
        cup, m = s.app.cup, s.app.machine
        # 傾倒時容器嘴的位置：杯口右上方
        self.pour_pos = (m.mx + cup.TR - 6, m.my + cup.T - 34)
        enter = self.start_pos or (self.pour_pos[0] + 70, self.pour_pos[1] - 60)
        self.v = {"kind": self.vessel, "x": enter[0], "y": enter[1], "tilt": 0.0,
                  "alpha": 0.0 if self.start_pos is None else 1.0, "fill": 1.0, "liquid": self.liquid,
                  "pour": 0.0}
        self.enter_from = enter
        s.vessel = self.v
        self.phase, self.t, self.poured = "enter", 0.0, 0.0
        self.max_tilt = {"kettle": 38, "bottle": 62, "pitcher": 58, "jug": 60, "tonic": 64,
                         "squeeze": 150}.get(self.vessel, 55)
        self.pre = 1.0 if self.vessel == "squeeze" else 0.55      # 醬料瓶：直接倒過來擠

    def update(self, s, dt):
        self.t += dt
        v = self.v
        if self.phase == "enter":
            k = clamp(self.t / 0.8, 0, 1)
            v["x"], v["y"] = arc_move(self.enter_from, self.pour_pos, k, 14)
            v["alpha"] = max(v["alpha"], clamp(k * 2, 0, 1))
            if k >= 1:
                self.phase, self.t = "tilt", 0.0
        elif self.phase == "tilt":
            k = clamp(self.t / 0.45, 0, 1)
            v["tilt"] = self.max_tilt * self.pre * ease(k)
            if k >= 1:
                self.phase, self.t = "pour", 0.0
                s.events.append("pour_start")
        elif self.phase == "pour":
            room = s.app.cup.cap * 0.97 - s.app.cup_volume()
            step = min(self.rate * dt, self.grams - self.poured)
            if room <= 0.5:
                step = 0.0
            self.poured += step
            frac = clamp(self.poured / max(1.0, self.grams), 0, 1)
            s.add_liquid(self.liquid, step, self.foam_vol * step / max(1.0, self.grams))
            v["fill"] = 1 - frac
            v["pour"] = 1.0
            v["tilt"] = self.max_tilt * (self.pre + (1 - self.pre) * frac)
            if self.art:
                # 前段從高處注入融合，後段壓低靠近液面拉花
                s.art_progress = clamp((frac - 0.5) / 0.48, 0, 1)
                v["y"] = self.pour_pos[1] + (10 if frac > 0.5 else 0) * ease((frac - 0.45) / 0.1)
            if self.poured >= self.grams - 0.01 or room <= 0.5:
                self.phase, self.t = "untilt", 0.0
                v["pour"] = 0.0
                s.events.append("pour_stop")
                if self.art:
                    s.art_progress = 1.0
        elif self.phase == "untilt":
            k = clamp(self.t / 0.4, 0, 1)
            v["tilt"] = self.max_tilt * (1 - ease(k))
            if k >= 1:
                self.phase, self.t = "exit", 0.0
                self.exit_from = (v["x"], v["y"])
        elif self.phase == "exit":
            k = clamp(self.t / 0.7, 0, 1)
            target = self.home or (self.exit_from[0] + 70, self.exit_from[1] - 60)
            v["x"], v["y"] = arc_move(self.exit_from, target, k, 14)
            if self.home is None:
                v["alpha"] = 1 - k
            if k >= 1:
                s.vessel = None
                self.done = True

    def status(self, s):
        if self.art and s.art_progress > 0:
            return T(self.art_label)
        label = T(self.label or self.LABEL.get(self.liquid, ""))
        return T("{label}  {g:.0f} g", label=label, g=self.poured) if self.liquid != "hot_milk" else label


class SteamStage(Stage):
    """打奶：蒸氣管（拉花杯移到管口）或獨立奶泡機"""
    name = "steam"

    def start(self, s):
        m, app = s.app.machine, s.app
        self.device = m.traits.milk
        self.total = steam_time(s.dp, m.traits, self.device, s.drink)
        self.t = 0.0
        s.milk_temp = 6.0
        s.milk_foam = 0.0
        self.phase = "approach" if self.device == "wand" else "run"
        if self.device == "wand":
            tip = (m.mx + m.wand_steam[0], m.my + m.wand_steam[1])
            self.dock = (tip[0] - 16, tip[1] - 14)     # 拉花杯嘴位置：管口伸進杯中
            start = (self.dock[0] + 50, self.dock[1] + 40)
            s.vessel = {"kind": "pitcher", "x": start[0], "y": start[1], "tilt": 0.0, "alpha": 0.0,
                        "fill": 1.0, "liquid": "hot_milk", "pour": 0.0}
            self.from_pos = start
            app.wand_angle = 0.0
        else:
            s.frother_on = True
            s.events.append("frother_start")
        self.last_chirp = 0.0

    def update(self, s, dt):
        self.t += dt
        if self.device == "wand":
            v = s.vessel
            if self.phase == "approach":
                k = clamp(self.t / 0.8, 0, 1)
                v["x"], v["y"] = arc_move(self.from_pos, self.dock, k, 0)
                v["alpha"] = clamp(k * 2, 0, 1)
                s.app.wand_angle = ease(k)
                if k >= 1:
                    self.phase, self.t = "run", 0.0
                    s.events.append("steam_start")
                return
            if self.phase == "purge":
                if self.t > 0.7:
                    self.done = True
                return
        k = clamp(self.t / self.total, 0, 1)
        target = s.dp.milk_temp
        s.milk_temp = lerp(6.0, target, k ** 0.9)
        stretch = clamp(k / 0.38, 0, 1)                  # 前段打入空氣，後段整合
        s.milk_foam = milk_plan(s.drink, s.dp)[1] * stretch
        s.stretching = k < 0.38
        if self.device == "wand" and s.vessel:
            s.vessel["y"] = self.dock[1] + 3 * stretch + math.sin(self.t * 40) * 0.25
        if k >= 1:
            s.stretching = False
            if self.device == "wand":
                s.events.append("steam_stop")
                s.app.wand_angle = 0.0
                s.events.append("purge")
                self.phase, self.t = "purge", 0.0
            else:
                s.frother_on = False
                s.events.append("frother_stop")
                self.done = True

    def status(self, s):
        if self.device == "wand":
            if self.phase == "approach":
                return T("拉花杯移到蒸氣管…")
            return T("打奶泡…  {t:.0f}°C", t=s.milk_temp)
        return T("奶泡機運轉中…  {t:.0f}°C", t=s.milk_temp)


class ToolStage(Stage):
    """杯口上方的小道具：篩網撒可可粉、鮮奶油槍擠鮮奶油、焦糖醬淋格紋。
    s.tool 給畫面用（種類、位置、透明度、是否正在出料）；成果累積在 app.topping[kind]（0–1）。"""
    KINDS = {
        "cocoa": ("shaker", 2.4, (0.5, 1.9), "撒可可粉…"),
        "whip": ("whip", 3.2, (0.5, 2.7), "擠上鮮奶油…"),
        "caramel": ("caramel", 3.0, (0.5, 2.5), "淋上焦糖醬…"),
        "cinnamon": ("shaker", 2.4, (0.5, 1.9), "撒肉桂粉…"),
    }

    def __init__(self, kind):
        self.kind = kind
        self.tool, self.total, (self.a, self.b), self.label = self.KINDS[kind]
        self.name = kind

    def start(self, s):
        self.t = 0.0
        s.app.topping[self.kind] = 0.0
        s.tool = {"kind": self.tool, "alpha": 0.0, "active": False, "k": 0.0, "dust": self.kind}

    def update(self, s, dt):
        self.t += dt
        tool = s.tool
        tool["alpha"] = clamp(self.t / 0.4, 0, 1) * clamp((self.total - self.t) / 0.4, 0, 1)
        tool["active"] = self.a < self.t < self.b
        k = clamp((self.t - self.a) / (self.b - self.a), 0, 1)
        tool["k"] = k
        s.app.topping[self.kind] = k
        if self.t >= self.total:
            s.app.topping[self.kind] = 1.0
            s.tool = None
            self.done = True

    def status(self, s):
        return T(self.label)


def CocoaStage():
    return ToolStage("cocoa")


class ScoopStage(Stage):
    """阿芙佳朵：冰淇淋勺把一球香草冰淇淋放進杯裡（球掉落與融化由畫面端處理）"""
    name = "scoop"

    def start(self, s):
        cup, m = s.app.cup, s.app.machine
        self.drop_pos = (m.mx + cup.CX + 4, m.my + cup.T - 30)
        self.enter = (self.drop_pos[0] + 80, self.drop_pos[1] - 50)
        s.vessel = {"kind": "scoop", "x": self.enter[0], "y": self.enter[1], "tilt": 0.0, "alpha": 0.0,
                    "ball": True, "pour": 0.0, "liquid": "", "fill": 1.0}
        self.phase, self.t = "enter", 0.0

    def update(self, s, dt):
        self.t += dt
        v = s.vessel
        if self.phase == "enter":
            k = clamp(self.t / 0.9, 0, 1)
            v["x"], v["y"] = arc_move(self.enter, self.drop_pos, k, 16)
            v["alpha"] = clamp(k * 2, 0, 1)
            if k >= 1:
                self.phase, self.t = "drop", 0.0
        elif self.phase == "drop":
            k = clamp(self.t / 0.35, 0, 1)
            v["tilt"] = -70 * ease(k)                    # 勺口往下翻
            if k >= 0.6 and v["ball"]:
                v["ball"] = False
                s.app.drop_icecream(s.dp.scoop_g, v["x"] - s.app.machine.mx, v["y"] - s.app.machine.my + 6)
            if k >= 1 and s.app.icecream and s.app.icecream["landed"]:
                self.phase, self.t = "exit", 0.0
                self.exit_from = (v["x"], v["y"])
        elif self.phase == "exit":
            k = clamp(self.t / 0.7, 0, 1)
            v["x"], v["y"] = arc_move(self.exit_from, self.enter, k, 16)
            v["tilt"] = -70 * (1 - ease(k))
            v["alpha"] = 1 - k
            if k >= 1:
                s.vessel = None
                self.done = True

    def status(self, s):
        return T("放入一球香草冰淇淋…")


class Session:
    """一杯飲品的完整流程"""

    def __init__(self, app, drink, full_flow, dp):
        self.app = app
        self.drink = drink
        self.dp = dp.copy()
        self.events = []
        self.vessel = None              # 正在用的容器（熱水壺、牛奶瓶、拉花杯、奶泡機壺、醬料瓶、冰淇淋勺）
        self.tool = None                # 杯口上方的小道具（篩網、鮮奶油槍、焦糖醬瓶）
        self.art_progress = 0.0
        self.art_seed = random.randint(0, 99999)
        self.milk = None
        self.milk_temp = 6.0
        self.milk_foam = 0.0
        self.stretching = False
        self.frother_on = False
        self.boiler_mode = "brew"
        self.result = None
        self.params, self.style, self.preset = shot_params(drink, app.params)
        self.order = None                # 點單模式：這杯是哪張訂單
        t = app.machine.traits
        family = base_of(drink)
        stages = []
        if t.steam_heatup and app.boiler.temp > self.params.temp + 3:
            stages.append(CoolStage())
        if full_flow:
            stages.append(PrepStage())
        if drink == "americano":
            stages.append(PourStage("kettle", "water", self.dp.water_g, 22.0))
        if family == "iced":
            stages.append(IceStage())
            if drink == "iced_latte":
                stages.append(PourStage("bottle", "cold_milk", self.dp.iced_milk_g, 24.0))
            elif drink == "espresso_tonic":
                stages.append(PourStage("tonic", "tonic", self.dp.tonic_g, 20.0))
            else:
                stages.append(PourStage("bottle", "cold_water", self.dp.iced_water_g, 24.0))
        if drink == "affogato":
            stages.append(ScoopStage())
        spec = DRINKS[drink]
        if spec.get("syrup"):
            g = spec["syrup_g"]
            g = getattr(self.dp, g) if isinstance(g, str) else g
            stages.append(PourStage("squeeze", spec["syrup"], g, 9.0))
        if drink == "caramel_macchiato":
            stages.append(PourStage("squeeze", "vanilla", self.dp.vanilla_g, 8.0))
        milk_stages = []
        if family == "milk":
            self.milk = evaluate_milk(self.dp, t, t.milk, drink=drink)
            if t.steam_heatup:
                milk_stages.append(HeatStage())
            milk_stages.append(SteamStage())
            grams, foam, _, _ = milk_plan(drink, self.dp)
            foam_vol = grams * foam / 100 * FOAM_EXPANSION * MILK_KINDS.get(self.dp.milk_kind, MILK_KINDS["dairy"])["foam"]
            small = drink == "macchiato"
            art = self.milk.art not in ("mark", "whip")
            kw = dict(art=art, foam_vol=foam_vol)
            if small:
                kw.update(label="點上奶泡…", art_label="點上奶泡…")
            elif not art:
                kw.update(label="倒入熱牛奶…")
            rate = 8.0 if small else (10.0 if drink == "cortado" else 14.0)
            if t.milk == "wand":
                milk_stages.append(PourStage("pitcher", "hot_milk", grams, rate, start="vessel", **kw))
            else:
                fp = app.machine.frother_pos
                home = (fp[0], fp[1])
                milk_stages.append(PourStage("jug", "hot_milk", grams, rate, start=home, home=home, **kw))
        if drink == "caramel_macchiato":
            # 先牛奶、後濃縮：濃縮穿過奶泡停在中間，形成分層
            stages += milk_stages
            if t.steam_heatup:
                stages.append(CoolStage())
            stages.append(BrewStage())
            stages.append(ToolStage("caramel"))
        else:
            stages.append(BrewStage())
            stages += milk_stages
        if drink == "cappuccino" and self.dp.cocoa:
            stages.append(ToolStage("cocoa"))
        if whip_on(drink, self.dp):
            stages.append(ToolStage("whip"))
            if spec.get("dust"):
                stages.append(ToolStage(spec["dust"]))
        elif spec.get("dust") and drink != "mocha":
            stages.append(ToolStage(spec["dust"]))
        self.stages = stages
        self.i = 0
        self.done = False
        self._start_current()

    @property
    def stage(self):
        return self.stages[self.i] if self.i < len(self.stages) else None

    @property
    def cocoa(self):
        return self.app.topping.get("cocoa", 0.0)

    def _start_current(self):
        st = self.stage
        if st is None:
            return
        if isinstance(st, PourStage) and st.start_pos == "vessel":
            v = self.vessel
            st.start_pos = (v["x"], v["y"]) if v else None
        st.start(self)

    def update(self, dt):
        st = self.stage
        if st is None:
            return
        st.update(self, dt)
        sh = self.app.shot
        if self.drink == "caramel_macchiato" and sh is not None:
            self.art_progress = max(self.art_progress, clamp(sh.weight / max(1.0, sh.p.yield_g), 0, 1))
        if st.done:
            self.i += 1
            if self.i >= len(self.stages):
                self.finish()
            else:
                self._start_current()

    def finish(self):
        from .model import shot_comment
        self.done = True
        last_steam = is_milk(self.drink) and self.drink != "caramel_macchiato"
        self.boiler_mode = "steam" if (last_steam and self.app.machine.traits.steam_heatup) else "brew"
        self.result = score_drink(self.drink, self.app.shot, self.dp, self.milk, shot_comment)

    def add_liquid(self, liquid, grams, foam_vol=0.0):
        c = self.app.contents
        if liquid in ("water", "cold_water", "tonic"):
            c["water"] += grams
        elif liquid in ("cold_milk", "hot_milk"):
            c["milk"] += grams
            c["foam"] += foam_vol
        elif liquid in SYRUPS:
            c["syrup"] += grams
            self.app.syrup_kind = liquid

    def status(self):
        st = self.stage
        return st.status(self) if st else ""

    @property
    def stage_name(self):
        st = self.stage
        return st.name if st else "done"
