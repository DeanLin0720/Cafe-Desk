"""手沖與冰滴：萃取模型、器具時間軸（Stage）、冰滴的背景批次

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
from .util import clamp
from .workflow import ease, arc_move

TIME_K = 3.0                  # 手沖畫面快轉倍數
POUR_RATE = 6.0               # 手沖壺注水速度（g／沖煮秒）
BLOOM_K = 2.5                 # 悶蒸水量＝粉量 × BLOOM_K
RETAIN_K = 2.0                # 咖啡粉吸住的水＝粉量 × RETAIN_K
TDS_POUR = (1.15, 1.45)       # 手沖的濃度目標（%）
TDS_COLD = (1.3, 1.9)
COLD_DUR = 3600.0             # 冰滴在畫面上滴多久（真實秒數）
COLD_SERVINGS = 4
COLD_SERVE_G = 100.0          # 每杯冰滴倒多少

# 沖煮方式：espresso＝義式咖啡機（machines/），其他兩種是獨立畫面
METHODS = {"espresso": "義式咖啡機", "pourover": "手沖", "colddrip": "冰滴"}
# 獨立畫面的版面：視窗跟目前的咖啡機一樣寬；器具用「器具座標」畫，再以檯面左端為基準放大 GEAR_K 倍
# （render/station.py 的 gear_to_scene）。杯子不放大，放在離右緣 CUP_RIGHT 的地方，右邊留位置給倒咖啡時傾斜的壺。
GEAR_K = {"pourover": 1.4, "colddrip": 1.3}     # 冰滴塔很高，放大少一點才不會超出畫面
GRINDER_X = 8                 # 手沖用磨豆機左緣（器具座標，下同）
PO_STAND_X = 100              # 濾杯與分享壺的中心
CD_TOWER_X = 84               # 冰滴塔左緣（塔寬 86）
CUP_RIGHT = {"pourover": 135, "colddrip": 130}  # 成品杯中心到視窗右緣（場景座標）
# 沖煮時拉近：磨豆機與杯子淡出，沖煮器具放大到 GEAR_ZOOM 倍、移到視窗中央（FOCUS_X 是器具座標的中心）；
# 沖完拉遠再倒進杯子。冰滴塔很高，拉近時頂端會伸進上方的透明區
GEAR_ZOOM = {"pourover": 3.0, "colddrip": 1.6}
FOCUS_X = {"pourover": PO_STAND_X + 14, "colddrip": CD_TOWER_X + 43}
ZOOM_SPEED = 1.6              # 拉近／拉遠的速度（每秒，0–1）
FOCUS_PHASES = {"pourover": ("kettle_in", "bloom_pour", "bloom", "pulse", "wait", "drawdown"),
                "colddrip": ("water", "valve")}


def _band(x, a, b, slope):
    return max(0.0, 100 - (a - x) * slope) if x < a else max(0.0, 100 - (x - b) * slope) if x > b else 100.0


def pourover_time(dp):
    """手沖總時間（秒）：研磨越細、水越多、段數越多越久"""
    fine = 650.0 / dp.po_grind
    water = dp.po_dose * dp.po_ratio
    return dp.po_bloom + 110 * fine ** 1.6 * (water / 240) ** 0.7 + 8 * (dp.po_pulses - 1)


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
    uneven = clamp(uneven, 0, 0.6)
    drive = (fine ** 0.8 * math.exp((dp.po_temp - 93) / 12) * (t / 180) ** 0.35 * (dp.po_ratio / 16) ** 0.3
             * (0.88 + 0.12 * bloom_ok))
    ey = r["ey_max"] * (1 - math.exp(-1.35 * r["sol"] * drive)) * (1 - 0.3 * uneven)
    beverage = dp.po_dose * (dp.po_ratio - RETAIN_K)
    tds = ey * dp.po_dose / max(1.0, beverage)
    lo, hi = r["target"]
    sweet = clamp(8.5 - abs(ey - (lo + hi) / 2) * 1.3 - uneven * 6 - stale * 2 + sweet_bonus(origin))
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
    uneven = clamp(max(0.0, 400 - dp.cd_grind) / 200 * 0.3 + max(0.0, dp.cd_rate - 16) * 0.02, 0, 0.5)
    drive = fine ** 0.8 * (hours / 6) ** 0.4 * (dp.cd_ratio / 10) ** 0.3
    ey = r["ey_max"] * 0.85 * (1 - math.exp(-1.7 * r["sol"] * drive)) * (1 - 0.3 * uneven)
    beverage = dp.cd_dose * (dp.cd_ratio - RETAIN_K)
    tds = ey * dp.cd_dose / max(1.0, beverage)
    lo, hi = r["target"][0] - 2.0, r["target"][1] - 2.0             # 冷萃萃取率低一點也好喝
    sweet = clamp(8.8 - abs(ey - (lo + hi) / 2) * 1.2 - uneven * 6 - stale * 2 + sweet_bonus(origin))
    score = (0.40 * _band(ey, lo, hi, 15) + 0.25 * _band(tds, *TDS_COLD, 80)
             + 0.35 * sweet * 10 - uneven * 40 - stale * 10)
    return Result(hours * 3600, ey, tds, uneven, sweet, clamp(score, 0, 100))


def brew_comment(res, roast, tds_target):
    lo, hi = ROASTS[roast]["target"]
    if res.channeling > 0.2:
        return T("萃取不均，味道混濁")
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
    return T("乾淨明亮、甜感飽滿")


# 自動模式／營業模式的咖啡師：依烘焙度調手沖與冰滴（淺焙磨細、水溫高；深焙磨粗、水溫低）。手動沖煮照使用者的設定
BARISTA = {"淺焙": dict(po_grind=500, po_temp=96, cd_grind=440, cd_ratio=11, cd_rate=7),
           "中焙": dict(po_grind=580, po_temp=93, cd_grind=500, cd_ratio=11, cd_rate=10),
           "深焙": dict(po_grind=700, po_temp=91, cd_grind=700, cd_ratio=11, cd_rate=12)}


def barista_dial(dp, roast, rnd=random):
    """咖啡師這一杯的手沖／冰滴參數（單杯副本，不寫回使用者設定）；每杯手感有些誤差"""
    d = dp.copy()
    for k, v in BARISTA.get(roast, BARISTA["中焙"]).items():
        setattr(d, k, v)
    d.po_grind = clamp(d.po_grind + rnd.gauss(0, 15), 400, 1000)
    d.po_temp = clamp(d.po_temp + rnd.gauss(0, 0.7), 85, 100)
    d.po_bloom = clamp(35 + rnd.gauss(0, 4), 20, 60)
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
        s.station = idle_pourover(s.app)
        k = s.station["kettle"]
        self.rest = (k["x"], k["y"])

    @property
    def clock(self):
        """沖煮時間（從第一次注水開始算）"""
        return self.bt

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
            k["tilt"] = 32 * ease(kk)
            if kk >= 1:
                self.phase, self.t, self.poured = "bloom_pour", 0.0, 0.0
                k["pour"] = 1.0
                s.events.append("kettle_start")
        elif self.phase in ("bloom_pour", "pulse"):
            bdt = dt * TIME_K
            self.bt += bdt
            amount = self.bloom_g if self.phase == "bloom_pour" else self.pulses[0]
            k["pour"] = 1.0
            k["tilt"] = 32 + 8 * clamp(self.poured / max(1.0, amount), 0, 1)
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
            k["tilt"] = max(18.0, k["tilt"] - 40 * dt)
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
            k["tilt"] = max(18.0, k["tilt"] - 40 * dt)
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
            k["tilt"] = 18 * (1 - ease(kk))
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

