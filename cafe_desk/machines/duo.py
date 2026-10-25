"""營業用雙頭機：跟一體機同一套外觀（深色顆粒烤漆、拉絲不鏽鋼背板、圓形黑按鍵、方形壓力錶），
寬機身、兩個沖煮頭、左側蒸氣管；右側自帶磨豆機（豆倉、出粉口與把手托架，敲渣盒在機器右邊）。

特性：大鍋爐水溫穩、萃取降溫少、蒸氣強；萃取的同時就能打奶；營業級的內建磨豆機研磨均勻（不像一體機有額外的通道效應）。
營業中排隊有兩位點了同類飲品時，兩個沖煮頭一起萃取，一次做兩杯（desk.py 的 start_pair）。

兩個沖煮頭共用一個 Machine 實例：g＝目前在算哪一個（0＝左、1＝右），group_pf、cup_cx 跟著換；
CafeDesk.on_twin() 換到第二杯時把 g 設成 1，結束時設回 0。
豆倉、出粉的粉、敲渣盒沿用一體機（AllInOne）的繪圖。
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath, QFont, QRadialGradient

from ..gfx import C, vgrad, hgrad, rrect
from ..util import clamp
from .allinone import AllInOne
from .base import Traits

PRESSURE_RANGE = (0.0, 12.0)
GROUPS = (114, 300)                       # 兩個沖煮頭的濾杯左上角 x（機身座標）；間隔要比把手長（約 173）
OUTLET = 486                              # 內建磨豆機出粉口左緣（機身座標）；第二支把手的尾端在 473
MX, MY = 20, 18
W, H = 600, 426


class Duo(AllInOne):
    key = "duo"
    name = "營業用雙頭機"
    traits = Traits(summary="雙沖煮頭、自帶磨豆機：萃取時同時打奶，營業中兩位客人點同類飲品就一起做；大鍋爐水溫穩、蒸氣強",
                    temp_noise=0.12, boiler_heat=0.7, boiler_draw=0.1, milk="wand", steam_power=1.5,
                    grinder="integrated", groups=2)

    drip_area = (52, 448, 338)            # 滴水盤（x1, x2, 上緣；機身座標）
    scene_w = 660
    mx, my = MX, MY
    cup_base = 314
    vent = (440, 98)
    card_cx = MX + 150
    gauge_r = 17
    knob = (26, 100)
    heat_lamp = (540, 98)
    grind_lamp = (500, 98)
    hopper = (474, -14, 564, 40)           # 豆倉玻璃（機身座標）：跟一體機一樣大（豆子圖快取共用）
    pad = (330, 452)                       # 頂部木質填壓墊

    # 內建磨豆區（場景座標）：出粉口在機器右側，敲渣盒在機器右邊
    fork = (MX + OUTLET, MY + 176)
    chute = (MX + OUTLET + 36, MY + 152)
    tamper_rest = (MX + 416, MY + 44)
    knock_box = (606, 312, 652, 366)
    knock = (593, 290)

    wand_pivot = (40, 112)
    wand_rest = (56, 210)
    wand_steam = (62, 222)

    machine_hit = (MX + 20, MY + 40, MX + 580, MY + 140)
    grinder_hit = (MX + 470, MY - 24, MX + 568, MY + 50)
    hover_area = (MX + 16, MY - 20, MX + 584, MY + 364)

    g = 0                                 # 目前的沖煮頭（0＝左、1＝右）

    @property
    def group_pf(self):
        return GROUPS[self.g], 128

    @property
    def cup_cx(self):
        return GROUPS[self.g] + 36

    def gauge_c(self, g):
        return GROUPS[g] + 36, 76

    def buttons(self, g):
        """每個沖煮頭左右各兩顆：單份、雙份｜沖煮（燈）、熱水"""
        cx = GROUPS[g] + 36
        return (cx - 68, 76), (cx - 42, 76), (cx + 42, 76), (cx + 68, 76)

    def gauges(self, a):
        return [(self.gauge_c(0), self.gauge_r, a.gauge, PRESSURE_RANGE),
                (self.gauge_c(1), self.gauge_r, a.twin_get("gauge"), PRESSURE_RANGE)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(20, 44, 580, 112, 14))
        path.addRect(QRectF(20, 100, 560, 240))
        path.addPath(rrect(16, 326, 584, 366, 10))
        path.addPath(rrect(470, -24, 568, 50, 6))
        return path

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), W, H)
        self.paint_shadow(a, p, 300, 370, 300, 600)
        # 不鏽鋼背板（直向拉絲）
        p.fillRect(QRectF(44, 106, 512, 232), hgrad(44, 556, [(0, C("#4a5056")), (0.12, C("#c3c9ce")),
                                                              (0.5, C("#8d949b")), (0.88, C("#b9bfc5")),
                                                              (1, C("#4a5056"))]))
        p.save()
        p.setClipRect(QRectF(44, 106, 512, 232))
        for i in range(123):
            x = 44 + i * 4.2
            p.setPen(QPen(C("#ffffff" if i % 2 else "#2a2e32", 18), 0.6))
            p.drawLine(QPointF(x, 106), QPointF(x, 338))
        p.restore()
        p.fillRect(QRectF(44, 106, 512, 30), vgrad(106, 136, [(0, C("#000000", 160)), (1, C("#000000", 0))]))
        # 側柱、中柱（兩個沖煮頭之間、沖煮區與磨豆區之間）與上方機身（深色顆粒烤漆）
        for x1, x2 in ((20, 44), (243, 257), (474, 484), (556, 580)):
            self.paint_speckled(p, rrect(x1, 100, x2, 340, 4), x1, 100, x2, 340, int(x1))
        body = rrect(20, 44, 580, 112, 14)
        self.paint_speckled(p, body, 20, 44, 580, 112, 3)
        base = rrect(16, 326, 584, 366, 10)
        self.paint_speckled(p, base, 16, 326, 584, 366, 9)

        # 頂部：不鏽鋼溫杯盤、木質填壓墊、豆倉底座與研磨刻度環
        p.fillPath(rrect(34, 38, 310, 46, 3), vgrad(38, 46, [(0, C("#e3e7ea")), (0.5, C("#9aa1a8")),
                                                            (1, C("#4e545a"))]))
        p.setPen(QPen(C("#2c3135", 140), 0.8))
        for x in range(46, 302, 8):
            p.drawLine(QPointF(x, 40), QPointF(x, 44))
        x1, x2 = self.pad
        p.fillPath(rrect(x1, 40, x2, 47, 3), vgrad(40, 47, [(0, C("#a07a58")), (1, C("#5a3e28"))]))
        hx1, _hy1, hx2, _hy2 = self.hopper
        p.fillPath(rrect(hx1 - 6, 38, hx2 + 6, 50, 4), vgrad(38, 50, [(0, C("#2a2b2e")), (1, C("#111213"))]))
        p.setPen(QPen(C("#c9ced3"), 0.7))
        for i in range(16):
            x = hx1 + 2 + i * 5.6
            p.drawLine(QPointF(x, 42), QPointF(x, 44 if i % 4 else 46))

        # 面板：每個沖煮頭一組按鍵與方形壓力錶
        for g in (0, 1):
            btns = self.buttons(g)
            for (x, y) in btns:
                rg = QRadialGradient(x - 3, y - 3, 13)
                rg.setColorAt(0, C("#4a4c50"))
                rg.setColorAt(1, C("#18191b"))
                p.setPen(QPen(C("#0a0a0b"), 1))
                p.setBrush(rg)
                p.drawEllipse(QPointF(x, y), 10, 10)
            p.setPen(QPen(C("#c9ced3"), 0.9))
            p.setBrush(Qt.NoBrush)
            cx, cy = btns[0]                                              # 單份
            p.drawRect(QRectF(cx - 3.5, cy - 2, 6, 5))
            cx, cy = btns[1]                                              # 雙份
            for dx in (-1.8, 1.8):
                p.drawEllipse(QPointF(cx + dx, cy), 2.2, 3.2)
            cx, cy = btns[3]                                              # 熱水
            p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 1))
            p.drawEllipse(QPointF(cx, cy + 2.5), 1.6, 1.6)
            gx, gy = self.gauge_c(g)
            frame = rrect(gx - 25, gy - 25, gx + 25, gy + 25, 9)
            p.fillPath(frame, vgrad(gy - 25, gy + 25, [(0, C("#e9ebec")), (1, C("#9aa1a8"))]))
            p.fillPath(rrect(gx - 22, gy - 22, gx + 22, gy + 22, 7), vgrad(gy - 22, gy + 22, [(0, C("#fbfbf9")),
                                                                                          (1, C("#e4e2dc"))]))
            self.paint_square_dial(a, p, (gx, gy), self.gauge_r, PRESSURE_RANGE)
        # 磨豆區的按鍵（研磨量）、銘牌、指示孔
        bx, by = 518, 76
        rg = QRadialGradient(bx - 3, by - 3, 13)
        rg.setColorAt(0, C("#4a4c50"))
        rg.setColorAt(1, C("#18191b"))
        p.setPen(QPen(C("#0a0a0b"), 1))
        p.setBrush(rg)
        p.drawEllipse(QPointF(bx, by), 10, 10)
        p.setPen(QPen(C("#c9ced3"), 0.9))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(bx, by), 3.5, 3.5)
        p.drawLine(QPointF(bx - 2, by + 2), QPointF(bx + 2, by - 2))
        f = QFont(a.mono, 6)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(C("#c9ced3", 160))
        p.drawText(QRectF(203, 92, 80, 12), Qt.AlignCenter, "DUO · 2G")
        p.setPen(Qt.NoPen)
        p.setBrush(C("#0a0a0b"))
        for pt in (self.heat_lamp, self.grind_lamp):
            p.drawEllipse(QPointF(*pt), 2.4, 2.4)
        p.drawEllipse(QPointF(*self.vent), 2.0, 1.3)

        # 內建磨豆機出粉口與把手托架（同一體機）
        outlet = rrect(OUTLET, 111.5, OUTLET + 64, 146, 6)
        outlet.addRect(QRectF(OUTLET, 111.5, 64, 8))
        p.fillPath(outlet.simplified(), vgrad(111.5, 146, [(0, C("#5d646b")), (0.3, C("#d0d5da")),
                                                           (1, C("#5d646b"))]))
        p.fillPath(rrect(OUTLET + 24, 144, OUTLET + 40, 152, 2), C("#141516"))
        p.fillPath(rrect(OUTLET, 202, OUTLET + 64, 208, 2), vgrad(202, 208, [(0, C("#2a2b2e")), (1, C("#0a0a0b"))]))
        for x in (OUTLET + 4, OUTLET + 56):
            p.fillPath(rrect(x, 196, x + 6, 206, 2), C("#1a1b1d"))

        # 沖煮頭與分水網（同 DESK·01，兩組）
        for gx in GROUPS:
            p.fillRect(QRectF(gx - 2, 111.5, 76, 18.5), vgrad(111.5, 130, [(0, C("#6e757c")), (0.35, C("#e3e7ea")),
                                                                          (0.6, C("#a7aeb5")), (1, C("#5c6369"))]))
            p.fillPath(rrect(gx + 4, 124, gx + 68, 133, 3), vgrad(124, 133, [(0, C("#5c6369")), (1, C("#2c3034"))]))
            p.setPen(Qt.NoPen)
            p.setBrush(C("#1a1c1f"))
            p.drawEllipse(QPointF(gx + 36, 132), 28, 2.4)
            p.setBrush(C("#7d848b", 150))
            p.drawEllipse(QPointF(gx + 36, 131.6), 23, 1.3)
        # 蒸氣閥座（深色，同一體機）
        p.fillPath(rrect(34, 92, 44, 128, 3), hgrad(34, 44, [(0, C("#2a2b2e")), (1, C("#0a0a0b"))]))

        self.paint_drip_tray(p, 52, 448, top=338)
        for g in (0, 1):                      # 每個沖煮頭下面一台電子秤
            self.g = g
            self.paint_scale(p)
        self.g = 0

    def paint_dynamic(self, a, p):
        wf = a.workflow
        if wf is None and a.twin is not None:                 # 第二杯在備粉時也算在磨豆
            wf = a.twin_get("workflow")
        grinding = bool(wf and wf.grinding)
        self.paint_hopper(a, p, grinding)
        hx1 = self.hopper[0]
        k = clamp((a.params.grind_um - 150) / 350, 0, 1)    # 研磨刻度窗
        p.fillPath(rrect(hx1 + 2 + 80 * k, 41, hx1 + 10 + 80 * k, 45, 1.5), C("#f0a050"))
        r = 7.5
        self.paint_brew_light(a, p, self.buttons(0)[2], r=r, halo_r=26)
        with a.on_twin():                     # 第二個沖煮頭的燈看第二杯
            self.paint_brew_light(a, p, self.buttons(1)[2], r=r, halo_r=26)
        if grinding:
            self.paint_lamp(a, p, self.grind_lamp, True, "#ffb050", 2.0)
        self.paint_lamp(a, p, self.heat_lamp, a.boiler.heater, "#ff7a30", 2.0)
        self.paint_wand(a, p)
        self.paint_steam_knob(a, p, self.knob, 7)

    def paint_dynamic_scene(self, a, p):
        for second in (False, True):          # 兩杯哪一杯在磨豆，粉就從出粉口落下
            wf = a.twin_get("workflow") if second else a.workflow
            if wf and wf.grinding:
                a.paint_falling_grounds(p, wf)

    def paint_collar(self, a, p, pf):
        gx = self.group_pf[0]
        self.paint_round_collar(a, p, pf, gx - 5, gx + 77, 121, 134, 134)
