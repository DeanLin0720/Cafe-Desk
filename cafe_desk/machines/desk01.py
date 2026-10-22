"""DESK·01：雙錶不鏽鋼機（原本那台）

特性：PID 溫控穩定、幫浦恆壓；沒有蒸氣管，打奶用旁邊的獨立奶泡機。
"""
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QRadialGradient, QPen, QPainterPath, QFont, QImage

from ..gfx import C, vgrad, hgrad, rrect
from .base import Machine, Traits

STEEL = [(0, "#5a6066"), (0.3, "#e7ebee"), (0.45, "#f8fafb"), (0.75, "#9aa1a8"), (1, "#4d5359")]
PRESSURE_RANGE = (0.0, 12.0)
W, H = 310, 426


def _stops(stops):
    return [(pos, C(col)) for pos, col in stops]


class Desk01(Machine):
    key = "desk01"
    name = "DESK·01 雙錶不鏽鋼機"
    traits = Traits(summary="PID 溫控穩定、恆壓幫浦；搭配獨立奶泡機",
                    temp_noise=0.15, boiler_draw=0.25, milk="frother")

    drip_area = (32, 268, 340)            # 滴水盤（x1, x2, 上緣；機身座標）
    tip_x = 411                           # 小費罐中心（場景座標）
    scene_w = 500
    frother_pos = (439, 296)          # 奶泡機玻璃壺的倒出口（場景座標）
    mx, my = 120, 18
    group_pf = (114, 128)
    cup_cx, cup_base = 150, 314
    vent = (262, 18)
    card_cx = 270
    gauge_c, gauge_r = (60, 62), 26
    temp_c, temp_r = (117, 62), 21
    btn = (240, 62)
    rail_y = 9

    machine_hit = (148, 18, 392, 188)
    hover_area = (148, 18, 392, 382)

    def gauges(self, a):
        return [(self.gauge_c, self.gauge_r, a.gauge, PRESSURE_RANGE),
                (self.temp_c, self.temp_r, a.boiler.temp, self.temp_range)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(28, 14, 272, 112, 16))
        path.addRect(QRectF(30, 100, 240, 250))
        path.addPath(rrect(32, 340, 268, 364, 8))
        return path

    def paint_static(self, a, p):
        # 柔和投影：把機身輪廓畫小再放大，做出模糊效果
        small = QImage(W // 6, H // 6, QImage.Format_ARGB32_Premultiplied)
        small.fill(Qt.transparent)
        sp = QPainter(small)
        sp.setRenderHint(QPainter.Antialiasing)
        sp.scale(1 / 6, 1 / 6)
        sp.translate(5, 8)
        sp.fillPath(self.silhouette(), C("#000000", 255))
        sp.end()
        blur = small.scaled(W // 12, H // 12, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        blur = blur.scaled(W, H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.setOpacity(0.42)
        p.drawImage(0, 0, blur)
        p.setOpacity(1.0)
        g = QRadialGradient(150, 368, 140)
        g.setColorAt(0, C("#000000", 110))
        g.setColorAt(1, C("#000000", 0))
        p.save()
        p.translate(150, 368)
        p.scale(1, 0.09)
        p.translate(-150, -368)
        p.fillRect(QRectF(0, 200, W, 340), g)
        p.restore()

        # 背板凹槽
        p.fillRect(QRectF(48, 104, 204, 244), vgrad(104, 348, [(0, C("#0d0b0a")), (0.25, C("#1f1a17")),
                                                               (1, C("#2d2622"))]))
        p.fillRect(QRectF(48, 104, 204, 30), vgrad(104, 134, [(0, C("#000000", 160)), (1, C("#000000", 0))]))
        rg = QRadialGradient(150, 270, 120)
        rg.setColorAt(0, C("#4a3a2e", 70))
        rg.setColorAt(1, C("#4a3a2e", 0))
        p.fillRect(QRectF(48, 104, 204, 244), rg)

        # 立柱（圓柱打光）
        for x1, x2 in ((30, 50), (250, 270)):
            p.fillRect(QRectF(x1, 100, x2 - x1, 250), hgrad(x1, x2, _stops(STEEL)))

        # 溫杯架
        p.setPen(QPen(C("#8d949b"), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(44, self.rail_y), QPointF(256, self.rail_y))
        p.setPen(QPen(C("#6c7379"), 2))
        for x in (64, 104, 150, 196, 236):
            p.drawLine(QPointF(x, self.rail_y), QPointF(x, self.rail_y + 7))

        # 機身：拉絲不鏽鋼
        body = rrect(28, 14, 272, 112, 16)
        p.fillPath(body, vgrad(14, 112, [(0, C("#f4f6f7")), (0.08, C("#dfe3e6")), (0.55, C("#b7bdc3")),
                                         (0.92, C("#8a9198")), (1, C("#6b7279"))]))
        p.save()
        p.setClipPath(body)
        rnd = random.Random(5)
        for _ in range(260):
            y = rnd.uniform(14, 112)
            x = rnd.uniform(20, 240)
            light = rnd.random() < 0.5
            p.setPen(QPen(C("#ffffff" if light else "#3a4046", rnd.randint(8, 26)), 0.6))
            p.drawLine(QPointF(x, y), QPointF(x + rnd.uniform(30, 120), y))
        p.fillRect(QRectF(28, 14, 244, 3), C("#ffffff", 150))
        p.restore()
        p.setPen(QPen(C("#5d646b"), 1))
        p.drawPath(body)

        # 洩壓口
        p.setPen(Qt.NoPen)
        p.setBrush(C("#3a3f44"))
        p.drawEllipse(QPointF(258, 22), 3.2, 2.2)
        p.setBrush(C("#15171a"))
        p.drawEllipse(QPointF(258, 22.4), 2.0, 1.2)

        # 銘牌（凹刻字）
        f = QFont(a.mono, 8)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(C("#ffffff", 140))
        p.drawText(QRectF(148, 43, 72, 14), Qt.AlignCenter, "ESPRESSO")
        p.setPen(C("#3c4247"))
        p.drawText(QRectF(148, 42, 72, 14), Qt.AlignCenter, "ESPRESSO")
        f2 = QFont(a.mono, 6)
        f2.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f2)
        p.setPen(C("#5d646b"))
        p.drawText(QRectF(148, 58, 72, 12), Qt.AlignCenter, "DESK · 01")

        # 壓力錶與水溫錶
        self.paint_dial_face(a, p, self.gauge_c, self.gauge_r, PRESSURE_RANGE, range(13), (0, 6, 12),
                             (0, 3, 6, 9, 12), [((8, 10), "#5fa865"), ((11, 12), "#d0605a")], "BAR")
        self.paint_dial_face(a, p, self.temp_c, self.temp_r, self.temp_range, range(80, 101, 2), (80, 90, 100),
                             (80, 90, 100), [((90, 96), "#5fa865"), ((98, 100), "#d0605a")], "°C")

        # 沖煮按鈕座
        bx, by = self.btn
        rg = QRadialGradient(bx - 6, by - 8, 28)
        rg.setColorAt(0, C("#f2f4f5"))
        rg.setColorAt(0.6, C("#9aa1a8"))
        rg.setColorAt(1, C("#4c5258"))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(bx, by), 20, 20)
        p.setBrush(C("#25282b"))
        p.drawEllipse(QPointF(bx, by), 16, 16)
        p.setFont(f2)
        p.setPen(C("#ffffff", 140))
        p.drawText(QRectF(bx - 20, by + 23, 40, 10), Qt.AlignCenter, "BREW")
        p.setPen(C("#4b5157"))
        p.drawText(QRectF(bx - 20, by + 22, 40, 10), Qt.AlignCenter, "BREW")

        # 沖煮頭與分水網（把手拿走時看得到）：從機身底部垂下並貼齊
        p.fillRect(QRectF(112, 111.5, 76, 18.5), vgrad(111.5, 130, [(0, C("#6e757c")), (0.35, C("#e3e7ea")),
                                                                    (0.6, C("#a7aeb5")), (1, C("#5c6369"))]))
        p.fillPath(rrect(118, 124, 182, 133, 3), vgrad(124, 133, [(0, C("#5c6369")), (1, C("#2c3034"))]))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#1a1c1f"))
        p.drawEllipse(QPointF(150, 132), 28, 2.4)
        p.setBrush(C("#7d848b", 150))
        p.drawEllipse(QPointF(150, 131.6), 23, 1.3)

        # 接水盤
        tray = rrect(32, 340, 268, 364, 8)
        p.fillPath(tray, vgrad(340, 364, [(0, C("#c9ced3")), (0.15, C("#8d949b")), (1, C("#4b5157"))]))
        p.setPen(QPen(C("#2c3135"), 2.2, Qt.SolidLine, Qt.RoundCap))
        for x in self.drip_slots():
            p.drawLine(QPointF(x, 346), QPointF(x, 357))
        p.setPen(QPen(C("#ffffff", 50), 0.8))
        for x in self.drip_slots():
            p.drawLine(QPointF(x + 2.2, 346), QPointF(x + 2.2, 357))

        self.paint_scale(p)

    def drip_slots(self):
        return range(46, 256, 7)

    def paint_front(self, a, p):
        for c, r in ((self.gauge_c, self.gauge_r), (self.temp_c, self.temp_r)):
            self.paint_dial_glass(p, c, r)

    def paint_dynamic(self, a, p):
        self.paint_brew_light(a, p, self.btn)

    def paint_collar(self, a, p, pf):
        self.paint_round_collar(a, p, pf, 109, 191, 121, 134, 134)
