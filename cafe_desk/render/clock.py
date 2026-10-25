"""營業模式右上角的翻頁鐘（參考使用者的 flip_clock：深色卡片、中間鉸鏈線，數字變化時上半片翻下來、下半片翻出來）

設定在 `CafeDesk.clock_cfg`（設定檔 `flip_clock`）：on 顯示、seconds 秒數、hour12 12 小時制、date 日期與星期。
右鍵「翻頁鐘（營業模式限定）」子選單改。
"""
import datetime
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QFont, QPen

from ..gfx import C, rrect, vgrad
from ..i18n import T, lang

FLIP_T = 0.32                 # 一次翻頁的秒數
CARD_W, CARD_H = 21, 32       # 一張數字卡片（視窗座標，不含縮放）
CARD_GAP, GROUP_GAP = 2, 9    # 同一組兩張卡片的間隔、時與分之間（放冒號）
CLOCK_DEFAULT = {"on": True, "seconds": False, "hour12": False, "date": True}
WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")
WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
CARD_TOP, CARD_BOT, CARD_INK, HINGE = "#2b2e33", "#25272b", "#f1f1f1", "#0a0a0b"


class ClockRenderer:
    def clock_shown(self):
        return self.business() and self.clock_cfg.get("on", True)

    def clock_text(self):
        """現在要顯示的數字（不含冒號）：時分（秒）"""
        c = self.clock_cfg
        now = datetime.datetime.now()
        h, m, s = now.hour, now.minute, now.second
        if c.get("hour12"):
            h = h % 12 or 12
        return f"{h:02d}{m:02d}" + (f"{s:02d}" if c.get("seconds") else "")

    def update_clock(self):
        """每幀：數字變了就記下翻頁（舊數字、開始時間）"""
        if not self.clock_shown():
            self._clock = None
            return
        text = self.clock_text()
        st = self._clock
        if st is None or len(st["digits"]) != len(text):
            self._clock = {"digits": list(text), "flips": [None] * len(text)}
            return
        now = time.perf_counter()
        for i, ch in enumerate(text):
            if ch != st["digits"][i]:
                st["flips"][i] = (st["digits"][i], now)
                st["digits"][i] = ch

    def clock_flipping(self):
        st = self._clock
        now = time.perf_counter()
        return bool(st) and any(f and now - f[1] < FLIP_T for f in st["flips"])

    def set_clock(self, key, value):
        self.clock_cfg[key] = value
        self._clock = None
        self.save_config()
        self.update()

    def paint_clock(self, p):
        """右上角（視窗座標，已乘縮放）：卡片一組兩位數，組間冒號；下面一行日期或「營業時間」"""
        st = self._clock
        if not st or not self.clock_shown():
            return
        digits = st["digits"]
        groups = len(digits) // 2
        w = groups * (2 * CARD_W + CARD_GAP) + (groups - 1) * GROUP_GAP
        x0 = self._scene_w - 10 - w
        y0 = 10
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing)
        p.fillPath(rrect(x0 - 6, y0 - 5, x0 + w + 6, y0 + CARD_H + (19 if self.clock_label() else 6), 6),
                   C("#000000", 70))
        f = QFont(self.mono, 15)
        f.setBold(True)
        now = time.perf_counter()
        x = x0
        for i, ch in enumerate(digits):
            flip = st["flips"][i]
            k = (now - flip[1]) / FLIP_T if flip else 1.0
            self._paint_card(p, QRectF(x, y0, CARD_W, CARD_H), ch, flip[0] if (flip and k < 1) else ch, min(k, 1.0), f)
            x += CARD_W + (CARD_GAP if i % 2 == 0 else GROUP_GAP)
            if i % 2 == 1 and i < len(digits) - 1:                 # 冒號：兩個小圓點
                cx = x - GROUP_GAP / 2
                p.setPen(Qt.NoPen)
                p.setBrush(C("#d8d4cc"))
                for dy in (0.36, 0.64):
                    p.drawEllipse(QPointF(cx, y0 + CARD_H * dy), 1.6, 1.6)
        label = self.clock_label()
        if label:
            p.setFont(QFont(self.ui, 7))
            p.setPen(C("#d8d0c4"))
            p.drawText(QRectF(x0 - 6, y0 + CARD_H + 2, w + 12, 14), Qt.AlignCenter, label)
        p.restore()

    def clock_label(self):
        c = self.clock_cfg
        if not c.get("date", True):
            return ""
        d = datetime.date.today()
        w = (WEEKDAYS if lang() == "zh" else WEEKDAYS_EN)[d.weekday()]
        return T("{m}/{d}（{w}）", m=d.month, d=d.day, w=w)

    def _paint_card(self, p, r, new, old, k, font):
        """一張數字卡片：上半片是新數字、下半片是舊數字；k＜0.5 舊的上半片往下翻到鉸鏈，之後新的下半片從鉸鏈翻出來"""
        hinge = r.top() + r.height() / 2
        top, bot = QRectF(r.left(), r.top(), r.width(), r.height() / 2), QRectF(r.left(), hinge, r.width(), r.height() / 2)
        self._card_half(p, r, top, new, CARD_TOP, font)
        self._card_half(p, r, bot, old if k < 0.5 else new, CARD_BOT, font)
        if k < 0.5:                                                  # 舊的上半片蓋下來（越來越扁）
            self._card_half(p, r, top, old, CARD_TOP, font, sy=1 - 2 * k, hinge=hinge, shade=k)
        elif k < 1.0:                                                # 新的下半片翻出來（越來越長）
            self._card_half(p, r, bot, new, CARD_BOT, font, sy=2 * k - 1, hinge=hinge, shade=1 - k)
        p.setPen(QPen(C(HINGE), 1.2))
        p.drawLine(QPointF(r.left(), hinge), QPointF(r.right(), hinge))
        p.setPen(Qt.NoPen)

    def _card_half(self, p, r, half, ch, bg, font, sy=1.0, hinge=0.0, shade=0.0):
        p.save()
        if sy != 1.0:
            p.translate(0, hinge)
            p.scale(1, max(0.02, sy))
            p.translate(0, -hinge)
        p.setClipRect(half)
        radius = 3
        p.fillPath(rrect(r.left(), r.top(), r.right(), r.bottom(), radius),
                   vgrad(r.top(), r.bottom(), [(0, C(bg)), (1, C(CARD_BOT))]))
        p.setFont(font)
        p.setPen(C(CARD_INK))
        p.drawText(r, Qt.AlignCenter, ch)
        if shade > 0:                                                # 翻的時候暗一點
            p.fillRect(half, C("#000000", int(140 * shade)))
        p.restore()
