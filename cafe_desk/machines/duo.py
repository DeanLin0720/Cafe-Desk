"""營業用雙頭機：參考營業用雙頭機的照片——霧黑機身（深色顆粒烤漆）、鏡面不鏽鋼背板、頂上的溫杯盤、
中間藍底的液晶顯示、每個沖煮頭上面一塊鉻色按鍵面板（五顆藍光圈圓鍵）、兩側的蒸氣桿座與小壓力錶；
寬機身、兩個沖煮頭、左側蒸氣管；磨豆機是獨立的一台「營業用磨豆機」（不鏽鋼、大豆倉，畫在機器左邊，兩個沖煮頭共用；
外觀在 render/grinder.py 的 commercial 款，備粉流程跟其他獨立磨豆機的機型一樣）。

特性：大鍋爐水溫穩、萃取降溫少、蒸氣強；萃取的同時就能打奶；營業級的磨豆機研磨均勻。
營業中排隊裡有能一起做的客人時，兩個沖煮頭一起萃取，一次做兩杯（desk.py 的 start_pair）。

兩個沖煮頭共用一個 Machine 實例：g＝目前在算哪一個（0＝左、1＝右），group_pf、cup_cx 跟著換；
CafeDesk.on_twin() 換到第二杯時把 g 設成 1，結束時設回 0。
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QPainterPath, QFont, QRadialGradient

from ..gfx import C, vgrad, hgrad, rrect
from ..util import clamp
from .base import Machine, Traits

PRESSURE_RANGE = (0.0, 12.0)
GROUPS = (140, 330)                       # 兩個沖煮頭的濾杯左上角 x（機身座標）；間隔要比把手長（約 173）
R = 520                                   # 機身右端（機身座標）：第二支把手的尾端在 473；右邊不再有磨豆區
MX, MY = 140, -2                          # 機身原點（場景座標）：左邊留給獨立磨豆機與敲渣盒（底座左緣 16+MX 在敲渣盒右邊，不重疊）
W, H = R + 30, 426
BODY = ("#3a3d43", "#25272b", "#101113")                # 上機身、下機身、側柱的烤漆漸層（上→下）
BODY_HI = "#4a4d54"


class Duo(Machine):
    key = "duo"
    name = "營業用雙頭機"
    grinder_style = "commercial"
    paint_extra = BODY + (BODY_HI,)                      # 霧黑亮面烤漆的顏色（咖啡機配色整組換）
    traits = Traits(summary="雙沖煮頭、搭配營業用獨立磨豆機（兩頭共用）：萃取時同時打奶，營業中排隊裡有能一起做的客人就兩杯一起做；大鍋爐水溫穩、蒸氣強",
                    temp_noise=0.12, boiler_heat=0.7, boiler_draw=0.1, milk="wand", steam_power=1.5,
                    grinder="external", groups=2)

    drip_area = (52, 488, 338)            # 滴水盤（x1, x2, 上緣；機身座標）
    scene_w = MX + R + 6
    side_gap = 92                         # 玻璃杯離機身遠一點
    side_trim = 44                        # 杯位、配料架往右挪了 22，右端收掉同樣的寬度，視窗總寬不變
    rack_gap = 30                         # 配料架離機身也遠一點
    mx, my = MX, MY
    cup_base = 314
    vent = (110, 50)
    gauge_r = 13
    knob = (32, 78)                       # 左邊蒸氣桿座的中心
    heat_lamp = (R - 14, 108)

    # 蒸氣管（機身座標）：左邊一支；有「雙打奶泡」升級時右邊再一支（鏡射），第二個沖煮頭（g＝1）的杯子用右邊那支
    _WAND = ((78, 118), (90, 210), (96, 222))                # 轉軸藏在遮檐後面                # 蒸氣管在機身內側（離側柱一段距離）

    def _wand(self, i):
        x, y = self._WAND[i]
        return (20 + R - x, y) if self.g == 1 and self.traits.dual_wand else (x, y)

    @property
    def wand_pivot(self):
        return self._wand(0)

    @property
    def wand_rest(self):
        return self._wand(1)

    @property
    def wand_steam(self):
        return self._wand(2)

    machine_hit = (MX + 20, MY + 40, MX + R, MY + 140)
    hover_area = (MX + 16, MY - 20, MX + R + 4, MY + 364)

    g = 0                                 # 目前的沖煮頭（0＝左、1＝右）

    @property
    def group_pf(self):
        return GROUPS[self.g], 128

    @property
    def cup_cx(self):
        return GROUPS[self.g] + 36

    def lcd_rects(self):
        """電子秤的重量與時間：顯示在每個沖煮頭面板下面（上機身），不放在杯子下面的秤上"""
        cx = GROUPS[self.g] + 36
        return QRectF(cx - 58, 86, 56, 13), QRectF(cx + 2, 86, 56, 13)

    def paint_scale(self, p):
        """杯子下面的電子秤（只有承盤；數字改顯示在上機身）"""
        cx, b = self.cup_cx, self.cup_base
        p.fillPath(rrect(cx - 74, b + 2, cx + 74, b + 29, 6), vgrad(b + 2, b + 29, [(0, C("#2a2c2f")), (1, C("#111214"))]))
        p.fillRect(QRectF(cx - 70, b + 2.5, 140, 1), C("#ffffff", 40))

    @property
    def card_cx(self):
        """曲線卡片與拉花卡片的中心（場景 x）：在正在做的那個沖煮頭的杯子上方（做第二杯時往右移）"""
        return MX + GROUPS[self.g] + 36

    def gauge_c(self, g):
        """背板上的小圓壓力錶：左邊的沖煮頭在背板左側、右邊的在右側"""
        return (60, 178) if g == 0 else (R - 40, 178)

    def buttons(self, g):
        """每個沖煮頭面板上的五顆鍵：單份、雙份、連續（中間，沖煮中亮暖色燈）、半連續、熱水"""
        cx = GROUPS[g] + 36
        return tuple((cx + 17.5 * k, 70) for k in (-2, -1, 0, 1, 2))

    def gauges(self, a):
        return [(self.gauge_c(0), self.gauge_r, a.gauge, PRESSURE_RANGE),
                (self.gauge_c(1), self.gauge_r, a.twin_get("gauge"), PRESSURE_RANGE)]

    def silhouette(self):
        path = QPainterPath()
        path.addPath(rrect(20, 44, R, 112, 22))
        path.addRect(QRectF(20, 100, R - 20, 240))
        path.addPath(rrect(16, 326, R + 4, 368, 18))
        return path

    def paint_static(self, a, p):
        self.paint_soft_shadow(p, self.silhouette(), W, H)
        self.paint_shadow(a, p, (20 + R) / 2, 370, (20 + R) / 2, R)
        # 鏡面不鏽鋼背板：亮面加斜的反光條
        px1, px2 = 38, R - 18
        p.fillRect(QRectF(px1, 106, px2 - px1, 232), hgrad(px1, px2, [(0, C("#6a7077")), (0.06, C("#d3d9de")),
                                                                      (0.5, C("#b4bcc3")), (0.94, C("#c4cbd1")),
                                                                      (1, C("#6a7077"))]))
        p.fillRect(QRectF(px1, 150, px2 - px1, 188), vgrad(150, 338, [(0, C("#10141a", 0)), (1, C("#10141a", 110))]))   # 下半部壓暗：玻璃杯才看得清楚
        p.save()
        p.setClipRect(QRectF(px1, 106, px2 - px1, 232))
        for x0, wd in ((96, 26), (190, 10), (330, 34), (414, 10)):
            path = QPainterPath()
            path.moveTo(x0, 106)
            path.lineTo(x0 + wd, 106)
            path.lineTo(x0 + wd - 60, 338)
            path.lineTo(x0 - 60, 338)
            path.closeSubpath()
            p.fillPath(path, C("#ffffff", 80))
        p.restore()
        # 側柱（霧黑烤漆加鉻色內緣）與中柱（細鉻柱，兩個沖煮頭之間）
        for x1, x2, edge in ((22, 38, 36), (R - 18, R - 2, R - 18)):
            p.fillPath(rrect(x1, 100, x2, 340, 5), hgrad(x1, x2, [(0, C(BODY_HI)), (0.5, C(BODY[1])), (1, C(BODY[2]))]))
            p.fillRect(QRectF(edge, 108, 2, 224), C("#eef1f3", 200))
        p.fillRect(QRectF((20 + R) / 2 - 3, 130, 6, 208), hgrad((20 + R) / 2 - 3, (20 + R) / 2 + 3, [(0, C("#7d848b")), (0.4, C("#f2f4f6")), (1, C("#8a9198"))]))
        # 頂部：寬而扁的上機身（兩端圓肩，亮面烤漆）、頂上的鉻色溫杯盤
        body = rrect(20, 46, R, 112, 24)
        p.fillPath(body, vgrad(46, 112, [(0, C(BODY[0])), (0.45, C(BODY[1])), (1, C(BODY[2]))]))
        p.fillRect(QRectF(48, 49, R - 96, 1.6), C("#ffffff", 80))                        # 肩上的亮線
        p.fillPath(rrect(40, 38, R - 20, 47, 3), vgrad(38, 47, [(0, C("#f2f4f6")), (0.5, C("#b8bfc5")),
                                                              (1, C("#6a7077"))]))
        # 面板：最左邊一塊三顆鍵（熱水、蒸氣），每個沖煮頭上面一塊五顆鍵（中間是沖煮鍵，亮燈畫在 paint_dynamic）
        self.paint_key_panel(p, 70, (-11, 0, 11), 7.2)
        for g in (0, 1):
            cx = self.buttons(g)[2][0]
            self.paint_key_panel(p, cx, (-35, -17.5, 0, 17.5, 35), 12.2, round_mid=True, group=g)
            self.g = g                         # 面板下面的液晶螢幕底框（重量、時間的數字由 paint_lcd 疊上去）
            for r in self.lcd_rects():
                lcd = rrect(r.left() - 1, r.top() - 1, r.right() + 1, r.bottom() + 1, 3)
                p.fillPath(lcd, vgrad(r.top() - 1, r.bottom() + 1, [(0, C("#0b0e10")), (1, C("#1a2024"))]))
                p.setPen(QPen(C("#c9ced3", 160), 0.8))
                p.setBrush(Qt.NoBrush)
                p.drawPath(lcd)
            self.g = 0
        f = QFont(a.mono, 6)
        f.setBold(True)
        f.setItalic(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        p.setFont(f)
        p.setPen(C("#e6ecee", 210))
        p.drawText(QRectF(R - 92, 70, 58, 20), Qt.AlignCenter, "DUO · 2G")                # 機身銘牌（右上角）
        # 背板下方的小壓力錶：圓形鉻框（左邊那個是左頭的、右邊是右頭的）
        for g in (0, 1):
            gx, gy = self.gauge_c(g)
            rg = QRadialGradient(gx - 6, gy - 7, 26)
            rg.setColorAt(0, C("#f6f8f9"))
            rg.setColorAt(1, C("#7d848b"))
            p.setPen(QPen(C("#2c3135", 160), 0.8))
            p.setBrush(rg)
            p.drawEllipse(QPointF(gx, gy), 19.5, 19.5)
            p.setPen(Qt.NoPen)
            p.setBrush(C("#fbfbf9"))
            p.drawEllipse(QPointF(gx, gy), 16.5, 16.5)
            self.paint_square_dial(a, p, (gx, gy), self.gauge_r, PRESSURE_RANGE)
        # 左右兩端的蒸氣桿座（黑色圓桿、鉻圈）：照片裡上機身兩端那對黑色橢圓
        for sx in (self.knob[0], R - 14):
            p.fillPath(rrect(sx - 12, 52, sx + 12, 104, 11), vgrad(52, 104, [(0, C("#f2f4f6")), (0.5, C("#9aa1a8")), (1, C("#4e545a"))]))
            p.fillPath(rrect(sx - 8, 56, sx + 8, 100, 8), C("#15161a"))
            p.fillPath(rrect(sx - 3.5, 61, sx + 3.5, 90, 3), vgrad(61, 90, [(0, C("#5a5c60")), (1, C("#0a0a0b"))]))
        p.setPen(Qt.NoPen)
        p.setBrush(C("#0a0a0b"))
        p.drawEllipse(QPointF(*self.heat_lamp), 2.4, 2.4)
        p.drawEllipse(QPointF(*self.vent), 2.0, 1.3)

        # 沖煮頭與分水網：每組有一塊梯形的鉻色座
        for gx in GROUPS:
            housing = QPainterPath()
            housing.moveTo(gx - 16, 111)
            housing.lineTo(gx + 88, 111)
            housing.lineTo(gx + 78, 133)
            housing.lineTo(gx - 6, 133)
            housing.closeSubpath()
            p.fillPath(housing, vgrad(111, 133, [(0, C("#f2f4f6")), (0.5, C("#b4bbc1")), (1, C("#6a7077"))]))
            p.fillRect(QRectF(gx - 2, 111.5, 76, 18.5), vgrad(111.5, 130, [(0, C("#6e757c")), (0.35, C("#e3e7ea")),
                                                                          (0.6, C("#a7aeb5")), (1, C("#5c6369"))]))
            p.fillPath(rrect(gx + 4, 124, gx + 68, 133, 3), vgrad(124, 133, [(0, C("#5c6369")), (1, C("#2c3034"))]))
            p.setPen(Qt.NoPen)
            p.setBrush(C("#1a1c1f"))
            p.drawEllipse(QPointF(gx + 36, 132), 28, 2.4)
            p.setBrush(C("#7d848b", 150))
            p.drawEllipse(QPointF(gx + 36, 131.6), 23, 1.3)
        # 下機身：整塊圓角的烤漆裙板（兩端大弧度、露在滴水盤外面），上緣一條鉻邊，底下兩個黑色機腳
        for fx in (42, R - 44):
            p.fillPath(rrect(fx, 360, fx + 22, 369, 3), C("#0a0a0b"))
        base = rrect(16, 326, R + 4, 366, 20)
        p.fillPath(base, vgrad(326, 366, [(0, C(BODY[0])), (0.35, C(BODY[1])), (1, C(BODY[2]))]))
        p.fillRect(QRectF(34, 329, R - 48, 1.4), C("#ffffff", 70))
        p.fillRect(QRectF(26, 326, R - 28, 3), hgrad(26, R, [(0, C("#7d848b")), (0.3, C("#f2f4f6")), (0.7, C("#b8bfc5")),
                                                             (1, C("#6a7077"))]))

    def paint_key_panel(self, p, cx, offsets, width, round_mid=False, group=None):
        """一塊深灰藍的觸控面板（照片裡上機身的鍵盤）：offsets＝各鍵相對面板中心的 x，width＝鍵的寬度；
        round_mid＝中間那顆是圓的沖煮鍵（亮燈由 paint_dynamic 畫）"""
        half = abs(offsets[0]) + width / 2 + 6
        pod = rrect(cx - half, 58, cx + half, 82, 5)
        p.fillPath(pod, vgrad(58, 82, [(0, C("#42525c")), (1, C("#1e272e"))]))
        p.setPen(QPen(C("#c9ced3", 200), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(pod)
        y = 70
        for k, dx in enumerate(offsets):
            x = cx + dx
            if round_mid and k == len(offsets) // 2:
                p.setPen(QPen(C("#c9ced3"), 1.0))
                p.setBrush(C("#12171b"))
                p.drawEllipse(QPointF(x, y), 6.2, 6.2)
                continue
            w2 = width / 2
            p.fillPath(rrect(x - w2, y - 5.5, x + w2, y + 5.5, 2.2), vgrad(y - 5.5, y + 5.5, [(0, C("#6f8590")), (1, C("#3d4e58"))]))
            p.setPen(QPen(C("#f2f6f8", 230), 0.8))                                       # 鍵上的小符號
            p.setBrush(Qt.NoBrush)
            if k == 0 and len(offsets) == 5:
                p.drawArc(QRectF(x - 2.6, y - 2.6, 5.2, 5.2), 0, -180 * 16)
            elif k == 1 and len(offsets) == 5:
                for d in (-2.6, 2.6):
                    p.drawArc(QRectF(x + d - 2.2, y - 2.2, 4.4, 4.4), 0, -180 * 16)
            else:
                for d in (-2, 0, 2):
                    p.drawLine(QPointF(x + d, y - 2.5), QPointF(x + d + (0.7 if k % 2 else -0.7), y + 2.5))


        self.paint_drip_tray(p, 52, R - 32, top=338, bottom=356)
        for g in (0, 1):                      # 每個沖煮頭下面一台電子秤
            self.g = g
            self.paint_scale(p)
        self.g = 0

    def paint_front(self, a, p):
        """前景圖層：上機身下面的斜面遮檐（蓋在蒸氣管上面，蒸氣管從遮檐後面掛下來）"""
        visor = QPainterPath()
        visor.moveTo(38, 110)
        visor.lineTo(R - 18, 110)
        visor.lineTo(R - 34, 130)
        visor.lineTo(54, 130)
        visor.closeSubpath()
        p.fillPath(visor, vgrad(110, 130, [(0, C("#e9edf0")), (0.5, C("#b4bbc1")), (1, C("#6a7077"))]))
        p.setPen(QPen(C("#2c3135", 90), 0.7))
        for x in range(60, R - 50, 6):
            p.drawLine(QPointF(x, 118), QPointF(x - 1, 126))
        p.fillRect(QRectF(22, 108, R - 22, 3), hgrad(22, R, [(0, C("#7d848b")), (0.3, C("#f2f4f6")), (0.7, C("#b8bfc5")),
                                                          (1, C("#6a7077"))]))

    def paint_dynamic(self, a, p):
        r = 5.6
        self.paint_brew_light(a, p, self.buttons(0)[2], r=r, halo_r=26)
        with a.on_twin():                     # 第二個沖煮頭的燈看第二杯
            self.paint_brew_light(a, p, self.buttons(1)[2], r=r, halo_r=26)
        self.paint_lamp(a, p, self.heat_lamp, a.boiler.heater, "#ff7a30", 2.0)
        right = a.twin_get("wand_angle") if a.twin is not None else 0.0
        if self.traits.dual_wand:
            self.paint_wand(a, p)
            old, self.g = self.g, 1                # 右邊那支（第二個沖煮頭的杯子用）
            try:
                self.paint_wand(a, p, angle=right)
            finally:
                self.g = old
        else:
            self.paint_wand(a, p, angle=max(a.wand_angle, right))     # 一支蒸氣管：兩杯誰在打奶它就動
        self.paint_steam_knob(a, p, self.knob, 7)

    def paint_collar(self, a, p, pf):
        gx = self.group_pf[0]
        self.paint_round_collar(a, p, pf, gx - 5, gx + 77, 121, 134, 134)
