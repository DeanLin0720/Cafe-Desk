"""一體機：內建磨豆機、頂部填壓座、方形壓力錶

特性：磨豆直接出粉到把手，研磨均勻度稍差（通道效應略多）；熱塊加熱快但水溫會飄；蒸氣稍弱。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QPen, QPainterPath, QRadialGradient

from ..gfx import mix, C, vgrad, hgrad, rrect
from ..layout import BEAN_COLORS
from ..util import clamp
from .base import Machine, Traits, SPECKLE_BODY

PRESSURE_RANGE = (0.0, 12.0)
RT = 360                                  # 機身右端（機身座標）：比原本（320）寬 40
MX, MY = 80, -2                           # 底座的底（機身座標 366）剛好在桌面 FLOOR（364）


class AllInOne(Machine):
    key = "allinone"
    paint_extra = tuple(c for _, c in SPECKLE_BODY)      # 深色顆粒烤漆的底色
    name = "一體機（內建磨豆）"
    traits = Traits(summary="內建磨豆機一台搞定；研磨均勻度稍差、熱塊水溫會飄、蒸氣稍弱",
                    channel_add=0.05, temp_noise=0.5, boiler_heat=0.9, boiler_draw=0.35,
                    milk="wand", steam_power=0.85, grinder="integrated")

    drip_area = (52, RT - 32, 338)            # 滴水盤（x1, x2, 上緣；機身座標）
    scene_w = 518
    mx, my = MX, MY
    group_pf = (160, 128)
    cup_cx, cup_base = 196, 314
    vent = (330, 56)
    card_cx = MX + 196
    gauge_c, gauge_r = (190, 76), 17
    buttons_l = ((66, 76), (94, 76), (122, 76))
    buttons_r = ((258, 76), (286, 76), (314, 76))
    hopper = (34, -14, 124, 40)            # 豆倉玻璃（機身座標）；上緣避開上方的曲線卡片

    # 內建磨豆區（場景座標）
    fork = (MX + 48, MY + 176)
    chute = (MX + 84, MY + 152)
    tamper_rest = (MX + 256, MY + 44)
    knock_box = (14, 312, 60, 366)
    knock = (1, 290)

    wand_pivot = (292, 112)               # 蒸氣管在機身內側、從上機身的底面掛下來（轉軸藏在上機身後面，見 paint_front）
    wand_rest = (304, 214)
    wand_steam = (310, 226)
    knob = (342, 78)                      # 蒸氣旋鈕：上機身右邊

    machine_hit = (MX + 20, MY + 40, MX + RT, MY + 140)
    grinder_hit = (MX + 30, MY - 24, MX + 128, MY + 50)
    hover_area = (MX + 16, MY - 20, MX + RT + 4, MY + 364)

    def gauges(self, a):
        return [(self.gauge_c, self.gauge_r, a.gauge, PRESSURE_RANGE)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(20, 44, RT, 112, 14))
        path.addRect(QRectF(20, 100, RT - 20, 240))
        path.addPath(rrect(16, 326, RT + 4, 366, 10))
        path.addPath(rrect(30, -24, 128, 50, 6))
        return path

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), RT + 40, 426)
        self.paint_shadow(a, p, RT / 2, 370, RT / 2, RT - 10)
        # 不鏽鋼背板
        p.fillRect(QRectF(44, 106, RT - 68, 232), hgrad(44, RT - 24, [(0, C("#4a5056")), (0.25, C("#c3c9ce")),
                                                              (0.5, C("#8d949b")), (0.8, C("#b9bfc5")),
                                                              (1, C("#4a5056"))]))
        p.save()
        p.setClipRect(QRectF(44, 106, RT - 68, 232))
        for i in range(int((RT - 68) / 4.2) + 1):
            x = 44 + i * 4.2
            p.setPen(QPen(C("#ffffff" if i % 2 else "#2a2e32", 18), 0.6))
            p.drawLine(QPointF(x, 106), QPointF(x, 338))
        p.restore()
        p.fillRect(QRectF(44, 106, RT - 68, 30), vgrad(106, 136, [(0, C("#000000", 160)), (1, C("#000000", 0))]))
        # 側柱與上方機身（深色顆粒烤漆）
        for x1, x2 in ((20, 44), (RT - 24, RT)):
            self.paint_speckled(p, rrect(x1, 100, x2, 340, 4), x1, 100, x2, 340, int(x1))
        body = rrect(20, 44, RT, 112, 14)
        self.paint_speckled(p, body, 20, 44, RT, 112, 3)
        # 底座
        base = rrect(16, 326, RT + 4, 366, 10)
        self.paint_speckled(p, base, 16, 326, RT + 4, 366, 9)

        # 頂部：豆倉底座、木質填壓墊
        p.fillPath(rrect(28, 38, 130, 50, 4), vgrad(38, 50, [(0, C("#2a2b2e")), (1, C("#111213"))]))
        p.setPen(QPen(C("#c9ced3"), 0.7))
        for i in range(16):                        # 研磨刻度環
            x = 36 + i * 5.6
            p.drawLine(QPointF(x, 42), QPointF(x, 44 if i % 4 else 46))
        p.fillPath(rrect(150, 40, 292, 47, 3), vgrad(40, 47, [(0, C("#a07a58")), (1, C("#5a3e28"))]))
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
        gx = self.gauge_c[0]
        g = rrect(gx - 25, 51, gx + 25, 101, 9)
        p.fillPath(g, vgrad(51, 101, [(0, C("#e9ebec")), (1, C("#9aa1a8"))]))
        p.fillPath(rrect(gx - 22, 54, gx + 22, 98, 7), vgrad(54, 98, [(0, C("#fbfbf9")), (1, C("#e4e2dc"))]))
        self.paint_square_dial(a, p)
        # 小指示孔
        for x in (122, self.buttons_r[0][0]):
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
        self.paint_drip_tray(p, 52, RT - 32, top=338)
        self.paint_scale(p)

    def paint_front(self, a, p):
        # 蒸氣管的轉軸：上機身蓋在蒸氣管上面（同一個顆粒烤漆、同樣的種子，只重畫轉軸附近一小塊），管子從上機身底面後面掛下來
        px = self.wand_pivot[0]
        p.save()
        p.setClipRect(QRectF(px - 9, 102, 18, 10))
        self.paint_speckled(p, rrect(20, 44, RT, 112, 14), 20, 44, RT, 112, 3)
        p.restore()
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
        self.paint_hopper(a, p, grinding)
        # 研磨刻度窗：橘色指示對應研磨粒徑
        k = clamp((a.params.grind_um - 150) / 350, 0, 1)
        p.fillPath(rrect(36 + 80 * k, 41, 44 + 80 * k, 45, 1.5), C("#f0a050"))
        # 按鍵燈
        self.paint_brew_light(a, p, self.buttons_r[0], r=7.5, halo_r=26)
        if grinding:
            self.paint_lamp(a, p, (122, 98), True, "#ffb050", 2.0)
        ss = a.session
        if ss and ss.stage_name == "steam":
            self.paint_lamp(a, p, (self.buttons_r[0][0], 98), True, "#ff7a40", 2.0)
        self.paint_wand(a, p)
        self.paint_steam_knob(a, p, self.knob, 7)

    def paint_hopper(self, a, p, grinding):
        """豆倉：煙燻玻璃 + 豆子 + 上蓋（磨豆時豆子跟著抖）"""
        x1, y1, x2, y2 = self.hopper
        p.fillPath(rrect(x1, y1, x2, y2, 6), C("#2a2622", 120))
        jig = math.sin(a.anim_t * 90) * 0.5 if grinding else 0.0
        p.drawPixmap(QPointF(x1, y1 + jig), self.bean_pixmap(a, a.hopper))
        p.fillPath(rrect(x1, y1, x2, y2, 6), C("#3a3632", 70))
        p.fillPath(rrect(x1 - 4, y1 - 10, x2 + 4, y1 + 1, 5), vgrad(y1 - 10, y1 + 1, [(0, C("#3a3b3e")),
                                                                                      (1, C("#121314"))]))

    def paint_dynamic_scene(self, a, p):
        wf = a.workflow
        if wf and wf.grinding:
            a.paint_falling_grounds(p, wf)

    def paint_static_scene(self, a, p):
        a.paint_knock_box(p, self.knock_box)

    def paint_collar(self, a, p, pf):
        self.paint_round_collar(a, p, pf, 155, 237, 121, 134, 134)
