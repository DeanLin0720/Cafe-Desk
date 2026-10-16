"""顧客點單模式：產生訂單、依訂單調整飲品參數、成品與訂單的符合度、顧客反應

訂單＝飲品＋0–2 個要求（不要太燙、換燕麥奶、想要葉子、少冰…）。
咖啡師照單製作（打奶溫度、奶泡量每杯會有些手感誤差），最後分數＝飲品本身 65%＋符合訂單 35%。
"""
import random
from dataclasses import dataclass, field

from .drinks import DRINKS, ART_NAMES, MILK_KINDS, FESTIVAL_DRINKS, base_of, is_milk, milk_plan
from .festivals import adjust_weights
from .i18n import T, lang
from .util import clamp

CUSTOMERS = ("小陳", "阿哲", "Amy", "小美", "Ken", "王先生", "林小姐", "Joe", "小雨", "阿凱", "Mia", "老張",
             "Ivy", "阿明", "陳太太", "Leo")
ORDER_WEIGHTS = {"espresso": 0.07, "ristretto": 0.03, "lungo": 0.03, "doppio": 0.05, "americano": 0.12,
                 "iced_americano": 0.1, "latte": 0.18, "cappuccino": 0.12, "flat_white": 0.08,
                 "cortado": 0.05, "macchiato": 0.04, "iced_latte": 0.13, "mocha": 0.09,
                 "caramel_macchiato": 0.1, "espresso_tonic": 0.06, "affogato": 0.06}
ART_MILK = ("latte", "cappuccino", "flat_white", "cortado")
OAT_OK = ("latte", "cappuccino", "flat_white", "cortado", "iced_latte", "mocha", "caramel_macchiato") + FESTIVAL_DRINKS

# (種類, 值) → 訂單上的文字
MOD_TEXT = {
    ("temp", "low"): "不要太燙", ("temp", "high"): "熱一點",
    ("milk", "oat"): "換燕麥奶", ("milk", "soy"): "換豆奶", ("milk", "almond"): "換杏仁奶",
    ("whip", "no"): "不要鮮奶油", ("scoop", "big"): "冰淇淋多一點",
    ("foam", "more"): "多一點奶泡", ("foam", "less"): "奶泡少一點",
    ("art", "heart"): "想要愛心", ("art", "tulip"): "想要鬱金香", ("art", "rosetta"): "想要葉子",
    ("cocoa", "no"): "不要可可粉",
    ("water", "less"): "濃一點", ("water", "more"): "淡一點",
    ("ice", "less"): "少冰", ("ice", "more"): "多冰",
}

ORDER_WEIGHT_DRINK = 0.65      # 最後分數：飲品本身的比重（其餘是符合訂單的程度）
SHOW_DONE = 9.0                # 完成後訂單卡停留秒數（顯示分數與顧客反應）


@dataclass
class Order:
    no: int
    name: str
    drink: str
    mods: list = field(default_factory=list)
    state: str = "waiting"       # waiting → making → done → leaving
    t: float = 0.0               # 進入目前狀態後經過的秒數（動畫用）
    drink_score: float = 0.0
    match: float = 100.0
    score: float = 0.0
    reaction: str = ""
    complaint: str = ""

    def has(self, kind):
        return next((v for k, v in self.mods if k == kind), None)

    @property
    def title(self):
        name = DRINKS[self.drink]["name"]
        milk = self.has("milk")
        if milk in MILK_KINDS and MILK_KINDS[milk]["prefix"]:
            name = name.replace("熱", "")
            return T("{prefix}{name}", prefix=T(MILK_KINDS[milk]["prefix"]), name=T(name))
        return T(name)

    @property
    def mod_lines(self):
        return [T(MOD_TEXT[m]) for m in self.mods if m[0] != "milk"]


def mod_pool(drink):
    pool = []
    family = base_of(drink)
    if family == "milk" and drink != "macchiato":
        pool += [("temp", "low"), ("temp", "high")]
    if drink in OAT_OK:
        pool += [("milk", "oat"), ("milk", "oat"), ("milk", "soy"), ("milk", "almond")]
    if drink == "mocha":
        pool += [("whip", "no")]
    if drink == "affogato":
        pool += [("scoop", "big")]
    if drink == "latte":
        pool += [("foam", "more"), ("foam", "less")]
    if drink in ART_MILK:
        arts = ("heart", "tulip") if drink in ("cappuccino", "cortado") else ("heart", "tulip", "rosetta")
        pool += [("art", a) for a in arts]
    if drink == "cappuccino":
        pool += [("cocoa", "no")]
    if drink in ("americano", "iced_americano"):
        pool += [("water", "less"), ("water", "more")]
    if family == "iced":
        pool += [("ice", "less"), ("ice", "more")]
    return pool


def make_order(no, rnd=random, last_name=None):
    weights = adjust_weights(ORDER_WEIGHTS, DRINKS)          # 夏天冰飲多、冬天熱飲多、節日點限定飲品
    keys = list(weights)
    drink = rnd.choices(keys, weights=[weights[k] for k in keys])[0]
    names = [n for n in CUSTOMERS if n != last_name]
    pool = mod_pool(drink)
    n = min(len(pool), rnd.choices((0, 1, 2), weights=(0.3, 0.45, 0.25))[0])
    mods = []
    rnd.shuffle(pool)
    for m in pool:
        if len(mods) >= n:
            break
        if all(m[0] != k for k, _ in mods):          # 同一類要求只會有一個
            mods.append(m)
    return Order(no, rnd.choice(names), drink, mods)


def order_params(order, dp, rnd=random):
    """依訂單改飲品參數；咖啡師手感：打奶溫度與奶泡量每杯有些誤差"""
    d = dp.copy()
    temp = order.has("temp")
    d.milk_temp = {"low": 54.0, "high": 66.0}.get(temp, d.milk_temp)
    d.milk_temp = clamp(d.milk_temp + rnd.gauss(0, 2.8), 45, 74)
    foam = order.has("foam")
    if foam:
        d.foam = 50.0 if foam == "more" else 15.0
    for attr in ("foam", "capp_foam", "flat_foam"):
        setattr(d, attr, clamp(getattr(d, attr) + rnd.gauss(0, 4), 3, 90))
    d.milk_kind = order.has("milk") or "dairy"
    d.whip = order.has("whip") != "no"
    if order.has("scoop") == "big":
        d.scoop_g = 95.0
    if order.has("cocoa") == "no":
        d.cocoa = False
    elif order.drink == "cappuccino":
        d.cocoa = True
    art = order.has("art")
    if art:
        d.art = art
    water = order.has("water")
    if water:
        k = 0.75 if water == "less" else 1.3
        d.water_g = clamp(d.water_g * k, 60, 200)
        d.iced_water_g = clamp(d.iced_water_g * k, 60, 220)
    ice = order.has("ice")
    if ice:
        d.ice = 2.0 if ice == "less" else 8.0
    return d


def evaluate(order, session):
    """(符合度 0–100, 顧客抱怨)"""
    m = session.milk
    checks = []
    complaint = ""
    for kind, value in order.mods:
        ok = 1.0
        if kind == "temp" and m is not None:
            if value == "low":
                ok = clamp(1 - (m.temp - 58) / 8, 0, 1)
                if ok < 0.8:
                    complaint = complaint or T("有點燙")
            else:
                ok = clamp(1 - (63 - m.temp) / 8, 0, 1)
                if ok < 0.8:
                    complaint = complaint or T("不夠熱")
        elif kind == "foam" and m is not None:
            target = 50.0 if value == "more" else 15.0
            ok = clamp(1 - (abs(m.foam - target) - 8) / 20, 0, 1)
            if ok < 0.8:
                complaint = complaint or T("奶泡跟我想的不太一樣")
        elif kind == "art" and m is not None:
            name = T(ART_NAMES[value])
            if m.art == value and not m.art_note:
                ok = 1.0
            elif m.art == value:
                ok = 0.5
                complaint = complaint or T("{name}糊糊的", name=name)
            else:
                ok = 0.0
                complaint = complaint or T("不是我要的{name}", name=name)
        checks.append(ok)
    match = 100.0 * (sum(checks) / len(checks) if checks else 1.0)
    return match, complaint


def reaction(score, complaint):
    if complaint:
        if score >= 80:
            return T("{c}，不過好喝！", c=complaint)
        if score >= 66:
            return T("{c}，還可以。", c=complaint)
        return T("嗯…{c}", c=complaint)
    if score >= 92:
        return T("太好喝了，下次還來！")
    if score >= 84:
        return T("好喝，謝謝！")
    if score >= 72:
        return T("還不錯。")
    if score >= 62:
        return T("普普通通。")
    return T("嗯…（默默喝完）")


def finish(order, session, drink_result):
    order.drink_score = drink_result.score
    order.match, order.complaint = evaluate(order, session)
    order.score = ORDER_WEIGHT_DRINK * order.drink_score + (1 - ORDER_WEIGHT_DRINK) * order.match
    order.reaction = reaction(order.score, order.complaint)
    order.state, order.t = "done", 0.0
