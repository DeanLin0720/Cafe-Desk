"""杯中液體、crema、流柱"""
import math
import time

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QLinearGradient, QRadialGradient, QPen, QPainterPath, QPolygonF

from ..gfx import mix, C, vgrad
from ..drinks import base_of
from ..layout import C_DARK, C_MID, C_TIGER, ROAST_LOOK, liquid_look
from ..model import ROASTS
from ..util import clamp, lerp


class LiquidRenderer:
    def surface_y(self):
        y = self.cup.level_y(self.cup_volume())
        if self.icecream and self.icecream["landed"]:          # 阿芙佳朵：濃縮落在冰淇淋頂端
            x, by, r, sy = self.affogato_ball()
            return min(y, by - r * sy)
        return y

    def liquid_surface_y(self):
        return self.cup.level_y(self.cup_volume())

    def crema_max(self, p):
        if p.bean_age < 5:
            return 7.5
        if p.bean_age <= 14:
            return 5.5
        return lerp(5.5, 2.0, min(1.0, (p.bean_age - 14) / 40))

    def update_crema(self, dt, sdt):
        s = self.shot
        if not s:
            return
        cm = self.crema_max(s.p)
        if s.phase == "brew":
            prog = s.progress
            base = cm * min(1.0, s.weight / 10)
            bloom = 0.7 * cm * math.sin(math.pi * min(1.0, prog / 0.7)) if prog < 0.7 else 0.0
            target = base + bloom
        elif s.phase == "tail":
            target = cm
        else:
            settle = min(1.0, (time.perf_counter() - s.done_clock) / 90)
            target = cm * (1 - 0.3 * settle)
        level_h = self.cup.liquid_bottom - self.surface_y()
        target = min(target, level_h * 0.55)
        self.crema_h += (target - self.crema_h) * min(1.0, dt * 2.0)
        self.swirl += sdt * (0.15 + 0.5 * (s.flow if s.phase == "brew" else 0.0))

    def surface_geom(self):
        ly = self.liquid_surface_y()
        l, r = self.cup.cup_x(ly)
        rx = (r - l) / 2
        return ly, (l + r) / 2, rx, rx * 0.11

    def stream_color(self, prog, offset=0.0):
        s = self.shot
        look = ROAST_LOOK[s.p.roast]
        if prog < 0.25:
            base = mix(C_DARK, C_MID, prog / 0.25)
        elif prog < s.blond_at:
            base = mix(C_MID, "#8c4a1c", (prog - 0.25) / (s.blond_at - 0.25))
        else:
            base = mix("#8c4a1c", look["blond"], (prog - s.blond_at) / (1 - s.blond_at + 1e-6))
        base = mix(base, look["tint"], look["tint_k"])           # 烘焙度偏色
        amp = 0.55 if 0.12 < prog < s.blond_at else 0.18
        return mix(base, C_TIGER, amp * (0.5 + 0.5 * math.sin(offset)))

    def paint_liquid(self, p):
        c = self.contents
        if base_of(self.drink_kind()) == "affogato":
            return self.paint_affogato(p)
        if base_of(self.drink_kind()) in ("pourover", "colddrip"):
            return self.paint_brew_liquid(p)                 # 手沖台的咖啡（render/station.py）
        if c["water"] > 0 or c["milk"] > 0 or c["syrup"] > 0 or base_of(self.drink_kind()) in ("americano", "iced"):
            return self.paint_mixed_liquid(p)
        return self.paint_liquid_espresso(p)

    def paint_liquid_espresso(self, p):
        s = self.shot
        if not s or s.weight <= 0.05:
            return
        ly, cx, rx, ry = self.surface_geom()
        wob = (0.5 * min(1.0, self.last_flow) if s.phase == "brew" else 0.0) * math.sin(self.anim_t * 21)
        ry_w = ry + wob
        cup = self.cup
        yb = cup.liquid_bottom
        bl, br = cup.cup_x(yb)
        brx, bry = (br - bl) / 2, (br - bl) / 2 * 0.11
        n = 24

        def arc_pts(cx_, cy_, rx_, ry_, a0, a1):
            return [QPointF(cx_ + rx_ * math.cos(a0 + (a1 - a0) * i / n),
                            cy_ + ry_ * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

        lower = arc_pts(cup.CX, yb, brx, bry, math.pi, 0)          # 杯底前緣（左→右）
        front = arc_pts(cx, ly, rx, ry_w, 0, math.pi)              # 液面前緣（右→左）
        body = QPolygonF(lower + front)
        p.setPen(Qt.NoPen)
        lo = ROASTS[s.p.roast]["target"][0]
        thin = clamp((lo - s.res.ey) / 6, 0, 1)
        top_c, bot_c, alpha = liquid_look(s.p.roast, s.res.tds, thin)
        turb = self.turbidity()
        crema_tone = ROAST_LOOK[s.p.roast]["crema"]
        upper = mix(top_c, crema_tone, 0.38 * turb)              # 上層：剛沖好時混著細小泡沫
        middle = mix(top_c, bot_c, 0.55 - 0.25 * turb)
        p.setBrush(vgrad(ly, yb, [(0, C(upper, alpha)), (0.35 + 0.2 * turb, C(middle, alpha)),
                                  (1, C(bot_c, alpha))]))
        p.drawPolygon(body)
        self.paint_crema_surface(p, ly, cx, rx, ry, ry_w)

    def paint_crema_surface(self, p, ly, cx, rx, ry, ry_w=None, scale=1.0):
        """crema：側面帶、表面、虎斑斑點、氣泡、掛杯、漣漪"""
        s = self.shot
        if ry_w is None:
            ry_w = ry
        n = 24

        def arc_pts(cx_, cy_, rx_, ry_, a0, a1):
            return [QPointF(cx_ + rx_ * math.cos(a0 + (a1 - a0) * i / n),
                            cy_ + ry_ * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

        # Crema：側面帶 + 表面
        ch = self.crema_h * scale
        stale = clamp((s.p.bean_age - 21) / 40, 0, 1)
        settle = 0.0 if s.phase != "done" else min(1.0, (time.perf_counter() - s.done_clock) / 120)
        crema = mix(mix("#a8622a", "#cf9050", 0.45 + 0.35 * s.res.sweetness / 10 - 0.35 * stale),
                    "#7a4a2a", settle * 0.45)
        crema = mix(crema, ROAST_LOOK[s.p.roast]["crema"], 0.45)       # 烘焙度偏色
        crema = mix(crema, "#e0c49a", clamp((7.5 - s.res.tds) / 5, 0, 0.35))   # 淡咖啡的 crema 較淺較薄
        if ch > 0.4:
            band = QPolygonF(arc_pts(cx, ly, rx, ry_w, math.pi, 0)
                             + arc_pts(cx, ly + ch, rx - 0.5, ry_w, 0, math.pi))
            p.setBrush(vgrad(ly, ly + ch + ry, [(0, C(crema)), (0.7, C(mix(crema, "#3d1f10", 0.4))),
                                                (1, C("#3d1f10", 0))]))
            p.drawPolygon(band)
        g = QRadialGradient(cx - rx * 0.25, ly - ry * 0.4, rx * 1.1)
        g.setColorAt(0, C(mix(crema, "#f4d3a0", 0.45)))
        g.setColorAt(0.55, C(crema))
        g.setColorAt(1, C(mix(crema, "#4a2510", 0.55)))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, ly), rx, ry_w)

        # 虎斑斑點（流入時會旋轉）
        p.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, ly), rx, ry_w)
        p.setClipPath(clip)
        # 同顏色的斑點合成一條路徑一次填色（80 顆分開畫太慢）
        dark_path, light_path = QPainterPath(), QPainterPath()
        swirl = self.swirl
        for rr, th, sz, dark in self.speckles:
            a = th + swirl * (1.2 - rr)
            x = cx + rx * rr * 0.95 * math.cos(a)
            y = ly + ry_w * rr * 0.95 * math.sin(a)
            (dark_path if dark else light_path).addEllipse(QPointF(x, y), sz, sz * 0.35)
        p.fillPath(dark_path, C("#5a2c10", 90))
        p.fillPath(light_path, C("#f2c890", 70))
        self.paint_bubbles(p, cx, ly, rx, ry_w)
        p.restore()
        self.paint_wall_film(p, ly, crema)

        # 漣漪
        p.setBrush(Qt.NoBrush)
        for rp in self.ripples:
            k = rp["age"] / rp["life"]
            rr = lerp(2, rp["r"], k)
            p.setPen(QPen(C("#ffe2b8", int(140 * (1 - k))), 0.9))
            p.drawEllipse(QPointF(rp["x"], rp["y"]), rr, rr * 0.22)

    def paint_streams(self, p):
        s = self.shot
        if not s:
            return
        ly = self.surface_y()
        flow = self.last_flow
        merge = clamp((flow - 0.9) / 0.9, 0, 1)
        w0 = clamp(1.3 + flow * 1.3, 1.5, 4.6)
        wob = s.res.channeling * 5 + 0.3
        prog = s.progress
        SPOUT_Y, CX = self.machine.spout_y, self.cup.CX
        for k, sx in enumerate(self.machine.spouts):
            st = self.stream[k]
            if st["head"] <= 0:
                continue
            ex = CX + (sx - CX) * 0.28 * (1 - merge)
            y0 = SPOUT_Y + st["tail"] * (ly - SPOUT_Y)
            y1 = SPOUT_Y + st["head"] * (ly - SPOUT_Y)
            n = 18
            left, right, center = [], [], []
            for i in range(n + 1):
                y = lerp(y0, y1, i / n)
                g = (y - SPOUT_Y) / max(1.0, ly - SPOUT_Y)
                e = g * g * (3 - 2 * g)
                x = sx + (ex - sx) * e + wob * math.sin(self.anim_t * 15 + g * 9 + k * 1.7) * g
                w = w0 * (1 - 0.38 * g) * (1 - 0.16 * math.sin(math.pi * g)) / 2     # 加速變細、中段頸縮
                left.append(QPointF(x - w, y))
                right.append(QPointF(x + w, y))
                center.append(QPointF(x - w * 0.35, y))
            poly = QPolygonF(left + right[::-1])
            gr = QLinearGradient(0, SPOUT_Y, 0, ly)
            for j in range(13):
                gr.setColorAt(j / 12, C(self.stream_color(prog, j * 1.5 - self.anim_t * 16 + k)))
            p.setPen(Qt.NoPen)
            p.setBrush(gr)
            p.drawPolygon(poly)
            p.setPen(QPen(C("#ffe0b0", 70), 0.7))
            p.drawPolyline(QPolygonF(center))

    def turbidity(self):
        """液體混濁度：萃取中與剛完成時 1，之後約 45 秒內沉降到 0"""
        s = self.shot
        if not s or s.phase != "done":
            return 1.0
        return math.exp(-(time.perf_counter() - s.done_clock) / 45)

    def paint_wall_film(self, p, ly, crema):
        """掛杯：crema 沾在液面上方的杯壁，沿兩側內壁留下一道漸淡的薄膜"""
        s = self.shot
        if s.weight < 3:
            return
        h = 3 + self.film_h
        for side in (-1, 1):
            l, r = self.cup.cup_x(ly)
            lt, rt = self.cup.cup_x(ly - h)
            if side < 0:
                pts = [QPointF(l, ly), QPointF(l + 3.5, ly), QPointF(lt + 2.0, ly - h), QPointF(lt, ly - h)]
            else:
                pts = [QPointF(r, ly), QPointF(r - 3.5, ly), QPointF(rt - 2.0, ly - h), QPointF(rt, ly - h)]
            p.setPen(Qt.NoPen)
            p.setBrush(vgrad(ly - h, ly, [(0, C(crema, 0)), (1, C(crema, 120))]))
            p.drawPolygon(QPolygonF(pts))

    def paint_bubbles(self, p, cx, ly, rx, ry):
        """crema 表面的氣泡（新鮮豆較多較大），會隨旋轉漂移，之後一顆顆破掉"""
        if not self.bubbles:
            return
        p.setBrush(Qt.NoBrush)
        k = ry / max(1.0, rx)
        rims, shines = QPainterPath(), QPainterPath()   # 完整的氣泡：外框、反光各合成一條路徑一次畫
        for b in self.bubbles:
            a = b["th"] + self.swirl * (1.2 - b["r"])
            x = cx + rx * b["r"] * 0.95 * math.cos(a)
            y = ly + ry * b["r"] * 0.95 * math.sin(a)
            sz = b["size"]
            if b["pop"] > 0:                       # 破掉：外擴的淡圈（每顆透明度不同，分開畫）
                rr = sz * (1 + 2.2 * b["pop"])
                p.setPen(QPen(C("#f6dcb0", int(120 * (1 - b["pop"]))), 0.6))
                p.drawEllipse(QPointF(x, y), rr, max(0.4, rr * k * 2.2))
                continue
            rims.addEllipse(QPointF(x, y), sz, max(0.45, sz * k * 2.2))
            shines.addEllipse(QPointF(x - sz * 0.35, y - sz * k * 0.6), sz * 0.3, sz * k * 0.7)
        p.strokePath(rims, QPen(C("#f6dcb0", 150), 0.6))
        p.fillPath(shines, C("#ffffff", 120))
        p.setPen(Qt.NoPen)

