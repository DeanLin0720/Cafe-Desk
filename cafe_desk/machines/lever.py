"""復古拉桿機：銅鍋爐、鍍鉻圓頂、彈簧拉桿

特性：拉下拉桿先低壓預浸，放開後彈簧推動、壓力隨萃取遞減（甜感高、通道少）；
大鍋爐熱交換，沖煮頭偏熱、水溫穩但會飄；蒸氣強。
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath, QRadialGradient, QFont

from ..gfx import C, vgrad, hgrad, rrect
from .base import Machine, Traits

PRESSURE_RANGE = (0.0, 12.0)
COPPER = [(0, "#3e1d0c"), (0.12, "#8a4520"), (0.3, "#e8a070"), (0.42, "#c4703e"), (0.75, "#7a3a18"),
          (0.92, "#a85a2c"), (1, "#3a1a0a")]
CHROME = [(0, "#4e545a"), (0.15, "#c9ced3"), (0.32, "#ffffff"), (0.48, "#aab1b8"), (0.78, "#6c737a"),
          (0.92, "#c3c8cd"), (1, "#3e4348")]


def _g(x1, x2, stops):
    return hgrad(x1, x2, [(pos, C(col)) for pos, col in stops])


class Lever(Machine):
    key = "lever"
    name = "復古拉桿機"
    traits = Traits(summary="彈簧拉桿：壓力隨萃取遞減、甜感高；大鍋爐蒸氣強、沖煮頭偏熱",
                    profile="lever", temp_offset=1.0, temp_noise=0.5, boiler_heat=0.35, boiler_draw=0.12,
                    sweet_add=0.5, pressure_cap=10.0, milk="wand", steam_power=1.3)

    drip_area = (40, 230, 340)            # 滴水盤（x1, x2, 上緣；機身座標）
    tip_x = 425                           # 小費罐中心（場景座標）
    scene_w = 455
    mx, my = 150, 18
    group_pf = (99, 128)
    cup_cx, cup_base = 135, 314
    vent = (135, -4)
    card_cx = 150 + 135
    gauge_c, gauge_r = (74, 112), 17
    pivot = (135, 78)
    lever_len = 112

    wand_pivot = (214, 142)
    wand_rest = (246, 236)
    wand_steam = (252, 246)
    knob = (214, 120)

    machine_hit = (150 + 50, 18 - 50, 150 + 220, 18 + 140)
    hover_area = (150 + 24, 18 - 20, 150 + 246, 18 + 364)

    def gauges(self, a):
        return [(self.gauge_c, self.gauge_r, a.gauge, PRESSURE_RANGE)]

    def silhouette(self):
        path = QPainterPath()
        path.addRect(QRectF(62, 40, 146, 260))
        path.addEllipse(QPointF(135, 44), 73, 22)
        path.addPath(rrect(24, 296, 246, 364, 10))
        return path

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), 300, 426)
        self.paint_shadow(a, p, 135, 368, 130, 280)

        # 底座（鍍鉻，銅色飾條）
        base = rrect(24, 296, 246, 364, 10)
        p.fillPath(base, vgrad(296, 364, [(0, C("#eef1f3")), (0.1, C("#b9bfc5")), (0.6, C("#7c838a")),
                                          (1, C("#3e4348"))]))
        p.fillRect(QRectF(28, 302, 214, 3), C("#c4703e"))
        p.fillRect(QRectF(28, 302, 214, 1), C("#ffd0a8", 160))

        # 鍋爐：銅筒 + 鍍鉻箍
        p.fillRect(QRectF(62, 44, 146, 256), _g(62, 208, COPPER))
        p.save()
        p.setClipRect(QRectF(62, 44, 146, 256))
        for i in range(40):                       # 縱向細紋
            x = 62 + i * 3.7
            p.setPen(QPen(C("#ffffff" if i % 3 else "#2a1206", 14), 0.6))
            p.drawLine(QPointF(x, 44), QPointF(x, 300))
        p.restore()
        for y in (64, 276):
            p.fillRect(QRectF(60, y, 150, 9), _g(60, 210, CHROME))
            p.fillRect(QRectF(60, y, 150, 1), C("#ffffff", 180))
        # 圓頂與頂部安全閥
        dome = QPainterPath()
        dome.moveTo(62, 46)
        dome.cubicTo(QPointF(62, 14), QPointF(208, 14), QPointF(208, 46))
        dome.closeSubpath()
        p.fillPath(dome, _g(62, 208, CHROME))
        p.fillPath(dome, vgrad(14, 46, [(0, C("#ffffff", 90)), (1, C("#000000", 30))]))
        p.fillPath(rrect(127, 2, 143, 24, 4), _g(127, 143, CHROME))
        rg = QRadialGradient(133, -2, 9)
        rg.setColorAt(0, C("#ffffff"))
        rg.setColorAt(1, C("#7c838a"))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(135, 0), 8, 6)

        # 銘牌
        p.fillPath(rrect(100, 200, 170, 222, 4), vgrad(200, 222, [(0, C("#f2d6a0")), (1, C("#a8783a"))]))
        f = QFont(a.mono, 6)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(C("#4a2c10"))
        p.drawText(QRectF(100, 200, 70, 22), Qt.AlignCenter, "LEVER · 01")

        # 沖煮頭：大鐘形鍍鉻 + 拉桿支架
        bell = QPainterPath()
        bell.moveTo(108, 84)
        bell.lineTo(162, 84)
        bell.cubicTo(QPointF(164, 104), QPointF(172, 112), QPointF(174, 122))
        bell.lineTo(96, 122)
        bell.cubicTo(QPointF(98, 112), QPointF(106, 104), QPointF(108, 84))
        p.fillPath(bell, _g(96, 174, CHROME))
        for x in (112, 152):
            p.fillPath(rrect(x, 64, x + 6, 90, 2), _g(x, x + 6, CHROME))
        p.fillPath(rrect(110, 60, 160, 68, 3), _g(110, 160, CHROME))

        # 壓力錶（左側小錶）
        p.fillPath(rrect(84, 108, 100, 114, 2), _g(84, 100, CHROME))
        self.paint_dial_face(a, p, self.gauge_c, self.gauge_r, PRESSURE_RANGE, range(13), (0, 6, 12),
                             (0, 6, 12), [((8, 10), "#5fa865"), ((11, 12), "#d0605a")], "BAR")

        # 蒸氣閥座
        p.fillPath(rrect(206, 112, 222, 150, 4), _g(206, 222, CHROME))

        self.paint_drip_tray(p, 40, 230)
        self.paint_scale(p)

    def paint_front(self, a, p):
        self.paint_dial_glass(p, self.gauge_c, self.gauge_r)

    def paint_dynamic(self, a, p):
        self.paint_lamp(a, p, (48, 330), a.boiler.heater, "#ff7a30")
        self.paint_wand(a, p)
        self.paint_steam_knob(a, p, self.knob, 8)

    def paint_collar(self, a, p, pf):
        self.paint_round_collar(a, p, pf, 94, 176, 121, 134, 134)

    def lever_pos(self, a):
        s = a.shot
        if s is None or s.phase == "done":
            return 0.0
        return s.lever_pos()

    def paint_overlay(self, a, p):
        """拉桿：豎起時往上，壓下時朝向觀看者（透視縮短、握球變大）"""
        pos = self.lever_pos(a)
        px, py = self.pivot
        ang = pos * math.radians(150)
        dy = -self.lever_len * math.cos(ang)
        if dy > 0:
            dy *= 0.55
        tip = QPointF(px, py + dy)
        near = math.sin(ang)                               # 越朝向觀看者越粗
        w0, w1 = 7 + 2 * near, 5 + 2 * near
        arm = QPainterPath()
        arm.moveTo(px - w0 / 2, py)
        arm.lineTo(tip.x() - w1 / 2, tip.y())
        arm.lineTo(tip.x() + w1 / 2, tip.y())
        arm.lineTo(px + w0 / 2, py)
        arm.closeSubpath()
        p.fillPath(arm, _g(px - 5, px + 5, CHROME))
        rg = QRadialGradient(px - 2, py - 2, 8)
        rg.setColorAt(0, C("#ffffff"))
        rg.setColorAt(1, C("#5d646b"))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(px, py), 6, 6)
        r = 9 + 4 * near
        ball = QRadialGradient(tip.x() - r * 0.35, tip.y() - r * 0.4, r * 1.3)
        ball.setColorAt(0, C("#6a4a34"))
        ball.setColorAt(0.5, C("#2a1a10"))
        ball.setColorAt(1, C("#0c0805"))
        p.setBrush(ball)
        p.drawEllipse(tip, r, r)
        p.setBrush(C("#ffffff", 70))
        p.drawEllipse(QPointF(tip.x() - r * 0.35, tip.y() - r * 0.4), r * 0.3, r * 0.2)
