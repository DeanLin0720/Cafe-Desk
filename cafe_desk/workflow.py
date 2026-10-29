"""完整沖煮流程：取下把手 →（敲渣）→ 磨豆 → 布粉 → 填壓 → 裝回 → 扣上 → 交給萃取

這裡只算時間軸、物件位置與要播的音效事件，不碰繪圖；位置都是視窗座標。
"""
import math
import random

from .layout import PF_BASKET_W
from .util import clamp, lerp
from .i18n import T

HANDLE_FULL = 0.0           # 扣在沖煮頭時握把朝前（握把往右轉開的橫向位移，0＝正對觀看者）
HANDLE_OFF = 24.0           # 轉開時握把往右轉一點（約 24°）
HANDLE_FORK = 0.0           # 放在磨豆機上時握把也朝前
DROP = 7.0                  # 轉開時往下掉的距離

STATUS = {
    "unlock": "取下把手…",
    "to_knock": "敲掉粉渣…",
    "knock": "敲掉粉渣…",
    "to_fork": "移到磨豆機…",
    "grind": "磨豆中…",
    "distribute": "布粉…",
    "tamp": "填壓…",
    "to_group": "裝回沖煮頭…",
    "lock": "扣上把手…",
}


def ease(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def bump(k, center, width):
    """在 center 附近隆起一下（0→1→0），用在敲擊、輕拍的小抖動"""
    x = (k - center) / width
    return math.exp(-x * x * 4) if abs(x) < 1.5 else 0.0


def arc_move(a, b, k, lift):
    e = ease(k)
    return lerp(a[0], b[0], e), lerp(a[1], b[1], e) - lift * math.sin(math.pi * e)


class Workflow:
    def __init__(self, p, used_puck, machine):
        self.p = p
        self.m = machine
        PF_GROUP = machine.pf_group_scene
        self.FORK, self.KNOCK, self.TAMPER_REST = machine.fork, machine.knock, machine.tamper_rest
        self.grind_rate = 3.2 * (p.grind_um / 300.0) ** 0.5          # g/s，磨越細越慢
        steps = [("unlock", 0.7)]
        if used_puck:
            steps += [("to_knock", 0.9), ("knock", 1.2)]
        steps += [("to_fork", 1.0), ("grind", p.dose / self.grind_rate + 0.5), ("distribute", 1.2),
                  ("tamp", 1.6), ("to_group", 1.0), ("lock", 0.6)]
        self.steps = steps
        self.i = 0
        self.t = 0.0
        self.done = False
        self.events = []                 # 讓主視窗播音效的事件
        self._fired = set()

        self.group = PF_GROUP
        self.group_off = (PF_GROUP[0], PF_GROUP[1] + DROP)
        self.pf = {"x": PF_GROUP[0], "y": PF_GROUP[1], "handle": HANDLE_FULL, "tilt": 0.0}
        self.tamper = self.TAMPER_REST
        self.ground_g = 0.0              # 已磨出的粉量
        self.level = 0.0                 # 0＝尖尖的粉堆，1＝布平
        self.tamped = 0.0                # 0＝鬆，1＝壓實
        self.unevenness = clamp(1 - p.distribution / 100, 0, 1)
        self.has_puck = used_puck        # 把手裡還有上一杯的粉餅
        self.puck = None                 # 敲出後掉進敲渣盒的粉餅
        self.grinding = False
        self._from = self.group_off
        self._from_handle, self._from_tilt = HANDLE_OFF, 0.0

    # ───────────── 查詢 ─────────────
    @property
    def name(self):
        return self.steps[self.i][0] if not self.done else "done"

    def status(self):
        n = self.name
        if n == "grind":
            return T("磨豆中…  {g:.1f} g", g=self.ground_g)
        return T(STATUS.get(n, ""))

    @property
    def grounds_visible(self):
        """濾杯裡看得到的咖啡粉（g）"""
        return self.ground_g

    # ───────────── 推進 ─────────────
    def fire(self, tag):
        key = (self.i, tag)
        if key not in self._fired:
            self._fired.add(key)
            self.events.append(tag)

    def update(self, dt):
        if self.done:
            return
        self.t += dt
        name, dur = self.steps[self.i]
        k = clamp(self.t / dur, 0, 1)
        getattr(self, "_" + name)(k)
        self._update_puck(dt)
        if self.t >= dur:
            self._from = (self.pf["x"], self.pf["y"])
            self._from_handle, self._from_tilt = self.pf["handle"], self.pf["tilt"]
            self.i += 1
            self.t = 0.0
            if self.i >= len(self.steps):
                self.done = True
                self.grinding = False

    # ───────────── 各步驟 ─────────────
    def _unlock(self, k):
        e = ease(k)
        self.pf.update(x=self.group[0], y=lerp(self.group[1], self.group_off[1], e),
                       handle=lerp(HANDLE_FULL, HANDLE_OFF, e), tilt=0.0)
        if k > 0.08:
            self.fire("lock")

    def _to_knock(self, k):
        PF_KNOCK = self.KNOCK
        x, y = arc_move(self._from, PF_KNOCK, k, 30)
        self.pf.update(x=x, y=y, handle=lerp(HANDLE_OFF, HANDLE_FORK, ease(k)), tilt=lerp(0, -24, ease(k)))

    def _knock(self, k):
        PF_KNOCK = self.KNOCK
        jerk = 5 * bump(k, 0.25, 0.12) + 5 * bump(k, 0.6, 0.12)
        self.pf.update(x=PF_KNOCK[0], y=PF_KNOCK[1] + jerk, handle=HANDLE_FORK, tilt=-24 - jerk)
        if k > 0.25:
            self.fire("knock")
        if k > 0.6:
            self.fire("knock2")
            if self.has_puck:
                self.has_puck = False
                cx = PF_KNOCK[0] + PF_BASKET_W / 2
                self.puck = {"x": cx, "y": PF_KNOCK[1] + 6, "vx": random.uniform(-8, 8),
                             "vy": 30.0, "rot": -24.0, "vr": random.uniform(-90, 90)}

    def _to_fork(self, k):
        PF_FORK = self.FORK
        x, y = arc_move(self._from, PF_FORK, k, 26)
        self.pf.update(x=x, y=y, handle=lerp(self._from_handle, HANDLE_FORK, ease(k)),
                       tilt=lerp(self._from_tilt, 0.0, ease(k)))

    def _grind(self, k):
        PF_FORK = self.FORK
        self.pf.update(x=PF_FORK[0], y=PF_FORK[1], handle=HANDLE_FORK, tilt=0.0)
        t = k * self.steps[self.i][1]
        self.grinding = t < self.p.dose / self.grind_rate + 0.2
        if self.grinding:
            self.fire("grind_start")
            self.ground_g = min(self.p.dose, self.grind_rate * max(0.0, t - 0.2))
        else:
            self.ground_g = self.p.dose
            self.fire("grind_stop")

    def _distribute(self, k):
        PF_FORK = self.FORK
        tap = 2.0 * bump(k, 0.3, 0.1) + 2.0 * bump(k, 0.65, 0.1)
        self.pf.update(x=PF_FORK[0], y=PF_FORK[1] + tap, handle=HANDLE_FORK, tilt=0.0)
        self.level = ease(k)
        if k > 0.3:
            self.fire("tap")
        if k > 0.65:
            self.fire("tap2")

    def _tamp(self, k):
        PF_FORK, TAMPER_REST = self.FORK, self.TAMPER_REST
        cx = PF_FORK[0] + PF_BASKET_W / 2
        above = (cx, PF_FORK[1] - 30)
        on_top = (cx, PF_FORK[1] - 2)
        pressed = (cx, PF_FORK[1] + 1.5)
        if k < 0.35:
            self.tamper = arc_move(TAMPER_REST, above, k / 0.35, 20)
        elif k < 0.5:
            self.tamper = arc_move(above, on_top, (k - 0.35) / 0.15, 0)
        elif k < 0.62:
            e = ease((k - 0.5) / 0.12)
            self.tamper = (cx, lerp(on_top[1], pressed[1], e))
            self.tamped = e
            if k > 0.56:
                self.fire("tamp")
        elif k < 0.72:
            self.tamper = arc_move(pressed, above, (k - 0.62) / 0.1, 0)
        else:
            self.tamper = arc_move(above, TAMPER_REST, (k - 0.72) / 0.28, 20)
        self.pf.update(x=PF_FORK[0], y=PF_FORK[1], handle=HANDLE_FORK, tilt=0.0)

    def _to_group(self, k):
        x, y = arc_move(self._from, self.group_off, k, 34)
        self.pf.update(x=x, y=y, handle=lerp(HANDLE_FORK, HANDLE_OFF, ease(k)), tilt=0.0)

    def _lock(self, k):
        e = ease(k)
        self.pf.update(x=self.group[0], y=lerp(self.group_off[1], self.group[1], e),
                       handle=lerp(HANDLE_OFF, HANDLE_FULL, e), tilt=0.0)
        if k > 0.85:
            self.fire("lock")

    def _update_puck(self, dt):
        pk = self.puck
        if not pk:
            return
        pk["vy"] += 500 * dt
        pk["x"] += pk["vx"] * dt
        pk["y"] += pk["vy"] * dt
        pk["rot"] += pk["vr"] * dt
        if pk["y"] > self.m.puck_floor:  # 掉進敲渣盒
            self.puck = None
            self.events.append("thud")
