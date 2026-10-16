"""一體機：內建磨豆機、頂部填壓座、方形壓力錶

特性：磨豆直接出粉到把手，研磨均勻度稍差（通道效應略多）；熱塊加熱快但水溫會飄；蒸氣稍弱。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QPen, QPainterPath, QRadialGradient, QFont

from ..gfx import mix, C, vgrad, hgrad, rrect
from ..layout import BEAN_COLORS
from ..util import clamp
from .base import Machine, Traits

PRESSURE_RANGE = (0.0, 12.0)
BODY = [(0, "#3c3d41"), (0.12, "#2e2f33"), (0.6, "#26272a"), (1, "#18191b")]
MX, MY = 80, 18


class AllInOne(Machine):
    key = "allinone"
    name = "一體機（內建磨豆）"
    traits = Traits(summary="內建磨豆機一台搞定；研磨均勻度稍差、熱塊水溫會飄、蒸氣稍弱",
                    channel_add=0.05, temp_noise=0.5, boiler_heat=0.9, boiler_draw=0.35,
                    milk="wand", steam_power=0.85, grinder="integrated")

    drip_area = (52, 288, 338)            # 滴水盤（x1, x2, 上緣；機身座標）
    scene_w = 478
    mx, my = MX, MY
    group_pf = (160, 128)
    cup_cx, cup_base = 196, 314
    vent = (300, 56)
    card_cx = MX + 196
    gauge_c, gauge_r = (170, 76), 17
    buttons_l = ((66, 76), (94, 76), (122, 76))
    buttons_r = ((218, 76), (246, 76), (274, 76))
    hopper = (34, -14, 124, 40)            # 豆倉玻璃（機身座標）；上緣避開上方的曲線卡片

    # 內建磨豆區（場景座標）
    fork = (MX + 48, MY + 176)
    chute = (MX + 84, MY + 152)
    tamper_rest = (MX + 236, MY + 44)
    knock_box = (14, 312, 60, 366)
    knock = (1, 290)

    wand_pivot = (322, 120)
    wand_rest = (342, 232)
    wand_steam = (348, 240)
    knob = (332, 100)

    machine_hit = (MX + 20, MY + 40, MX + 320, MY + 140)
    grinder_hit = (MX + 30, MY - 24, MX + 128, MY + 50)
    hover_area = (MX + 16, MY - 20, MX + 324, MY + 364)

    def gauges(self, a):
        return [(self.gauge_c, self.gauge_r, a.gauge, PRESSURE_RANGE)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(20, 44, 320, 112, 14))
        path.addRect(QRectF(20, 100, 300, 240))
        path.addPath(rrect(16, 326, 324, 366, 10))
        path.addPath(rrect(30, -24, 128, 50, 6))
        return path

    def paint_speckled(self, p, path, x1, y1, x2, y2, seed):
        p.fillPath(path, vgrad(y1, y2, [(pos, C(col)) for pos, col in BODY]))
        p.save()
        p.setClipPath(path)
        rnd = random.Random(seed)
        p.setPen(Qt.NoPen)
        n = int((x2 - x1) * (y2 - y1) / 22)
        for _ in range(n):
            p.setBrush(C("#9a9ca0" if rnd.random() < 0.5 else "#0a0a0b", rnd.randint(40, 110)))
            p.drawEllipse(QPointF(rnd.uniform(x1, x2), rnd.uniform(y1, y2)), 0.45, 0.45)
        p.fillRect(QRectF(x1, y1, x2 - x1, 2), C("#ffffff", 40))
        p.restore()

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), 360, 426)
        self.paint_shadow(a, p, 170, 370, 170, 360)
        # 不鏽鋼背板
        p.fillRect(QRectF(44, 106, 252, 232), hgrad(44, 296, [(0, C("#4a5056")), (0.25, C("#c3c9ce")),
                                                              (0.5, C("#8d949b")), (0.8, C("#b9bfc5")),
                                                              (1, C("#4a5056"))]))
        p.save()
        p.setClipRect(QRectF(44, 106, 252, 232))
        for i in range(60):
            x = 44 + i * 4.2
            p.setPen(QPen(C("#ffffff" if i % 2 else "#2a2e32", 18), 0.6))
            p.drawLine(QPointF(x, 106), QPointF(x, 338))
        p.restore()
        p.fillRect(QRectF(44, 106, 252, 30), vgrad(106, 136, [(0, C("#000000", 160)), (1, C("#000000", 0))]))
        # 側柱與上方機身（深色顆粒烤漆）
        for x1, x2 in ((20, 44), (296, 320)):
            self.paint_speckled(p, rrect(x1, 100, x2, 340, 4), x1, 100, x2, 340, int(x1))
        body = rrect(20, 44, 320, 112, 14)
        self.paint_speckled(p, body, 20, 44, 320, 112, 3)
        # 底座
        base = rrect(16, 326, 324, 366, 10)
        self.paint_speckled(p, base, 16, 326, 324, 366, 9)

        # 頂部：豆倉底座、木質填壓墊
        p.fillPath(rrect(28, 38, 130, 50, 4), vgrad(38, 50, [(0, C("#2a2b2e")), (1, C("#111213"))]))
        p.setPen(QPen(C("#c9ced3"), 0.7))
        for i in range(16):                        # 研磨刻度環
            x = 36 + i * 5.6
            p.drawLine(QPointF(x, 42), QPointF(x, 44 if i % 4 else 46))
        p.fillPath(rrect(150, 40, 272, 47, 3), vgrad(40, 47, [(0, C("#a07a58")), (1, C("#5a3e28"))]))
        # 面板：按鍵與方形壓力錶
        for (x, y) in self.buttons_l + self.buttons_r:
            rg = QRadialGradient(x - 3, y - 3, 13)
            rg.setColorAt(0, C("#4a4c50"))
            rg.setColorAt(1, C("#18191b"))
            p.setPen(QPen(C("#0a0a0b"), 1))
            p.setBrush(rg)
            p.drawEllipse(QPointF(x, y), 10, 10)
        p.setPen(QPen(C("#c9ced3"), 0.9))
        p.setBrush(Qt.NoBrush)
        icons = self.buttons_l + self.buttons_r
        p.drawEllipse(QPointF(*icons[0]), 3.5, 3.5)                       # 電源
        p.drawLine(QPointF(icons[0][0], icons[0][1] - 5), QPointF(icons[0][0], icons[0][1] - 1))
        p.drawEllipse(QPointF(*icons[1]), 3.5, 3.5)                       # 研磨量
        p.drawLine(QPointF(icons[1][0] - 2, icons[1][1] + 2), QPointF(icons[1][0] + 2, icons[1][1] - 2))
        for dx in (-1.8, 1.8):                                            # 雙份
            p.drawEllipse(QPointF(icons[2][0] + dx, icons[2][1]), 2.2, 3.2)
        cx, cy = icons[3]                                                 # 單杯
        p.drawRect(QRectF(cx - 3.5, cy - 2, 6, 5))
        cx, cy = icons[4]
        p.drawRect(QRectF(cx - 3.5, cy - 1, 6, 4))
        p.drawRect(QRectF(cx - 2, cy - 4, 6, 4))
        cx, cy = icons[5]                                                 # 蒸氣
        for dx in (-2, 0, 2):
            p.drawLine(QPointF(cx + dx, cy - 4), QPointF(cx + dx, cy + 3))
        g = rrect(145, 51, 195, 101, 9)
        p.fillPath(g, vgrad(51, 101, [(0, C("#e9ebec")), (1, C("#9aa1a8"))]))
        p.fillPath(rrect(148, 54, 192, 98, 7), vgrad(54, 98, [(0, C("#fbfbf9")), (1, C("#e4e2dc"))]))
        self.paint_square_dial(a, p)
        # 小指示孔
        for x in (122, 218):
            p.setPen(Qt.NoPen)
            p.setBrush(C("#0a0a0b"))
            p.drawEllipse(QPointF(x, 98), 2.4, 2.4)

        # 內建磨豆出粉口與把手托架
        outlet = rrect(52, 111.5, 116, 146, 6)
        outlet.addRect(QRectF(52, 111.5, 64, 8))                 # 上緣直角，貼齊機身底部
        p.fillPath(outlet.simplified(), vgrad(111.5, 146, [(0, C("#5d646b")), (0.3, C("#d0d5da")),
                                                           (1, C("#5d646b"))]))
        p.fillPath(rrect(76, 144, 92, 152, 2), C("#141516"))
        p.fillPath(rrect(52, 202, 116, 208, 2), vgrad(202, 208, [(0, C("#2a2b2e")), (1, C("#0a0a0b"))]))
        for x in (56, 108):
            p.fillPath(rrect(x, 196, x + 6, 206, 2), C("#1a1b1d"))
        # 沖煮頭：從機身底部垂下（同 DESK·01），分水網在把手拿走時看得到
        p.fillRect(QRectF(158, 111.5, 76, 18.5), vgrad(111.5, 130, [(0, C("#6e757c")), (0.35, C("#e3e7ea")),
                                                                  (0.6, C("#a7aeb5")), (1, C("#5c6369"))]))
        p.fillPath(rrect(164, 124, 228, 133, 3), vgrad(124, 133, [(0, C("#5c6369")), (1, C("#2c3034"))]))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#1a1c1f"))
        p.drawEllipse(QPointF(196, 132), 28, 2.4)
        p.setBrush(C("#7d848b", 150))
        p.drawEllipse(QPointF(196, 131.6), 23, 1.3)
        # 蒸氣閥座
        p.fillPath(rrect(316, 92, 326, 128, 3), hgrad(316, 326, [(0, C("#2a2b2e")), (1, C("#0a0a0b"))]))
        self.paint_drip_tray(p, 52, 288, top=338)
        self.paint_scale(p)

    def paint_square_dial(self, a, p):
        from ..layout import dial_angle
        cx, cy = self.gauge_c
        r = self.gauge_r
        p.setPen(QPen(C("#3a3a3a"), 0.8))
        for v in range(13):
            ang = math.radians(dial_angle(v, *PRESSURE_RANGE))
            r1 = r * (0.72 if v % 3 == 0 else 0.84)
            p.drawLine(QPointF(cx + r1 * math.cos(ang), cy - r1 * math.sin(ang)),
                       QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang)))
        zr = r * 0.92
        p.setPen(QPen(C("#f0a050"), 2.2, Qt.SolidLine, Qt.FlatCap))
        a0, a1 = dial_angle(10, *PRESSURE_RANGE), dial_angle(8, *PRESSURE_RANGE)
        p.drawArc(QRectF(cx - zr, cy - zr, zr * 2, zr * 2), int(a0 * 16), int((a1 - a0) * 16))
        p.setFont(QFont(a.mono, 5))
        p.setPen(C("#3a3a3a"))
        p.drawText(QRectF(cx - 10, cy + 6, 20, 8), Qt.AlignCenter, "bar")

    def paint_front(self, a, p):
        # 豆倉玻璃的反光
        x1, y1, x2, y2 = self.hopper
        p.fillPath(rrect(x1 + 6, y1 + 6, x1 + 11, y2 - 6, 2), C("#ffffff", 60))
        p.setPen(QPen(C("#ffffff", 90), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(x1, y1, x2, y2, 6))

    # ───────────── 每幀 ─────────────
    def bean_pixmap(self, a, level):
        key = (round(level * 20), a.devicePixelRatioF(), a.scale_f, a.params.roast)
        cache = getattr(a, "_aio_beans", None)
        if cache and cache[0] == key:
            return cache[1]
        x1, y1, x2, y2 = self.hopper
        ratio = a.devicePixelRatioF() * a.scale_f
        w, h = x2 - x1, y2 - y1
        pm = QPixmap(int(w * ratio), int(h * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        q.setClipPath(rrect(0, 0, w, h, 6))
        top = h - (h - 8) * clamp(key[0] / 20, 0, 1)
        rnd = random.Random(12)
        for _ in range(int(240 * clamp(key[0] / 20, 0.05, 1)) + 10):
            bx, by = rnd.uniform(0, w), rnd.uniform(top, h + 2)
            q.setPen(Qt.NoPen)
            dark, light, line = BEAN_COLORS.get(key[3], BEAN_COLORS["中焙"])
            q.setBrush(C(mix(dark, light, rnd.random())))
            q.save()
            q.translate(bx, by)
            q.rotate(rnd.uniform(0, 180))
            q.drawEllipse(QPointF(0, 0), 3.4, 2.4)
            q.setPen(QPen(C(line, 160), 0.6))
            q.drawLine(QPointF(-2.6, 0), QPointF(2.6, 0))
            q.restore()
        q.end()
        a._aio_beans = (key, pm)
        return pm

    def paint_dynamic(self, a, p):
        wf = a.workflow
        grinding = bool(wf and wf.grinding)
        x1, y1, x2, y2 = self.hopper
        # 豆倉：煙燻玻璃 + 豆子 + 上蓋
        p.fillPath(rrect(x1, y1, x2, y2, 6), C("#2a2622", 120))
        jig = math.sin(a.anim_t * 90) * 0.5 if grinding else 0.0
        p.drawPixmap(QPointF(x1, y1 + jig), self.bean_pixmap(a, a.hopper))
        p.fillPath(rrect(x1, y1, x2, y2, 6), C("#3a3632", 70))
        p.fillPath(rrect(x1 - 4, y1 - 10, x2 + 4, y1 + 1, 5), vgrad(y1 - 10, y1 + 1, [(0, C("#3a3b3e")),
                                                                                      (1, C("#121314"))]))
        # 研磨刻度窗：橘色指示對應研磨粒徑
        k = clamp((a.params.grind_um - 150) / 350, 0, 1)
        p.fillPath(rrect(36 + 80 * k, 41, 44 + 80 * k, 45, 1.5), C("#f0a050"))
        # 按鍵燈
        self.paint_brew_light(a, p, self.buttons_r[0], r=7.5, halo_r=26)
        if grinding:
            self.paint_lamp(a, p, (122, 98), True, "#ffb050", 2.0)
        ss = a.session
        if ss and ss.stage_name == "steam":
            self.paint_lamp(a, p, (218, 98), True, "#ff7a40", 2.0)
        self.paint_wand(a, p)
        self.paint_steam_knob(a, p, self.knob, 7)

    def paint_dynamic_scene(self, a, p):
        wf = a.workflow
        if wf and wf.grinding:
            a.paint_falling_grounds(p, wf)

    def paint_static_scene(self, a, p):
        a.paint_knock_box(p, self.knock_box)

    def paint_collar(self, a, p, pf):
        self.paint_round_collar(a, p, pf, 155, 237, 121, 134, 134)
