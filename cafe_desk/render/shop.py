"""營業模式：咖啡機旁的出杯台與出餐架、櫃檯畫面（現代 POS、交付）（場景座標）、打烊日報收據（視窗座標）"""
import random
import time

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QFont, QFontMetricsF, QPainterPath, QImage, QPainter, QLinearGradient

from ..cups import PAPER_SIZE, ICED_CUPS, paint_paper_body
from .. import orders
from ..drinks import DRINKS
from .icons import drink_icon
from ..machines import MACHINES
from ..gfx import C, rrect, vgrad, hgrad
from ..growth import MAX_LEVEL, level_name
from ..i18n import T, money, retext
from ..layout import TOP_PAD, WIN_H, FLOOR
from ..util import clamp, lerp

SIDE_W, SIDE_W2 = 170, 128  # 營業模式咖啡機右邊的出杯台寬度（雙頭機多一個杯位）
SHELF_Y = FLOOR - 178       # 出杯台上方出餐架的高度（場景座標）
MAT_H = 6                   # 出杯台吧台墊的厚度：杯底在墊子上緣
MENU_X0, MENU_X1 = 170, 840  # 櫃檯畫面：吊掛菜單看板與後方層架的左右範圍（右上角留給翻頁鐘）
CASE_IN = 300               # 前櫃檯右段甜點玻璃櫃的左端距視窗右邊
CUPS_X = 150                # 做好的杯子從這裡開始排（POS 在甜點櫃左邊）
# 店面配色（使用者選的暖木）：牆、看板、後檯、前櫃檯、地板
STORE = {"wall": ("#2b2522", "#1b1715"), "blind": "#c8b89a", "board": "#1e1c1a", "accent": "#ffd27a", "shelf": "#8a6440",
         "front": ("#7a5434", "#4a3220"), "top": ("#e8dcc8", "#b8a88e"), "logo": "#f0dcb8",
         "floor": ("#5a4030", "#3a2a20")}
SIGN_DX, SIGN_W = 122, 62  # 座位小黑板：中心在 POS 左邊多遠、寬度
COUNTER_CUP_K = 0.4         # 櫃檯上的杯子縮小成跟 POS 相稱的真實比例（紙杯跟刷卡機差不多高）
PASS_K = 0.55               # 出餐架上等著的杯子縮小的比例
COUNTER_TOP = 300           # 櫃檯畫面的檯面高度（場景座標）
FLOAT_SEC = 1.6
RESULT_SHOW = 15.0          # 營業模式：客人的評價在狀態列顯示幾秒（之後回到「等待客人點單…」）             # 收錢時金額往上飄的秒數
DELIVERY_T = {"in": 0.7, "place": 0.9, "pickup": 0.9, "out": 0.65}   # 櫃檯交付各段的秒數（模擬時間；咖啡師在等，改了要重跑平衡模擬）
CHECKOUT_T = {"in": 0.5, "pay": 2.0}        # 接單時在櫃檯結帳：切到櫃檯、每一組客人刷卡（同上，改了要重跑平衡模擬）
REPORT_SEC = 15.0           # 日報停留秒數（點一下就收起）
REPORT_W = 214


class ShopRenderer:
    # ───────────── 出杯台（咖啡機畫面，場景座標） ─────────────
    def side_on(self):
        """營業模式的義式畫面：咖啡機右邊多一段出杯台，杯子放這裡（量杯在沖煮頭下接濃縮，拿過來倒）"""
        return self.business() and self.method == "espresso"

    def side_extra(self):
        """出杯台的寬度（雙頭機有兩個杯位）"""
        if not self.business():
            return 0
        return SIDE_W + (SIDE_W2 if self.machine.traits.groups > 1 else 0)

    def side_spot(self, g=0):
        """出杯台上第 g 個杯位的杯底中心（場景座標）"""
        return self.machine.scene_w + 66 + g * SIDE_W2, FLOOR

    def paint_side_counter(self, p):
        """出杯台的吧台墊與上方的出餐架（背景圖層）"""
        if not self.side_on():
            return
        x0 = self.machine.scene_w + 6
        x1 = self.machine.scene_w + self.side_extra() - 6
        for g in range(1 + (self.machine.traits.groups > 1)):
            cx, base = self.side_spot(g)
            top = base - MAT_H                                          # 墊子上緣＝杯底（杯子站在墊子上）
            p.fillPath(rrect(cx - 60, top, cx + 60, base, 2), vgrad(top, base, [(0, C("#3a3c40")), (0.35, C("#25262a")),
                                                                                (1, C("#111213"))]))
            p.setPen(QPen(C("#46484c"), 0.8))
            for x in range(int(cx - 54), int(cx + 56), 6):
                p.drawLine(QPointF(x, top + 1.5), QPointF(x + 1.5, base - 1.5))
            p.setPen(Qt.NoPen)
        y = SHELF_Y                                                     # 出餐架：等同一張單的其他杯子
        p.fillPath(rrect(x0, y, x1, y + 6, 2), vgrad(y, y + 6, [(0, C("#b98a5a")), (1, C("#6a4a2e"))]))
        for x in (x0 + 10, x1 - 14):
            p.fillPath(rrect(x, y + 6, x + 4, y + 20, 1), C("#3a3632"))

    def paint_pass_cups(self, p):
        """出餐架上等著一起送出去的杯子（縮小）"""
        if not self.ready or not self.side_on():
            return
        x = self.machine.scene_w + 30
        for c in self.ready[-4:]:
            p.save()
            p.translate(x, SHELF_Y)
            p.scale(PASS_K, PASS_K)
            self.paint_ready_cup(p, c, 0.0, 0.0)
            p.restore()
            x += (c["top"] * PASS_K) + 14

    # ───────────── 做好的杯子 ─────────────
    def take_cup(self, o):
        """營業模式一杯做完：把杯子連同杯中的咖啡拍成一張圖（cup.paint_back → 液體 → paint_front），杯子收起來。
        同一張單的杯子都好了，就排進櫃檯交付（pending_deliveries）；還沒好的放在出餐架上等"""
        cup = self.cup
        x1, y1, x2, y2 = cup.TL - 14, cup.T - 46, cup.TR + 34, cup.B + 8
        ratio = self.devicePixelRatioF() * self.scale_f
        img = QImage(int((x2 - x1) * ratio) + 1, int((y2 - y1) * ratio) + 1, QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(ratio)
        img.fill(Qt.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.Antialiasing)
        q.translate(-x1, -y1)
        cup.paint_back(q)
        self.paint_liquid(q)
        self.paint_ice(q)
        self.paint_condensation(q)
        cup.paint_front(q)
        q.end()
        self.ready.append({"img": img, "off": (x1 - cup.CX, y1 - cup.B), "top": cup.TR - cup.TL, "h": cup.B - cup.T,
                           "handle": cup.handle, "paper": cup.paper, "z": cup.z, "mark": cup.mark(), "iced": cup.kind in ICED_CUPS, "to_go": o.to_go,
                           "whip": self.topping.get("whip", 0) > 0.05,
                           "order": o})
        if self._in_twin:
            self.cup = None                                   # 雙頭機的第二杯：右邊的杯位收走
        else:
            self.cup_away = True
        self.check_party(o.party or [o])

    def check_party(self, party):
        """同一張單的杯子都做好了：從出餐架拿下來，排進櫃檯交付"""
        if not all(x.state in ("done", "leaving") for x in party):
            return
        cups = [c for c in self.ready if any(c["order"] is x for x in party)]
        if not cups:
            return
        self.ready = [c for c in self.ready if all(c is not k for k in cups)]
        self.pending_deliveries.append({"cups": cups, "orders": list(party), "paid": True,
                                        "price": sum(x.price for x in party), "tip": sum(x.tip for x in party)})

    def paint_ready_cup(self, p, c, x, base, alpha=1.0):
        """一杯做好的飲品（拍好的圖）：外帶紙杯加杯蓋與隔熱套、外帶冰飲加圓頂蓋、內用有把手的放杯盤"""
        p.save()
        p.setOpacity(p.opacity() * alpha)
        if not c["to_go"] and c["handle"]:
            paint_saucer(p, x, base, c["top"] * 1.3)
        ox, oy = c["off"]
        p.drawImage(QPointF(x + ox, base + oy), c["img"])
        if c["paper"]:                                                      # 加鮮奶油的外帶熱飲：圓頂蓋罩住鮮奶油
            paint_paper_cup(p, x, base, c["paper"], c["z"], c.get("mark", ""), dome=c.get("whip", False))
        elif c["to_go"] and c["iced"]:
            paint_dome_lid(p, x, base - c["h"], c["top"])
        p.restore()

    # ───────────── 接單結帳（櫃檯畫面） ─────────────
    def start_checkout(self):
        """咖啡師接單：先在櫃檯讓排隊裡還沒付錢的客人一組一組刷卡（點單付錢），結完才開始做。咖啡師要等（busy）"""
        groups = []
        for x in [self.order] + self.queue:
            if x is None or x.state != "waiting" or x.paid:
                continue
            g = x.party or [x]
            if all(g is not y for y in groups):
                groups.append(g)
        parties = [{"orders": g, "cups": g, "price": sum(x.price for x in g)} for g in groups]
        if not parties:
            return
        self.checkout = {"parties": parties, "i": 0, "phase": "in", "t": 0.0, "k": 0.0}
        if not self.counter_view:
            self.begin_fade()
            self.counter_view = True
        self.set_frame_interval(16)

    def update_checkout(self, sdt):
        """接單結帳的時間軸（模擬時間）：in →（每一組）pay；刷卡時嗶一聲、收據印出來、飄出金額"""
        ck = self.checkout
        ck["t"] += sdt
        ck["k"] = k = clamp(ck["t"] / CHECKOUT_T[ck["phase"]], 0, 1)
        party = ck["parties"][ck["i"]]
        if ck["phase"] == "pay" and not party.get("paid") and k >= 0.45:
            party["paid"] = True
            for x in party["orders"]:
                x.paid = True
            self.sound.once("beep", 0.35)
            self.sound.once("coin", 0.45)
            self.reg_floats.append({"text": "+" + money(party["price"]), "tip": 0, "t": 0.0})
        if k < 1:
            return
        if ck["phase"] == "in":
            ck["phase"] = "pay"
        else:
            ck["i"] += 1
            if ck["i"] >= len(ck["parties"]):
                self.checkout = None                                        # 結完了：接著開始做（update_order）
                return
        ck["t"], ck["k"] = 0.0, 0.0

    # ───────────── 櫃檯交付（獨立畫面，不顯示咖啡機） ─────────────
    def start_delivery(self):
        """把排好的單一次帶到櫃檯：切到櫃檯畫面、放杯子、客人一位一位取走（取走後才評分），再切回咖啡機。咖啡師要等（busy）"""
        parties, self.pending_deliveries = self.pending_deliveries, []
        self.delivery = {"parties": parties, "i": 0, "phase": "in", "t": 0.0, "k": 0.0}
        self.begin_fade()
        self.counter_view = True
        self.set_frame_interval(16)

    def reveal_party(self, party):
        """客人取餐後公布這張單的分數：寫進紀錄（成就、營業額）、POS 顯示星等、飄出小費、狀態列顯示客人的反應、
        點單紙蓋章；好幾杯的看平均"""
        shown = [x for x in party["orders"] if not x.revealed]
        for x in shown:
            x.revealed = True
            if x.rec is not None:
                self.save_cup(x.rec)
                x.rec = None
            if x is self.order and x.state == "done":
                x.t = 0.0                                                   # 點單紙現在才蓋章
        if not shown:
            return
        avg = sum(x.score for x in shown) / len(shown)
        party["score"] = avg
        tip = sum(x.tip for x in shown)
        if tip > 0:                                                         # 喝了才給小費
            self.reg_floats.append({"text": T("小費 +{m}", m=money(tip)), "tip": 0, "t": 0.0})
        if len(party["cups"]) >= 3:
            self.announce(self.stats.unlock("party_3"))
        last = shown[-1].result
        if last is not None:
            if len(shown) > 1:                                              # 好幾杯：「n 杯 平均分數」，反應看分數最低的那杯
                low = min(shown, key=lambda x: x.score)
                last = type(last)(last.drink, avg, T("{name}：{text}", name=T(low.name), text=low.reaction),
                                  last.milk, T("{n} 杯", n=len(shown)))
            self.result = last
            self.result_until = time.perf_counter() + RESULT_SHOW                # 評價顯示一陣子就收起來
        self.sound.once("ding_hi" if avg >= 80 else "ding_lo", 0.55)

    def flush_unpaid(self):
        """關掉程式時還沒結帳的杯子：直接寫進紀錄（不然做好的杯子會不見）"""
        groups = [c["order"] for c in self.ready]
        for d in self.pending_deliveries + (self.delivery["parties"] if self.delivery else []):
            groups += d["orders"]
        for x in groups:
            if not x.revealed and x.rec is not None:
                x.revealed = True
                self.save_cup(x.rec)
                x.rec = None

    def update_delivery(self, sdt):
        """櫃檯交付的時間軸（模擬時間：咖啡師在等，營業模擬要算進去）"""
        for f in self.reg_floats:
            f["t"] += sdt
        self.reg_floats = [f for f in self.reg_floats if f["t"] < FLOAT_SEC]
        d = self.delivery
        if d is None:
            return
        d["t"] += sdt
        d["k"] = k = clamp(d["t"] / DELIVERY_T[d["phase"]], 0, 1)
        party = d["parties"][d["i"]] if d["i"] < len(d["parties"]) else None
        if k < 1:
            return
        if d["phase"] == "in":
            d["phase"] = "place"
        elif d["phase"] == "place":
            d["phase"] = "pickup"
        elif d["phase"] == "pickup":
            self.reveal_party(party)                                        # 客人拿到飲品：公布分數
            self.seated += [random.uniform(*orders.SIT_TIME) for x in party["orders"] if not x.to_go]   # 內用的去坐
            if len(self.seated) >= self.seats():
                self.announce(self.stats.unlock("seats_full"))
            d["i"] += 1
            if d["i"] < len(d["parties"]):
                d["phase"] = "pickup"
            else:
                d["phase"] = "out"
                if not self.idle_counter():                                 # 沒客人等著做就留在櫃檯
                    self.begin_fade()
                    self.counter_view = False
        elif d["phase"] == "out":
            self.delivery = None
            return
        d["t"], d["k"] = 0.0, 0.0

    def paint_room(self, p, W, top):
        """店面（照使用者的參考圖，配色跟遊戲一樣偏暗暖）：牆、左邊百葉窗、吊掛的菜單看板、
        後檯的咖啡機（遊戲裡的機型，店鋪頁可以選哪一台）"""
        pal = STORE
        p.fillRect(QRectF(0, -TOP_PAD, W, top + TOP_PAD), vgrad(-TOP_PAD, top - 64, [          # 牆：跟操作畫面的背景同一套，
            (0, C(pal["wall"][0])), (1, C(pal["wall"][1]))]))                               # 越往下越暗，跟檯面分得開
        # 左邊的窗與百葉
        p.fillPath(rrect(14, -96, 124, 214, 3), C("#1a1410"))
        p.fillRect(QRectF(20, -90, 98, 298), vgrad(-90, 208, [(0, C("#1c2a3e")), (1, C("#3a4a5e"))]))
        p.setPen(QPen(C(pal["blind"], 200), 3))
        for y in range(-86, 206, 9):
            p.drawLine(QPointF(20, y), QPointF(118, y))
        p.setPen(Qt.NoPen)
        # 吊掛的菜單看板（四塊；第二塊是熱賣前三，第一、三塊畫一杯飲品，第四塊是其他品項）
        title, top3 = self.stats.top_drinks(3)
        n, bw, bh = 4, 150, 70
        gap = (MENU_X1 - MENU_X0 - n * bw) / (n - 1)
        for i in range(n):
            bx = MENU_X0 + i * (bw + gap)
            by = -84
            p.setPen(QPen(C("#111111"), 1))
            for wx in (bx + 20, bx + bw - 20):
                p.drawLine(QPointF(wx, -TOP_PAD), QPointF(wx, by))
            p.setPen(Qt.NoPen)
            light = False
            p.fillPath(rrect(bx - 3, by - 3, bx + bw + 3, by + bh + 3, 4), C("#0e0d0c"))
            p.fillPath(rrect(bx, by, bx + bw, by + bh, 2), C(pal["board2"] if light else pal["board"]))
            ink = C("#3a2a1e") if light else C("#efe6d4")
            sub = C("#7a6a56") if light else C("#c8b8a0")
            if i in (0, 2):                                                 # 品項清單
                keys = [k for k, _n in top3] if i == 0 and top3 else ["espresso", "americano", "latte", "cappuccino"]
                head = T(title) if i == 0 and top3 else "COFFEE"
                if i == 2:
                    keys, head = ["iced_americano", "iced_latte", "mocha", "flat_white"], "MILK & ICE"
                f = QFont(self.ui, 6.5)
                f.setBold(True)
                p.setPen(C(pal["accent"]))
                self.fit_text(p, QRectF(bx + 6, by + 3, bw - 12, 12), head, f, Qt.AlignCenter)
                rf = QFont(self.ui, 5.5)
                for j, k in enumerate(keys[:4]):
                    y = by + 17 + j * 12.5
                    p.setPen(ink)
                    self.fit_text(p, QRectF(bx + 8, y, bw - 56, 11), T(DRINKS[k]["name"]), rf)
                    p.setPen(sub)
                    self.fit_text(p, QRectF(bx + bw - 48, y, 40, 11), money(orders.PRICES.get(k, orders.FESTIVAL_PRICE)),
                                  rf, Qt.AlignRight | Qt.AlignVCenter)
            else:                                                           # 一杯飲品的圖＋品名
                k = (top3[0][0] if top3 else "latte") if i == 1 else "iced_latte"
                pm = drink_icon(k, 52, True, 2.0)
                p.drawPixmap(QRectF(bx + 8, by + 9, 52, 52), pm, QRectF(0, 0, pm.width(), pm.height()))
                f = QFont(self.ui, 7)
                f.setBold(True)
                p.setPen(ink)
                self.fit_text(p, QRectF(bx + 64, by + 18, bw - 70, 14), T(DRINKS[k]["name"]), f)
                p.setPen(sub)
                self.fit_text(p, QRectF(bx + 64, by + 34, bw - 70, 12), money(orders.PRICES.get(k, orders.FESTIVAL_PRICE)),
                              QFont(self.ui, 6.5))
        p.setPen(Qt.NoPen)
        # 後檯：店鋪頁選的咖啡機（遊戲裡的機型），獨立磨豆機的機型旁邊放一台磨豆機
        bt = top - 64
        p.fillRect(QRectF(0, bt, W, top - bt), vgrad(bt, bt + (WIN_H - FLOOR), [   # 跟操作畫面的檯面同一套（paint_window_backdrop）
            (0, C("#4a3a30")), (0.04, C("#3a2d25")), (1, C("#1e1814"))]))
        self.paint_back_drawers(p, 10, self.case_left(W) - 4, bt + 10, top)
        m = self.showcase_machine()
        img = self.showcase_image(m)
        hgt = 118                                                           # 擺在後檯上的高度（場景座標）
        wid = img.width() * hgt / max(1, img.height())
        if wid > 250:
            wid, hgt = 250, img.height() * 250 / max(1, img.width())
        mx = MENU_X0 + 72
        p.drawImage(QRectF(mx, bt - hgt + 2, wid, hgt), img)
        if m.traits.grinder == "external":                                  # 獨立磨豆機
            gx = MENU_X0 + 30
            p.fillPath(rrect(gx - 16, bt - 70, gx + 16, bt - 30, 4), C("#2a2b2e"))
            p.fillPath(rrect(gx - 12, bt - 88, gx + 12, bt - 68, 3), C("#7a5a3a", 200))
            p.fillRect(QRectF(gx - 4, bt - 30, 8, 30), C("#3a3b3e"))

    def paint_back_drawers(self, p, x0, x1, y0, y1):
        """後檯檯面下的收納抽屜（立面，下緣被前櫃檯擋住）：暖木抽屜＋黃銅把手（使用者選的 A 方案）"""
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(x0, y0 - 2, x1 - x0, 2), C("#000000", 90))         # 檯面下緣的陰影
        n = max(1, round((x1 - x0) / 96))
        w = (x1 - x0) / n
        for i in range(n):
            a, b = x0 + i * w + 2, x0 + (i + 1) * w - 2
            p.fillPath(rrect(a, y0 + 2, b, y1 + 4, 2), vgrad(y0, y1, [(0, C("#6e4c30")), (1, C("#4e3420"))]))
            p.fillRect(QRectF(a + 4, y0 + 6, b - a - 8, 1), C("#8a6440", 160))   # 面板倒角的亮線
            cx = (a + b) / 2
            p.fillPath(rrect(cx - 14, y0 + 13, cx + 14, y0 + 17, 2), C("#c9a35a"))  # 黃銅把手
            p.fillRect(QRectF(cx - 14, y0 + 17, 28, 1), C("#000000", 70))

    def showcase_machine(self):
        """櫃檯畫面後檯擺的咖啡機：店鋪頁指定的營業用咖啡機（隨機或還沒解鎖就是上一杯用的那台）"""
        key = self.showcase
        if key in MACHINES and self.machine_open(key):
            return MACHINES[key]
        return self.machine

    def showcase_image(self, m):
        """後檯咖啡機的圖（跟圖鑑同一套繪圖，裁掉空白）；依機型與升級快取"""
        key = (m.key, tuple(sorted(self.stats.data.get("owned", []))))
        cache = getattr(self, "_showcase_cache", None)
        if cache is None or cache[0] != key:
            from .gear_icons import machine_image
            self._showcase_cache = cache = (key, machine_image(self, m))
        return cache[1]

    def counter_left(self, W):
        """前櫃檯的左端（整排櫃檯）"""
        return 10

    def case_left(self, W):
        """前櫃檯右段甜點玻璃櫃的左端"""
        return W - CASE_IN

    def pos_x(self, W):
        """POS 大螢幕的中心 x（在甜點櫃左邊，刷卡機在它右邊）"""
        return self.case_left(W) - 128

    def paint_counter_body(self, p, W, top):
        """整排前櫃檯：木檯面、前板（印店名）、底部燈條、右段甜點玻璃櫃（檯面上是玻璃櫃，前板是展示窗）、木地板。
        回傳 (左端, 杯子開始的 x)"""
        pal = STORE
        x0, x1 = self.counter_left(W), W - 10
        p.fillRect(QRectF(0, WIN_H - 22, W, 22), vgrad(WIN_H - 22, WIN_H, [(0, C(pal["floor"][0])), (1, C(pal["floor"][1]))]))
        p.setPen(QPen(C("#000000", 50), 1))
        for x in range(0, int(W), 60):
            p.drawLine(QPointF(x, WIN_H - 22), QPointF(x - 14, WIN_H))
        p.setPen(Qt.NoPen)
        front = [(0, C(pal["front"][0])), (1, C(pal["front"][1]))]
        p.fillRect(QRectF(x0, top + 10, x1 - x0, WIN_H - 30 - top - 10), vgrad(top + 10, WIN_H - 30, front))
        p.setPen(QPen(C("#000000", 36), 1))                                  # 直紋木板
        for x in range(int(x0) + 18, int(x1), 24):
            p.drawLine(QPointF(x, top + 12), QPointF(x, WIN_H - 32))
        p.setPen(Qt.NoPen)
        glow = QLinearGradient(0, WIN_H - 34, 0, WIN_H - 18)               # 底部燈條
        glow.setColorAt(0, C("#ffd9a0", 120))
        glow.setColorAt(1, C("#ffd9a0", 0))
        p.fillRect(QRectF(x0, WIN_H - 32, x1 - x0, 14), glow)
        p.fillRect(QRectF(x0, WIN_H - 32, x1 - x0, 2), C("#ffe2b0", 160))
        f = QFont(self.ui, 15)                                              # 店名
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.setPen(C(pal["logo"]))
        p.drawText(QRectF(x0 + 36, top + 30, 300, 30), Qt.AlignLeft | Qt.AlignVCenter, "CAFÉ DESK")
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(x0 - 4, top, x1 + 4, top + 12, 2), vgrad(top, top + 12, [(0, C(pal["top"][0])), (1, C(pal["top"][1]))]))
        # 甜點玻璃櫃：檯面上的玻璃櫃＋前板的展示窗
        cx0, cx1 = self.case_left(W), x1 - 14
        p.fillPath(rrect(cx0, top - 74, cx1, top, 4), C("#dfeef4", 34))
        p.setPen(QPen(C("#ffffff", 120), 1.1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(rrect(cx0, top - 74, cx1, top, 4))
        p.setPen(Qt.NoPen)
        p.fillRect(QRectF(cx0 - 2, top - 77, cx1 - cx0 + 4, 4), C(pal["shelf"]))
        p.fillRect(QRectF(cx0, top + 18, cx1 - cx0, 72), vgrad(top + 18, top + 90, [(0, C("#2a2622")), (1, C("#1a1714"))]))
        warm = QLinearGradient(0, top + 18, 0, top + 40)
        warm.setColorAt(0, C("#ffd9a0", 70))
        warm.setColorAt(1, C("#ffd9a0", 0))
        p.fillRect(QRectF(cx0, top + 18, cx1 - cx0, 22), warm)
        p.setPen(QPen(C("#ffffff", 70), 1))
        p.drawRect(QRectF(cx0, top + 18, cx1 - cx0, 72))
        p.setPen(Qt.NoPen)
        rnd = random.Random(3)
        for y in (top - 42, top - 6, top + 50, top + 86):
            p.fillRect(QRectF(cx0 + 4, y, cx1 - cx0 - 8, 2.5), C("#c8c0b0", 200))
            x = cx0 + 16
            while x < cx1 - 14:
                kind = rnd.randrange(3)
                if kind == 0:                                               # 可頌
                    p.setBrush(C("#c8883a"))
                    p.drawEllipse(QPointF(x, y - 6), 11, 6)
                elif kind == 1:                                             # 蛋糕
                    p.fillRect(QRectF(x - 9, y - 16, 18, 16), C("#f2e2c8"))
                    p.fillRect(QRectF(x - 9, y - 16, 18, 4), C("#b0505a"))
                else:                                                       # 馬芬
                    p.setBrush(C("#6a3a22"))
                    p.drawEllipse(QPointF(x, y - 12), 9, 7)
                    p.fillRect(QRectF(x - 7, y - 10, 14, 10), C("#d8a870"))
                x += 30
        return x0, CUPS_X

    def paint_counter(self, p):
        """櫃檯畫面（場景座標）：木質櫃檯、現代 POS（平板、刷卡機、收據機）、做好的杯子"""
        W = self._scene_w
        top = COUNTER_TOP
        p.save()
        p.setPen(Qt.NoPen)
        self.paint_room(p, W, top)                                          # 店面：牆、窗、菜單看板、層架、後檯
        x0, cups_x = self.paint_counter_body(p, W, top)                     # 整排前櫃檯（右段是甜點櫃）
        self.paint_pos(p, W, top)
        # 杯子
        d = self.delivery
        if d is not None:
            allc = [cc for pp in d["parties"] for cc in pp["cups"]]
            cups_x = max(cups_x, self.seat_sign_left(W) - 8 - sum(counter_gap(cc) for cc in allc))   # 座位小黑板左邊，靠右排
            for j, party in enumerate(d["parties"]):
                if j < d["i"]:
                    continue                                                # 已經拿走了
                for n, c in enumerate(party["cups"]):
                    before = [cc for pp in d["parties"][:j] for cc in pp["cups"]] + party["cups"][:n]
                    x = cups_x + sum(counter_gap(cc) for cc in before) + counter_gap(c) / 2   # 依杯子寬度排（杯盤不疊在一起）
                    a, dx, dy = 1.0, 0.0, 0.0
                    if d["phase"] == "in":
                        a = 0.0
                    elif d["phase"] == "place":                             # 從左邊滑上櫃檯
                        e = d["k"] * d["k"] * (3 - 2 * d["k"])
                        a, dx = e, -60 * (1 - e)
                    elif d["phase"] == "pickup" and j == d["i"]:            # 客人拿起來帶走
                        a, dx, dy = 1 - d["k"], 18 * d["k"], -30 * d["k"]
                    elif d["phase"] == "out":
                        a = 0.0
                    if a > 0.01:                                            # 縮小成跟 POS 相稱的真實大小
                        p.save()
                        p.translate(x + dx, top + 1 + dy)
                        p.scale(COUNTER_CUP_K, COUNTER_CUP_K)
                        self.paint_ready_cup(p, c, 0.0, 0.0, a)
                        p.restore()
        # 收錢時飄出來的金額
        px = self.pos_x(W)                                                  # 金額飄在店員的大螢幕上面
        for fl in self.reg_floats:
            k = fl["t"] / FLOAT_SEC
            a = clamp(min(k / 0.12, (1 - k) / 0.35), 0, 1)
            y = top - 152 - 26 * k
            ff = QFont(self.ui, 11)
            ff.setBold(True)
            p.setFont(ff)
            p.setPen(C("#ffd27a", int(255 * a)))
            p.drawText(QRectF(px - 80, y - 15, 160, 16), Qt.AlignCenter, fl["text"])
            if fl["tip"] > 0:
                p.setFont(QFont(self.ui, 9))
                p.setPen(C("#f6e6b0", int(255 * a)))
                p.drawText(QRectF(px - 80, y + 2, 160, 14), Qt.AlignCenter, T("小費 +{m}", m=money(fl["tip"])))
        p.restore()

    def pos_pending(self):
        """櫃檯畫面沒在結帳時：目前這位客人點的單（還在等、還沒開始做）給 POS 顯示；沒有就 None"""
        o = self.order
        if not self.business() or o is None or o.state != "waiting" or o.paid:
            return None
        group = o.party or [o]
        return {"orders": group, "cups": group, "price": sum(x.price for x in group), "pending": True}

    def paint_pos(self, p, W, top):
        """POS（場景座標）：立架上的大螢幕（品項、合計、付款狀態與小費、結帳後的評分；底下是收據機）、刷卡機；
        在甜點櫃左邊"""
        d, ck = self.delivery, self.checkout
        party = None
        if ck is not None:                                                  # 接單結帳：這一組點了什麼、刷卡
            party = ck["parties"][min(ck["i"], len(ck["parties"]) - 1)]
        elif d is not None and d["phase"] in ("pickup", "out"):            # 取餐：這一組（取走後顯示評分）
            party = d["parties"][min(d["i"], len(d["parties"]) - 1)]
            if d["phase"] == "pickup" and d["i"] > 0 and "score" not in party:
                party = d["parties"][d["i"] - 1]                            # 前一組的評分留著，直到這一組也取走
        if party is None:
            party = self.pos_pending()                                      # 客人剛點單（還沒結帳）：POS 顯示點了什麼
        paid = bool(party and party.get("paid"))
        cx, sw, sh = self.pos_x(W), 150, 104                                # 店員的大螢幕
        sy = top - 34 - sh
        rx = cx - 34                                                        # 收據機：在大螢幕下面
        p.fillPath(rrect(rx - 24, top - 26, rx + 24, top, 5), vgrad(top - 26, top, [(0, C("#3a3b3e")), (1, C("#1a1b1d"))]))
        p.fillRect(QRectF(rx - 14, top - 26, 28, 2), C("#0a0a0b"))
        if ck is not None and paid:                                         # 收據從出紙口捲出來，垂在收據機前面
            k = clamp((ck["k"] - 0.45) / 0.4, 0, 1) if ck["phase"] == "pay" else 1.0
            if k > 0.02:
                p.fillRect(QRectF(rx - 12, top - 27, 24, 4), C("#fbf8f0"))
                p.fillRect(QRectF(rx - 12, top - 24, 24, 22 * k), C("#fbf8f0"))
                p.setPen(QPen(C("#9a8a76"), 0.7))
                for i in range(int(22 * k // 5)):
                    yy = top - 20 + i * 5
                    p.drawLine(QPointF(rx - 8, yy), QPointF(rx + (8 if i % 2 else 2), yy))
                p.setPen(Qt.NoPen)
        p.fillPath(rrect(cx + 10, top - 6, cx + 50, top, 2), C("#2a2b2e"))  # 立架（偏右，讓出收據機）
        p.fillRect(QRectF(cx + 26.5, top - 34, 7, 30), C("#4a4c50"))
        p.fillPath(rrect(cx - sw / 2 - 4, sy - 4, cx + sw / 2 + 4, sy + sh + 4, 7), C("#141516"))
        p.fillPath(rrect(cx - sw / 2, sy, cx + sw / 2, sy + sh, 3), vgrad(sy, sy + sh, [(0, C("#f6f8fa")), (1, C("#dfe6ec"))]))
        f = QFont(self.ui, 8)
        f.setBold(True)
        small = QFont(self.ui, 7)
        L, R = cx - sw / 2 + 8, cx + sw / 2 - 8
        if party:
            orders_ = party["orders"]
            p.setFont(f)
            p.setPen(C("#2a3a4a"))
            p.drawText(QRectF(L, sy + 4, R - L, 14), Qt.AlignLeft | Qt.AlignVCenter,
                       T("{name} · {n} 杯", name=T(orders_[0].name), n=len(party["cups"])) if len(party["cups"]) > 1
                       else T("{name} · 1 杯", name=T(orders_[0].name)))
            p.setFont(small)
            for i, o in enumerate(orders_[:3]):                             # 品項與單價
                y = sy + 20 + i * 12
                p.setPen(C("#3a4a5a"))
                self.fit_text(p, QRectF(L, y, R - L - 46, 12), o.title, small)
                p.drawText(QRectF(R - 46, y, 46, 12), Qt.AlignRight | Qt.AlignVCenter, money(o.price))
            p.setPen(QPen(C("#b8c4ce"), 0.8))
            p.drawLine(QPointF(L, sy + 58), QPointF(R, sy + 58))
            big = QFont(self.ui, 13)
            big.setBold(True)
            p.setFont(big)
            p.setPen(C("#2a3a4a"))
            p.drawText(QRectF(L, sy + 59, R - L, 22), Qt.AlignRight | Qt.AlignVCenter, money(party["price"]))
            p.setFont(small)
            p.drawText(QRectF(L, sy + 59, R - L, 22), Qt.AlignLeft | Qt.AlignVCenter, T("合計"))
            badge = QRectF(L, sy + 84, R - L, 15)
            p.setFont(f)
            if paid:
                p.setBrush(C("#3aa36a"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(badge, 3, 3)
                p.setPen(C("#ffffff"))
                if "score" in party:                                        # 結帳完：這張單的評分
                    n = int(round(party["score"] / 20))
                    text = T("{stars} {s:.0f} 分", stars="★" * n + "☆" * (5 - n), s=party["score"])
                else:
                    text = T("已付款") if ck is not None else T("已付款 · 取餐中…")
                self.fit_text(p, badge, text, f, Qt.AlignCenter)
            else:
                p.setPen(C("#6a7a8a"))
                p.drawText(badge, Qt.AlignCenter, T("點單中…") if party.get("pending") else T("等待客人付款…"))
        else:
            dd = self.stats.day()
            big = QFont(self.ui, 12)
            big.setBold(True)
            p.setFont(big)
            p.setPen(C("#5a6a7a"))
            p.drawText(QRectF(cx - sw / 2, sy + 22, sw, 24), Qt.AlignCenter, T("今日 {m}", m=money(dd["revenue"])))
            p.setFont(f)
            p.drawText(QRectF(cx - sw / 2, sy + 58, sw, 20), Qt.AlignCenter, T("小費 {m}", m=money(dd["tips"])))
        # 刷卡機
        kx = self.pos_x(W) + 104
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(kx - 13, top - 40, kx + 13, top, 5), vgrad(top - 40, top, [(0, C("#3a3b3e")), (1, C("#18191b"))]))
        p.fillPath(rrect(kx - 9, top - 36, kx + 9, top - 22, 2), C("#0d1a12"))
        on = bool(party) and ck is not None and ck["phase"] == "pay"
        p.setBrush(C("#5adf8a" if paid else ("#ffd27a" if on else "#2a3a2e")))
        p.drawEllipse(QPointF(kx, top - 14), 2.2, 2.2)
        self.paint_seat_sign(p, self.pos_x(W) - SIGN_DX, top)

    def seat_sign_left(self, W):
        """座位小黑板的左端（做好的杯子排在它左邊）"""
        return self.pos_x(W) - SIGN_DX - SIGN_W / 2

    def paint_seat_sign(self, p, x, top):
        """POS 左邊的小黑板立牌（跟吊掛看板同一套配色）：坐著的內用客人／總座位，坐滿寫「客滿」"""
        n, total = len(self.seated), self.seats()
        w, h = SIGN_W, 50
        y0 = top - 8 - h
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(C("#4a3220"), 3))                                     # A 字架的後腳
        p.drawLine(QPointF(x - w / 2 + 8, y0 + h - 4), QPointF(x - w / 2 + 2, top))
        p.drawLine(QPointF(x + w / 2 - 8, y0 + h - 4), QPointF(x + w / 2 - 2, top))
        p.setPen(Qt.NoPen)
        p.fillPath(rrect(x - w / 2, y0, x + w / 2, y0 + h, 4), C(STORE["shelf"]))
        p.fillPath(rrect(x - w / 2 + 3, y0 + 3, x + w / 2 - 3, y0 + h - 3, 2), C(STORE["board"]))
        f = QFont(self.ui, 7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(C("#d8ccb8"))
        p.drawText(QRectF(x - w / 2, y0 + 5, w, 12), Qt.AlignCenter, T("座位"))
        big = QFont(self.ui, 12)
        big.setBold(True)
        full = n >= total
        p.setPen(C("#ff8a6a" if full else STORE["accent"]))
        self.fit_text(p, QRectF(x - w / 2 + 4, y0 + 19, w - 8, 24), T("客滿") if full else f"{n} / {total}", big, Qt.AlignCenter)

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


def counter_gap(c):
    """櫃檯上一杯佔的寬度（場景座標）：杯盤或杯身加把手，再留一點空"""
    w = c["top"] * (1.3 if (not c["to_go"] and c["handle"]) else 1.0) + (14 if c["handle"] else 0)
    return w * COUNTER_CUP_K + 10


def paint_paper_cup(p, x, base, size, z=(1.0, 1.0), mark="", dome=False):
    """外帶紙杯：杯身（cups.paint_paper_body）、牛皮紙隔熱套、杯蓋（場景座標，杯底中心）；z 是大中小杯的 (寬, 高) 縮放；
    dome：加鮮奶油的用透明圓頂蓋（不插吸管）"""
    h0, tw0, bw0 = PAPER_SIZE[size]
    h, top_w, bot_w = h0 * z[1], tw0 * z[0], bw0 * z[0]
    top = base - h
    paint_paper_body(p, x, base, size, z, mark)
    # 隔熱套：杯身中段
    s1, s2 = top + h * 0.34, top + h * 0.72

    def half(y):
        f = (y - (top + 2)) / (base - top - 2)
        return lerp(top_w / 2, bot_w / 2, f) + 0.8
    sleeve = QPainterPath()
    sleeve.moveTo(x - half(s1), s1)
    sleeve.lineTo(x + half(s1), s1)
    sleeve.lineTo(x + half(s2), s2)
    sleeve.lineTo(x - half(s2), s2)
    sleeve.closeSubpath()
    p.fillPath(sleeve, hgrad(x - half(s1), x + half(s1), [(0, C("#8a6440")), (0.35, C("#c49a6a")),
                                                           (0.7, C("#b08458")), (1, C("#7a5634"))]))
    p.setPen(QPen(C("#ffffff", 70), 0.7))
    p.drawLine(QPointF(x - half(s1) + 2, s1 + 1), QPointF(x + half(s1) - 2, s1 + 1))
    if dome:
        paint_dome_lid(p, x, top + 1, top_w, straw=False)
        return
    # 杯蓋：外緣一圈＋上面凸起的平台與喝口
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(x - top_w / 2 - 2, top + 1, x + top_w / 2 + 2, top + 6, 2.2),
               vgrad(top + 1, top + 6, [(0, C("#f4f2ee")), (1, C("#b8b2a8"))]))
    lid = QPainterPath()
    lid.moveTo(x - top_w / 2 + 3, top + 1.5)
    lid.lineTo(x - top_w / 2 + 7, top - 4)
    lid.lineTo(x + top_w / 2 - 7, top - 4)
    lid.lineTo(x + top_w / 2 - 3, top + 1.5)
    lid.closeSubpath()
    p.fillPath(lid, vgrad(top - 4, top + 2, [(0, C("#fbfaf8")), (1, C("#d4cec4"))]))
    p.setBrush(C("#4a3a2e"))
    p.drawRoundedRect(QRectF(x + top_w / 2 - 17, top - 4, 7, 1.6), 0.8, 0.8)


def paint_dome_lid(p, x, top, width, straw=True):
    """外帶冰飲：透明圓頂蓋與吸管（場景座標，杯口中心）；加鮮奶油的熱飲也用（不插吸管）"""
    r = width / 2 + 2
    p.save()
    p.setPen(QPen(C("#ffffff", 220), 1.6))                                  # 看得出是蓋子：輪廓與蓋緣比較明顯
    p.setBrush(C("#e8f4f8", 95))
    dome = QPainterPath()
    dome.moveTo(x - r, top + 1)
    dome.cubicTo(QPointF(x - r, top - r * 0.75), QPointF(x + r, top - r * 0.75), QPointF(x + r, top + 1))
    dome.closeSubpath()
    p.drawPath(dome)
    p.setPen(QPen(C("#ffffff", 120), 1.2))                                  # 圓頂上的反光
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(x - r * 0.7, top - r * 0.5, r * 0.8, r * 0.9), 100 * 16, 60 * 16)
    p.setPen(Qt.NoPen)
    p.fillPath(rrect(x - r - 2, top - 2, x + r + 2, top + 4, 2), C("#f4fafc", 210))   # 蓋緣（扣在杯口）
    p.fillRect(QRectF(x - r - 2, top + 3, 2 * r + 4, 1), C("#8aa0a8", 160))
    if not straw:
        p.restore()
        return
    p.setPen(QPen(C("#2a5a3a"), 3.2, Qt.SolidLine, Qt.RoundCap))           # 吸管
    p.drawLine(QPointF(x + 6, top + 30), QPointF(x + 14, top - r * 0.8 - 18))
    p.setPen(QPen(C("#5a9a6a"), 1.0, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x + 5.4, top + 30), QPointF(x + 13.4, top - r * 0.8 - 18))
    p.restore()


def paint_saucer(p, x, base, width):
    """內用：陶瓷杯盤（場景座標，杯底中心）"""
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(C("#000000", 60))
    p.drawEllipse(QPointF(x + 1.5, base + 2), width / 2, 3)
    p.setBrush(C("#d8d2c8"))
    p.drawEllipse(QPointF(x, base + 0.5), width / 2, 3.6)
    p.setBrush(C("#f6f3ee"))
    p.drawEllipse(QPointF(x, base - 0.4), width / 2 - 2, 2.6)
    p.restore()
