"""營業模式的成長：檯面上的小費罐（場景座標）與打烊日報收據（視窗座標）"""
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QFont, QFontMetricsF, QPainterPath

from ..drinks import DRINKS
from ..gfx import C, rrect, vgrad
from ..growth import JAR_FULL, MAX_LEVEL, level_name
from ..i18n import T, money, retext
from ..layout import TOP_PAD, WIN_H, FLOOR
from ..util import clamp, lerp

JAR_W, JAR_H = 26, 32
COIN_FALL = 0.45            # 硬幣從上方掉進罐子的秒數
REPORT_SEC = 15.0           # 日報停留秒數（點一下就收起）
REPORT_W = 214


class ShopRenderer:
    # ───────────── 小費罐（場景座標） ─────────────
    def tip_spot(self):
        """小費罐底部中心（場景座標）：義式在咖啡機右邊（各台 machine.tip_x），沖煮台在成品杯右邊"""
        if self.method == "espresso":
            return self.machine.tip_x, FLOOR
        return self._scene_w - 44, FLOOR - 2

    def tip_jar_on(self):
        """小費罐只在營業模式出現（跟點單紙一樣）"""
        return self.business()

    def drop_coin(self, amount):
        """收到小費：一枚硬幣從上方掉進罐子，落下時「叮」一聲（update_coins）"""
        self.coins.append({"t": 0.0, "amount": amount, "seed": len(self.coins) + int(amount), "landed": False})

    def update_coins(self, dt):
        for c in self.coins:
            c["t"] += dt
            if not c["landed"] and c["t"] >= COIN_FALL:
                c["landed"] = True
                self.sound.once("coin", 0.45)
        self.coins = [c for c in self.coins if c["t"] < COIN_FALL + 0.3]

    def paint_tip_jar(self, p):
        if not self.tip_jar_on():
            return
        x, base = self.tip_spot()
        tips = self.stats.day()["tips"]
        falling = sum(c["amount"] for c in self.coins if not c["landed"])
        fill = clamp((tips - falling) / JAR_FULL, 0, 1.6)      # 還在掉的硬幣落下後才算進去
        w, h = JAR_W, JAR_H
        l, r, top = x - w / 2, x + w / 2, base - h
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 60))                            # 影子
        p.drawEllipse(QPointF(x + 1.5, base - 0.5), w * 0.55, 2.4)
        body = rrect(l, top + 3, r, base, 4)
        p.fillPath(body, C("#cfe4ec", 26))                      # 玻璃後壁
        # 罐子裡的硬幣與紙鈔：固定的亂數排列，依今日小費一層一層疊上去
        n = int(round(min(1.0, fill) * 26))
        rnd = random.Random(11)
        p.save()
        p.setClipPath(body)
        if fill > 0.55:                                         # 紙鈔（摺起來斜斜塞在硬幣上面）
            for i in range(1 + int((fill - 0.55) * 6)):
                bx = l + 4 + rnd.uniform(0, w - 12)
                by = base - h * min(0.95, 0.35 + 0.12 * i + 0.3 * min(1.0, fill))
                p.save()
                p.translate(bx, by)
                p.rotate(rnd.uniform(-28, 28))
                p.fillRect(QRectF(-6, -3, 13, 6), C("#7fa36a"))
                p.fillRect(QRectF(-6, -3, 13, 1.2), C("#a8c890"))
                p.restore()
        for i in range(n):
            row, col = divmod(i, 5)
            cx = l + 4.5 + col * (w - 9) / 4 + rnd.uniform(-1.5, 1.5)
            cy = base - 2.6 - row * 2.6 + rnd.uniform(-0.6, 0.6)
            gold = rnd.random() < 0.35
            p.setBrush(C("#c8a040" if gold else "#a9b0b6"))
            p.drawEllipse(QPointF(cx, cy), 3.0, 1.5)
            p.setBrush(C("#f0d888" if gold else "#dfe4e8"))
            p.drawEllipse(QPointF(cx - 0.6, cy - 0.4), 1.5, 0.6)
        p.restore()
        if fill > 1.0:                                          # 超過 $500：紙鈔從罐口露出來
            for i in range(min(4, 1 + int((fill - 1.0) * 6))):
                p.save()
                p.translate(x - 6 + i * 4.5, top + 2)
                p.rotate(-18 + i * 12)
                p.fillRect(QRectF(-2.5, -9, 5, 11), C("#7fa36a"))
                p.fillRect(QRectF(-2.5, -9, 1.3, 11), C("#a8c890"))
                p.restore()
        # 玻璃外壁：邊框、反光、罐口
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#d8ecf4", 120), 1.0))
        p.drawPath(body)
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(l + 3, top + 6, 2.2, h - 10), C("#ffffff", 70))
        p.fillRect(QRectF(r - 5, top + 8, 1.2, h - 14), C("#ffffff", 35))
        p.setBrush(C("#c9d6dc", 150))
        p.drawRoundedRect(QRectF(l - 1.5, top, w + 3, 4), 1.5, 1.5)
        # 紙標籤
        lab = QRectF(l + 3, top + 12, w - 6, 9)
        p.setBrush(C("#efe3c8", 230))
        p.drawRoundedRect(lab, 1, 1)
        f = QFont(self.ui, 4.6)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C("#6a4a2a"))
        p.drawText(lab, Qt.AlignCenter, T("小費"))
        # 正在掉的硬幣
        for c in self.coins:
            if c["landed"]:
                continue
            k = clamp(c["t"] / COIN_FALL, 0, 1)
            cy = lerp(top - 46, base - 4 - min(1.0, fill) * 14, k * k)
            spin = abs(math.cos(c["t"] * 22 + c["seed"]))
            p.setPen(Qt.NoPen)
            p.setBrush(C("#d8b04a"))
            p.drawEllipse(QPointF(x + 2, cy), 3.2, 0.6 + 2.8 * spin)
        p.restore()

    # ───────────── 打烊日報（視窗座標） ─────────────
    def show_report(self, data):
        """顯示打烊日報收據（data 來自 growth.report）"""
        if data is None:
            return
        self.report_card = {"data": data, "t0": time.perf_counter()}
        self.cfg["report_seen"] = max(self.cfg.get("report_seen", ""), data["day"])
        self.tray_message(T("打烊日報 {day}：服務 {n} 位，營業額 {rev}", day=data["day"], n=data["served"],
                            rev=money(data["revenue"])))
        self.sound.once("ding_hi", 0.3)
        self.save_config()
        self.update()                                  # wanted_interval 在收據顯示時維持 AMBIENT

    def report_alpha(self):
        rc = self.report_card
        if rc is None:
            return 0.0
        t = time.perf_counter() - rc["t0"]
        if t >= REPORT_SEC:
            self.report_card = None
            return 0.0
        return clamp(min(t / 0.4, (REPORT_SEC - t) / 0.6), 0, 1)

    def dismiss_report(self):
        rc = self.report_card
        if rc is not None:                             # 快速淡出
            rc["t0"] = min(rc["t0"], time.perf_counter() - REPORT_SEC + 0.6)

    def report_lines(self, d):
        """收據內容：(左, 右, 種類)；種類 head／sub／row／dash／text／bar"""
        lines = [(T("打烊日報"), "", "head"), (d["day"], "", "sub"),
                 (T("Lv.{n} {name}", n=d["level"], name=T(level_name(d["level"]))), "", "sub"), ("", "", "dash"),
                 (T("服務客人"), T("{n} 位", n=d["served"]), "row"),
                 (T("等太久離開"), T("{n} 位", n=d["walkouts"]), "row"),
                 (T("營業額"), money(d["revenue"]), "row"),
                 (T("　其中小費"), money(d["tips"]), "row"),
                 (T("平均分數"), f"{d['avg']:.1f}", "row"),
                 (T("平均等待"), T("{s:.0f} 秒", s=d["wait"]) if d["wait"] is not None else "—", "row"),
                 ("", "", "dash")]
        best = d.get("best")
        if best:
            name = retext(best.get("title")) if best.get("title") not in DRINKS else T(DRINKS[best["drink"]]["name"])
            lines += [(T("最佳一杯"), "", "row"), (T("{name} · {score:.0f} 分", name=name, score=best["score"]), "", "text")]
        if d["change"] is not None:
            arrow = "↑" if d["change"] >= 0 else "↓"
            lines.append((T("比上一個營業日"), f"{arrow} {abs(d['change']) * 100:.0f}%", "row"))
        lines.append(("", "", "dash"))
        lv, nxt, prog = d["progress"]
        if d["level"] > d["level_from"]:
            lines.append((T("升級！Lv.{a} → Lv.{b}", a=d["level_from"], b=d["level"]), "", "text"))
        if lv < MAX_LEVEL:
            lines.append((T("距離 Lv.{n}", n=lv + 1), T("還差 {m}", m=money(d["need"])), "row"))
            lines.append(("", prog, "bar"))
        else:
            lines.append((T("已經是最高等級"), "", "text"))
        if d["achievements"]:
            lines.append((T("今天解鎖 {n} 個成就", n=len(d["achievements"])), "", "text"))
        lines.append((T("點一下收起"), "", "hint"))
        return lines

    def paint_report(self, p):
        a = self.report_alpha()
        if a <= 0.01:
            return
        d = self.report_card["data"]
        lines = self.report_lines(d)
        lh = {"head": 19, "sub": 12.5, "row": 13.5, "text": 13.5, "dash": 8, "bar": 9, "hint": 14}
        h = 14 + sum(lh[k] for _, _, k in lines)
        w = REPORT_W
        x0 = self._scene_w / 2 - w / 2
        y0 = TOP_PAD + WIN_H / 2 - h / 2 - 20 + (1 - a) * 26        # 從下面往上滑出來
        p.save()
        p.setOpacity(a)
        p.translate(x0, y0)
        paper = QPainterPath()                                     # 收據：下緣鋸齒
        paper.moveTo(0, 0)
        paper.lineTo(w, 0)
        paper.lineTo(w, h)
        teeth = 14
        for i in range(teeth):
            xa = w - (i + 0.5) * w / teeth
            paper.lineTo(xa, h - 4)
            paper.lineTo(w - (i + 1) * w / teeth, h)
        paper.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(C("#000000", 80))
        p.drawPath(paper.translated(3, 4))
        p.fillPath(paper, vgrad(0, h, [(0, C("#fbf8f0")), (1, C("#efe8d8"))]))
        y = 8
        mono = QFont(self.ui, 8)
        bold = QFont(self.ui, 8)
        bold.setBold(True)
        for left, right, kind in lines:
            hh = lh[kind]
            rect = QRectF(14, y, w - 28, hh)
            if kind == "head":
                f = QFont(self.ui, 11)
                f.setBold(True)
                p.setFont(f)
                p.setPen(C("#2a1d12"))
                p.drawText(rect, Qt.AlignCenter, left)
            elif kind == "sub":
                p.setFont(QFont(self.ui, 7))
                p.setPen(C("#7a6a56"))
                p.drawText(rect, Qt.AlignCenter, left)
            elif kind == "dash":
                p.setPen(QPen(C("#b8ab92"), 0.8, Qt.DashLine))
                p.drawLine(QPointF(14, y + hh / 2), QPointF(w - 14, y + hh / 2))
            elif kind == "bar":
                p.setPen(Qt.NoPen)
                p.fillRect(QRectF(14, y + 2, w - 28, 3.5), C("#e2d8c2"))
                p.fillRect(QRectF(14, y + 2, (w - 28) * right, 3.5), C("#b06a2a"))
            elif kind == "hint":
                p.setFont(QFont(self.ui, 6))
                p.setPen(C("#a89a86"))
                p.drawText(rect.adjusted(0, 2, 0, 0), Qt.AlignCenter, left)
            else:
                p.setFont(bold if kind == "text" else mono)
                p.setPen(C("#3a2a1a" if kind == "row" else "#8a4a1a"))
                fm = QFontMetricsF(p.font())
                rw = fm.horizontalAdvance(right) + 6 if right else 0
                p.drawText(rect.adjusted(0, 0, -rw, 0), Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(left, Qt.ElideRight, rect.width() - rw))
                if right:
                    p.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, right)
            y += hh
        p.restore()
