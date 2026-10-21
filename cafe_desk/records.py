"""紀錄與收集冊視窗：今天、近兩週、成就、拉花收集、飲品圖鑑"""
import datetime

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPixmap, QPen, QFont, QColor
from PySide6.QtWidgets import (QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QGridLayout,
                               QScrollArea, QPushButton, QFrame)

from .drinks import DRINKS, DRINK_KEYS, FESTIVAL_DRINKS, ART_NAMES, MILK_KINDS
from .beans import ORIGINS
from .festivals import today, FESTIVALS
from .i18n import T
from .machines import MACHINES
from .stats import ACHIEVEMENTS, ART_BOOK, TIER_GROUPS, TIER_OF
from .render.milk import make_art

ACCENT = "#8a5426"


def _title(text):
    lab = QLabel(text)
    lab.setStyleSheet("font-weight:bold; font-size:13px; padding-top:6px;")
    return lab


def _muted(text):
    lab = QLabel(text)
    lab.setStyleSheet("color:#7a6a5a;")
    lab.setWordWrap(True)
    return lab


MEDAL_COLORS = ("#c07a3e", "#aab2ba", "#e0b030")       # 銅、銀、金


def _medals(have, dpr=1.0):
    """分級成就的三個獎牌：解鎖的上色，沒解鎖的是灰色空圈"""
    w, h, r = 46, 18, 6.5
    pm = QPixmap(int(w * dpr), int(h * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    for i, ok in enumerate(have):
        c = QPointF(8 + i * 15, h / 2)
        if ok:
            p.setPen(QPen(QColor(MEDAL_COLORS[i]).darker(140), 1))
            p.setBrush(QColor(MEDAL_COLORS[i]))
            p.drawEllipse(c, r, r)
            p.setPen(QPen(QColor(255, 255, 255, 150), 1))
            p.drawArc(QRectF(c.x() - r + 2.5, c.y() - r + 2.5, 2 * r - 5, 2 * r - 5), 40 * 16, 100 * 16)
        else:
            p.setPen(QPen(QColor("#c8beb2"), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, r - 0.5, r - 0.5)
    p.end()
    return pm


class DaysChart(QWidget):
    """近 14 天：每天杯數（長條）與平均分數（點）"""

    def __init__(self, days):
        super().__init__()
        self.days = days
        self.setMinimumSize(460, 200)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 34, 34, 14, 34
        pw, ph = w - left - right, h - top - bottom
        cups = [d.get("cups", 0) for _, d in self.days]
        cmax = max(5, max(cups) if cups else 0)
        p.setPen(QPen(QColor("#d8cfc4"), 1))
        for i in range(5):
            y = top + ph * i / 4
            p.drawLine(QPointF(left, y), QPointF(left + pw, y))
        p.setPen(QColor("#7a6a5a"))
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        p.drawText(QRectF(0, top - 6, left - 4, 12), Qt.AlignRight | Qt.AlignVCenter, str(cmax))
        p.drawText(QRectF(0, top + ph - 6, left - 4, 12), Qt.AlignRight | Qt.AlignVCenter, "0")
        p.drawText(QRectF(left + pw + 4, top - 6, right, 12), Qt.AlignLeft | Qt.AlignVCenter, "100")
        p.drawText(QRectF(left + pw + 4, top + ph - 6, right, 12), Qt.AlignLeft | Qt.AlignVCenter, "50")
        n = len(self.days)
        slot = pw / max(1, n)
        prev = None
        for i, (date, d) in enumerate(self.days):
            x = left + slot * i + slot / 2
            c = d.get("cups", 0)
            bh = ph * c / cmax
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#c9a27a" if date != today().isoformat() else ACCENT))
            p.drawRoundedRect(QRectF(x - slot * 0.32, top + ph - bh, slot * 0.64, bh), 2, 2)
            p.setPen(QColor("#7a6a5a"))
            md = datetime.date.fromisoformat(date)
            p.drawText(QRectF(x - slot / 2, top + ph + 4, slot, 12), Qt.AlignCenter, f"{md.month}/{md.day}")
            if c:
                avg = d["score_sum"] / c
                y = top + ph - ph * max(0.0, avg - 50) / 50
                if prev:
                    p.setPen(QPen(QColor("#4a7ab0"), 1.4))
                    p.drawLine(prev, QPointF(x, y))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#4a7ab0"))
                p.drawEllipse(QPointF(x, y), 2.6, 2.6)
                prev = QPointF(x, y)
        p.setPen(QColor("#7a6a5a"))
        p.drawText(QRectF(left, h - 14, pw, 12), Qt.AlignCenter, T("長條：杯數　藍點：平均分數"))
        p.end()


class RecordsDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(T("紀錄與收集冊"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        if app.stats.tampered:
            warn = QLabel(T("⚠ 偵測到 {n} 筆紀錄被修改或刪除，這些紀錄不列入統計", n=app.stats.tampered))
            warn.setStyleSheet("color:#b03020; font-weight:bold; padding:4px;")
            warn.setWordWrap(True)
            lay.addWidget(warn)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        st = app.stats.data
        tabs.addTab(self.today_tab(), T("今天"))
        tabs.addTab(self.days_tab(), T("近兩週"))
        tabs.addTab(self.scroll(self.recent_tab()), T("最近幾杯"))
        n = len(st["achievements"])
        tabs.addTab(self.scroll(self.achievements_tab()), T("成就 {n}/{total}", n=n, total=len(ACHIEVEMENTS)))
        tabs.addTab(self.scroll(self.art_tab()), T("拉花收集"))
        tabs.addTab(self.scroll(self.book_tab()), T("圖鑑"))
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(T("關閉"))
        b.clicked.connect(self.close)
        row.addWidget(b)
        lay.addLayout(row)

    @staticmethod
    def scroll(w):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(w)
        return sa

    def today_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        d = self.app.stats.day()
        cups = d["cups"]
        g.addWidget(_title(T("今天 {date}", date=today().isoformat())), 0, 0, 1, 2)
        rows = [(T("杯數"), f"{cups}"),
                (T("平均分數"), f"{d['score_sum'] / cups:.1f}" if cups else "—"),
                (T("點單"), f"{d['orders']}"),
                (T("營業額"), f"${d['revenue']:,}"),
                (T("等太久離開的客人"), f"{d['walkouts']}"),
                (T("平均等待"), T("{s:.0f} 秒", s=d["wait_sum"] / d["waited"]) if d["waited"] else "—"),
                (T("用掉的豆子"), f"{d['beans_g']:.0f} g")]
        for i, (k, v) in enumerate(rows, start=1):
            g.addWidget(QLabel(k), i, 0)
            lab = QLabel(v)
            lab.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(lab, i, 1)
        r = len(rows) + 1
        best = d.get("best")
        g.addWidget(_title(T("今天最好的一杯")), r, 0, 1, 2)
        if best:
            name = best.get("title") if best.get("title") not in DRINKS else T(DRINKS[best["drink"]]["name"])
            g.addWidget(QLabel(T("{name} · {score:.0f} 分", name=name, score=best["score"])), r + 1, 0, 1, 2)
            g.addWidget(_muted(best.get("comment", "")), r + 2, 0, 1, 2)
        else:
            g.addWidget(_muted(T("今天還沒有做咖啡")), r + 1, 0, 1, 2)
        r += 3
        g.addWidget(_title(T("今天做了什麼")), r, 0, 1, 2)
        r += 1
        for k, n in sorted(d["drinks"].items(), key=lambda kv: -kv[1]):
            if k in DRINKS:
                g.addWidget(QLabel(T(DRINKS[k]["name"])), r, 0)
                g.addWidget(QLabel(T("{n} 杯", n=n)), r, 1)
                r += 1
        g.setRowStretch(r, 1)
        g.setColumnStretch(1, 1)
        return w

    def days_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        days = self.app.stats.data["days"]
        t = today()
        series = []
        for i in range(13, -1, -1):
            key = (t - datetime.timedelta(days=i)).isoformat()
            series.append((key, days.get(key, {})))
        lay.addWidget(_title(T("近兩週")))
        lay.addWidget(DaysChart(series))
        total = sum(d.get("cups", 0) for _, d in series)
        ssum = sum(d.get("score_sum", 0) for _, d in series)
        lay.addWidget(_muted(T("兩週共 {n} 杯，平均 {avg} 分；累計 {all} 杯", n=total,
                               avg=f"{ssum / total:.1f}" if total else "—", all=self.app.stats.data["total"])))
        lay.addStretch(1)
        return w

    def recent_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        rows = self.app.stats.recent(30)
        if not rows:
            g.addWidget(_muted(T("還沒有紀錄")), 0, 0)
        for i, c in enumerate(rows):
            ts = (c["ts"] or "")[5:16].replace("T", " ")
            name = c["title"] if c["title"] and c["title"] not in DRINKS else T(DRINKS.get(c["drink"], {}).get("name", c["drink"]))
            g.addWidget(_muted(ts), i, 0)
            g.addWidget(QLabel(name + ("  " + T("（點單）") if c.get("is_order") else "")), i, 1)
            sc = QLabel(T("{score:.0f} 分", score=float(c["score"] or 0)))
            sc.setStyleSheet(f"font-weight:bold; color:{ACCENT};")
            g.addWidget(sc, i, 2)
            com = _muted(c["comment"] or "")
            g.addWidget(com, i, 3)
        g.setColumnStretch(3, 1)
        g.setRowStretch(len(rows) + 1, 1)
        return w

    def achievements_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        st = self.app.stats
        got = st.data["achievements"]
        info = {k: (n, d) for k, n, d in ACHIEVEMENTS}
        values = st.tier_values()
        shown = set()
        i = 0
        for key, name, desc in ACHIEVEMENTS:
            if key in TIER_OF:
                # 分級成就：一組一列，三個獎牌；名稱是目前最高級，說明是下一級
                group = TIER_OF[key][0]
                if group in shown:
                    continue
                shown.add(group)
                tiers = TIER_GROUPS[group]
                level = sum(1 for k, _ in tiers if k in got)
                ok = level > 0
                top = tiers[level - 1][0] if ok else tiers[0][0]
                name = info[top][0]
                if level < 3:
                    nxt = tiers[level][0]
                    desc = T("{desc}（目前 {n:,}）", desc=T(info[nxt][1]), n=values[group])
                    desc = T("下一級：{desc}", desc=desc) if ok else desc
                else:
                    desc = T("已達最高級：{desc}", desc=T(info[top][1]))
                icon = QLabel()
                icon.setPixmap(_medals([k in got for k, _ in tiers], self.devicePixelRatioF()))
                date = max(got[k] for k, _ in tiers if k in got) if ok else ""
                lab = QLabel(f"<b>{T(name)}</b><br><span style='color:#7a6a5a'>{desc}</span>")
            else:
                ok = key in got
                icon = QLabel("🏆" if ok else "🔒")
                icon.setStyleSheet("font-size:18px;" + ("" if ok else "color:#b0a898;"))
                date = got[key] if ok else ""
                lab = QLabel(f"<b>{T(name)}</b><br><span style='color:#7a6a5a'>{T(desc)}</span>")
            if not ok:
                lab.setStyleSheet("color:#9a8e80;")
            g.addWidget(icon, i, 0)
            g.addWidget(lab, i, 1)
            g.addWidget(_muted(date), i, 2)
            i += 1
        g.setColumnStretch(1, 1)
        return w

    def art_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        col = self.app.stats.data["collection"]["art"]
        g.addWidget(_muted(T("每種圖案保留拉得最好的一次")), 0, 0, 1, 4)
        for i, pat in enumerate(ART_BOOK):
            r, c = divmod(i, 4)
            box = QVBoxLayout()
            pic = QLabel()
            pic.setFixedSize(104, 104)
            pic.setAlignment(Qt.AlignCenter)
            info = col.get(pat)
            pm = QPixmap(104, 104)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ece6de"))
            p.drawEllipse(QPointF(52, 52), 50, 50)
            if info:
                tops = {"whip": 1.0, "cocoa": 1.0} if pat == "whip" else ({"caramel": 1.0} if pat == "mark" else {})
                base = "#e9d6bb" if pat not in ("dot",) else "#b07a4a"
                img = make_art(pat, 1.0, info["q"], info["seed"], base, "#8a5a32", 160, tops=tops)
                p.drawImage(QRectF(6, 6, 92, 92), img)
            else:
                p.setBrush(QColor("#d4ccc2"))
                p.drawEllipse(QPointF(52, 52), 44, 44)
                f = QFont(self.font())
                f.setPointSize(26)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#f4efe8"))
                p.drawText(QRectF(0, 0, 104, 104), Qt.AlignCenter, "?")
            p.end()
            pic.setPixmap(pm)
            box.addWidget(pic, 0, Qt.AlignHCenter)
            name = T(ART_NAMES[pat].split("（")[0]) if info else "？？？"
            text = f"<b>{name}</b>"
            if info:
                text += "<br><span style='color:#7a6a5a'>" + T("品質 {q:.0f} · {date}", q=info["q"] * 100,
                                                               date=info["date"]) + "</span>"
            lab = QLabel(text)
            lab.setAlignment(Qt.AlignCenter)
            box.addWidget(lab)
            g.addLayout(box, r + 1, c)
        g.setRowStretch(3, 1)
        return w

    def book_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        col = self.app.stats.data["collection"]
        g.addWidget(_title(T("飲品")), 0, 0, 1, 3)
        r = 1
        keys = list(DRINK_KEYS) + list(FESTIVAL_DRINKS)
        for k in keys:
            info = col["drinks"].get(k)
            name = T(DRINKS[k]["name"]) if info else "？？？"
            if DRINKS[k].get("festival"):
                name += T("（{fest}限定）", fest=T(FESTIVALS[DRINKS[k]["festival"]][0]))
            lab = QLabel(name)
            if not info:
                lab.setStyleSheet("color:#9a8e80;")
            g.addWidget(lab, r, 0)
            g.addWidget(QLabel(T("{n} 杯", n=info["count"]) if info else ""), r, 1)
            g.addWidget(QLabel(T("最高 {s:.0f} 分", s=info["best"]) if info else ""), r, 2)
            r += 1
        for title, items, names in (
                (T("咖啡機"), col["machines"], {k: m.name for k, m in MACHINES.items()}),
                (T("牛奶"), col["milks"], {k: v["name"] for k, v in MILK_KINDS.items()}),
                (T("豆子產地"), col["origins"], {k: v[0] for k, v in ORIGINS.items()})):
            g.addWidget(_title(T("{title}（{n}/{total}）", title=title, n=len(items), total=len(names))), r, 0, 1, 3)
            r += 1
            text = T("、").join(T(names[k]) for k in names if k in items) or "—"
            g.addWidget(_muted(text), r, 0, 1, 3)
            r += 1
        g.setColumnStretch(0, 1)
        g.setRowStretch(r, 1)
        return w
