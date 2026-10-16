"""粒子：滴落、水花、漣漪、蒸氣"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QRadialGradient

from ..gfx import C
from ..util import clamp, lerp


class ParticleSystem:
    def update_particles(self, dt, sdt):
        s = self.shot
        surf = self.surface_y()
        cup, m = self.cup, self.machine
        SPOUTS, SPOUT_Y = m.spouts, m.spout_y

        def spawn(x, y, vx=0.0, vy=20.0, size=2.0, spray=False):
            self.drops.append({"x": x, "y": y, "vx": vx, "vy": vy, "size": size, "spray": spray,
                               "col": self.stream_color(s.progress)})

        self.update_bubbles(sdt)

        if s and s.phase == "brew" and s.t > s.t_drip - 1.0 and s.flow < 0.55:
            for sx in SPOUTS:
                if random.random() < (0.05 + s.flow * 0.35) * sdt * 60:
                    spawn(sx + random.uniform(-0.8, 0.8), SPOUT_Y + 1)
        if s and s.phase == "tail" and s.flow < 0.55:
            rate = 0.10 * max(0.0, 1 - (s.t - s.t_stop) / 2.8)
            for sx in SPOUTS:
                if random.random() < rate * sdt * 60:
                    spawn(sx + random.uniform(-0.8, 0.8), SPOUT_Y + 1)
        if s and s.phase == "brew" and s.flow > 0.55 and s.res.channeling > 0.18:
            if random.random() < s.res.channeling * 0.3 * sdt * 60:
                spawn(random.choice(SPOUTS), SPOUT_Y + 3, vx=random.uniform(-50, 50),
                      vy=random.uniform(0, 35), size=1.2, spray=True)

        alive = []
        for d in self.drops:
            d["vy"] += 600 * sdt
            d["x"] += d["vx"] * sdt
            d["y"] += d["vy"] * sdt
            l, r = cup.cup_x(min(max(d["y"], cup.T), cup.B))
            if d["y"] >= surf and l < d["x"] < r:
                self.ripples.append({"x": d["x"], "y": surf, "age": 0.0, "life": 0.7, "r": 10})
                for _ in range(random.randint(2, 4)):
                    self.splash.append({"x": d["x"], "y": surf, "vx": random.uniform(-35, 35),
                                        "vy": random.uniform(-110, -55), "col": d["col"]})
                if not d.get("spray") and not any(st["head"] > 0 for st in self.stream):
                    self.sound.drip()
                continue
            if d["y"] > cup.B + 40:
                continue
            alive.append(d)
        self.drops = alive

        alive = []
        for p in self.splash:
            p["vy"] += 600 * sdt
            p["x"] += p["vx"] * sdt
            p["y"] += p["vy"] * sdt
            if p["y"] <= surf + 1:
                alive.append(p)
        self.splash = alive

        # 流柱落點持續產生漣漪
        if s and s.phase == "brew" and any(st["head"] >= 1 for st in self.stream):
            self._ripple_clock += sdt
            if self._ripple_clock > 0.12:
                self._ripple_clock = 0.0
                self.ripples.append({"x": cup.CX + random.uniform(-2, 2), "y": surf,
                                     "age": 0.0, "life": 0.6, "r": 14})
        for rp in self.ripples:
            rp["age"] += sdt
            rp["y"] = surf
        self.ripples = [r for r in self.ripples if r["age"] < r["life"]]

        # 蒸氣
        intensity = 0.0
        from ..drinks import DRINKS
        if not DRINKS[self.drink_kind()]["hot"]:
            s = None                                    # 冰飲不冒煙
        if s and s.phase == "done":
            age = time.perf_counter() - s.done_clock
            intensity = max(0.0, 1 - age / 150) * min(1.0, age / 2 + 0.4)
        elif s and s.weight > 15:
            intensity = 0.35
        self.steam_intensity = intensity
        if intensity > 0.02 and random.random() < 9 * intensity * dt:
            self.steam.append({"x": cup.CX + random.uniform(-20, 20), "y": cup.T - 2,
                               "vx": random.uniform(-3, 3), "vy": random.uniform(-16, -10),
                               "age": 0.0, "life": random.uniform(3.5, 5.5),
                               "ph": random.random() * 6.28})
        for p in self.steam:
            p["age"] += dt
            p["x"] += (p["vx"] + 5 * math.sin(self.anim_t * 1.3 + p["ph"])) * dt
            p["y"] += p["vy"] * dt
        self.steam = [p for p in self.steam if p["age"] < p["life"]]

    def paint_particles(self, p):
        p.setPen(Qt.NoPen)
        for d in self.drops:
            sz = d["size"]
            p.setBrush(C(d["col"]))
            p.drawEllipse(QPointF(d["x"], d["y"]), sz * 0.8, sz * 1.15)
            p.setBrush(C("#ffffff", 90))
            p.drawEllipse(QPointF(d["x"] - sz * 0.25, d["y"] - sz * 0.3), sz * 0.25, sz * 0.3)
        for sp in self.splash:
            p.setBrush(C(sp["col"], 220))
            p.drawEllipse(QPointF(sp["x"], sp["y"]), 0.9, 0.9)

    def paint_steam(self, p):
        p.setPen(Qt.NoPen)
        k = getattr(self, "steam_intensity", 0.0)
        for s in self.steam:
            a = s["age"] / s["life"]
            if a <= 0:
                continue
            size = lerp(s.get("s0", 5), s.get("s1", 22), a)
            alpha = s.get("boost", 46 * max(k, 0.25)) * math.sin(math.pi * a)
            g = QRadialGradient(s["x"], s["y"], size)
            g.setColorAt(0, C("#f2ede6", alpha))
            g.setColorAt(1, C("#f2ede6", 0))
            p.setBrush(g)
            p.drawEllipse(QPointF(s["x"], s["y"]), size, size)

    # ───────────── crema 氣泡 ─────────────
    def update_bubbles(self, sdt):
        s = self.shot
        if not s:
            return
        co2 = max(0.0, 5 - s.p.bean_age) / 5
        fresh = clamp(1 - (s.p.bean_age - 5) / 30, 0, 1)
        if s.phase in ("brew", "tail") and s.flow > 0.2 and s.weight > 2 and len(self.bubbles) < 70:
            rate = (3 + 9 * co2 + 4 * fresh) * s.flow
            if random.random() < rate * sdt:
                self.bubbles.append({"r": random.uniform(0.0, 0.35), "th": random.uniform(0, 6.283),
                                     "size": random.uniform(0.5, 1.3) * (1 + 0.6 * co2),
                                     "age": 0.0, "life": random.uniform(4, 45) * (0.5 + fresh), "pop": 0.0})
        push = s.flow if s.phase in ("brew", "tail") else 0.0
        alive = []
        for b in self.bubbles:
            b["age"] += sdt
            b["r"] = min(0.92, b["r"] + 0.06 * push * sdt)       # 被流柱往外推
            if b["age"] > b["life"]:
                b["pop"] += sdt / 0.25
            if b["pop"] < 1.0:
                alive.append(b)
        self.bubbles = alive

    # ───────────── 待機時的小動靜 ─────────────
    def idle_event(self):
        """洩壓口放一口氣，或出水口滴下一滴水"""
        if random.random() < 0.6:
            vx, vy = self.machine.vent
            for i in range(7):
                self.steam.append({"x": vx + random.uniform(-1, 1), "y": vy - 2, "vx": random.uniform(4, 14),
                                   "vy": random.uniform(-38, -24), "age": -i * 0.05, "life": random.uniform(1.0, 1.6),
                                   "ph": random.random() * 6.28, "boost": 70, "s0": 2, "s1": 12})
            self.sound.once("hiss", 0.3)
        else:
            sx = random.choice(self.machine.spouts)
            self.drops.append({"x": sx + random.uniform(-0.6, 0.6), "y": self.machine.spout_y + 1, "vx": 0.0, "vy": 15.0,
                               "size": 1.8, "spray": False, "col": "#cfdde6", "idle": True})

