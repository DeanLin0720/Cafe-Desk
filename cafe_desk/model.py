"""萃取模型（簡化、只求合理）、單杯時間軸、自動模式的咖啡師"""
import math
import random
import time
from dataclasses import dataclass, asdict

from .i18n import T
from .beans import sweet_bonus
from .util import clamp

ROASTS = {
    "淺焙": {"ey_max": 23.0, "sol": 0.85, "target": (19.5, 22.5)},
    "中焙": {"ey_max": 25.0, "sol": 1.00, "target": (18.5, 21.5)},
    "深焙": {"ey_max": 26.0, "sol": 1.15, "target": (17.5, 20.5)},
}


TDS_TARGET = (8.0, 12.0)

# 濃縮變化的評分基準：Ristretto 短萃（萃取率低一點、濃度高）、Lungo 長萃（濃度低、萃取率可以高一點）
STYLES = {
    "ristretto": {"name": "Ristretto", "ey": -2.0, "tds": (11.0, 16.0)},
    "lungo": {"name": "Lungo", "ey": 1.5, "tds": (5.0, 8.5)},
}


def style_targets(roast, style=None):
    """(萃取率目標下限, 上限, TDS 目標)"""
    lo, hi = ROASTS[roast]["target"]
    st = STYLES.get(style)
    if st:
        return lo + st["ey"], hi + st["ey"], st["tds"]
    return lo, hi, TDS_TARGET


@dataclass
class Params:
    grind_um: float = 300.0
    dose: float = 18.0
    yield_g: float = 36.0
    temp: float = 93.0
    pressure: float = 9.0
    preinfusion: float = 0.0
    distribution: float = 80.0
    bean_age: float = 10.0
    basket: float = 18.0
    roast: str = "中焙"
    origin: str = ""             # 豆子產地（beans.ORIGINS 的 key），影響甜感

    def copy(self):
        return Params(**asdict(self))


@dataclass
class Result:
    time: float
    ey: float
    tds: float
    channeling: float
    sweetness: float
    score: float


def simulate(p: Params, traits=None, temp_shift=0.0, style=None) -> Result:
    """traits：咖啡機特性（水溫偏差、拉桿壓力曲線、研磨均勻度…）；temp_shift：這一杯的水溫隨機偏差；
    style：濃縮變化（ristretto／lungo），只影響評分基準"""
    r = ROASTS[p.roast]
    temp = p.temp + temp_shift + (traits.temp_offset if traits else 0.0)
    pressure = min(p.pressure, traits.pressure_cap) if traits else p.pressure
    lever = bool(traits and traits.profile == "lever")
    if lever:
        pressure *= 0.78                     # 彈簧推動：壓力從峰值一路遞減，平均較低
    fine = 300.0 / p.grind_um
    ratio = p.yield_g / p.dose
    co2 = max(0.0, 5 - p.bean_age) / 5
    stale = clamp((p.bean_age - 21) / 40, 0, 1)

    pi_n = min(p.preinfusion, 10) / 10
    mismatch = abs(p.dose - p.basket) / p.basket
    channel = ((1 - p.distribution / 100) * 0.45
               + max(0.0, pressure - 9) * 0.03
               + max(0.0, 220 - p.grind_um) / 100 * 0.25
               + max(0.0, mismatch - 0.08) * 1.2
               + co2 * 0.12)
    if traits:
        channel += traits.channel_add - (0.04 if lever else 0.0)
    channel = clamp(channel * (1 - 0.45 * pi_n), 0, 0.7)

    resistance = (p.dose / 18) * fine ** 2.2 * (1 + 0.25 * co2) * (1 - 0.15 * stale)
    flow = 1.3 * (pressure / 9) ** 0.6 / resistance * (1 + 0.8 * channel)
    t = p.yield_g / flow + p.preinfusion

    drive = (fine * math.exp((temp - 93) / 15) * (ratio / 2) ** 0.55
             * (t / 28) ** 0.25 * (pressure / 9) ** 0.1)
    ey = r["ey_max"] * (1 - math.exp(-1.609 * r["sol"] * drive)) * (1 - 0.35 * channel)
    tds = ey * p.dose / p.yield_g

    lo, hi, tds_target = style_targets(p.roast, style)
    dev = ey - (lo + hi) / 2
    sweet = clamp(8.5 - abs(dev) * 1.3 - channel * 6 - stale * 2 + (traits.sweet_add if traits else 0.0)
                  + sweet_bonus(p.origin))

    def band(x, a, b, slope):
        return max(0.0, 100 - (a - x) * slope) if x < a else \
               max(0.0, 100 - (x - b) * slope) if x > b else 100.0

    score = (0.40 * band(ey, lo, hi, 15) + 0.25 * band(tds, *tds_target, 10)
             + 0.35 * sweet * 10 - channel * 40 - stale * 10)
    return Result(t, ey, tds, channel, sweet, clamp(score, 0, 100))


def shot_comment(res: Result, p: Params, style=None) -> str:
    lo, hi, tds_target = style_targets(p.roast, style)
    if res.channeling > 0.25:
        return T("有通道效應，酸苦混雜")
    if res.ey < lo - 1.5:
        return T("萃取不足，偏酸單薄")
    if res.ey < lo:
        return T("略酸，明亮但收尾短")
    if res.ey > hi + 1.5:
        return T("過度萃取，苦澀乾口")
    if res.ey > hi:
        return T("略苦，尾韻偏乾")
    if res.tds < tds_target[0]:
        return T("平衡但偏淡")
    if res.tds > tds_target[1]:
        return T("濃郁厚重")
    return T("甜感飽滿、平衡乾淨")


class Shot:
    """把模擬結果展開成時間軸：預浸泡 → 加壓 → 滴落 → 流柱 → 收尾 → 完成"""

    def __init__(self, p: Params, traits=None, style=None):
        self.p = p
        self.traits = traits
        self.style = style
        self.preset = False      # 這一杯的粉量／液重是飲品預設（不是使用者參數）
        self.lever = bool(traits and traits.profile == "lever")
        self.temp_shift = random.gauss(0, traits.temp_noise) if traits and traits.temp_noise > 0 else 0.0
        self.res = simulate(p, traits, self.temp_shift, style)
        fine = 300.0 / p.grind_um
        # 拉桿機：拉下拉桿時一定有一段低壓預浸
        self.t_pi = max(p.preinfusion, 3.0) if self.lever else p.preinfusion
        self.t_drip = self.t_pi + min(9.0, 2.0 + 3.0 * fine ** 2)
        self.t_end = max(self.res.time, self.t_drip + 4)
        dur = self.t_end - self.t_drip
        self.ramp = min(3.0, dur * 0.3)
        self.base_flow = p.yield_g / (dur - self.ramp / 2)
        lo, hi = ROASTS[p.roast]["target"]
        self.blond_at = clamp(0.72 - (self.res.ey - (lo + hi) / 2) * 0.06, 0.4, 0.9)
        self.t = 0.0
        self.weight = 0.0
        self.flow = 0.0
        self.phase = "brew"
        self.t_stop = None
        self.done_clock = None
        self.log = []           # (時間, 壓力, 流速, 重量)，給數據卡片用

    TAPER = 0.45            # 幫浦停止後流速衰減的時間常數（秒）

    def update(self, dt):
        self.t += dt
        if self.phase == "brew":
            if self.t >= self.t_drip:
                x = self.t - self.t_drip
                self.flow = self.base_flow * min(1.0, x / self.ramp) * (0.92 + 0.16 * self.progress)
                if self.lever:                       # 彈簧壓力遞減，流速跟著前快後慢
                    self.flow *= 1.18 - 0.36 * self.progress
            else:
                self.flow = 0.0
            self.weight += self.flow * dt
            # 提早關幫浦：剩下的量由逐漸變細的流柱補上，最後重量才會剛好到目標
            if self.weight >= self.p.yield_g - self.flow * self.TAPER or self.t > self.t_end + 6:
                self.phase, self.t_stop = "tail", self.t
        elif self.phase == "tail":
            self.flow *= math.exp(-dt / self.TAPER)
            if self.flow < 0.05:
                self.flow = 0.0
            self.weight = min(self.weight + self.flow * dt + 0.08 * dt, self.p.yield_g + 0.6)
            if self.t - self.t_stop > 2.8:
                self.phase, self.flow = "done", 0.0
                self.done_clock = time.perf_counter()

    @property
    def progress(self):
        return min(1.0, self.weight / self.p.yield_g)

    @property
    def timer(self):
        return self.t_stop if self.t_stop is not None else self.t

    def pressure_target(self):
        if self.phase != "brew":
            return 0.0
        if self.lever:
            if self.t < self.t_pi:
                return 1.2 * min(1.0, self.t / 0.6)            # 只有鍋爐水壓
            peak = min(self.p.pressure, self.traits.pressure_cap)
            rise = min(1.0, (self.t - self.t_pi) / 0.6)
            return peak * rise * (1 - 0.55 * self.progress)
        if self.t < self.t_pi:
            return 2.5 * min(1.0, self.t / 1.0)
        base = 2.5 if self.t_pi > 0 else 0.0
        peak = min(self.p.pressure, self.traits.pressure_cap) if self.traits else self.p.pressure
        target = base + (peak - base) * min(1.0, (self.t - self.t_pi) / 2.0)
        if self.t > self.t_drip:
            target *= 1 - 0.1 * self.progress
        return target

    def lever_pos(self):
        """拉桿位置：0＝豎起，1＝壓到底"""
        if self.phase != "brew":
            return 0.0
        if self.t < self.t_pi:
            return min(1.0, self.t / 0.5)
        return max(0.0, 1 - self.progress) * 0.92

    def stage(self):
        if self.phase == "brew":
            if self.t < self.t_pi:
                return T("拉下拉桿，預浸泡中…" if self.lever else "預浸泡中…")
            if self.t < self.t_drip:
                return T("加壓中…")
            return T("萃取中…")
        if self.phase == "tail":
            return T("收尾滴落…")
        return None



class Barista:
    """自動模式的咖啡師：記錄這包豆子沖了幾杯、連續幾杯好喝"""

    def __init__(self):
        self.shots_on_bag = 0
        self.good_streak = 0
        self.skill = 1.0                # 熟練度的手感誤差倍率（growth.skill），desk 會更新

    def shake_up(self, p):
        """換一包豆子或連續好杯後：依烘焙度重新設定起始參數"""
        p.grind_um = float(random.randrange(220, 400, 5))
        p.temp = {"淺焙": 94.0, "中焙": 93.0, "深焙": 91.0}[p.roast] + random.choice((-1, 0, 1))
        p.preinfusion = float(random.choice((0, 0, 4, 6)))
        p.distribution = float(random.randrange(55, 90, 5))
        self.shots_on_bag = self.good_streak = 0

    def dial_in(self, p, shot):
        """依上一杯的結果調整參數（直接修改 p），連續好杯或沖太多杯就換一包新豆子"""
        if shot is None:
            return
        res, sp = shot.res, shot.p
        lo, hi, _ = style_targets(sp.roast, shot.style)
        self.shots_on_bag += 1
        self.good_streak = self.good_streak + 1 if res.score >= 85 else 0
        if self.good_streak >= 3:
            self.shake_up(p)                 # 連續好杯：換個手法重新找參數，畫面才有變化
            return
        if res.ey < lo:
            p.grind_um -= random.choice((10, 15, 20)) if res.ey < lo - 2 else 5
            if sp.roast == "淺焙" and p.temp < 96:
                p.temp += 1
        elif res.ey > hi:
            p.grind_um += random.choice((10, 15)) if res.ey > hi + 2 else 5
            if sp.roast == "深焙" and p.temp > 88:
                p.temp -= 1
        if shot.style or shot.preset:                # 濃縮變化、馥列白等固定比例：不拿來調液重
            pass
        elif res.tds < TDS_TARGET[0]:
            p.yield_g = max(p.dose * 1.5, p.yield_g - 3)
        elif res.tds > TDS_TARGET[1]:
            p.yield_g = min(p.dose * 3, p.yield_g + 3)
        if res.channeling > 0.2:
            p.distribution = min(95.0, p.distribution + 15)
            p.preinfusion = max(p.preinfusion, 5.0)
        p.distribution = clamp(p.distribution + random.uniform(-8, 4) * self.skill, 40, 100)
        p.grind_um = clamp(p.grind_um, 160, 480)
        p.bean_age += 1


class Boiler:
    """鍋爐水溫：加熱器有遲滯開關（會發出繼電器聲），萃取時被冷水帶走熱量而下降"""

    HEAT = 0.45             # 加熱器全開時每秒升溫
    DRAW = 0.25             # 每 1 g/s 流量每秒降溫（一杯約掉 1°C）
    LOSS = 0.0015           # 自然散熱係數

    def __init__(self, setpoint):
        self.temp = setpoint
        self.heater = False

    def update(self, dt, setpoint, flow):
        """回傳 True 表示這一步加熱器切換了（可播繼電器聲）"""
        switched = False
        if self.heater and self.temp > setpoint + 0.15:
            self.heater, switched = False, True
        elif not self.heater and self.temp < setpoint - 0.45:
            self.heater, switched = True, True
        heat = self.HEAT if self.heater else 0.0
        self.temp += (heat - self.DRAW * flow - self.LOSS * (self.temp - 25)) * dt
        return switched
