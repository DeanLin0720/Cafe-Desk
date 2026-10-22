"""手沖、冰滴、摩卡壺、虹吸壺：萃取模型、器具時間軸（Stage）、冰滴的背景批次

摩卡壺（MokaStage）與虹吸壺（SiphonStage）跟手沖一樣：時間軸以沖煮秒數計算、畫面快轉（MOKA_K／SIPHON_K）。

兩種沖法各自是一個「沖煮方式」（右鍵「沖煮方式」），有自己的畫面：左邊一台手沖用磨豆機，
不顯示咖啡機（畫面在 render/station.py）：
- 手沖：磨粉 → 悶蒸 → 分段注水 → 滴濾 → 拿掉濾杯 → 從分享壺倒進杯子。
  時間軸以「沖煮秒數」計算，畫面快轉 TIME_K 倍（3 分鐘的手沖約 1 分鐘做完），狀態列顯示的是沖煮秒數。
- 冰滴：第一次點冰滴會先架好冰滴塔（磨粉、加冰水、開閥），然後在背景用真實時間慢慢滴 COLD_DUR 秒；
  關掉程式再開也會接著滴（狀態存在設定檔 cold_drip）。滴完可以做 COLD_SERVINGS 杯冰滴咖啡（加冰塊倒進杯子）。
評分沿用 model.Result 與 ROASTS 的萃取率目標；濃度目標是一般濾泡咖啡的 TDS。
"""
import math
import random
import time

from .i18n import T
from .model import ROASTS, Result
from .beans import sweet_bonus
from .util import clamp, lerp
from .workflow import ease, arc_move
from . import vessels

TIME_K = 3.0                  # 手沖畫面快轉倍數
KETTLE_FULL, KETTLE_EMPTY = 0.85, 0.3   # 手沖壺開始注水、全部注完時壺裡的水（佔壺的比例）
KETTLE_REST = 12.0            # 分段之間把壺扶正多少度（水停住）
POUR_RATE = 6.0               # 手沖壺注水速度（g／沖煮秒）
BLOOM_K = 2.5                 # 悶蒸水量＝粉量 × BLOOM_K
RETAIN_K = 2.0                # 咖啡粉吸住的水＝粉量 × RETAIN_K
TDS_POUR = (1.15, 1.45)       # 手沖的濃度目標（%）
TDS_COLD = (1.3, 1.9)
COLD_DUR = 3600.0             # 冰滴在畫面上滴多久（真實秒數）
COLD_SERVINGS = 4
COLD_SERVE_G = 100.0          # 每杯冰滴倒多少

# 摩卡壺與虹吸壺
MOKA_K = 6.0                  # 摩卡壺畫面快轉倍數（等水煮開那段很長）
MOKA_WATER = 150.0            # 下壺加水到洩壓閥（g）
MOKA_LEFT = 15.0              # 下壺最後留下、推不上去的水
TDS_MOKA = (2.6, 4.2)         # 摩卡壺比濾泡濃很多，但不到濃縮
SIPHON_K = 4.0                # 虹吸壺畫面快轉倍數
SIPHON_RATIO = 15.0           # 虹吸壺粉水比固定 1:15（下壺的水量依粉量）
TDS_SIPHON = (1.2, 1.55)
TDS_TARGET = {"pourover": TDS_POUR, "colddrip": TDS_COLD, "moka": TDS_MOKA, "siphon": TDS_SIPHON}

# 沖煮方式：espresso＝義式咖啡機（machines/），其他是獨立畫面
METHODS = {"espresso": "義式咖啡機", "pourover": "手沖", "colddrip": "冰滴", "moka": "摩卡壺", "siphon": "虹吸壺"}
# 獨立畫面的版面：視窗跟目前的咖啡機一樣寬；器具用「器具座標」畫，再以檯面左端為基準放大 GEAR_K 倍
# （render/station.py 的 gear_to_scene）。杯子不放大，放在離右緣 CUP_RIGHT 的地方，右邊留位置給倒咖啡時傾斜的壺。
GEAR_K = {"pourover": 1.4, "colddrip": 1.3, "moka": 1.45, "siphon": 1.3}   # 冰滴塔、虹吸壺很高，放大少一點
GRINDER_X = 8                 # 手沖用磨豆機左緣（器具座標，下同）
PO_STAND_X = 100              # 濾杯與分享壺的中心
CD_TOWER_X = 84               # 冰滴塔左緣（塔寬 86）
MK_STOVE_X = 116              # 摩卡壺爐子（與壺）的中心
SY_X = 116                    # 虹吸壺（燈、下壺、上壺）的中心
CUP_RIGHT = {"pourover": 170, "colddrip": 160, "moka": 165, "siphon": 170}  # 成品杯中心到視窗右緣（場景座標）：右邊要留位置給倒的時候傾斜的壺
# 沖煮時拉近：磨豆機與杯子淡出，沖煮器具放大到 GEAR_ZOOM 倍、移到視窗中央（FOCUS_X 是器具座標的中心）；
# 沖完拉遠再倒進杯子。冰滴塔很高，拉近時頂端會伸進上方的透明區
GEAR_ZOOM = {"pourover": 3.0, "colddrip": 1.6, "moka": 3.0, "siphon": 1.75}
FOCUS_X = {"pourover": PO_STAND_X + 14, "colddrip": CD_TOWER_X + 43, "moka": MK_STOVE_X, "siphon": SY_X + 6}
ZOOM_SPEED = 1.6              # 拉近／拉遠的速度（每秒，0–1）
FOCUS_PHASES = {"pourover": ("kettle_in", "bloom_pour", "bloom", "pulse", "wait", "drawdown"),
                "colddrip": ("water", "valve"),
                "moka": ("ignite", "heat", "brew", "sputter"),
                "siphon": ("light", "heat", "rise", "add", "stir", "steep", "stir2", "drawdown")}
GRIND_ATTR = {"pourover": "po_grind", "colddrip": "cd_grind", "moka": "mk_grind", "siphon": "sy_grind"}


def _band(x, a, b, slope):
    return max(0.0, 100 - (a - x) * slope) if x < a else max(0.0, 100 - (x - b) * slope) if x > b else 100.0


def pourover_time(dp):
    """手沖總時間（秒）：研磨越細、水越多、段數越多越久"""
    fine = 650.0 / dp.po_grind
    water = dp.po_dose * dp.po_ratio
    return dp.po_bloom + 110 * fine ** 1.6 * (water / 240) ** 0.7 + 8 * (dp.po_pulses - 1)


FINES_K = 1.0       # 手沖用磨豆機的細粉倍率：萃取不均乘上它（商店的鬼齒刀盤會降低，store.apply_upgrades 設定）
CLARITY = 0.0       # 手沖用磨豆機的乾淨度：甜感加成（鬼齒刀盤細粉少，杯子比較乾淨、甜）


def simulate_pourover(dp, roast, bean_age, origin):
    """手沖萃取：研磨、水溫、粉水比、悶蒸、注水段數 → Result（time、ey、tds、channeling＝萃取不均、甜感、分數）"""
    r = ROASTS[roast]
    fine = 650.0 / dp.po_grind
    t = pourover_time(dp)
    co2 = max(0.0, 7 - bean_age) / 7                    # 太新鮮的豆子要悶蒸排氣
    stale = clamp((bean_age - 30) / 40, 0, 1)
    bloom_ok = clamp(dp.po_bloom / 30, 0, 1) * (1 - clamp((dp.po_bloom - 60) / 60, 0, 0.5))
    uneven = (0.10 if dp.po_pulses <= 1 else 0.0) + max(0.0, 450 - dp.po_grind) / 200 * 0.3 \
        + co2 * 0.15 * (1 - bloom_ok)
    uneven = clamp(uneven * FINES_K, 0, 0.6)
    drive = (fine ** 0.8 * math.exp((dp.po_temp - 93) / 12) * (t / 180) ** 0.35 * (dp.po_ratio / 16) ** 0.3
             * (0.88 + 0.12 * bloom_ok))
    ey = r["ey_max"] * (1 - math.exp(-1.35 * r["sol"] * drive)) * (1 - 0.3 * uneven)
    beverage = dp.po_dose * (dp.po_ratio - RETAIN_K)
    tds = ey * dp.po_dose / max(1.0, beverage)
    lo, hi = r["target"]
    sweet = clamp(8.5 - abs(ey - (lo + hi) / 2) * 1.3 - uneven * 6 - stale * 2 + sweet_bonus(origin) + CLARITY)
    score = (0.40 * _band(ey, lo, hi, 15) + 0.25 * _band(tds, *TDS_POUR, 120)
             + 0.35 * sweet * 10 - uneven * 40 - stale * 10)
    return Result(t, ey, tds, uneven, sweet, clamp(score, 0, 100))


def cold_hours(dp):
    """冰滴相當於實際滴幾個小時：滴速（滴／10 秒）越慢越久"""
    return 6.0 * 10.0 / dp.cd_rate


def simulate_colddrip(dp, roast, bean_age, origin):
    r = ROASTS[roast]
    fine = 550.0 / dp.cd_grind
    hours = cold_hours(dp)
    stale = clamp((bean_age - 30) / 40, 0, 1)
    uneven = clamp((max(0.0, 400 - dp.cd_grind) / 200 * 0.3 + max(0.0, dp.cd_rate - 16) * 0.02) * FINES_K, 0, 0.5)
    drive = fine ** 0.8 * (hours / 6) ** 0.4 * (dp.cd_ratio / 10) ** 0.3
    ey = r["ey_max"] * 0.85 * (1 - math.exp(-1.7 * r["sol"] * drive)) * (1 - 0.3 * uneven)
    beverage = dp.cd_dose * (dp.cd_ratio - RETAIN_K)
    tds = ey * dp.cd_dose / max(1.0, beverage)
    lo, hi = r["target"][0] - 2.0, r["target"][1] - 2.0             # 冷萃萃取率低一點也好喝
    sweet = clamp(8.8 - abs(ey - (lo + hi) / 2) * 1.2 - uneven * 6 - stale * 2 + sweet_bonus(origin) + CLARITY)
    score = (0.40 * _band(ey, lo, hi, 15) + 0.25 * _band(tds, *TDS_COLD, 80)
             + 0.35 * sweet * 10 - uneven * 40 - stale * 10)
    return Result(hours * 3600, ey, tds, uneven, sweet, clamp(score, 0, 100))


def moka_beverage(dp):
    """摩卡壺倒出的咖啡（g）：下壺的水扣掉留在下壺的與粉吸住的"""
    return MOKA_WATER - MOKA_LEFT - dp.mk_dose * 1.4


def moka_times(dp):
    """(等水煮開的秒數, 咖啡冒出到噴完的秒數)：火越大越快；粉越細越慢"""
    h = dp.mk_heat
    fine = 320.0 / dp.mk_grind
    return 260.0 / (h + 0.6), 55.0 * fine ** 0.7 * (3.6 / (h + 0.6)) ** 0.5


def simulate_moka(dp, roast, bean_age, origin):
    """摩卡壺：粉量、研磨、火力 → Result。火太大會煮焦、噴濺（萃取不均、苦）；粉太細會悶住、過萃"""
    r = ROASTS[roast]
    fine = 320.0 / dp.mk_grind
    heat_t, flow_t = moka_times(dp)
    temp = 90 + 2.4 * (dp.mk_heat - 1)
    stale = clamp((bean_age - 30) / 40, 0, 1)
    scorch = clamp((dp.mk_heat - 3.5) / 1.5, 0, 1)
    choke = max(0.0, 240 - dp.mk_grind) / 60
    uneven = clamp((0.3 * scorch + 0.2 * choke + max(0.0, dp.mk_grind - 450) / 150 * 0.1) * FINES_K, 0, 0.6)
    drive = fine ** 0.8 * math.exp((temp - 94) / 12) * (flow_t / 55) ** 0.3 * (1 + 0.15 * choke)
    ey = r["ey_max"] * (1 - math.exp(-1.6 * r["sol"] * drive)) * (1 - 0.25 * uneven)
    beverage = moka_beverage(dp)
    tds = ey * dp.mk_dose / max(1.0, beverage)
    lo, hi = r["target"]
    sweet = clamp(8.2 - abs(ey - (lo + hi) / 2) * 1.3 - uneven * 6 - stale * 2 + sweet_bonus(origin) + CLARITY)
    score = (0.40 * _band(ey, lo, hi, 15) + 0.25 * _band(tds, *TDS_MOKA, 40)
             + 0.35 * sweet * 10 - uneven * 40 - stale * 10)
    return Result(heat_t + flow_t, ey, tds, uneven, sweet, clamp(score, 0, 100))


def siphon_water(dp):
    return dp.sy_dose * SIPHON_RATIO


def siphon_beverage(dp):
    return dp.sy_dose * (SIPHON_RATIO - RETAIN_K)


def simulate_siphon(dp, roast, bean_age, origin):
    """虹吸壺：研磨、上壺水溫（火力）、浸泡秒數 → Result。粉太細會卡住濾布、抽不下來（萃取不均、過萃）"""
    r = ROASTS[roast]
    fine = 600.0 / dp.sy_grind
    stale = clamp((bean_age - 30) / 40, 0, 1)
    clog = max(0.0, 450 - dp.sy_grind) / 150
    uneven = clamp((0.3 * clog + max(0.0, dp.sy_temp - 94) * 0.03) * FINES_K, 0, 0.6)
    drive = (fine ** 0.8 * math.exp((dp.sy_temp - 91) / 12) * (dp.sy_steep / 50) ** 0.45 * (1 + 0.2 * clog))
    ey = r["ey_max"] * (1 - math.exp(-1.45 * r["sol"] * drive)) * (1 - 0.25 * uneven)
    tds = ey * dp.sy_dose / max(1.0, siphon_beverage(dp))
    lo, hi = r["target"]
    sweet = clamp(8.6 - abs(ey - (lo + hi) / 2) * 1.3 - uneven * 6 - stale * 2 + sweet_bonus(origin) + CLARITY)
    score = (0.40 * _band(ey, lo, hi, 15) + 0.25 * _band(tds, *TDS_SIPHON, 120)
             + 0.35 * sweet * 10 - uneven * 40 - stale * 10)
    return Result(90 + dp.sy_steep + 40 * (1 + clog), ey, tds, uneven, sweet, clamp(score, 0, 100))


SIMULATE = {"pourover": simulate_pourover, "moka": simulate_moka, "siphon": simulate_siphon}


def brew_comment(res, roast, tds_target, family="pourover"):
    lo, hi = ROASTS[roast]["target"]
    if res.channeling > 0.2:
        return {"moka": T("火太大，帶焦苦味"), "siphon": T("粉太細卡住濾布，味道混濁")}.get(
            family, T("萃取不均，味道混濁"))
    if res.ey < lo - 1.5:
        return T("萃取不足，偏酸單薄")
    if res.ey < lo:
        return T("略酸，明亮但收尾短")
    if res.ey > hi + 1.5:
        return T("過度萃取，苦澀乾口")
    if res.ey > hi:
        return T("略苦，尾韻偏乾")
    if res.tds < tds_target[0]:
        return T("乾淨但偏淡")
    if res.tds > tds_target[1]:
        return T("濃郁厚重")
    return {"moka": T("濃郁厚實、帶焦糖甜感"), "siphon": T("圓潤乾淨、香氣飽滿")}.get(family, T("乾淨明亮、甜感飽滿"))


# 營業模式的咖啡師：依烘焙度調手沖、冰滴、摩卡壺、虹吸壺（淺焙磨細、溫度高；深焙磨粗、溫度低）。手動沖煮照使用者的設定
BARISTA = {"淺焙": dict(po_grind=500, po_temp=96, cd_grind=440, cd_ratio=11, cd_rate=7,
                       mk_grind=260, mk_heat=3.0, sy_grind=500, sy_temp=93, sy_steep=60),
           "中焙": dict(po_grind=580, po_temp=93, cd_grind=500, cd_ratio=11, cd_rate=10,
                       mk_grind=320, mk_heat=2.5, sy_grind=600, sy_temp=91, sy_steep=50),
           "深焙": dict(po_grind=700, po_temp=91, cd_grind=700, cd_ratio=11, cd_rate=12,
                       mk_grind=400, mk_heat=2.0, sy_grind=640, sy_temp=90, sy_steep=45)}


def barista_dial(dp, roast, rnd=random, skill=1.0):
    """咖啡師這一杯的手沖／冰滴參數（單杯副本，不寫回使用者設定）；每杯手感有些誤差（skill：熟練度的誤差倍率）"""
    d = dp.copy()
    for k, v in BARISTA.get(roast, BARISTA["中焙"]).items():
        setattr(d, k, v)
    d.po_grind = clamp(d.po_grind + rnd.gauss(0, 15 * skill), 400, 1000)
    d.po_temp = round(clamp(d.po_temp + rnd.gauss(0, 0.7 * skill), 85, 100) * 2) / 2   # 手沖壺溫度設定是 0.5°C 一格
    d.po_bloom = clamp(35 + rnd.gauss(0, 4 * skill), 20, 60)
    d.mk_grind = clamp(d.mk_grind + rnd.gauss(0, 12 * skill), 200, 600)
    d.mk_dose, d.sy_dose = 17.0, 15.0
    d.sy_grind = clamp(d.sy_grind + rnd.gauss(0, 15 * skill), 400, 900)
    d.sy_steep = clamp(d.sy_steep + rnd.gauss(0, 4 * skill), 20, 90)
    return d


def bloom_ok(dp):
    """悶蒸剛好（成就）：30–45 秒、分 2 段以上注水"""
    return 30 <= dp.po_bloom <= 45 and dp.po_pulses >= 2


# ───────────── 手沖時間軸 ─────────────
class PourOverStage:
    """手沖：準備 → 研磨 → 手沖壺就位 → 悶蒸注水 → 悶蒸 → 分段注水 → 滴濾 → 壺歸位 → 拿掉濾杯

    畫面狀態存在 s.station（render/station.py 畫）：bed（粉床 0–1）、swell（悶蒸膨脹）、water（濾杯裡的水 g）、
    server（分享壺裡的咖啡 g）、kettle（位置、傾角、出水）、drip（濾杯底下在滴）、dripper（濾杯透明度）。"""
    name = "pourover"
    done = False

    def start(self, s):
        dp = s.dp
        self.water_total = dp.po_dose * dp.po_ratio
        self.bloom_g = dp.po_dose * BLOOM_K
        n = max(1, int(round(dp.po_pulses)))
        self.pulses = [(self.water_total - self.bloom_g) / n] * n
        t_total = pourover_time(dp)
        self.beverage = dp.po_dose * (dp.po_ratio - RETAIN_K)
        self.out_rate = self.beverage / max(30.0, t_total - dp.po_bloom * 0.6 - 15)   # 濾杯出水（g／沖煮秒）
        self.absorb = dp.po_dose * RETAIN_K            # 粉先吸住的水，吸飽才開始滴
        self.phase, self.t, self.bt = "setup", 0.0, 0.0
        self.poured, self.target = 0.0, 0.0
        self.kettle_out = 0.0                          # 手沖壺總共倒出多少水（決定壺要傾斜多少）
        s.station = idle_pourover(s.app)
        k = s.station["kettle"]
        self.rest = (k["x"], k["y"])

    @property
    def clock(self):
        """沖煮時間（從第一次注水開始算）"""
        return self.bt

    def kettle_tilt(self):
        """手沖壺要傾斜幾度水才碰到壺嘴（vessels.pour_tilt）：壺裡一開始約八分滿，倒完剩三成"""
        left = KETTLE_FULL - (KETTLE_FULL - KETTLE_EMPTY) * clamp(self.kettle_out / max(1.0, self.water_total), 0, 1)
        return vessels.pour_tilt("kettle", left)

    def _flow(self, s, bdt):
        """濾杯：注進來的水先被粉吸住，之後依出水速度滴進分享壺"""
        st = s.station
        out = 0.0
        if self.absorb <= 0 and st["water"] > 0:
            out = min(st["water"], self.out_rate * bdt * clamp(st["water"] / 25, 0.35, 1.4))
        st["water"] -= out
        st["server"] += out
        st["drip"] = clamp(out / max(1e-6, bdt) / 2.5, 0, 1)

    def _pour(self, s, bdt, amount):
        st = s.station
        step = min(POUR_RATE * bdt, amount - self.poured)
        self.poured += step
        self.kettle_out += step
        soak = min(step, self.absorb)
        self.absorb -= soak
        st["water"] += step - soak
        return self.poured >= amount - 1e-6

    def update(self, s, dt):
        self.t += dt
        st = s.station
        k = st["kettle"]
        pour_at = s.app.station_pos("kettle_pour")
        if self.phase == "setup":
            if self.t >= 0.8:
                self.phase, self.t = "grind", 0.0
                s.events.append("grind")
        elif self.phase == "grind":
            grind_into(st, self.t, "bed")
            if self.t >= 2.2:
                self.phase, self.t = "kettle_in", 0.0
        elif self.phase == "kettle_in":
            kk = clamp(self.t / 0.9, 0, 1)
            k["x"], k["y"] = arc_move(self.rest, pour_at, kk, 18)
            k["tilt"] = (self.kettle_tilt() - KETTLE_REST) * ease(kk)
            if kk >= 1:
                self.phase, self.t, self.poured = "bloom_pour", 0.0, 0.0
                k["pour"] = 1.0
                s.events.append("kettle_start")
        elif self.phase in ("bloom_pour", "pulse"):
            bdt = dt * TIME_K
            self.bt += bdt
            amount = self.bloom_g if self.phase == "bloom_pour" else self.pulses[0]
            k["pour"] = 1.0
            target = self.kettle_tilt()                   # 壺裡的水越少，要傾斜越多才流得出來
            k["tilt"] += clamp(target - k["tilt"], -80 * dt, 80 * dt)
            k["x"] = pour_at[0] + math.sin(self.bt * 1.6) * 4            # 繞圈注水
            st["swell"] = max(st["swell"], 0.6 if self.phase == "bloom_pour" else st["swell"])
            finished = self._pour(s, bdt, amount)
            self._flow(s, bdt)
            if finished:
                k["pour"] = 0.0
                s.events.append("kettle_stop")
                if self.phase == "pulse":
                    self.pulses.pop(0)
                self.phase, self.t, self.poured = ("bloom" if self.phase == "bloom_pour" else "wait"), 0.0, 0.0
                self.wait_bt = 0.0
        elif self.phase == "bloom":
            bdt = dt * TIME_K
            self.bt += bdt
            self.wait_bt += bdt
            k["tilt"] = max(self.kettle_tilt() - KETTLE_REST, k["tilt"] - 40 * dt)   # 稍微扶正，水就停了
            st["swell"] = 0.6 + 0.4 * clamp(self.wait_bt / 12, 0, 1)
            self._flow(s, bdt)
            if self.wait_bt >= s.dp.po_bloom:
                self.phase, self.t, self.poured = ("pulse" if self.pulses else "drawdown"), 0.0, 0.0
                if self.pulses:
                    s.events.append("kettle_start")
        elif self.phase == "wait":
            # 分段之間：等水位降下來再注下一段
            bdt = dt * TIME_K
            self.bt += bdt
            k["tilt"] = max(self.kettle_tilt() - KETTLE_REST, k["tilt"] - 40 * dt)   # 稍微扶正，水就停了
            st["swell"] = max(0.5, st["swell"] - 0.02 * bdt)
            self._flow(s, bdt)
            if not self.pulses:
                self.phase, self.t = "drawdown", 0.0
            elif st["water"] <= 35:
                self.phase, self.t, self.poured = "pulse", 0.0, 0.0
                s.events.append("kettle_start")
        elif self.phase == "drawdown":
            bdt = dt * TIME_K
            self.bt += bdt
            kk = clamp(self.t / 0.9, 0, 1)
            k["x"], k["y"] = arc_move(pour_at, self.rest, kk, 18)
            if self.t <= dt:
                self.rest_from = k["tilt"]
            k["tilt"] = self.rest_from * (1 - ease(kk))
            st["swell"] = max(0.2, st["swell"] - 0.02 * bdt)
            if st["water"] < 1.5:
                st["water"] = 0.0
                self.absorb = 0.0
            self._flow(s, bdt)
            if kk >= 1 and st["water"] <= 0:
                st["server"] = self.beverage            # 誤差歸零：倒進杯子的量固定
                st["drip"] = 0.0
                self.phase, self.t = "remove", 0.0
        elif self.phase == "remove":
            st["dripper"] = 1 - clamp(self.t / 0.6, 0, 1)
            if self.t >= 0.75 + 1 / ZOOM_SPEED:        # 等畫面拉遠、看得到杯子再倒
                self.done = True

    def status(self, s):
        dp = s.dp
        clock = "{:d}:{:02d}".format(int(self.bt) // 60, int(self.bt) % 60)
        if self.phase == "setup":
            return T("準備濾杯與濾紙…")
        if self.phase == "grind":
            return T("研磨 {g:.0f}g（{um:.0f}µm）…", g=dp.po_dose, um=dp.po_grind)
        if self.phase == "kettle_in":
            return T("手沖壺就位…  {t:.0f}°C", t=dp.po_temp)
        if self.phase == "bloom_pour":
            return T("悶蒸注水  {g:.0f} g", g=self.poured)
        if self.phase == "bloom":
            return T("悶蒸中…  {t:.0f}/{b:.0f}s", t=self.wait_bt, b=dp.po_bloom)
        if self.phase == "pulse":
            n = int(round(dp.po_pulses)) - len(self.pulses) + 1
            return T("第 {n} 段注水  {clock}", n=n, clock=clock)
        if self.phase in ("wait", "drawdown"):
            return T("滴濾中…  {clock}", clock=clock)
        return T("拿掉濾杯…")


def idle_pourover(app):
    """手沖畫面沒在沖的時候：濾杯架在分享壺上、手沖壺放在旁邊"""
    x, y = app.station_pos("kettle_rest")
    return {"bed": 0.0, "swell": 0.0, "water": 0.0, "server": 0.0, "dripper": 1.0, "drip": 0.0,
            "kettle": {"x": x, "y": y, "tilt": 0.0, "pour": 0.0}, "catch": 0.0, "grinding": False}


def grind_into(st, t, target):
    """磨豆：前 1.4 秒磨進接粉杯，接著倒進濾杯（或冰滴塔）"""
    st["grinding"] = t < 1.4
    if t < 1.4:
        st["catch"] = ease(clamp(t / 1.3, 0, 1))
    else:
        k = ease(clamp((t - 1.5) / 0.6, 0, 1))
        st["catch"] = 1 - k
        st[target] = k


# ───────────── 冰滴 ─────────────
class ColdSetupStage:
    """架好冰滴塔：冰滴塔就位 → 研磨 → 加冰水 → 開閥；完成後由 desk 開始背景滴"""
    name = "cold_setup"
    done = False

    def start(self, s):
        self.phase, self.t = "setup", 0.0
        s.station = {"grounds": 0.0, "top": 0.0, "valve": 0.0, "catch": 0.0, "grinding": False}

    def update(self, s, dt):
        self.t += dt
        st = s.station
        if self.phase == "setup":
            if self.t >= 0.8:
                self.phase, self.t = "grind", 0.0
                s.events.append("cold_grind")
        elif self.phase == "grind":
            grind_into(st, self.t, "grounds")
            if self.t >= 2.2:
                self.phase, self.t = "water", 0.0
                s.events.append("pour_start")
        elif self.phase == "water":
            st["top"] = ease(clamp(self.t / 2.2, 0, 1))
            if self.t >= 2.4:
                self.phase, self.t = "valve", 0.0
                s.events.append("valve")
        elif self.phase == "valve":
            st["valve"] = clamp(self.t / 0.5, 0, 1)
            if self.t >= 0.8:
                self.done = True

    def status(self, s):
        dp = s.dp
        return {"setup": T("架好冰滴塔…"),
                "grind": T("研磨 {g:.0f}g（{um:.0f}µm）…", g=dp.cd_dose, um=dp.cd_grind),
                "water": T("加入冰水 {g:.0f}g…", g=dp.cd_dose * dp.cd_ratio),
                "valve": T("調整滴速：每 10 秒 {n:.0f} 滴", n=dp.cd_rate)}[self.phase]


def new_cold_batch(dp, roast, bean_age, origin, now=None):
    """開始一壺冰滴：結果在開始時就算好（豆子、研磨、粉水比、滴速）"""
    res = simulate_colddrip(dp, roast, bean_age, origin)
    return {"start": now if now is not None else time.time(), "dur": COLD_DUR, "dose": dp.cd_dose,
            "ratio": dp.cd_ratio, "grind": dp.cd_grind, "rate": dp.cd_rate, "roast": roast, "origin": origin,
            "bean_age": bean_age, "res": [res.time, res.ey, res.tds, res.channeling, res.sweetness, res.score],
            "servings": 0, "done": False}


def cold_progress(batch, now=None):
    if batch is None:
        return 0.0
    now = now if now is not None else time.time()
    return clamp((now - batch["start"]) / max(1.0, batch["dur"]), 0, 1)


def valid_batch(b):
    try:
        return (isinstance(b, dict) and float(b["start"]) > 0 and float(b["dur"]) > 0 and len(b["res"]) == 6
                and b["roast"] in ROASTS and int(b["servings"]) >= 0)
    except (KeyError, TypeError, ValueError):
        return False


def batch_result(b):
    return Result(*b["res"])


def cold_remaining_min(batch, now=None):
    return max(1, int(math.ceil((1 - cold_progress(batch, now)) * batch["dur"] / 60)))


def drop_phase(rate, now, offset=0.0):
    """冰滴水滴：每 10/rate 秒一滴，回傳這一滴落下的進度 0–1（大於 1 表示還在等下一滴）

    背景滴一小時，不為了水滴提高幀率（閒置幀率約每秒 10 張），所以落下時間很短，看起來是一滴一滴掉"""
    period = 10.0 / max(1.0, rate)
    return ((now + offset * period) % period) / min(0.3, period * 0.5)


# ───────────── 摩卡壺時間軸 ─────────────
def idle_moka():
    """摩卡壺沒在煮的時候：組好放在爐子上、火關著、蓋子蓋著"""
    return {"basket": 0.0, "lift": 0.0, "twist": 0.0, "flame": 0.0, "knob": 0.0, "lid": 0.0, "coffee": 0.0,
            "gush": 0.0, "sputter": 0.0, "catch": 0.0, "grinding": False}


class MokaStage:
    """摩卡壺：轉開上壺 → 研磨進粉槽 → 鎖回 → 點火 → 等水煮開 → 咖啡從中柱冒出 → 噴濺收尾 → 關火

    s.station（render/station.py 畫）：basket（粉槽裡的粉）、lift（上壺拿起來的程度）、twist（鎖緊時的轉動）、
    flame（火焰 0–1）、knob（爐子旋鈕）、lid（蓋子打開）、coffee（上壺咖啡 0–1）、gush（中柱冒出的力道）、sputter（噴濺）"""
    name = "moka"
    done = False

    def start(self, s):
        self.heat_t, self.flow_t = moka_times(s.dp)
        self.phase, self.t, self.bt = "setup", 0.0, 0.0
        s.station = idle_moka()

    @property
    def clock(self):
        return self.bt

    def update(self, s, dt):
        self.t += dt
        st = s.station
        if self.phase == "setup":                       # 轉開、拿起上壺
            st["lift"] = ease(clamp(self.t / 0.8, 0, 1))
            if self.t >= 0.9:
                self.phase, self.t = "grind", 0.0
                s.events.append("grind")
        elif self.phase == "grind":
            grind_into(st, self.t, "basket")
            if self.t >= 2.2:
                self.phase, self.t = "assemble", 0.0
                s.events.append("tap")
        elif self.phase == "assemble":                  # 上壺放回去、轉緊
            st["lift"] = 1 - ease(clamp(self.t / 0.7, 0, 1))
            st["twist"] = math.sin(clamp((self.t - 0.7) / 0.5, 0, 1) * math.pi * 2) if self.t > 0.7 else 0.0
            if self.t >= 1.3:
                st["twist"] = 0.0
                self.phase, self.t = "ignite", 0.0
                s.events.append("ignite")
        elif self.phase == "ignite":                    # 轉旋鈕點火、打開蓋子
            st["knob"] = ease(clamp(self.t / 0.6, 0, 1))
            st["flame"] = ease(clamp((self.t - 0.2) / 0.5, 0, 1)) * (0.45 + 0.11 * s.dp.mk_heat)
            st["lid"] = ease(clamp((self.t - 0.4) / 0.6, 0, 1))
            if self.t >= 1.0:
                self.phase, self.t = "heat", 0.0
        elif self.phase == "heat":                      # 等下壺的水煮開（快轉）
            self.bt += dt * MOKA_K
            if self.bt >= self.heat_t:
                self.phase, self.t, self.flow_bt = "brew", 0.0, 0.0
                s.events.append("moka_start")
        elif self.phase in ("brew", "sputter"):
            bdt = dt * MOKA_K
            self.bt += bdt
            self.flow_bt += bdt
            k = clamp(self.flow_bt / self.flow_t, 0, 1)
            st["coffee"] = k
            st["gush"] = 0.35 + 0.65 * math.sin(math.pi * min(1.0, k / 0.85)) if k < 0.85 else 0.25
            if self.phase == "brew" and k >= 0.8:
                self.phase = "sputter"                  # 快噴完：咕嚕咕嚕、噴出蒸氣
                s.events.append("sputter")
            if self.phase == "sputter":
                st["sputter"] = clamp((k - 0.8) / 0.2, 0, 1)
            if k >= 1:
                self.phase, self.t = "off", 0.0
                s.events.append("flame_off")
        elif self.phase == "off":                       # 關火、蓋上蓋子
            st["knob"] = 1 - ease(clamp(self.t / 0.4, 0, 1))
            st["flame"] *= max(0.0, 1 - dt * 8)
            st["sputter"] = max(0.0, st["sputter"] - dt * 1.5)
            st["gush"] = max(0.0, st["gush"] - dt * 2)
            st["lid"] = 1 - ease(clamp((self.t - 0.3) / 0.5, 0, 1))
            if self.t >= 0.9 + 1 / ZOOM_SPEED:          # 等畫面拉遠、看得到杯子再倒
                st["flame"] = 0.0
                self.done = True

    def status(self, s):
        dp = s.dp
        clock = "{:d}:{:02d}".format(int(self.bt) // 60, int(self.bt) % 60)
        return {"setup": T("轉開摩卡壺、下壺加水…"),
                "grind": T("研磨 {g:.0f}g（{um:.0f}µm）…", g=dp.mk_dose, um=dp.mk_grind),
                "assemble": T("裝粉、鎖緊上壺…"),
                "ignite": T("點火（火力 {h:g}）…", h=dp.mk_heat),
                "heat": T("等水煮開…  {clock}", clock=clock),
                "brew": T("咖啡冒出來了…  {clock}", clock=clock),
                "sputter": T("咕嚕咕嚕…快好了  {clock}", clock=clock),
                "off": T("關火…")}[self.phase]


# ───────────── 虹吸壺時間軸 ─────────────
def idle_siphon():
    """虹吸壺沒在煮的時候：下壺裝好水、上壺插在上面、燈蓋著"""
    return {"lower": 0.8, "lower_coffee": 0.0, "upper": 0.0, "grounds": 0.0, "mixed": 0.0, "dome": 0.0,
            "boil": 0.0, "flame": 0.0, "paddle": 0.0, "stir": 0.0, "upper_alpha": 1.0, "upper_lift": 0.0,
            "catch": 0.0, "grinding": False}


class SiphonStage:
    """虹吸壺：研磨 → 點燈 → 下壺加熱冒泡 → 水被推上上壺 → 下粉 → 攪拌 → 浸泡 → 第二次攪拌、熄火
    → 咖啡被吸回下壺 → 拿掉上壺

    s.station：lower（下壺液量 0–1）、lower_coffee（下壺是咖啡的程度）、upper（上壺液量）、grounds（上壺的粉）、
    mixed（上壺液體變成咖啡的程度）、dome（抽完留在濾布上的粉）、boil（冒泡）、flame、paddle（攪拌棒）、stir（攪拌相位）"""
    name = "siphon"
    done = False
    LOW = 0.8                   # 下壺一開始的水位
    HEAT_T = 70.0               # 加熱到水被推上去的沖煮秒數（快轉）
    RISE_T = 2.4                # 水被推上去的時間（真實秒數）
    DOWN_T = 3.2                # 咖啡被吸回下壺的時間

    def start(self, s):
        self.phase, self.t, self.bt = "setup", 0.0, 0.0
        s.station = idle_siphon()

    @property
    def clock(self):
        return self.bt

    def update(self, s, dt):
        self.t += dt
        st = s.station
        if self.phase == "setup":
            if self.t >= 0.8:
                self.phase, self.t = "grind", 0.0
                s.events.append("grind")
        elif self.phase == "grind":                     # 先磨進接粉杯，水上去之後才下粉
            st["grinding"] = self.t < 1.4
            st["catch"] = ease(clamp(self.t / 1.3, 0, 1))
            if self.t >= 1.6:
                self.phase, self.t = "light", 0.0
                s.events.append("ignite")
        elif self.phase == "light":
            st["flame"] = ease(clamp(self.t / 0.6, 0, 1))
            if self.t >= 0.8:
                self.phase, self.t = "heat", 0.0
        elif self.phase == "heat":                      # 下壺加熱：先是小氣泡，越來越多
            self.bt += dt * SIPHON_K
            st["boil"] = clamp(self.bt / self.HEAT_T, 0, 1) ** 1.5
            if self.bt >= self.HEAT_T:
                self.phase, self.t = "rise", 0.0
                s.events.append("rise")
        elif self.phase == "rise":                      # 水沿著玻璃管被推上去
            k = ease(clamp(self.t / self.RISE_T, 0, 1))
            st["lower"] = lerp(self.LOW, 0.08, k)
            st["upper"] = k
            st["boil"] = 1.0
            if self.t >= self.RISE_T:
                self.phase, self.t = "add", 0.0
                s.events.append("tap")
        elif self.phase == "add":                       # 接粉杯的粉倒進上壺，浮在水面
            k = clamp(self.t / 0.7, 0, 1)
            st["catch"] = 1 - k
            st["grounds"] = k
            st["boil"] = 0.6
            if self.t >= 0.9:
                self.phase, self.t = "stir", 0.0
                s.events.append("stir")
        elif self.phase in ("stir", "stir2"):           # 攪拌棒繞圈
            st["paddle"] = min(1.0, st["paddle"] + dt * 5)
            st["stir"] += dt * 9
            st["mixed"] = min(1.0, st["mixed"] + dt * (0.55 if self.phase == "stir" else 0.3))
            if self.phase == "stir2":
                st["flame"] = max(0.0, st["flame"] - dt * 3)
            if self.t >= 1.4:
                st["paddle"] = 0.0
                if self.phase == "stir":
                    self.phase, self.t, self.steep_bt = "steep", 0.0, 0.0
                else:
                    st["flame"] = 0.0
                    self.phase, self.t = "drawdown", 0.0
                    s.events.append("drawdown")
        elif self.phase == "steep":                     # 浸泡（快轉）
            bdt = dt * SIPHON_K
            self.bt += bdt
            self.steep_bt += bdt
            st["mixed"] = min(1.0, max(st["mixed"], 0.75 + 0.25 * self.steep_bt / max(1.0, s.dp.sy_steep)))
            st["boil"] = 0.35
            if self.steep_bt >= s.dp.sy_steep:
                self.phase, self.t = "stir2", 0.0
                s.events.append("stir")
                s.events.append("flame_off")
        elif self.phase == "drawdown":                  # 熄火後下壺降溫，咖啡被吸回去；粉留在濾布上鼓成一座小山
            k = ease(clamp(self.t / self.DOWN_T, 0, 1))
            st["upper"] = 1 - k
            st["lower"] = lerp(0.08, self.LOW * 0.92, k)
            st["lower_coffee"] = clamp(k * 1.4, 0, 1)
            st["dome"] = k
            st["boil"] = max(0.0, st["boil"] - dt * 2)
            if self.t >= self.DOWN_T + 0.3:
                self.phase, self.t = "remove", 0.0
        elif self.phase == "remove":                    # 拿掉上壺
            k = clamp(self.t / 0.6, 0, 1)
            st["upper_lift"] = ease(k)
            st["upper_alpha"] = 1 - k
            if self.t >= 0.75 + 1 / ZOOM_SPEED:
                self.done = True

    def status(self, s):
        dp = s.dp
        clock = "{:d}:{:02d}".format(int(self.bt) // 60, int(self.bt) % 60)
        if self.phase == "steep":
            return T("浸泡中…  {t:.0f}/{b:.0f}s", t=self.steep_bt, b=dp.sy_steep)
        return {"setup": T("下壺加入 {g:.0f}g 熱水…", g=siphon_water(dp)),
                "grind": T("研磨 {g:.0f}g（{um:.0f}µm）…", g=dp.sy_dose, um=dp.sy_grind),
                "light": T("點燈…"),
                "heat": T("加熱下壺…  {clock}", clock=clock),
                "rise": T("水被推上上壺…"),
                "add": T("下粉…  {t:.0f}°C", t=dp.sy_temp),
                "stir": T("攪拌…"),
                "stir2": T("第二次攪拌、熄火…"),
                "drawdown": T("咖啡被吸回下壺…"),
                "remove": T("拿掉上壺…")}[self.phase]

