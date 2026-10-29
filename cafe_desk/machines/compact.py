"""小型單鍋爐機：拉絲鋼方盒、三個翹板開關

特性：溫控差，每杯水溫飄動大；洩壓閥偏高（11 bar）；
單鍋爐打奶前要等鍋爐升到蒸氣溫度，打完再沖要先降溫。
"""
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath, QFont

from ..gfx import C, vgrad, hgrad, rrect
from .base import Machine, Traits

PRESSURE_RANGE = (0.0, 15.0)
STEEL = [(0, "#5a6066"), (0.3, "#e7ebee"), (0.45, "#f8fafb"), (0.75, "#9aa1a8"), (1, "#4d5359")]


class Compact(Machine):
    key = "compact"
    name = "小型單鍋爐機"
    traits = Traits(summary="單鍋爐：水溫飄動大、洩壓閥偏高；打奶前要等鍋爐升溫",
                    temp_noise=1.4, boiler_heat=0.6, boiler_draw=0.38, pressure_cap=11.0,
                    milk="wand", steam_power=0.95, steam_heatup=True, steam_temp=125.0)

    drip_area = (44, 226, 338)            # 滴水盤（x1, x2, 上緣；機身座標）
    scene_w = 470
    mx, my = 160, 0                   # 底座的底剛好在桌面 FLOOR（364）
    group_pf = (99, 128)
    cup_cx, cup_base = 135, 314
    vent = (214, 26)
    card_cx = 160 + 135
    temp_range = (80.0, 140.0)
    gauge_c, gauge_r = (66, 70), 16
    temp_c, temp_r = (204, 70), 16
    rockers = ((112, 84), (135, 84), (158, 84))
    lamps = ((112, 60), (135, 60), (158, 60))

    wand_pivot = (232, 112)
    wand_rest = (254, 216)
    wand_steam = (260, 226)
    knob = (238, 92)

    machine_hit = (160 + 40, 10, 160 + 230, 140)
    hover_area = (160 + 40, 10, 160 + 240, 364)

    def gauges(self, a):
        return [(self.gauge_c, self.gauge_r, a.gauge, PRESSURE_RANGE),
                (self.temp_c, self.temp_r, a.boiler.temp, self.temp_range)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(40, 22, 230, 112, 10))
        path.addRect(QRectF(40, 100, 190, 242))
        path.addPath(rrect(44, 338, 226, 364, 8))
        return path

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), 300, 426)
        self.paint_shadow(a, p, 135, 368, 120, 260)
        # 背板凹槽
        p.fillRect(QRectF(58, 104, 154, 238), vgrad(104, 342, [(0, C("#0d0b0a")), (0.3, C("#1f1a17")),
                                                               (1, C("#2d2622"))]))
        p.fillRect(QRectF(58, 104, 154, 30), vgrad(104, 134, [(0, C("#000000", 160)), (1, C("#000000", 0))]))
        for x1, x2 in ((40, 58), (212, 230)):
            p.fillRect(QRectF(x1, 100, x2 - x1, 242), hgrad(x1, x2, [(pos, C(col)) for pos, col in STEEL]))
        # 上方機身
        body = rrect(40, 22, 230, 112, 10)
        self.paint_brushed(p, body, 40, 22, 230, 112, [(0, "#f2f4f5"), (0.1, "#dfe3e6"), (0.6, "#b4bac0"),
                                                       (1, "#7a8188")], seed=17, n=180)
        p.fillRect(QRectF(40, 22, 190, 2.5), C("#ffffff", 150))
        p.setPen(QPen(C("#5d646b"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(body)
        # 頂部溫杯格柵與水箱蓋縫
        p.setPen(QPen(C("#7a8188"), 1.2))
        for x in range(56, 216, 8):
            p.drawLine(QPointF(x, 26), QPointF(x + 4, 26))
        p.setPen(QPen(C("#2c3135", 120), 1))
        p.drawLine(QPointF(44, 36), QPointF(226, 36))
        # 洩壓口
        p.setPen(Qt.NoPen)
        p.setBrush(C("#15171a"))
        p.drawEllipse(QPointF(214, 28), 2.2, 1.4)
        # 錶
        self.paint_dial_face(a, p, self.gauge_c, self.gauge_r, PRESSURE_RANGE, range(0, 16, 3), (0, 9, 15),
                             (0, 9, 15), [((8, 11), "#5fa865"), ((12, 15), "#d0605a")], "BAR")
        self.paint_dial_face(a, p, self.temp_c, self.temp_r, self.temp_range, range(80, 141, 10), (80, 120, 140),
                             (80, 140), [((90, 96), "#5fa865"), ((118, 130), "#e09040")], "°C")
        # 翹板開關座與標示
        f = QFont(a.mono, 4)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        p.setFont(f)
        for (x, y), label in zip(self.rockers, ("POWER", "BREW", "STEAM")):
            p.fillPath(rrect(x - 8, y - 11, x + 8, y + 11, 3), C("#1a1b1d"))
            p.setPen(C("#3c4247"))
            p.drawText(QRectF(x - 14, y + 13, 28, 7), Qt.AlignCenter, label)
            p.setPen(Qt.NoPen)
        p.setFont(QFont(a.mono, 6))
        p.setPen(C("#4b5157"))
        p.drawText(QRectF(90, 42, 90, 10), Qt.AlignCenter, "COMPACT · S1")
        # 沖煮頭：從機身底部垂下（同 DESK·01），分水網在把手拿走時看得到
        p.fillRect(QRectF(97, 111.5, 76, 18.5), vgrad(111.5, 130, [(0, C("#6e757c")), (0.35, C("#e3e7ea")),
                                                                 (0.6, C("#a7aeb5")), (1, C("#5c6369"))]))
        p.fillPath(rrect(103, 124, 167, 133, 3), vgrad(124, 133, [(0, C("#5c6369")), (1, C("#2c3034"))]))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#1a1c1f"))
        p.drawEllipse(QPointF(135, 132), 28, 2.4)
        p.setBrush(C("#7d848b", 150))
        p.drawEllipse(QPointF(135, 131.6), 23, 1.3)
        self.paint_drip_tray(p, 44, 226, top=338)
        self.paint_scale(p)

    def paint_front(self, a, p):
        for c, r in ((self.gauge_c, self.gauge_r), (self.temp_c, self.temp_r)):
            self.paint_dial_glass(p, c, r)

    def paint_dynamic(self, a, p):
        ss = a.session
        steam_mode = bool(ss and ss.boiler_mode == "steam") or a.idle_boiler_mode() == "hold"
        target = self.traits.steam_temp if steam_mode else a.params.temp
        ready = abs(a.boiler.temp - target) < 2 and not a.warming
        brewing = a.brewing()
        states = (True, brewing, steam_mode)
        for (x, y), on in zip(self.rockers, states):     # 翹板：開的時候上半部壓下去、亮紅
            top = rrect(x - 6, y - 9, x + 6, y, 2)
            bot = rrect(x - 6, y, x + 6, y + 9, 2)
            p.fillPath(top, vgrad(y - 9, y, [(0, C("#d04030" if on else "#3a3c40")),
                                             (1, C("#8a2418" if on else "#202226"))]))
            p.fillPath(bot, vgrad(y, y + 9, [(0, C("#2a2c30")), (1, C("#4a4c50" if on else "#5a5c60"))]))
        self.paint_lamp(a, p, self.lamps[0], True, "#7ad070")
        self.paint_lamp(a, p, self.lamps[1], ready, "#ffb050")
        self.paint_lamp(a, p, self.lamps[2], steam_mode, "#ff7a40")
        self.paint_wand(a, p)
        p.fillPath(rrect(228, 84, 236, 120, 3), hgrad(228, 236, [(0, C("#5d646b")), (0.5, C("#dfe3e6")),   # 蒸氣閥座與旋鈕蓋在管子轉軸上面
                                                                 (1, C("#5d646b"))]))
        self.paint_steam_knob(a, p, self.knob, 7)

    def paint_collar(self, a, p, pf):
        self.paint_round_collar(a, p, pf, 94, 176, 121, 134, 134)
