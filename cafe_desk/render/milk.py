"""牛奶與飲品相關的畫面：

    容器（熱水壺、牛奶瓶、拉花杯、奶泡機玻璃壺）與傾倒流柱
    獨立奶泡機（場景座標）、蒸氣管上的蒸氣
    美式／拿鐵／冰拿鐵的杯中液體分層、冰塊、凝結水珠
    拉花俯視圖（程式繪製）與浮出的拉花卡片
"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QPainter, QImage, QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont,
                           QRadialGradient)

from ..drinks import ART_NAMES, MILK_KINDS, SYRUPS, DUSTS, base_of
from ..i18n import T
from ..gfx import mix, C, vgrad, hgrad, rrect
from ..layout import ROAST_LOOK, TOP_PAD, liquid_look
from ..model import ROASTS
from ..util import clamp, lerp

MILK = "#f4eee4"
FOAM = "#fbf7f0"
WATER = "#cfdde4"
OAT = "#efe3cc"
COCOA = "#5a321a"
TONIC = "#eef3e6"
CREAM = "#fbf3df"
CARAMEL = "#b8691f"


def _ease(t):
    t = clamp(t, 0, 1)
    return t * t * (3 - 2 * t)


# ═══════════════════════════ 拉花圖案（俯視） ═══════════════════════════

def _wobbly(cx, cy, r, amp, rnd, n=48, sx=1.0, sy=1.0):
    ph = [rnd.uniform(0, 6.28) for _ in range(3)]
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        w = 1 + amp * (math.sin(2 * t + ph[0]) * 0.6 + math.sin(3 * t + ph[1]) * 0.3 + math.sin(5 * t + ph[2]) * 0.2)
        pts.append(QPointF(cx + r * w * sx * math.cos(t), cy + r * w * sy * math.sin(t)))
    return pts


def _heart_pts(cx, cy, r, n=48):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append(QPointF(cx + x * r / 16.5, cy + y * r / 16.5 + r * 0.12))
    return pts


def _circle_pts(cx, cy, r, n=48):
    # 與 _heart_pts 同樣的參數順序，才能平滑變形
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        pts.append(QPointF(cx + r * math.sin(t), cy - r * math.cos(t)))
    return pts


def make_art(pattern, k, q, seed, base_col, crema_col, size=128, tops=None):
    """畫出杯面俯視圖：k＝拉花進度（0–1），q＝品質（0–1）；
    tops：杯面配料 {cocoa／cinnamon：撒粉，caramel：焦糖格紋，whip：鮮奶油}（0–1）"""
    tops = tops or {}
    caramel, whip = tops.get("caramel", 0.0), tops.get("whip", 0.0)
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    R = size / 2
    p.translate(R, R)
    p.scale(R, R)
    clip = QPainterPath()
    clip.addEllipse(QPointF(0, 0), 1, 1)
    p.setClipPath(clip)
    bg = QRadialGradient(0, 0, 1)
    bg.setColorAt(0, C(mix(base_col, "#e9d3b4", 0.25)))
    bg.setColorAt(0.7, C(base_col))
    bg.setColorAt(0.93, C(crema_col))
    bg.setColorAt(1, C(mix(crema_col, "#2a150a", 0.45)))
    p.fillRect(QRectF(-1, -1, 2, 2), bg)
    rnd = random.Random(seed)
    for _ in range(70):                                       # 表面細斑
        a, r = rnd.uniform(0, 6.28), math.sqrt(rnd.random())
        p.setPen(Qt.NoPen)
        p.setBrush(C("#5a2c10" if rnd.random() < 0.6 else "#f2d4a8", 50))
        p.drawEllipse(QPointF(r * math.cos(a), r * math.sin(a)), 0.03, 0.03)
    if pattern == "mark":                                     # 焦糖瑪奇朵：滿滿的奶泡，濃縮穿過留下的印子
        p.fillRect(QRectF(-1, -1, 2, 2), C(FOAM))
        if k > 0:
            g = QRadialGradient(0.05, 0.02, 0.32 * (0.4 + 0.6 * _ease(k)))
            g.setColorAt(0, C(crema_col, 230))
            g.setColorAt(0.55, C(mix(crema_col, "#e9d6bb", 0.4), 160))
            g.setColorAt(1, C(crema_col, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(0.05, 0.02), 0.34, 0.34)
        _caramel(p, caramel, seed)
        _dusts(p, tops)
        p.end()
        return img
    if k <= 0 or pattern == "whip":
        _whip(p, whip, seed)
        _dusts(p, tops)
        p.end()
        return img
    jit = 1 - q
    ox, oy = (rnd.random() - 0.5) * 0.22 * jit, (rnd.random() - 0.5) * 0.18 * jit
    white = QColor(FOAM)
    edge = C(mix(crema_col, base_col, 0.4), int(140 + 80 * q))

    def blob(pts, outline=True):
        poly = QPolygonF(pts)
        if jit > 0.15:                                        # 品質差：邊緣毛躁
            p.setPen(QPen(C(FOAM, 80), 0.05 * jit + 0.01))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(poly)
        p.setPen(QPen(edge, 0.022) if outline else Qt.NoPen)
        p.setBrush(white)
        p.drawPolygon(poly)

    def cut_line(y0, y1, w=0.03):
        p.setPen(QPen(white, w, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(ox, y0), QPointF(ox + jit * 0.05, y1))

    if pattern == "dot":                                      # 瑪奇朵：一匙奶泡點在 crema 中間
        r = 0.08 + 0.26 * _ease(k)
        blob(_wobbly(ox, oy, r, 0.04 + 0.08 * jit, rnd), outline=True)
        p.setPen(Qt.NoPen)
        p.setBrush(C("#ffffff", 120))
        p.drawEllipse(QPointF(ox - r * 0.3, oy - r * 0.3), r * 0.35, r * 0.25)
    elif pattern == "blob":
        r = 0.18 + 0.38 * _ease(k)
        blob(_wobbly(ox * 2, 0.1 + oy * 2, r, 0.12 + 0.1 * jit, rnd, sx=1.15, sy=0.9), outline=False)
    elif pattern == "heart":
        g = clamp(k / 0.8, 0, 1)
        r = 0.12 + 0.46 * _ease(g)
        cy = 0.12 + 0.1 * (1 - g) + oy
        f = clamp((k - 0.8) / 0.2, 0, 1)
        circ = _circle_pts(ox, cy, r)
        heart = _heart_pts(ox, cy - 0.02, r * 1.05)
        pts = [QPointF(lerp(a.x(), b.x(), f), lerp(a.y(), b.y(), f)) for a, b in zip(circ, heart)]
        if jit > 0.25:
            w = _wobbly(0, 0, 1, 0.05 * jit, rnd)
            pts = [QPointF(pt.x() * (0.97 + 0.06 * (q2.x())), pt.y()) for pt, q2 in zip(pts, w)]
        blob(pts)
        if f > 0:
            cut_line(cy - r * 0.6, cy - r * 0.6 + (r * 1.85) * f, 0.035)
    elif pattern == "tulip":
        layers = [(-0.26, 0.44), (0.06, 0.36), (0.33, 0.27)]
        f = clamp((k - 0.78) / 0.22, 0, 1)
        for i, (cy, r) in enumerate(layers):
            g = clamp((k - i * 0.25) / 0.25, 0, 1)
            if g <= 0:
                break
            rr = r * (0.3 + 0.7 * _ease(g))
            x0 = ox * (1 + i * 0.3)
            circ = [QPointF(x0 + (pt.x() - x0) * 1.15, cy + oy + (pt.y() - cy - oy) * 0.82)
                    for pt in _circle_pts(x0, cy + oy, rr)]
            heart = _heart_pts(x0, cy + oy - 0.03, rr * 1.12)
            m = f * (0.75 if i == len(layers) - 1 else 0.45)
            pts = [QPointF(lerp(a.x(), b.x(), m), lerp(a.y(), b.y(), m)) for a, b in zip(circ, heart)]
            blob(pts)
        if f > 0:
            cut_line(-0.62 + oy, -0.62 + oy + 1.3 * f, 0.028)
    elif pattern == "rosetta":
        n = 10
        shown = clamp(k / 0.78, 0, 1) * n
        p.setBrush(Qt.NoBrush)
        for j in range(n):
            if j >= shown:
                break
            a = clamp(shown - j, 0, 1)
            y = -0.62 + 1.0 * j / (n - 1) + oy
            w = 0.18 + 0.42 * (j / (n - 1)) ** 0.8
            zig = (0.035 if j % 2 else -0.035) * (0.4 + jit)
            path = QPainterPath()
            path.moveTo(ox - w + zig, y + 0.07)
            path.quadTo(QPointF(ox + zig, y - 0.13 * a), QPointF(ox + w + zig, y + 0.07))
            p.setPen(QPen(C(FOAM, int(255 * a)), 0.07 + 0.03 * j / n, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(path)
        base = clamp((k - 0.6) / 0.2, 0, 1)
        if base > 0:
            blob(_wobbly(ox, 0.5 + oy, 0.16 * base, 0.05 * jit, rnd, sx=1.3, sy=0.7))
        f = clamp((k - 0.8) / 0.2, 0, 1)
        if f > 0:
            cut_line(-0.72 + oy, -0.72 + oy + 1.38 * f, 0.03)
    _whip(p, whip, seed)
    _dusts(p, tops)
    p.end()
    return img


def _caramel(p, k, seed):
    """焦糖醬淋成格紋：先畫一個方向的斜線，再畫交叉方向，最後繞一圈"""
    if k <= 0.01:
        return
    col = C("#b8691f", 235)
    hi = C("#f0b060", 160)
    lines = []
    for d in (1, -1):
        for i in range(-3, 4):
            lines.append((d, i * 0.22))
    n = len(lines)
    shown = k * (n + 4)
    rnd = random.Random(seed)
    for j, (d, off) in enumerate(lines):
        a = clamp(shown - j, 0, 1)
        if a <= 0:
            break
        # 斜線：沿 (1, d) 方向，垂直位移 off
        nx, ny = -d / math.sqrt(2), 1 / math.sqrt(2)
        dx, dy = 1 / math.sqrt(2), d / math.sqrt(2)
        cx0, cy0 = nx * off, ny * off
        L = math.sqrt(max(0.0, 0.8 ** 2 - off ** 2))
        x1, y1 = cx0 - dx * L, cy0 - dy * L
        x2, y2 = cx0 + dx * L * (2 * a - 1), cy0 + dy * L * (2 * a - 1)
        path = QPainterPath(QPointF(x1, y1))
        steps = 10
        for t in range(1, steps + 1):
            f = t / steps
            w = math.sin(f * 9 + rnd.random()) * 0.008
            path.lineTo(QPointF(lerp(x1, x2, f) + w, lerp(y1, y2, f) - w))
        p.setPen(QPen(col, 0.032, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(hi, 0.01, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
    ring = clamp(shown - n, 0, 4) / 4
    if ring > 0:
        p.setPen(QPen(col, 0.034, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(QRectF(-0.78, -0.78, 1.56, 1.56), 90 * 16, int(-360 * 16 * ring))


def _whip(p, k, seed):
    """鮮奶油（俯視）：由外往內繞的螺旋，一圈圈堆高"""
    if k <= 0.01:
        return
    rnd = random.Random(seed + 3)
    turns = 3.2
    shown = turns * k
    pts = []
    n = 120
    for i in range(n + 1):
        t = turns * i / n
        if t > shown:
            break
        r = 0.78 * (1 - t / (turns + 0.4))
        a = t * 2 * math.pi + rnd.uniform(-0.02, 0.02)
        pts.append(QPointF(r * math.cos(a), r * math.sin(a)))
    if len(pts) < 2:
        return
    path = QPainterPath(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(C("#d9d2c8"), 0.26, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(QPen(C("#fffdf8"), 0.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(path)
    p.setPen(QPen(C("#ffffff", 200), 0.05, Qt.SolidLine, Qt.RoundCap))
    p.translate(-0.03, -0.04)
    p.drawPath(path)
    p.translate(0.03, 0.04)


def _dusts(p, tops):
    for kind, (col, flower) in DUSTS.items():
        amt = tops.get(kind, 0.0)
        if amt > 0.01:
            _dust(p, amt, col, flower)


def _dust(p, amt, col=COCOA, flower=False):
    """撒在杯面上的粉（可可、肉桂）或乾燥桂花：中間濃、外圍淡"""
    tint = QRadialGradient(0, 0, 0.85)
    tint.setColorAt(0, C(col, int((20 if flower else 70) * amt)))
    tint.setColorAt(1, C(col, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(tint)
    p.drawEllipse(QPointF(0, 0), 0.85, 0.85)
    r2 = random.Random(9)
    n = int((60 if flower else 320) * amt)
    for i in range(n):
        a, r = r2.uniform(0, 6.28), 0.8 * r2.random() ** 0.8
        x, y = r * math.cos(a), r * math.sin(a)
        if flower:                                            # 小小的四瓣花
            p.setBrush(C(col, r2.randint(170, 240)))
            for j in range(4):
                b = j * 1.57 + a
                p.drawEllipse(QPointF(x + 0.012 * math.cos(b), y + 0.012 * math.sin(b)), 0.011, 0.011)
        else:
            p.setBrush(C(col if r2.random() < 0.7 else mix(col, "#c08a50", 0.4), r2.randint(90, 190)))
            p.drawEllipse(QPointF(x, y), 0.012, 0.012)


# ═══════════════════════════ 渲染 mixin ═══════════════════════════

class MilkRenderer:
    # ───────────── 每步更新 ─────────────
    def update_drink_fx(self, dt, sdt):
        surf = self.surface_y()
        liquid = self.liquid_weight()
        # 冰塊：落下、停在杯底或其他冰塊上；有液體時浮起來
        max_row = max([c.get("row", 0) for c in self.ice], default=0)
        for c in self.ice:
            if not c["landed"]:
                c["vy"] += 700 * sdt
                c["y"] += c["vy"] * sdt
                c["rot"] += c["vr"] * sdt
                if c["y"] >= c["rest"]:
                    c["y"] = c["rest"]
                    c["vy"] = 0.0
                    c["landed"] = True
                    c["vr"] = 0.0
                    self.sound.once("ice", random.uniform(0.35, 0.55))
            else:
                c["bob"] += dt
                if liquid > 1:
                    row = c.get("row", 0)
                    float_y = surf + c["size"] * 0.28 + (max_row - row) * c["size"] * 0.62
                    target = min(c["rest"], float_y) + math.sin(c["bob"] * 1.3) * 0.4
                    c["y"] += (target - c["y"]) * min(1.0, sdt * 3)
        # 冰飲杯外的凝結水珠
        kind = self.drink_kind()
        ic = self.icecream
        if ic:                                                    # 阿芙佳朵：冰淇淋掉落、融化
            if not ic["landed"]:
                ic["vy"] += 700 * sdt
                ic["y"] += ic["vy"] * sdt
                if ic["y"] >= ic["rest"]:
                    ic["y"], ic["vy"], ic["landed"] = ic["rest"], 0.0, True
                    self.sound.once("tamp", 0.2)
            else:
                e = self.shot.weight if self.shot else 0.0
                heat = clamp(e / 36, 0, 1)
                ic["melt"] = min(1.0, ic["melt"] + sdt * (0.0012 + 0.011 * heat * (1 - 0.5 * ic["melt"])))
        if (kind == "caramel_macchiato" or self.contents["syrup"] > 0) and self.shot and self.contents["milk"] > 0:
            self.mix_t += sdt                                     # 濃縮暈開、巧克力醬慢慢拌開
        iced = base_of(kind) == "iced"
        if iced and self.ice:
            self.condense = min(1.0, self.condense + dt / 25)
        # 冰拿鐵、冰美式：濃縮在牛奶／冷水裡慢慢擴散
        if self.shot and (self.contents["milk"] > 0 or self.contents["water"] > 0) and iced:
            self.mix_t += sdt
        self.vortex += sdt * (9 if self.session and self.session.frother_on else 0)
        # 奶泡機壺裡的奶量（體積隨奶泡膨脹）
        ss = self.session
        if ss and ss.frother_on:
            self.frother_fill = 0.42 * (1 + ss.milk_foam / 100)
        # 蒸氣管噴出的蒸氣
        if ss and self.machine.traits.milk == "wand" and ss.stage_name == "steam" and self.wand_angle > 0.95 \
                and getattr(ss.stage, "phase", "") == "run":
            m = self.machine
            if random.random() < 14 * dt:
                v = ss.vessel
                x = (v["x"] - m.mx) + random.uniform(4, 32) if v else m.wand_steam[0]
                y = (v["y"] - m.my) + 2 if v else m.wand_steam[1]
                self.steam.append({"x": x, "y": y, "vx": random.uniform(-6, 6), "vy": random.uniform(-30, -18),
                                   "age": 0.0, "life": random.uniform(0.8, 1.4), "ph": random.random() * 6.28,
                                   "boost": 55, "s0": 3, "s1": 14})

    def purge_wand(self):
        m = self.machine
        if not m.wand_rest:
            return
        x, y = m.wand_rest
        for i in range(10):
            self.steam.append({"x": x + random.uniform(-2, 2), "y": y + 2, "vx": random.uniform(-10, 10),
                               "vy": random.uniform(10, 30), "age": -i * 0.03, "life": random.uniform(0.7, 1.2),
                               "ph": random.random() * 6.28, "boost": 75, "s0": 3, "s1": 16})

    # ───────────── 杯中液體（機身座標） ─────────────
    def drink_kind(self):
        return self.session.drink if self.session else self.last_drink

    def espresso_color(self):
        s = self.shot
        lo = ROASTS[s.p.roast]["target"][0]
        thin = clamp((lo - s.res.ey) / 6, 0, 1)
        top_c, bot_c, alpha = liquid_look(s.p.roast, s.res.tds, thin)
        return top_c, bot_c

    def body_polygon(self, ly, rx, ry, cx):
        cup = self.cup
        yb = cup.liquid_bottom
        bl, br = cup.cup_x(yb)
        brx, bry = (br - bl) / 2, (br - bl) / 2 * 0.11
        n = 24

        def arc(cx_, cy_, rx_, ry_, a0, a1):
            return [QPointF(cx_ + rx_ * math.cos(a0 + (a1 - a0) * i / n),
                            cy_ + ry_ * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        return QPolygonF(arc(cup.CX, yb, brx, bry, math.pi, 0) + arc(cx, ly, rx, ry, 0, math.pi))

    def paint_mixed_liquid(self, p):
        """美式、拿鐵、冰拿鐵的杯中液體"""
        kind = self.drink_kind()
        c, s = self.contents, self.shot
        e = s.weight if s else 0.0
        liquid = e + c["water"] + c["milk"] + c["syrup"]
        if liquid <= 0.05:
            return
        ly, cx, rx, ry = self.surface_geom()
        yb = self.cup.liquid_bottom
        body = self.body_polygon(ly, rx, ry, cx)
        p.setPen(Qt.NoPen)
        look = ROAST_LOOK[s.p.roast] if s else ROAST_LOOK["中焙"]

        if kind == "americano":
            if e <= 0.05:
                p.setBrush(vgrad(ly, yb, [(0, C(WATER, 50)), (1, C(WATER, 75))]))
                p.drawPolygon(body)
                p.setBrush(C("#ffffff", 70))
                p.drawEllipse(QPointF(cx, ly), rx, ry)
                return
            conc = e / (e + c["water"])
            strength = clamp(conc * s.res.tds / 2.4, 0, 1)
            col = mix(look["amber"], look["deep"], 0.3 + 0.55 * strength)
            alpha = int(150 + 105 * strength)
            k = clamp((time.perf_counter() - self.mix_clock) / 8, 0, 1) if s.phase == "done" else 0.35
            top = mix(mix(look["deep"], col, 0.4), col, k)
            bottom = mix(mix(WATER, col, 0.45), col, k)
            p.setBrush(vgrad(ly, yb, [(0, C(top, alpha)), (1, C(bottom, int(alpha * (0.75 + 0.25 * k))))]))
            p.drawPolygon(body)
            self.paint_crema_surface(p, ly, cx, rx, ry, scale=0.75)
            return

        if kind == "espresso_tonic":
            return self.paint_tonic(p, ly, cx, rx, ry, yb, body, e, c["water"], look)

        if kind == "iced_americano":
            total = max(1.0, liquid)
            ef = e / total
            mk = clamp(self.mix_t / 40.0, 0, 1)
            if ef <= 0.01:
                p.setBrush(vgrad(ly, yb, [(0, C(WATER, 45)), (1, C(WATER, 70))]))
                p.drawPolygon(body)
                p.setBrush(C("#ffffff", 60))
                p.drawEllipse(QPointF(cx, ly), rx, ry)
                return
            esp_top, esp_bot = self.espresso_color()
            strength = clamp(ef * s.res.tds / 2.0, 0, 1)
            mixed = mix(look["amber"], look["deep"], 0.35 + 0.5 * strength)
            boundary = clamp(ef * 1.3, 0.05, 1)
            a_mix = int(150 + 90 * strength)
            stops = [(0, C(mix(esp_top, mixed, mk), 240)),
                     (clamp(boundary * (1 - 0.7 * mk), 0.02, 0.97), C(mix(esp_bot, mixed, mk), int(lerp(235, a_mix, mk)))),
                     (clamp(boundary + 0.1 + 0.6 * mk, 0.05, 0.99), C(mix(WATER, mixed, 0.2 + 0.8 * mk), int(lerp(70, a_mix, mk)))),
                     (1, C(mix(WATER, mixed, 0.1 + 0.85 * mk), int(lerp(60, a_mix * 0.92, mk))))]
            p.setBrush(vgrad(ly, yb, stops))
            p.drawPolygon(body)
            if mk < 0.85:                                         # 往下沉的咖啡細流
                p.save()
                p.setClipPath(self.cup.inner_path())
                by = lerp(ly, yb, boundary)
                rnd = random.Random(int(e) // 6 + 23)
                for i in range(6):
                    x0 = cx + rnd.uniform(-rx * 0.8, rx * 0.8)
                    length = (yb - by) * (0.3 + 0.6 * mk) * rnd.uniform(0.5, 1)
                    path = QPainterPath(QPointF(x0, by))
                    ph = rnd.uniform(0, 6.28)
                    for j in range(1, 9):
                        path.lineTo(QPointF(x0 + math.sin(self.anim_t * 0.6 + ph + j * 0.8) * 4 * j / 8,
                                            by + length * j / 8))
                    p.setPen(QPen(C(esp_bot, int(130 * (1 - mk))), 2.0, Qt.SolidLine, Qt.RoundCap))
                    p.drawPath(path)
                p.restore()
                p.setPen(Qt.NoPen)
            self.paint_crema_surface(p, ly, cx, rx, ry, scale=0.6 * (1 - 0.5 * mk))
            return

        if kind == "iced_latte":
            milk_c = self.milk_col()
            total = max(1.0, liquid)
            ef = e / total
            mk = clamp(self.mix_t / 50.0, 0, 1)
            esp_top, esp_bot = self.espresso_color() if s else ("#3a1e10", "#2a150a")
            tan = mix(milk_c, look["amber"], 0.55)
            boundary = clamp(ef * 1.15, 0, 1)
            stops = [(0, C(mix(esp_top, tan, mk * 0.8), 245))]
            if ef > 0.01:
                stops.append((clamp(boundary * (1 - 0.6 * mk), 0.02, 0.98), C(mix(esp_bot, tan, mk * 0.7), 245)))
                stops.append((clamp(boundary + 0.08 + 0.55 * mk, 0.05, 1), C(mix(milk_c, tan, 0.25 + 0.55 * mk), 240)))
            stops.append((1, C(mix(milk_c, tan, 0.15 + 0.6 * mk * ef * 3), 238)))
            if ef <= 0.01:
                stops = [(0, C(milk_c, 232)), (1, C(mix(milk_c, "#d8d0c4", 0.3), 238))]
            p.setBrush(vgrad(ly, yb, stops))
            p.drawPolygon(body)
            if ef > 0.01 and mk < 0.85:                            # 往下沉的咖啡細流
                p.save()
                p.setClipPath(self.cup.inner_path())
                by = lerp(ly, yb, boundary)
                rnd = random.Random(int(e) // 6 + 11)
                for i in range(6):
                    x0 = cx + rnd.uniform(-rx * 0.8, rx * 0.8)
                    length = (yb - by) * (0.3 + 0.6 * mk) * rnd.uniform(0.5, 1)
                    path = QPainterPath(QPointF(x0, by))
                    ph = rnd.uniform(0, 6.28)
                    for j in range(1, 9):
                        yy = by + length * j / 8
                        path.lineTo(QPointF(x0 + math.sin(self.anim_t * 0.6 + ph + j * 0.8) * 4 * j / 8, yy))
                    p.setPen(QPen(C(esp_bot, int(110 * (1 - mk))), 2.2 - 1.2 * j / 8, Qt.SolidLine, Qt.RoundCap))
                    p.drawPath(path)
                p.restore()
                p.setPen(Qt.NoPen)
            top_col = mix(look["crema"], tan, mk) if ef > 0.01 else mix(milk_c, "#ffffff", 0.4)
            p.setBrush(C(top_col, 245))
            p.drawEllipse(QPointF(cx, ly), rx, ry)
            return

        # 熱牛奶飲品
        if kind == "caramel_macchiato" and c["milk"] > 0.05:
            self.paint_layered(p, ly, cx, rx, ry, yb, body, e)
        elif c["milk"] <= 0.05:
            if e > 0.05:
                self.paint_liquid_espresso(p)
            self.paint_syrup_layer(p, e)
            return
        else:
            f = c["milk"] / max(1.0, c["milk"] + e)
            esp_top, esp_bot = self.espresso_color()
            latte = mix(mix(esp_bot, "#8a5a32", 0.4), self.milk_col(), clamp(0.3 + 0.32 * f, 0, 0.62))
            if kind == "macchiato":                               # 瑪奇朵：底下幾乎是濃縮，上面一層奶泡
                latte = mix(esp_bot, "#8a5a32", 0.25)
            elif kind == "mocha":                                 # 摩卡：巧克力色
                latte = mix(latte, "#5a2e18", 0.3)
            elif c["syrup"] > 0:                                  # 季節拿鐵：帶一點醬的顏色
                latte = mix(latte, SYRUPS[self.syrup_kind]["color"], 0.12)
            foam_frac = clamp(c["foam"] / max(1.0, self.cup_volume()), 0, 0.6)
            syr = mix(SYRUPS[self.syrup_kind]["color"], "#000000", 0.25)
            choc_bot = mix(latte, syr, clamp(1 - self.mix_t / 30, 0, 0.75)) if c["syrup"] > 0 else None
            stops = [(0, C(FOAM, 252)), (max(0.01, foam_frac * 0.75), C(mix(FOAM, latte, 0.12), 252)),
                     (min(0.98, foam_frac + 0.05), C(mix(latte, self.milk_col(), 0.25), 252)),
                     (min(0.99, foam_frac + 0.12), C(latte, 252))]
            if choc_bot:                                          # 杯底還沒拌開的巧克力醬
                stops += [(0.86, C(mix(latte, esp_bot, 0.3), 252)), (1, C(choc_bot, 252))]
            else:
                stops.append((1, C(mix(latte, esp_bot, 0.3), 252)))
            p.setBrush(vgrad(ly, yb, stops))
            p.drawPolygon(body)
        img = self.current_art_image()
        p.save()
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, ly), rx, ry)
        p.setClipPath(clip)
        p.drawImage(QRectF(cx - rx, ly - ry, rx * 2, ry * 2), img)
        p.restore()
        self.paint_whip_dome(p, ly, cx, rx, ry)

    def milk_col(self):
        ss = self.session
        dp = ss.dp if ss else getattr(self, "last_dp", None)
        kind = dp.milk_kind if dp is not None else "dairy"
        return MILK_KINDS.get(kind, MILK_KINDS["dairy"])["color"]

    # ───────────── 新飲品的杯中畫面（機身座標） ─────────────
    def paint_syrup_layer(self, p, e):
        """杯底的巧克力醬／香草糖漿（比重大，沉在最下面）"""
        g = self.contents["syrup"]
        if g <= 0.05:
            return
        cup = self.cup
        ys = cup.level_y(g * 1.6)
        l, r = cup.cup_x(ys)
        rx = (r - l) / 2
        col = SYRUPS[self.syrup_kind]["color"]
        if e > 0.05 and self.syrup_kind == "choc":
            col = mix(col, "#2a1408", 0.3)
        body = self.body_polygon(ys, rx, rx * 0.11, (l + r) / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(ys, cup.liquid_bottom, [(0, C(mix(col, "#ffffff", 0.12), 245)), (1, C(col, 250))]))
        p.drawPolygon(body)
        if e <= 0.05:
            p.setBrush(C(mix(col, "#ffffff", 0.25), 245))
            p.drawEllipse(QPointF((l + r) / 2, ys), rx, rx * 0.11)

    def paint_layered(self, p, ly, cx, rx, ry, yb, body, e):
        """焦糖瑪奇朵：奶泡 → 濃縮帶 → 牛奶（底部帶香草糖漿），濃縮慢慢往下暈開"""
        c = self.contents
        total = max(1.0, self.cup_volume())
        milk_c = self.milk_col()
        foam_frac = clamp(c["foam"] / total, 0.02, 0.5)
        ef = e / total
        mk = clamp(self.mix_t / 80.0, 0, 1)
        vanilla = SYRUPS["vanilla"]["color"]
        bottom = mix(milk_c, vanilla, 0.4 * (1 - mk)) if c["syrup"] > 0 else milk_c
        stops = [(0, C(FOAM, 252)), (foam_frac * 0.85, C(mix(FOAM, milk_c, 0.2), 252))]
        if ef > 0.005:
            esp_top, esp_bot = self.espresso_color()
            look = ROAST_LOOK[self.shot.p.roast]
            tan = mix(milk_c, look["amber"], 0.5)
            b1 = clamp(foam_frac + 0.02, 0, 0.95)
            b2 = clamp(foam_frac + ef * 1.4 * (1 + 0.8 * mk), b1 + 0.02, 0.97)
            b3 = clamp(b2 + 0.06 + 0.3 * mk, b2 + 0.01, 0.985)
            stops += [(b1, C(mix(esp_top, tan, 0.15 + 0.5 * mk), 250)),
                      (b2, C(mix(esp_bot, tan, 0.35 + 0.45 * mk), 250)),
                      (b3, C(mix(milk_c, tan, 0.3 + 0.3 * mk), 250))]
        else:
            stops.append((clamp(foam_frac + 0.06, 0, 0.95), C(milk_c, 250)))
        stops.append((1, C(bottom, 250)))
        p.setPen(Qt.NoPen)
        p.setBrush(vgrad(ly, yb, stops))
        p.drawPolygon(body)

    def paint_tonic(self, p, ly, cx, rx, ry, yb, body, e, w, look):
        """濃縮通寧：清澈的通寧水、往上冒的氣泡，濃縮浮在最上層"""
        total = max(1.0, e + w)
        ef = e / total
        mk = clamp(self.mix_t / 240.0, 0, 0.45)                 # 擴散得很慢，分層維持很久
        p.setPen(Qt.NoPen)
        if ef > 0.005:
            esp_top, esp_bot = self.espresso_color()
            boundary = clamp(ef * 1.25, 0.04, 0.95)
            stops = [(0, C(mix(esp_top, look["crema"], 0.3), 240)),
                     (boundary, C(esp_bot, 235)),
                     (clamp(boundary + 0.05 + 0.3 * mk, 0, 0.99), C(mix(TONIC, look["amber"], 0.35 + 0.4 * mk), 120)),
                     (1, C(mix(TONIC, look["amber"], 0.25 * mk), 70))]
        else:
            boundary = 0.0
            stops = [(0, C(TONIC, 60)), (1, C(TONIC, 80))]
        p.setBrush(vgrad(ly, yb, stops))
        p.drawPolygon(body)
        # 氣泡
        p.save()
        p.setClipPath(self.cup.inner_path())
        p.setClipRect(QRectF(cx - rx - 4, ly, rx * 2 + 8, yb - ly), Qt.IntersectClip)
        rnd = random.Random(31)
        by = lerp(ly, yb, boundary)
        for i in range(34):
            sp = rnd.uniform(0.12, 0.35)
            fy = (self.anim_t * sp + rnd.random()) % 1.0
            y = lerp(yb - 2, ly + 1, fy)
            l, r = self.cup.cup_x(y)
            x = lerp(l + 3, r - 3, rnd.random()) + math.sin(self.anim_t * 3 + i) * 0.6
            rad = rnd.uniform(0.5, 1.3) * (0.7 + 0.5 * fy)
            col = "#ffffff" if y > by else "#e8c8a0"
            p.setBrush(C(col, 150 if y > by else 90))
            p.drawEllipse(QPointF(x, y), rad, rad)
        p.restore()
        p.setPen(Qt.NoPen)
        if ef > 0.005:                                           # 通寧水碰到濃縮起的泡沫
            p.setBrush(C(mix(look["crema"], "#e9cfa8", 0.35), 245))
        else:
            p.setBrush(C("#ffffff", 70))
        p.drawEllipse(QPointF(cx, ly), rx, ry)

    def paint_whip_dome(self, p, ly, cx, rx, ry):
        """鮮奶油：一圈圈往上堆的螺旋（側面）＋可可粉"""
        w = self.topping.get("whip", 0.0)
        if w <= 0.01:
            return
        layers = 4
        shown = w * layers
        p.setPen(Qt.NoPen)
        top_y = ly
        for i in range(layers):
            a = clamp(shown - i, 0, 1)
            if a <= 0:
                break
            k = 1 - i / layers
            r = rx * (0.82 * k + 0.1) * (0.6 + 0.4 * a)
            h = 7.5 * (0.5 + 0.5 * k)
            cy = ly - 2 - i * 6.2
            puff = QPainterPath()
            puff.addEllipse(QPointF(cx, cy), r, h)
            p.fillPath(puff, vgrad(cy - h, cy + h, [(0, C("#ffffff", 252)), (0.6, C("#f5efe6", 252)),
                                                    (1, C("#d8cfc2", 252))]))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(C("#cfc5b8", 200), 0.8))
            p.drawArc(QRectF(cx - r * 0.9, cy - h * 0.6, r * 1.8, h * 1.6), 200 * 16, 140 * 16)
            p.setPen(Qt.NoPen)
            top_y = cy - h
        if shown >= layers - 0.2:                                # 尖頂
            tip = QPainterPath()
            tip.moveTo(cx - 6, top_y + 4)
            tip.quadTo(QPointF(cx - 1, top_y - 4), QPointF(cx + 3, top_y - 7))
            tip.quadTo(QPointF(cx + 2, top_y), QPointF(cx + 6, top_y + 4))
            tip.closeSubpath()
            p.fillPath(tip, C("#fbf8f2"))
        for kind, (col, flower) in DUSTS.items():
            amt = self.topping.get(kind, 0.0)
            if amt <= 0.01:
                continue
            rnd = random.Random(12)
            for i in range(int(90 * amt)):
                x = cx + rnd.uniform(-1, 1) * rx * 0.6
                y = top_y + rnd.uniform(0, ly - top_y)
                p.setBrush(C(col, rnd.randint(110, 200)))
                p.drawEllipse(QPointF(x, y), 0.6, 0.6)

    def affogato_ball(self):
        """(x, y, 半徑, 垂直壓扁比例)；冰淇淋越融越小、越扁"""
        ic = self.icecream
        m = ic["melt"]
        r = ic["r"] * (1 - 0.42 * m)
        sy = 1 - 0.28 * m
        y = ic["y"] + (ic["r"] - r) * 0.9 if ic["landed"] else ic["y"]
        return ic["x"], y, r, sy

    def paint_affogato(self, p):
        """阿芙佳朵：杯中一球香草冰淇淋，濃縮淋上去後慢慢融化成咖啡色漩渦"""
        ic = self.icecream
        s = self.shot
        e = s.weight if s else 0.0
        melted = ic["g"] * ic["melt"] * 0.8 if ic else 0.0
        liquid = e + melted
        cup = self.cup
        yb = cup.liquid_bottom
        look = ROAST_LOOK[s.p.roast] if s else ROAST_LOOK["中焙"]
        ly = cx = rx = ry = None
        if liquid > 0.3 and s:
            ly, cx, rx, ry = self.surface_geom()
            body = self.body_polygon(ly, rx, ry, cx)
            cf = melted / max(1.0, liquid)                    # 液體裡冰淇淋的比例
            esp_top, esp_bot = self.espresso_color()
            top = mix(esp_top, "#c89a6a", 0.85 * cf)
            bot = mix(esp_bot, "#a87850", 0.6 * cf)
            p.setPen(Qt.NoPen)
            p.setBrush(vgrad(ly, yb, [(0, C(top, 245)), (1, C(bot, 248))]))
            p.drawPolygon(body)
        if ic:
            x, y, r, sy = self.affogato_ball()
            self.paint_scoop_ball(p, x, y, r, sy, ic, e)
            if ly is not None and ly < y + r * sy:            # 泡在咖啡裡的下半部
                p.save()
                clip = QPainterPath()
                clip.addRect(QRectF(x - r - 2, ly, r * 2 + 4, 200))
                p.setClipPath(clip)
                p.setClipPath(cup.inner_path(), Qt.IntersectClip)
                cf = melted / max(1.0, liquid)
                p.setPen(Qt.NoPen)
                p.setBrush(C(mix("#6a3a1a", "#c89a6a", cf), 170))
                p.drawEllipse(QPointF(x, y), r + 0.5, r * sy + 0.5)
                p.restore()
        if ly is not None:                                    # 液面：融化的奶油拉出的白色漩渦
            p.save()
            surf = QPainterPath()
            surf.addEllipse(QPointF(cx, ly), rx, ry)
            if ic:
                x, y, r, sy = self.affogato_ball()
                hole = QPainterPath()
                hole.addEllipse(QPointF(x, y), r, r * sy)
                surf = surf.subtracted(hole)
            p.setClipPath(surf)
            p.fillRect(QRectF(cx - rx, ly - ry, rx * 2, ry * 2), C(mix(look["crema"], "#e0c09a", 0.5 * clamp(melted / 30, 0, 1)), 240))
            m = ic["melt"] if ic else 0.0
            if m > 0.03:
                p.setBrush(Qt.NoBrush)
                for i in range(4):
                    ph = self.anim_t * 0.25 + i * 1.57
                    path = QPainterPath()
                    for j in range(30):
                        t = j / 29
                        a = ph + t * 4.2
                        rr = rx * (0.25 + 0.7 * t)
                        pt = QPointF(cx + rr * math.cos(a), ly + rr * 0.11 * math.sin(a))
                        (path.lineTo if j else path.moveTo)(pt)
                    p.setPen(QPen(C(CREAM, int(170 * min(1.0, m * 2))), 1.1))
                    p.drawPath(path)
            p.restore()

    def paint_scoop_ball(self, p, x, y, r, sy, ic, e):
        p.save()
        p.translate(x, y)
        p.scale(1, sy)
        g = QRadialGradient(-r * 0.35, -r * 0.4, r * 1.4)
        g.setColorAt(0, C("#fffaf0"))
        g.setColorAt(0.55, C(CREAM))
        g.setColorAt(1, C("#d8c49c"))
        ball = QPainterPath()
        ball.addEllipse(QPointF(0, 0), r, r)
        p.fillPath(ball, g)
        p.setClipPath(ball)
        rnd = random.Random(int(ic["rot"] * 100))
        p.setPen(QPen(C("#d9c8a4", 150), 0.8))
        p.setBrush(Qt.NoBrush)
        for i in range(7):                                    # 挖球留下的紋路
            a = rnd.uniform(0, 6.28)
            rr = rnd.uniform(0.3, 0.85) * r
            p.drawArc(QRectF(-rr, -rr * 0.8 + rnd.uniform(-3, 3), rr * 2, rr * 1.6),
                      int(math.degrees(a) * 16), 70 * 16)
        p.setPen(Qt.NoPen)
        for i in range(26):                                   # 香草籽
            a, rr = rnd.uniform(0, 6.28), r * math.sqrt(rnd.random()) * 0.9
            p.setBrush(C("#2a1a10", 150))
            p.drawEllipse(QPointF(rr * math.cos(a), rr * math.sin(a)), 0.45, 0.45)
        if e > 0.3:                                           # 濃縮從頂端往下流的痕跡
            k = clamp(e / 30, 0, 1)
            p.setBrush(QBrush(vgrad(-r, r, [(0, C("#4a2410", int(150 * k))), (1, C("#7a4422", 0))])))
            cap = QPainterPath()
            cap.addEllipse(QPointF(0, -r * 0.55), r * 0.75, r * 0.5 * (0.5 + k))
            p.drawPath(cap)
            p.setPen(QPen(C("#5a2c14", int(150 * k)), 1.6, Qt.SolidLine, Qt.RoundCap))
            for i in range(5):
                x0 = rnd.uniform(-0.6, 0.6) * r
                length = r * (0.4 + 1.1 * k * rnd.uniform(0.5, 1))
                path = QPainterPath(QPointF(x0, -r * 0.6))
                path.cubicTo(QPointF(x0 * 1.1, -r * 0.2), QPointF(x0 * 1.25, 0),
                             QPointF(x0 * 1.3, -r * 0.6 + length))
                p.drawPath(path)
        p.setClipping(False)
        p.setPen(Qt.NoPen)
        p.setBrush(C("#ffffff", 150))
        p.drawEllipse(QPointF(-r * 0.38, -r * 0.45), r * 0.22, r * 0.14)
        p.restore()

    def liquid_weight(self):
        c = self.contents
        return (self.shot.weight if self.shot else 0.0) + c["water"] + c["milk"]

    # ───────────── 冰塊與凝結水珠（機身座標） ─────────────
    def paint_ice(self, p):
        if not self.ice:
            return
        surf = self.surface_y()
        liquid = self.liquid_weight()
        tint = MILK
        if self.shot and self.contents["milk"] > 0:
            tint = mix(MILK, "#a0663a", clamp(self.mix_t / 50, 0, 1) * 0.5)
        elif self.contents["milk"] <= 0:                     # 冰美式：冰塊浸在水／咖啡裡
            tint = mix(WATER, "#6a3a1a", clamp(self.mix_t / 40, 0, 1) * 0.7) if self.shot else WATER
        p.save()
        p.setClipPath(self.cup.inner_path())
        for c in sorted(self.ice, key=lambda c: -c.get("row", 0)):
            sz = c["size"]
            p.save()
            p.translate(c["x"], c["y"])
            p.rotate(c["rot"])
            cube = rrect(-sz / 2, -sz / 2, sz / 2, sz / 2, 3.2)
            p.fillPath(cube, vgrad(-sz / 2, sz / 2, [(0, C("#ffffff", 150)), (0.5, C("#dcebf2", 110)),
                                                     (1, C("#b8d0dc", 130))]))
            p.setPen(QPen(C("#ffffff", 190), 0.9))
            p.drawPath(cube)
            p.fillPath(rrect(-sz / 2 + 2.5, -sz / 2 + 2.5, -sz / 2 + 6, sz / 2 - 3, 1.5), C("#ffffff", 120))
            p.restore()
            if liquid > 1:                                     # 液面以下：被牛奶色蓋住一些
                p.save()
                p.setClipRect(QRectF(c["x"] - sz, surf, sz * 2, 400), Qt.IntersectClip)
                p.translate(c["x"], c["y"])
                p.rotate(c["rot"])
                p.fillPath(rrect(-sz / 2, -sz / 2, sz / 2, sz / 2, 3.2), C(tint, 150))
                p.restore()
        p.restore()

    def paint_condensation(self, p):
        a = self.condense
        if a <= 0.01 or self.cup.kind != "iced":
            return
        cup = self.cup
        rnd = random.Random(77)
        p.setPen(Qt.NoPen)
        for i in range(70):
            fy = rnd.random()
            y = lerp(cup.T + 10, cup.B - 6, fy)
            l, r = cup.cup_x(y, inner=False)
            x = lerp(l + 3, r - 3, rnd.random())
            sz = rnd.uniform(0.6, 1.6)
            slide = 0.0
            if i % 9 == 0:                                     # 少數水珠慢慢往下滑
                slide = ((self.anim_t * 0.6 + rnd.random() * 10) % 10) * 3
                y = min(cup.B - 6, y + slide)
            p.setBrush(C("#ffffff", int(110 * a)))
            p.drawEllipse(QPointF(x, y), sz, sz * 1.2)
            p.setBrush(C("#ffffff", int(200 * a)))
            p.drawEllipse(QPointF(x - sz * 0.3, y - sz * 0.4), sz * 0.3, sz * 0.3)

    # ───────────── 傾倒流柱（機身座標） ─────────────
    def paint_pour_stream(self, p):
        ss = self.session
        v = ss.vessel if ss else None
        if not v or v.get("pour", 0) <= 0:
            return
        m = self.machine
        x0, y0 = v["x"] - m.mx, v["y"] - m.my
        surf = self.surface_y()
        cx = self.cup.CX + 8
        liquid = v["liquid"]
        col = {"water": WATER, "cold_water": WATER, "tonic": TONIC, "cold_milk": self.milk_col(), "hot_milk": FOAM,
               **{k: v["color"] for k, v in SYRUPS.items()}}[liquid]
        watery = liquid in ("water", "cold_water", "tonic")
        alpha = 120 if watery else 245
        w0 = 3.0 if watery else (2.2 if liquid in SYRUPS else 3.6)
        n = 16
        left, right = [], []
        for i in range(n + 1):
            t = i / n
            y = lerp(y0, surf, t)
            x = lerp(x0, cx, t ** 0.6) + math.sin(self.anim_t * 14 + t * 8) * 0.4 * t
            w = w0 * (1 - 0.35 * t) / 2
            left.append(QPointF(x - w, y))
            right.append(QPointF(x + w, y))
        p.setPen(Qt.NoPen)
        p.setBrush(C(col, alpha))
        p.drawPolygon(QPolygonF(left + right[::-1]))
        p.setPen(QPen(C("#ffffff", 140), 0.7))
        p.drawPolyline(QPolygonF([QPointF(pt.x() + 0.6, pt.y()) for pt in left]))
        if random.random() < 0.5:
            self.ripples.append({"x": cx + random.uniform(-2, 2), "y": surf, "age": 0.0, "life": 0.5, "r": 12})

    # ───────────── 容器（場景座標，原點＝倒出口） ─────────────
    def paint_vessel(self, p, v):
        if v is None or v.get("alpha", 1) <= 0.01:
            return
        p.save()
        p.setOpacity(v.get("alpha", 1))
        p.translate(v["x"], v["y"])
        p.rotate(-v["tilt"])
        kind = v["kind"]
        if kind == "pitcher":
            self.paint_pitcher(p)
        elif kind == "kettle":
            self.paint_kettle(p)
        elif kind == "bottle":
            self.paint_bottle(p, v)
        elif kind == "jug":
            self.paint_jug(p, v.get("fill", 1.0) * self.frother_fill, False, v.get("pour", 0) > 0)
        elif kind == "tonic":
            self.paint_tonic_bottle(p, v)
        elif kind == "squeeze":
            self.paint_squeeze(p, v)
        elif kind == "scoop":
            self.paint_scoop(p, v)
        p.restore()

    def paint_squeeze(self, p, v):
        """醬料擠瓶（原點＝瓶嘴）：巧克力醬或香草糖漿"""
        kind = v.get("liquid", "choc")
        syrup = SYRUPS.get(kind, SYRUPS["choc"])
        col = syrup["color"]
        nozzle = QPainterPath()
        nozzle.moveTo(-1.2, 0)
        nozzle.lineTo(1.2, 0)
        nozzle.lineTo(3.5, 10)
        nozzle.lineTo(-3.5, 10)
        nozzle.closeSubpath()
        p.fillPath(nozzle, C("#e8e2d8" if kind == "vanilla" else "#d23a2a"))
        p.fillPath(rrect(-7, 9, 7, 15, 2), C("#f0ece6" if kind == "vanilla" else "#b82a1e"))
        body = rrect(-10, 14, 10, 52, 5)
        p.fillPath(body, hgrad(-10, 10, [(0, C(mix(col, "#000000", 0.3))), (0.35, C(mix(col, "#ffffff", 0.25))),
                                         (1, C(mix(col, "#000000", 0.4)))]))
        p.fillPath(rrect(-10, 24, 10, 40, 0), C("#f6efe2", 230))           # 標籤
        p.setPen(C(mix(col, "#000000", 0.35)))
        f = QFont(self.ui, 4.2 if len(syrup["label"]) <= 6 else 3.6)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(-10, 24, 20, 16), Qt.AlignCenter, syrup["label"])
        p.fillPath(rrect(-7, 16, -4, 50, 1.5), C("#ffffff", 70))

    def paint_tonic_bottle(self, p, v):
        """通寧水小玻璃瓶（原點＝瓶口）"""
        glass = QPainterPath()
        glass.moveTo(-4, 0)
        glass.lineTo(4, 0)
        glass.lineTo(4, 12)
        glass.cubicTo(QPointF(11, 16), QPointF(11, 20), QPointF(11, 24))
        glass.lineTo(11, 56)
        glass.quadTo(QPointF(11, 59), QPointF(8, 59))
        glass.lineTo(-8, 59)
        glass.quadTo(QPointF(-11, 59), QPointF(-11, 56))
        glass.lineTo(-11, 24)
        glass.cubicTo(QPointF(-11, 20), QPointF(-11, 16), QPointF(-4, 12))
        glass.closeSubpath()
        p.fillPath(glass, C("#7fb08a", 70))
        self._liquid_in(p, glass, v.get("fill", 1.0) * 0.85, TONIC, 120, v.get("pour", 0) > 0)
        p.setPen(QPen(C("#d8f0dc", 190), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(glass)
        p.fillPath(rrect(-8, 26, -5, 54, 1.5), C("#ffffff", 110))
        p.fillPath(rrect(-11, 32, 11, 44, 0), C("#f4efe2", 230))
        p.setPen(C("#2f6a48"))
        f = QFont(self.ui, 4.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(-11, 32, 22, 12), Qt.AlignCenter, "TONIC")

    def paint_scoop(self, p, v):
        """冰淇淋勺（原點＝勺口中心）：把手往右上；勺子裡有一球冰淇淋"""
        p.setPen(QPen(C("#4e545a"), 5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(14, -4), QPointF(56, -30))
        p.setPen(QPen(C("#c9ced3"), 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(15, -5), QPointF(55, -30))
        p.fillPath(rrect(40, -32, 64, -20, 5).translated(0, 0), C("#2a2c2f"))
        if v.get("ball"):
            r = 23.0 * (self.session.dp.scoop_g / 70) ** (1 / 3) if self.session else 23.0
            self.paint_scoop_ball(p, 0, 2, r * 0.95, 1.0, {"rot": 1.0}, 0.0)
        bowl = QPainterPath()
        bowl.moveTo(-16, -2)
        bowl.cubicTo(QPointF(-16, -22), QPointF(16, -22), QPointF(16, -2))
        bowl.lineTo(13, -2)
        bowl.cubicTo(QPointF(13, -18), QPointF(-13, -18), QPointF(-13, -2))
        bowl.closeSubpath()
        p.fillPath(bowl, hgrad(-16, 16, [(0, C("#6b7177")), (0.4, C("#f2f4f5")), (1, C("#5d646b"))]))

    def paint_pitcher(self, p):
        body = QPainterPath()
        body.moveTo(0, 0)
        body.lineTo(8, 4)
        body.lineTo(34, 4)
        body.cubicTo(QPointF(35, 18), QPointF(39, 30), QPointF(38, 41))
        body.lineTo(5, 41)
        body.cubicTo(QPointF(4, 30), QPointF(6, 14), QPointF(7, 6))
        body.closeSubpath()
        p.fillPath(body, hgrad(4, 39, [(0, C("#6b7177")), (0.25, C("#f2f4f5")), (0.45, C("#b9bfc5")),
                                       (0.8, C("#80878e")), (1, C("#4e545a"))]))
        p.setPen(QPen(C("#ffffff", 160), 1))
        p.drawLine(QPointF(1, 0.5), QPointF(34, 4.3))
        hd = QPainterPath(QPointF(36, 9))
        hd.cubicTo(QPointF(47, 9), QPointF(48, 30), QPointF(38, 32))
        p.setPen(QPen(C("#5d646b"), 3.5, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(hd)
        p.setPen(QPen(C("#d9dde0"), 1.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(hd)
        # 溫度標籤
        ss = self.session
        if ss and ss.stage_name in ("steam",):
            p.setPen(Qt.NoPen)
            p.fillPath(rrect(12, 16, 31, 27, 2), C("#121212", 220))
            f = QFont(self.mono, 5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(C("#ffc566"))
            p.drawText(QRectF(12, 16, 19, 11), Qt.AlignCenter, f"{ss.milk_temp:.0f}°")

    def paint_kettle(self, p):
        spout = QPainterPath(QPointF(0, 0))
        spout.cubicTo(QPointF(8, 2), QPointF(14, 18), QPointF(22, 34))
        spout.lineTo(30, 42)
        p.setPen(QPen(C("#5d646b"), 4.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(spout)
        p.setPen(QPen(C("#dfe3e6"), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(spout)
        body = QPainterPath()
        body.moveTo(30, 16)
        body.lineTo(70, 16)
        body.cubicTo(QPointF(74, 30), QPointF(76, 44), QPointF(72, 52))
        body.lineTo(28, 52)
        body.cubicTo(QPointF(24, 44), QPointF(26, 30), QPointF(30, 16))
        p.fillPath(body, hgrad(24, 76, [(0, C("#4a5056")), (0.3, C("#e7ebee")), (0.5, C("#a8afb6")),
                                        (0.85, C("#6c737a")), (1, C("#3e4348"))]))
        p.fillPath(rrect(34, 11, 66, 17, 3), vgrad(11, 17, [(0, C("#d0d5da")), (1, C("#6b7177"))]))
        p.fillPath(rrect(47, 6, 53, 12, 2), C("#2a2c2f"))
        hd = QPainterPath(QPointF(70, 20))
        hd.cubicTo(QPointF(86, 18), QPointF(88, 44), QPointF(72, 46))
        p.setPen(QPen(C("#2a2c2f"), 4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(hd)

    def _liquid_in(self, p, interior, fill, col, alpha, pouring):
        """容器內液面：維持水平（不跟著容器旋轉）"""
        world = p.worldTransform()
        inv, ok = world.inverted()
        if not ok:
            return
        poly = world.map(interior)
        r = poly.boundingRect()
        level = (r.top() + 2) if pouring else r.bottom() - r.height() * fill * 0.9
        cut = QPainterPath()
        cut.addRect(QRectF(r.left() - 5, level, r.width() + 10, r.bottom() - level + 5))
        region = inv.map(poly.intersected(cut))
        p.fillPath(region, C(col, alpha))

    def paint_bottle(self, p, v):
        glass = QPainterPath()
        glass.moveTo(-5, 0)
        glass.lineTo(5, 0)
        glass.lineTo(5, 9)
        glass.cubicTo(QPointF(13, 12), QPointF(13, 16), QPointF(13, 20))
        glass.lineTo(13, 52)
        glass.quadTo(QPointF(13, 55), QPointF(10, 55))
        glass.lineTo(-10, 55)
        glass.quadTo(QPointF(-13, 55), QPointF(-13, 52))
        glass.lineTo(-13, 20)
        glass.cubicTo(QPointF(-13, 16), QPointF(-13, 12), QPointF(-5, 9))
        glass.closeSubpath()
        p.fillPath(glass, C("#ffffff", 30))
        water = v.get("liquid") == "cold_water"
        self._liquid_in(p, glass, v.get("fill", 1.0) * 0.8, WATER if water else MILK, 110 if water else 240,
                        v.get("pour", 0) > 0)
        p.setPen(QPen(C("#ffffff", 170), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(glass)
        p.fillPath(rrect(-10, 22, -7, 50, 1.5), C("#ffffff", 110))
        p.fillPath(rrect(-13, 30, 13, 40, 0), C("#4aa0b8" if water else "#3d6fa8", 200))        # 標籤
        p.setPen(C("#ffffff"))
        f = QFont(self.ui, 5 if not water else 4.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(-13, 30, 26, 10), Qt.AlignCenter, "WATER" if water else "MILK")

    def jug_glass(self):
        glass = QPainterPath()
        glass.moveTo(0, 2)
        glass.lineTo(6, 6)
        glass.lineTo(42, 6)
        glass.lineTo(43, 52)
        glass.quadTo(QPointF(43, 56), QPointF(39, 56))
        glass.lineTo(7, 56)
        glass.quadTo(QPointF(3, 56), QPointF(3, 52))
        glass.lineTo(4, 9)
        glass.closeSubpath()
        return glass

    def paint_jug(self, p, fill, on_base, pouring=False):
        """奶泡機的玻璃壺（原點＝倒出口）：看得到牛奶、奶泡與漩渦"""
        glass = self.jug_glass()
        p.fillPath(glass, C("#ffffff", 26))
        ss = self.session
        foam_pct = ss.milk_foam if ss else 0.0
        if fill > 0.02:
            if on_base:
                top = 56 - 50 * fill
                foam_h = 50 * fill * clamp(foam_pct / 100 / (1 + foam_pct / 100), 0, 0.6)
                milk = QPainterPath()
                milk.addRect(QRectF(4, top, 39, 56 - top))
                region = glass.intersected(milk)
                warm = clamp(((ss.milk_temp if ss else 6) - 6) / 54, 0, 1)
                p.fillPath(region, vgrad(top, 56, [(0, C(FOAM, 245)),
                                                   (clamp(foam_h / max(1, 56 - top), 0.01, 0.9), C(FOAM, 245)),
                                                   (1, C(mix(MILK, "#efe1c8", warm * 0.4), 240))]))
                if ss and ss.frother_on:                              # 漩渦
                    p.setPen(QPen(C("#d9cfc0", 160), 0.8))
                    for i in range(4):
                        ph = self.vortex + i * 1.57
                        path = QPainterPath(QPointF(23 + 16 * math.cos(ph), top + 3))
                        for j in range(1, 12):
                            a = ph + j * 0.35
                            rr = 16 * (1 - j / 14)
                            path.lineTo(QPointF(23 + rr * math.cos(a), top + 3 + j * 1.6))
                        p.drawPath(path)
                    p.setPen(Qt.NoPen)
                    p.setBrush(C(mix(MILK, "#d9cfc0", 0.4), 200))
                    p.drawEllipse(QPointF(23, top + 2), 9, 2.2)
            else:
                self._liquid_in(p, glass, fill, FOAM, 245, pouring)
        p.setPen(QPen(C("#ffffff", 170), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(glass)
        p.fillPath(rrect(7, 12, 10, 50, 1.5), C("#ffffff", 100))
        p.fillPath(rrect(4, 2.5, 43, 8, 2), vgrad(2.5, 8, [(0, C("#e3e7ea")), (1, C("#5d646b"))]))   # 壺蓋
        hd = QPainterPath(QPointF(42, 14))
        hd.cubicTo(QPointF(55, 14), QPointF(56, 44), QPointF(43, 46))
        p.setPen(QPen(C("#202224"), 4.5, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(hd)

    # ───────────── 獨立奶泡機（場景座標） ─────────────
    def paint_frother(self, p):
        fp = self.machine.frother_pos
        if not fp:
            return
        x, y = fp
        bx = x + 23
        floor = y + 56 + 12
        sh = QRadialGradient(bx, floor, 40)
        sh.setColorAt(0, C("#000000", 110))
        sh.setColorAt(1, C("#000000", 0))
        p.save()
        p.translate(bx, floor)
        p.scale(1, 0.12)
        p.translate(-bx, -floor)
        p.fillRect(QRectF(bx - 45, floor - 40, 90, 80), sh)
        p.restore()
        base = rrect(bx - 28, y + 55, bx + 28, floor, 5)
        p.fillPath(base, vgrad(y + 55, floor, [(0, C("#3a3d41")), (0.2, C("#1d1f22")), (1, C("#0e0f10"))]))
        p.fillRect(QRectF(bx - 25, y + 55.5, 50, 1), C("#ffffff", 50))
        ss = self.session
        on = bool(ss and ss.frother_on)
        warm = clamp(((ss.milk_temp if ss else 6) - 6) / 54, 0, 1) if on else 0
        led = mix("#4aa8ff", "#ff9a40", warm) if on else "#2a3a48"
        if on:
            halo = QRadialGradient(bx, floor - 5, 18)
            halo.setColorAt(0, C(led, 120))
            halo.setColorAt(1, C(led, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(bx, floor - 5), 18, 9)
        p.setPen(QPen(C(led), 1.6))
        p.drawLine(QPointF(bx - 10, floor - 5), QPointF(bx + 10, floor - 5))
        v = ss.vessel if ss else None
        if not (v and v["kind"] == "jug"):
            p.save()
            p.translate(x, y)
            self.paint_jug(p, self.frother_fill, True)
            p.restore()

    def paint_drip_water(self, p):
        """滴水盤：格柵縫隙裡看得到的水位，滿了會溢到上緣（機身座標）"""
        area = self.machine.drip_area
        if not area:
            return
        from ..maintenance import DRIP_FULL
        level = clamp(self.maint.get("drip", 0) / DRIP_FULL, 0, 1.15)
        if level <= 0.05:
            return
        x1, x2, top = area
        h = 11 * min(1.0, level)
        p.setPen(Qt.NoPen)
        shimmer = 0.5 + 0.5 * math.sin(self.anim_t * 2)
        for x in range(int(x1) + 12, int(x2) - 10, 7):
            p.fillRect(QRectF(x - 1.1, top + 17 - h, 2.2, h), C(mix("#6a5040", "#9ab8c8", 0.4), 150))
            p.fillRect(QRectF(x - 1.1, top + 17 - h, 2.2, 0.8), C("#d8f0ff", int(90 + 60 * shimmer)))
        if level > 1.0:                                       # 溢出
            p.setBrush(C("#a8c8d8", 90))
            p.drawEllipse(QPointF((x1 + x2) / 2, top + 2), (x2 - x1) * 0.42, 2.2)

    # ───────────── 可可粉篩網（機身座標） ─────────────
    def paint_tool(self, p):
        """杯口上方的小道具：可可粉篩網、鮮奶油槍、焦糖醬瓶（機身座標）"""
        ss = self.session
        tool = ss.tool if ss else None
        if not tool or tool["alpha"] <= 0.01:
            return
        cup = self.cup
        surf = self.surface_y()
        ly, cx, rx, ry = self.surface_geom()
        kind, active, k = tool["kind"], tool["active"], tool["k"]
        p.save()
        p.setOpacity(tool["alpha"])
        if kind == "shaker":
            shake = math.sin(self.anim_t * 38) * 2.2 if active else 0.0
            x, y = cup.CX + 6 + shake, cup.T - 30
            top = surf - 6 * 4 * self.topping.get("whip", 0.0)
            if active:                                         # 飄落的可可粉
                p.setPen(Qt.NoPen)
                rnd = random.Random(5)
                for i in range(40):
                    ph = (self.anim_t * 1.5 + rnd.random()) % 1.0
                    yy = lerp(y + 6, top, ph)
                    xx = x + rnd.uniform(-13, 13) * (0.6 + 0.6 * ph)
                    p.setBrush(C(DUSTS.get(tool.get("dust"), (COCOA, False))[0], int(200 * (1 - 0.5 * ph))))
                    p.drawEllipse(QPointF(xx, yy), 0.7, 0.7)
            p.setPen(QPen(C("#5d646b"), 2.4, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x + 15, y), QPointF(x + 40, y - 9))
            p.setPen(QPen(C("#d9dde0"), 0.9, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x + 15, y - 0.6), QPointF(x + 40, y - 9.6))
            cup_path = QPainterPath()
            cup_path.moveTo(x - 15, y - 3)
            cup_path.lineTo(x + 15, y - 3)
            cup_path.quadTo(QPointF(x + 14, y + 8), QPointF(x, y + 8))
            cup_path.quadTo(QPointF(x - 14, y + 8), QPointF(x - 15, y - 3))
            p.fillPath(cup_path, vgrad(y - 3, y + 8, [(0, C("#b9bfc5", 200)), (1, C("#6b7177", 220))]))
            p.setPen(QPen(C("#3e2414", 120), 0.5))
            for i in range(-12, 13, 3):
                p.drawLine(QPointF(x + i, y - 2), QPointF(x + i * 0.8, y + 7))
            p.setBrush(C(DUSTS.get(tool.get("dust"), (COCOA, False))[0], 230))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, y - 3), 15, 3)
            p.setPen(QPen(C("#e3e7ea"), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y - 3), 15, 3)
        elif kind == "whip":
            # 鮮奶油槍倒過來，噴嘴繞圈往上
            a = self.anim_t * 7
            rr = rx * 0.55 * (1 - k) if active else rx * 0.5
            x = cx + rr * math.cos(a)
            y = ly - 14 - 26 * k
            if active:
                p.setPen(QPen(C("#fbf8f2"), 4, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x, y + 8), QPointF(x * 0.6 + cx * 0.4, y + 14))
            star = QPainterPath()
            star.moveTo(x - 4, y + 8)
            star.lineTo(x + 4, y + 8)
            star.lineTo(x + 3, y)
            star.lineTo(x - 3, y)
            star.closeSubpath()
            p.fillPath(star, C("#d9dde0"))
            can = rrect(x - 11, y - 52, x + 11, y, 6)
            p.fillPath(can, hgrad(x - 11, x + 11, [(0, C("#4e545a")), (0.3, C("#f2f4f5")), (0.55, C("#b9bfc5")),
                                                   (1, C("#3e4348"))]))
            p.fillPath(rrect(x - 11, y - 10, x + 11, y - 4, 2), C("#2a2c2f"))
        elif kind == "caramel":
            # 焦糖醬瓶倒過來，左右來回淋出格紋
            phase = k * 7
            sweep = (phase % 1.0) * 2 - 1 if int(phase) % 2 == 0 else 1 - (phase % 1.0) * 2
            x = cx + sweep * rx * 0.7
            y = ly - 22
            if active:
                p.setPen(QPen(C(CARAMEL, 230), 1.4, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x, y), QPointF(x - sweep * 2, ly))
            p.save()
            p.translate(x, y)
            p.rotate(180)
            p.translate(0, 0)
            self.paint_squeeze(p, {"liquid": "vanilla"})
            p.restore()
            p.setPen(Qt.NoPen)
            p.fillPath(rrect(x - 10, y - 40, x + 10, y - 24, 0), C(CARAMEL, 200))
            f = QFont(self.ui, 4.2)
            f.setBold(True)
            p.setFont(f)
            p.setPen(C("#fff4e0"))
            p.drawText(QRectF(x - 10, y - 40, 20, 16), Qt.AlignCenter, "CARAMEL")
        p.restore()

    # ───────────── 拉花卡片（視窗座標） ─────────────
    def art_state(self):
        """(圖案, 進度, 品質, 種子, (可可粉, 焦糖, 鮮奶油))；沒有拉花時回傳 None"""
        ss = self.session
        if ss and ss.milk is not None:
            t = self.topping
            return ss.milk.art, ss.art_progress, ss.milk.art_q, ss.art_seed, dict(t)
        if not ss and self.last_art:
            return self.last_art
        return None

    def current_art_image(self):
        st = self.art_state()
        s = self.shot
        if s is None:
            crema, base = "#9a5a2a", "#c89a6a"
        else:
            look = ROAST_LOOK[s.p.roast]
            crema = mix(look["crema"], "#7a4a2a", 0.25)
            f = self.contents["milk"] / max(1.0, self.contents["milk"] + s.weight)
            if st is not None and st[0] == "dot":                 # 瑪奇朵：底色就是 crema
                f = 0.0
            base = mix(crema, "#e9d6bb", clamp(0.2 + 0.7 * f, 0, 0.85))
            if self.contents["syrup"] > 0 and self.syrup_kind != "vanilla":   # 加了醬的拿鐵：底色帶醬的顏色
                base = mix(base, SYRUPS[self.syrup_kind]["color"], 0.3)
        if st is None:
            pattern, k, q, seed, tops = "heart", 0.0, 0.5, 1, {}
        else:
            pattern, k, q, seed, tops = st
        key = (pattern, round(k * 80), round(q, 2), seed, crema, base,
               tuple(sorted((a, round(v * 50)) for a, v in tops.items())))
        cache = getattr(self, "_art_cache", None)
        if cache and cache[0] == key:
            return cache[1]
        img = make_art(pattern, k, q, seed, base, crema, tops=tops)
        self._art_cache = (key, img)
        return img

    def art_rect(self, with_chart):
        w, h = 124, 120
        cx = self.machine.card_cx
        lo = self.cards_left()
        if with_chart:
            left = clamp(cx - 169, lo, self.machine.scene_w - 4 - 344)
            return QRectF(left + 220, TOP_PAD - 132, w, h)
        return QRectF(max(lo, cx - w / 2), TOP_PAD - 132, w, h)

    def paint_art_card(self, p):
        a = self.art_alpha
        st = self.art_state()
        if a <= 0.01 or st is None:
            return
        r = self.art_rect(self.card_alpha > 0.05)
        p.save()
        p.setOpacity(a)
        p.setBrush(QBrush(C("#14110f", 225)))
        p.setPen(QPen(C("#ffffff", 40), 1))
        p.drawRoundedRect(r, 10, 10)
        tip = QPainterPath()
        cx = r.center().x()
        tip.moveTo(cx - 8, r.bottom() - 0.5)
        tip.lineTo(cx, r.bottom() + 8)
        tip.lineTo(cx + 8, r.bottom() - 0.5)
        tip.closeSubpath()
        p.fillPath(tip, C("#14110f", 225))
        f = QFont(self.ui, 8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C("#efe6da"))
        pattern, k, q, _, tops = st
        ss = self.session
        milk = ss.milk if ss else getattr(self, "last_milk", None)
        if pattern == "dot":
            label = T("奶泡點")
        elif pattern == "mark":
            label = T("焦糖格紋")
        elif pattern == "whip":
            label = T("鮮奶油 · 可可粉" if tops.get("cocoa", 0) > 0.5 else
                      ("鮮奶油 · 肉桂粉" if tops.get("cinnamon", 0) > 0.5 else "鮮奶油"))
        elif k < 1:
            wanted = milk.wanted if milk else "auto"
            label = T("拉花") if wanted == "auto" else T("拉花 · 指定{name}", name=T(ART_NAMES[wanted]))
        elif milk is not None and milk.art_note:
            label = milk.art_note
        else:
            label = T("拉花 · {name}", name=T(ART_NAMES[pattern].split("（")[0]))
        self.fit_text(p, QRectF(r.x() + 10, r.y() + 6, r.width() - 20, 14), label, f)
        p.setPen(Qt.NoPen)
        rad = 42
        c = QPointF(cx, r.y() + 24 + rad)
        p.setPen(Qt.NoPen)
        ring = QRadialGradient(c.x(), c.y() - 8, rad + 6)
        ring.setColorAt(0.8, C("#f4f1ec"))
        ring.setColorAt(1, C("#b9b2a8"))
        p.setBrush(ring)
        p.drawEllipse(c, rad + 5, rad + 5)
        p.drawImage(QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2), self.current_art_image())
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#ffffff", 120), 1))
        p.drawEllipse(c, rad, rad)
        p.restore()
