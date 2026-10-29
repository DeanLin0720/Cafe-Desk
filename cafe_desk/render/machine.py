"""場景圖層組裝（背景／前景）與把手、咖啡粉繪製

座標：paint_background / paint_front 以場景座標繪製；paint_portafilter 以場景座標繪製。
"""
import math
import random

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath

from ..gfx import mix, C, vgrad, hgrad, rrect
from ..layout import PF_BASKET_W, PF_BASKET_H, PF_TIPS, PF_TIP_Y
from ..util import clamp, lerp

PF_HANDLE_LEN = 88.0         # 握把全長（轉到側面時的長度）
PF_HANDLE_REACH = 60.0       # 握把往右轉開到 90° 的橫向位移


class MachineRenderer:
    """把咖啡機、杯子、磨豆區組成背景與前景圖層；把手與咖啡粉的繪製（所有機器共用）"""

    def paint_background(self, p):
        m = self.machine
        self.paint_side_counter(p)               # 營業模式：咖啡機右邊的出杯台與出餐架
        external = m.traits.grinder == "external"
        if external:
            self.paint_grinder_shadow(p)
        p.save()
        p.translate(m.mx, m.my)
        with self.machine_tint(m):
            m.paint_static(self, p)
        if not self.cupless():
            self.cup.paint_back(p)
        if self.twin_live() and not self.backflushing():   # 雙頭機第二杯：第一杯先送走（cup_away）時照樣畫
            self.twin["cup"].paint_back(p)
        p.restore()
        if external:
            self.paint_grinder_static(p)
        with self.machine_tint(m):
            m.paint_static_scene(self, p)

    def machine_tint(self, m=None):
        """畫這台咖啡機時套用的烤漆換色（裝潢的「咖啡機配色」，沒買或預設銀色就什麼都不換）"""
        from .. import decor
        from ..gfx import recolor
        spec = decor.machine_tint(self.decor_look()[0])
        if spec is None:
            return recolor(None)
        m = m or self.machine
        key = (m.key, spec)
        cache = self.__dict__.setdefault("_remap_cache", {})
        if key not in cache:
            cache[key] = decor.make_remap(m, spec)
        return recolor(cache[key])

    def paint_front(self, p):
        m = self.machine
        p.save()
        p.translate(m.mx, m.my)
        if not self.cupless():
            self.cup.paint_front(p)
        if self.twin_live() and not self.backflushing():
            self.twin["cup"].paint_front(p)
        with self.machine_tint(m):
            m.paint_front(self, p)
        p.restore()

    # ───────────── 把手（視窗座標） ─────────────
    def paint_portafilter(self, p, pf, contents=None):
        """pf: x, y（濾杯左上角）、handle（握把長度）、tilt（度）
        contents: None 或 {"grounds": g, "dose": g, "level": 0~1, "tamped": 0~1, "uneven": 0~1, "puck": bool}"""
        x, y, L, tilt = pf["x"], pf["y"], pf["handle"], pf["tilt"]
        bw = PF_BASKET_W
        p.save()
        p.translate(x, y)
        if abs(tilt) > 0.01:
            p.translate(bw / 2, PF_BASKET_H / 2)
            p.rotate(tilt)
            p.translate(-bw / 2, -PF_BASKET_H / 2)
        bh = PF_BASKET_H
        cx = bw / 2
        chrome_v = [(0, C("#6b7177")), (0.35, C("#f2f4f5")), (0.6, C("#b4bbc1")), (1, C("#4e545a"))]

        # Y 型雙出水嘴：中央短柱往下，再分成兩支斜出
        p.fillPath(rrect(cx - 4.5, bh - 2, cx + 4.5, bh + 4, 1.5),
                   hgrad(cx - 4.5, cx + 4.5, [(0, C("#4e545a")), (0.4, C("#e3e7ea")), (1, C("#4e545a"))]))
        tip_y = PF_TIP_Y
        for tx in PF_TIPS:
            p.setPen(QPen(C("#4e545a"), 5.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx, bh + 2), QPointF(tx, tip_y - 1.5))
            p.setPen(QPen(C("#d9dde0"), 2.0, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(cx - 0.6, bh + 1.6), QPointF(tx - 0.6, tip_y - 2))
            p.setPen(Qt.NoPen)
            p.setBrush(C("#1c1e21"))
            p.drawEllipse(QPointF(tx, tip_y - 0.6), 2.0, 1.0)

        # 卡耳
        for ex in (-3.5, bw - 0.5):
            p.fillPath(rrect(ex, 1.2, ex + 4, 4.6, 1.2), vgrad(1.2, 4.6, chrome_v))
        # 濾杯：直筒鍍鉻杯身（圓柱打光用直向高光）
        body = QPainterPath()
        body.moveTo(1, 4)
        body.lineTo(bw - 1, 4)
        body.lineTo(bw - 1.8, bh - 4)
        body.quadTo(QPointF(bw - 2.5, bh), QPointF(bw - 8, bh))
        body.lineTo(8, bh)
        body.quadTo(QPointF(2.5, bh), QPointF(1.8, bh - 4))
        body.closeSubpath()
        p.fillPath(body, hgrad(0, bw, [(0, C("#555b61")), (0.1, C("#bfc5ca")), (0.27, C("#f7f9fa")),
                                       (0.4, C("#a9b0b7")), (0.68, C("#6c737a")), (0.86, C("#c3c8cd")),
                                       (1, C("#4a5056"))]))
        p.fillPath(body, vgrad(4, bh, [(0, C("#000000", 0)), (0.7, C("#000000", 0)), (1, C("#000000", 70))]))
        # 杯口與溝槽
        p.fillPath(rrect(0, 0, bw, 5.2, 1.6), hgrad(0, bw, [(0, C("#6a7076")), (0.25, C("#ffffff")),
                                                          (0.45, C("#c3c9ce")), (0.8, C("#8a9198")),
                                                          (1, C("#5a6066"))]))
        p.fillRect(QRectF(1, 5.2, bw - 2, 0.9), C("#2a2e32", 170))
        p.fillRect(QRectF(1.5, 6.4, bw - 3, 0.7), C("#ffffff", 90))
        if contents:
            self.paint_grounds(p, contents)
        self.paint_pf_handle(p, bw, bh, L)
        p.restore()

    def paint_pf_handle(self, p, bw, bh, L):
        """握把：一般朝前（從沖煮頭往觀看者伸出來，畫面上是從濾杯前面往下探出的一小段、尾端比較大）；
        L 是握把往右轉開的橫向位移（0＝正對前面，沖煮頭上與放在磨豆機上都是 0；轉開時最多約 24）。
        轉開的角度 φ：sinφ＝L／PF_HANDLE_REACH，握把全長 PF_HANDLE_LEN，朝前的分量讓尖端往下掉（俯視的透視）"""
        chrome_v = [(0, C("#6b7177")), (0.35, C("#f2f4f5")), (0.6, C("#b4bbc1")), (1, C("#4e545a"))]
        s = clamp(L / PF_HANDLE_REACH, 0.0, 1.0)
        c = math.sqrt(1 - s * s)
        cx = bw / 2
        ox, oy = lerp(cx, bw + 13, s), lerp(bh - 5, 12.0, s)                 # 握把根部（頸部接環）
        tx, ty = ox + PF_HANDLE_LEN * s * 0.8, oy + PF_HANDLE_LEN * c * 0.3   # 尖端
        w0, w1 = 9.0, lerp(15.0, 13.0, s)                                    # 根部與尖端的粗細（尖端離觀看者比較近）
        # 頸部：鍍鉻短管與接環
        p.fillPath(rrect(ox - 7, oy - 4, ox + 7, oy + 4, 2), vgrad(oy - 4, oy + 4, chrome_v))
        dx, dy = tx - ox, ty - oy
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        grip = QPainterPath()
        grip.moveTo(ox + nx * w0 / 2, oy + ny * w0 / 2)
        grip.lineTo(tx + nx * w1 / 2, ty + ny * w1 / 2)
        grip.lineTo(tx - nx * w1 / 2, ty - ny * w1 / 2)
        grip.lineTo(ox - nx * w0 / 2, oy - ny * w0 / 2)
        grip.closeSubpath()
        grip.addEllipse(QPointF(tx, ty), w1 / 2, w1 / 2 * (0.9 if s < 0.5 else 0.8))
        top = min(oy, ty) - w1 / 2
        bot = max(oy, ty) + w1 / 2
        p.setPen(Qt.NoPen)
        p.fillPath(grip, vgrad(top, bot, [(0, C("#4a4c50")), (0.25, C("#2a2b2e")), (0.6, C("#141516")), (1, C("#060607"))]))
        p.setPen(QPen(C("#ffffff", 46), 0.9))                                  # 握把上的高光
        p.drawLine(QPointF(ox + nx * 2 - dx * 0.02, oy + ny * 2), QPointF(tx + nx * 2 - dx * 0.06, ty + ny * 2 - dy * 0.06))
        # 尾端的金屬蓋：朝前時是一個圓盤（正對觀看者）
        p.setPen(QPen(C("#b9bfc5"), 1.1))
        p.setBrush(vgrad(ty - w1 / 2, ty + w1 / 2, [(0, C("#e6e9ec")), (1, C("#5a6168"))]))
        r2 = w1 / 2 - 2.2
        p.drawEllipse(QPointF(tx, ty), r2, r2 * (0.9 if s < 0.5 else 0.8))


    def paint_grounds(self, p, c):
        """濾杯上緣的咖啡粉：尖堆 →（布粉）平面 →（填壓）薄而平滑；或用過的濕粉餅"""
        bw = PF_BASKET_W
        p.setPen(Qt.NoPen)
        if c.get("puck"):
            top = QPainterPath()
            top.addEllipse(QPointF(bw / 2, 0.5), bw / 2 - 6, 2.2)
            p.fillPath(top, vgrad(-2, 3, [(0, C("#3a2416")), (1, C("#1e120a"))]))
            p.setBrush(C("#ffffff", 30))
            p.drawEllipse(QPointF(bw / 2 - 12, 0), 14, 0.8)
            return
        g, dose = c.get("grounds", 0.0), max(1.0, c.get("dose", 18.0))
        if g <= 0.05:
            return
        fill = min(1.0, g / dose)
        level, tamped, uneven = c.get("level", 0.0), c.get("tamped", 0.0), c.get("uneven", 0.0)
        peak = 9 * fill * (1 - level) * (1 - tamped)           # 尖堆高度
        flat = (2.8 * fill) * (1 - 0.55 * tamped)               # 布平後的厚度
        rough = (0.5 + 2.6 * uneven) * level * (1 - tamped)     # 布粉不均的起伏
        rnd = random.Random(int(uneven * 100) + 3)
        bumps = [rnd.uniform(-1, 1) for _ in range(9)]
        path = QPainterPath(QPointF(7, 1))
        n = 24
        for i in range(n + 1):
            u = i / n
            xx = 7 + (bw - 14) * u
            mound = peak * math.sin(math.pi * u) ** 1.4
            bi = u * 8
            j = int(bi)
            fr = bi - j
            noise = bumps[min(j, 8)] * (1 - fr) + bumps[min(j + 1, 8)] * fr
            path.lineTo(QPointF(xx, 1 - flat - mound - rough * noise * math.sin(math.pi * u)))
        path.lineTo(QPointF(bw - 7, 1))
        path.closeSubpath()
        dark = "#24160c" if tamped > 0.5 else "#2e1c10"
        p.fillPath(path, vgrad(-14, 2, [(0, C(mix("#6a4228", "#4a2e1a", tamped))), (1, C(dark))]))
        if tamped < 0.9:
            rnd = random.Random(4)
            for _ in range(int(60 * fill)):
                u = rnd.random()
                xx = 9 + (bw - 18) * u
                top = 1 - flat - peak * math.sin(math.pi * u) ** 1.4
                p.setBrush(C("#7a5236" if rnd.random() < 0.5 else "#1e120a", int(150 * (1 - tamped))))
                p.drawEllipse(QPointF(xx, rnd.uniform(top + 0.8, 1)), 0.8, 0.8)
        else:
            p.setBrush(C("#ffffff", 26))
            p.drawEllipse(QPointF(bw / 2 - 10, -flat + 1.2), 22, 0.7)
