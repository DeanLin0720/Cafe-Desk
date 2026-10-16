"""磨豆區（視窗座標）：磨豆機、填壓器、敲渣盒、敲出的粉餅、落粉"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QRadialGradient, QPen, QPainterPath, QFont

from ..gfx import mix, C, vgrad, hgrad, rrect
from ..layout import BEAN_COLORS
from ..util import clamp

DIAL = (63, 140)
HOPPER = [(26, 24), (100, 24), (86, 100), (40, 100)]
GRIND_RANGE = (150.0, 500.0)


def _hopper_path():
    path = QPainterPath()
    path.moveTo(*HOPPER[0])
    for pt in HOPPER[1:]:
        path.lineTo(*pt)
    path.closeSubpath()
    return path


class GrinderRenderer:
    # ───────────── 靜態背景 ─────────────
    def paint_grinder_shadow(self, p):
        sh = QRadialGradient(80, 370, 72)
        sh.setColorAt(0, C("#000000", 110))
        sh.setColorAt(1, C("#000000", 0))
        p.save()
        p.translate(80, 370)
        p.scale(1, 0.1)
        p.translate(-80, -370)
        p.fillRect(QRectF(0, -400, 170, 1600), sh)
        p.restore()

    def paint_grinder_static(self, p):
        # 底座與填壓墊
        p.fillPath(rrect(16, 334, 108, 366, 7), vgrad(334, 366, [(0, C("#3a3d41")), (0.12, C("#26282b")),
                                                                 (1, C("#111214"))]))
        p.fillRect(QRectF(20, 334.5, 84, 1), C("#ffffff", 45))
        p.fillPath(rrect(26, 326, 98, 335, 3), vgrad(326, 335, [(0, C("#4a3a30")), (1, C("#2a201a"))]))
        # 背柱（把手放在它前面）
        p.fillPath(rrect(66, 210, 98, 336, 4), hgrad(66, 98, [(0, C("#1a1b1d")), (0.4, C("#3a3d41")),
                                                              (1, C("#121315"))]))
        # 機身（霧黑）
        body = rrect(28, 100, 98, 226, 10)
        p.fillPath(body, hgrad(28, 98, [(0, C("#121315")), (0.22, C("#3b3e43")), (0.35, C("#4a4e53")),
                                        (0.7, C("#232528")), (1, C("#0f1011"))]))
        p.fillRect(QRectF(32, 101, 62, 1.2), C("#ffffff", 60))
        # 研磨刻度盤（指針是動態的）
        cx, cy = DIAL
        rg = QRadialGradient(cx - 5, cy - 6, 26)
        rg.setColorAt(0, C("#f2f4f5"))
        rg.setColorAt(0.6, C("#9aa1a8"))
        rg.setColorAt(1, C("#4c5258"))
        p.setPen(Qt.NoPen)
        p.setBrush(rg)
        p.drawEllipse(QPointF(cx, cy), 19, 19)
        p.setBrush(C("#1d1f22"))
        p.drawEllipse(QPointF(cx, cy), 14, 14)
        for i in range(21):
            a = math.radians(220 - i * 13)
            r1 = 9.5 if i % 5 == 0 else 11.5
            p.setPen(QPen(C("#d9dde0", 200), 1 if i % 5 == 0 else 0.6))
            p.drawLine(QPointF(cx + r1 * math.cos(a), cy - r1 * math.sin(a)),
                       QPointF(cx + 13 * math.cos(a), cy - 13 * math.sin(a)))
        f = QFont(self.mono, 5)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(C("#8b9095"))
        p.drawText(QRectF(33, 160, 60, 8), Qt.AlignCenter, "GRIND")
        # 顯示窗、指示燈座
        p.fillPath(rrect(38, 172, 88, 188, 3), vgrad(172, 188, [(0, C("#0a140e")), (1, C("#13241a"))]))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#2a2c2f"))
        p.drawEllipse(QPointF(63, 201), 4.4, 4.4)
        # 出粉口與叉架
        chute, fork = self.machine.chute, self.machine.fork
        p.fillPath(rrect(55, 222, 71, chute[1], 2), hgrad(55, 71, [(0, C("#3a3f44")), (0.4, C("#c9ced3")),
                                                                    (1, C("#3a3f44"))]))
        p.fillPath(rrect(36, fork[1] - 6, 98, fork[1] - 1, 2),
                   vgrad(fork[1] - 6, fork[1] - 1, [(0, C("#c9ced3")), (1, C("#4a5055"))]))
        # 豆倉上蓋與頸部
        p.fillPath(rrect(22, 14, 104, 24, 5), vgrad(14, 24, [(0, C("#3e4247")), (1, C("#141517"))]))
        p.fillPath(rrect(36, 96, 90, 104, 2), vgrad(96, 104, [(0, C("#c9ced3")), (1, C("#5d646b"))]))
        # 敲渣盒
        self.paint_knock_box(p, self.machine.knock_box)

    def paint_knock_box(self, p, box):
        x1, y1, x2, y2 = box
        kb = rrect(x1 + 2, y1 + 4, x2 - 2, y2, 6)
        p.fillPath(kb, hgrad(x1, x2, [(0, C("#0f1011")), (0.3, C("#2e3135")), (1, C("#0c0d0e"))]))
        p.fillPath(rrect(x1, y1, x2, y1 + 7, 3), vgrad(y1, y1 + 7, [(0, C("#e3e7ea")), (1, C("#5d646b"))]))
        p.fillPath(rrect(x1 + 4, y1 + 10, x2 - 4, y1 + 15, 2.5), vgrad(y1 + 10, y1 + 15, [(0, C("#5a5e63")),
                                                                                        (1, C("#1e2023"))]))

    # ───────────── 動態 ─────────────
    def bean_pixmap(self, level):
        """豆倉裡的咖啡豆：依存量分級快取，避免每幀畫幾百顆豆子"""
        key = (round(level * 20), self.devicePixelRatioF(), self.scale_f, self.params.roast)
        cache = getattr(self, "_bean_cache", None)
        if cache and cache[0] == key:
            return cache[1]
        # 邏輯尺寸固定 130×110（場景座標），解析度＝螢幕倍率 × 大小比例；
        # 大小比例只由貼圖時的畫筆套用一次，避免放大兩次
        ratio = self.devicePixelRatioF() * self.scale_f
        pm = QPixmap(int(130 * ratio), int(110 * ratio))
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        q.setClipPath(_hopper_path())
        top = 100 - 52 * clamp(key[0] / 20, 0, 1)
        rnd = random.Random(8)
        for _ in range(260):
            bx, by = rnd.uniform(24, 102), rnd.uniform(top, 104)
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
        self._bean_cache = (key, pm)
        return pm

    def paint_grinder_dynamic(self, p):
        wf = self.workflow
        grinding = bool(wf and wf.grinding)
        # 豆子（磨豆時微微震動）
        jig = math.sin(self.anim_t * 90) * 0.5 if grinding else 0.0
        p.save()
        p.translate(0, jig)
        p.drawPixmap(QPointF(0, 0), self.bean_pixmap(self.hopper))
        p.restore()
        hop = _hopper_path()
        p.fillPath(hop, C("#9fb0bc", 38))
        p.setPen(QPen(C("#ffffff", 90), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(hop)
        (x0, y0), (x1, y1) = HOPPER[0], HOPPER[3]                    # 左側斜邊：上寬下窄
        def edge(y):
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
        strip = QPainterPath()
        strip.moveTo(edge(30) + 4, 30)
        strip.lineTo(edge(30) + 9, 30)
        strip.lineTo(edge(92) + 8, 92)
        strip.lineTo(edge(92) + 4, 92)
        strip.closeSubpath()
        p.save()
        p.setClipPath(hop)
        p.fillPath(strip, vgrad(30, 92, [(0, C("#ffffff", 70)), (1, C("#ffffff", 20))]))
        p.restore()

        # 刻度盤指針：對應研磨粒徑
        cx, cy = DIAL
        k = clamp((self.params.grind_um - GRIND_RANGE[0]) / (GRIND_RANGE[1] - GRIND_RANGE[0]), 0, 1)
        a = math.radians(220 - k * 260)
        p.setPen(QPen(C("#ff9a3c"), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(cx + 10 * math.cos(a), cy - 10 * math.sin(a)))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#9aa1a8"))
        p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)

        # 顯示窗：平時顯示粒徑，磨豆時顯示重量
        if wf and wf.name == "grind":
            text = f"{wf.ground_g:4.1f} g"
        else:
            text = f"{self.params.grind_um:.0f}µm"
        f = QFont(self.mono, 7)
        f.setBold(True)
        p.setFont(f)
        rect = QRectF(38, 172, 50, 16)
        p.setPen(C("#ffb040", int(60 * (1 + self.light["night"]))))
        for dx in (-0.7, 0.7):
            p.drawText(rect.translated(dx, 0), Qt.AlignCenter, text)
        p.setPen(C("#ffc566"))
        p.drawText(rect, Qt.AlignCenter, text)

        # 指示燈
        if grinding:
            halo = QRadialGradient(63, 201, 16)
            halo.setColorAt(0, C("#ffa040", 140))
            halo.setColorAt(1, C("#ffa040", 0))
            p.setBrush(halo)
            p.drawEllipse(QPointF(63, 201), 16, 16)
        p.setBrush(C("#ffb050" if grinding else "#4a3b2e"))
        p.drawEllipse(QPointF(63, 201), 3.2, 3.2)

        # 落粉
        if grinding:
            self.paint_falling_grounds(p, wf)

    def paint_falling_grounds(self, p, wf):
        chute, fork = self.machine.chute, self.machine.fork
        surface = fork[1] - 2 - 9 * clamp(wf.ground_g / max(1.0, wf.p.dose), 0, 1)
        length = max(4.0, surface - chute[1])
        rnd = random.Random(2)
        p.setPen(Qt.NoPen)
        for i in range(26):
            ph = (self.anim_t * 3.2 + rnd.random()) % 1.0
            y = chute[1] + ph * length
            x = chute[0] + rnd.gauss(0, 1.1) * (0.4 + ph)
            p.setBrush(C("#3a2414" if i % 3 else "#6a4228", 230))
            p.drawEllipse(QPointF(x, y), 0.9, 0.9)

    def paint_tamper(self, p, pos):
        cx, by = pos
        # 壓粉座：直徑接近濾杯內徑（約 60 px，濾杯外緣 72 px）
        p.fillPath(rrect(cx - 30, by - 11, cx + 30, by, 3),
                   vgrad(by - 11, by, [(0, C("#eef1f3")), (0.45, C("#a7aeb5")), (1, C("#5d646b"))]))
        p.fillRect(QRectF(cx - 28, by - 10.5, 56, 1), C("#ffffff", 120))
        # 頸部與木握把
        p.fillPath(rrect(cx - 6, by - 16, cx + 6, by - 10, 2),
                   hgrad(cx - 6, cx + 6, [(0, C("#5d646b")), (0.45, C("#dfe3e6")), (1, C("#5d646b"))]))
        grip = QPainterPath()
        grip.moveTo(cx - 7, by - 16)
        grip.cubicTo(QPointF(cx - 13, by - 22), QPointF(cx - 12, by - 32), QPointF(cx - 8, by - 36))
        grip.lineTo(cx + 8, by - 36)
        grip.cubicTo(QPointF(cx + 12, by - 32), QPointF(cx + 13, by - 22), QPointF(cx + 7, by - 16))
        grip.closeSubpath()
        p.fillPath(grip, hgrad(cx - 13, cx + 13, [(0, C("#3b2312")), (0.4, C("#8a5a35")), (1, C("#3b2312"))]))

    def paint_puck(self, p, pk):
        if pk["y"] > self.machine.knock_box[1] + 3:          # 已進到敲渣盒裡
            return
        p.save()
        p.translate(pk["x"], pk["y"])
        p.rotate(pk["rot"])
        p.fillPath(rrect(-20, -5, 20, 5, 4), vgrad(-5, 5, [(0, C("#4a2e1c")), (1, C("#1a0f08"))]))
        p.restore()
