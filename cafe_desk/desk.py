"""主視窗：設定、選單、系統匣、滑鼠、模擬推進與繪圖排程"""
import datetime
import os
import math
import random
import time
from contextlib import contextmanager, nullcontext
from dataclasses import asdict, fields

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, QPointF, QUrl
from PySide6.QtGui import (QPainter, QPixmap, QImage, QAction, QActionGroup, QLinearGradient, QRadialGradient, QColor,
                           QDesktopServices)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon, QFileDialog, QInputDialog

from . import config, update, theme, music, vessels
from .gfx import pick_family
from .host import HostWindow
from .cups import Cup, paper_kind, cup_fit
from .drinks import (Session, DRINKS, DRINK_ORDER, DrinkParams, ICE_VOL, ART_CHOICES, ART_NEED,
                     MILK_KINDS, FESTIVAL_DRINKS, DRINK_KEYS, STATION_FAMILIES, is_milk, milk_plan, method_of, pair_kind, pair_compat, pair_shared_milk, base_of,
                     shot_params, Together)
from . import orders, beans, maintenance, festivals, brew, growth, store, ingredients
from .stats import Stats, ACHIEVEMENTS, TIER_OF, TIER_ICONS, tier_rank, db_path
from .records import RecordsDialog
from .about import AboutDialog
from .intro import IntroDialog
from . import challenges, regulars, decor
from .i18n import T, LANGS, set_lang, retext, money
from .layout import WIN_H, TOP_PAD, FLOOR
from .machines import MACHINES, DEFAULT_MACHINE
from .logo import load_icon
from .model import ROASTS, Params, Shot, Barista, Boiler
from .render.grinder import GrinderRenderer
from .render.liquid import LiquidRenderer
from .render.machine import MachineRenderer
from .render.milk import MilkRenderer
from .render.overlay import OverlayRenderer
from .render.particles import ParticleSystem
from .render.shop import ShopRenderer
from .render.station import StationRenderer
from .render.clock import ClockRenderer, CLOCK_DEFAULT
from .render.station import UNIFORM_W, WINDOW_SIZES
from .settings import SettingsDialog
from .sound import SoundBank, AMBIENCE
from .util import clamp
from .workflow import HANDLE_FULL

# 繪圖間隔（毫秒）：萃取中最順，閒置時省 CPU，縮到系統匣時不繪圖
FRAME_ACTIVE = 16      # 約 60 fps：萃取、完整流程、滴落、水花
FRAME_AMBIENT = 33     # 約 30 fps：蒸氣、指針回穩、氣泡破裂、卡片淡入淡出
FRAME_IDLE = 100       # 10 fps：只剩狀態列倒數與水溫微動
FADE_T = 0.6           # 換咖啡機／沖煮方式時，舊畫面淡出的秒數
SWITCH_PAUSE = 0.5     # 點單換了咖啡機／沖煮方式：漸變完再停這麼久才開始做
FRAME_HIDDEN = 250     # 縮到系統匣：只推進模擬（自動模式照常）
SIM_STEP = 0.05        # 模擬子步長（秒）：間隔拉長時切成多步，結果不受幀率影響
LOG_STEP = 0.1         # 萃取曲線取樣間隔（沖煮時間，秒）
WARMUP = 18.0          # 啟動時鍋爐比設定溫度低幾度，模擬預熱
UPDATE_DELAY = 10.0    # 啟動後幾秒才檢查新版本（不跟啟動搶時間）
UPDATE_RETRY = 3600.0  # 檢查失敗（沒網路）多久後再試；成功的話一天只查一次

# 雙頭機第二個沖煮頭（第二杯）的狀態：這些每杯各一份，on_twin() 時跟 self.twin 對調，
# 所以做第二杯、畫第二杯都可以直接沿用單杯的程式（self.cup、self.shot、self.session…）
TWIN_FIELDS = ("session", "cup", "contents", "syrup_kind", "topping", "icecream", "ice", "condense", "mix_t",
               "mix_clock", "shot", "stream", "last_flow", "drops", "splash", "ripples", "bubbles", "crema_h",
               "film_h", "swirl", "pf_used", "workflow", "gauge", "gauge_v", "_log_clock", "_ripple_clock",
               "last_drink", "shot_frac", "wand_angle",
               "card_alpha", "art_alpha", "last_art", "last_milk", "art_show_until", "_art_cache")      # 兩杯各自的曲線卡片與拉花卡片


def _inside(x, y, box):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


VIEW_LOCKS = ("follow", "counter", "machine")      # 營業模式的畫面：跟隨咖啡師／鎖定櫃檯／鎖定咖啡機


class Pair:
    """雙頭機成對做兩杯的進度：a_pre（第一杯備粉）→ b_pre（第二杯備粉）→ brew（兩杯一起萃取，第一杯同時打兩杯份的奶）
    → a_post（倒第一杯）→ b_post（倒第二杯）。a、b 是兩杯的 Session（b 平常存在 self.twin["session"]）"""

    def __init__(self, a, b):
        self.a, self.b = a, b
        self.phase = "a_pre"

    @property
    def focus_b(self):
        """狀態列、卡片、聲音現在看第二杯"""
        return self.phase in ("b_pre", "b_post")


def window_scale(old):
    """設定檔的縮放 → 16:9 視窗大小選項中最接近的一個（沒有設定時 1280×720）。
    1.4 版以前的縮放是 800 寬的倍率（0.8–1.5），照視窗寬度換成最接近的像素寬"""
    choices = [px / UNIFORM_W for px in WINDOW_SIZES]
    if not old:
        return 1280 / UNIFORM_W
    for c in choices:
        if abs(c - old) < 1e-6:
            return c
    px = old * 800 if old <= 1.6 else old * UNIFORM_W
    return min(choices, key=lambda c: abs(c * UNIFORM_W - px))


class CafeDesk(QWidget, MachineRenderer, GrinderRenderer, LiquidRenderer, ParticleSystem, OverlayRenderer,
                   MilkRenderer, StationRenderer, ShopRenderer, ClockRenderer):
    def __init__(self):
        super().__init__()
        self.cfg = self.load_config()
        names = {f.name for f in fields(Params)}
        self.params = Params(**{k: v for k, v in self.cfg.get("params", {}).items() if k in names})
        if self.params.roast not in ROASTS:
            self.params.roast = "中焙"
        self.auto = self.cfg.get("auto", False)
        self.interval = self.cfg.get("interval", 60)
        self.speed = self.cfg.get("speed", 1.0)
        self.topmost = self.cfg.get("topmost", False)
        self.windowed = self.cfg.get("windowed", True)    # 視窗化（預設）：一般視窗（標題列、工作列、不透明背景）；關掉是透明桌面擺件
        # 這是使用者在手動／自動模式的偏好；營業模式一律視窗化（is_windowed()）
        self.scale_f = window_scale(self.cfg.get("scale"))         # 16:9 視窗的大小（舊版的縮放換成最接近的一個）
        self.light_mode = self.cfg.get("light_mode", "auto")
        self.chart_on = self.cfg.get("chart", True)
        self.clock_cfg = {k: v for k, v in dict(CLOCK_DEFAULT, **self.cfg.get("flip_clock", {})).items()
                          if k in CLOCK_DEFAULT}             # 營業模式右上角的翻頁鐘（render/clock.py）
        self._clock = None
        self.showcase = self.cfg.get("showcase", "auto")   # 營業用咖啡機（auto＝隨機；店鋪頁選），櫃檯後檯也畫這台
        self.result_until = None                 # 營業模式：客人評價在狀態列顯示到什麼時候（perf_counter）
        self.machine = MACHINES.get(self.cfg.get("machine"), MACHINES[DEFAULT_MACHINE])
        self.drink = self.cfg.get("drink", "espresso")
        if self.drink not in DRINKS or (self.drink in FESTIVAL_DRINKS and self.drink != festivals.festival_drink()):
            self.drink = "latte" if self.drink in DRINKS else "espresso"
        self.method = method_of(self.drink)      # 沖煮方式：espresso／pourover／colddrip（跟著飲品）
        bag = self.cfg.get("bean_bag")
        self.bag = bag if (isinstance(bag, dict) and beans.valid_bag(bag)) else beans.new_bag("house")
        pending = self.cfg.get("pending_bag")
        shelf = self.cfg.get("bean_shelf")                 # 開過還沒用完的豆子（產地 → 一包）：換豆子時剩下的留著，之後按需再倒回磨豆機
        self.shelf = {k: b for k, b in (shelf.items() if isinstance(shelf, dict) else [])
                      if isinstance(b, dict) and beans.valid_bag(b) and b.get("origin") == k and k != self.bag["origin"]
                      and float(b["left"]) >= beans.MIN_LEFT}
        ab = self.cfg.get("auto_buy_beans")
        self.auto_buy = [k for k in (ab if isinstance(ab, list) else []) if k in beans.ORIGINS]   # 自動購買：庫存沒有時從這幾種買一包
        ai = self.cfg.get("auto_buy_ingredients")
        self.auto_ing = [k for k in (ai if isinstance(ai, list) else []) if k in ingredients.ALL]   # 食材自動補貨：營業中庫存沒有就買一包
        self.pending_bag = pending if pending in beans.ORIGINS else None   # 「這杯做完就換」的下一包豆子（產地 key；開包時才從庫存拿）
        saved = self.cfg.get("maintenance", {})
        self.maint_all = {}                      # 每台咖啡機各自的清潔保養計數（self.maint 是目前這台的）
        for key in MACHINES:
            st = maintenance.default_state()
            got = saved.get(key) if isinstance(saved, dict) else None
            if isinstance(got, dict):
                st.update({k: v for k, v in got.items() if k in st})
            self.maint_all[key] = st
        self.job = None                          # 正在進行的清潔保養
        cold = self.cfg.get("cold_drip")
        self.cold = cold if brew.valid_batch(cold) else None    # 冰滴：背景慢慢滴的這一壺（brew.new_cold_batch）
        self.last_brew_res = None                # 上一杯手沖／冰滴的萃取結果（杯中顏色）
        self.brew_zoom = 0.0                     # 手沖／冰滴畫面拉近的程度（0＝全景，1＝只看沖煮器具）
        self._fade = None                        # 換咖啡機／沖煮方式的漸變：(舊畫面, 開始時間)
        self._switch_wait = None                 # 點單換了咖啡機／沖煮方式後的等待：[訂單, 剩幾秒]
        self.session = None
        self.pair = None                         # 雙頭機成對做兩杯（Pair）
        self.twin = None                         # 雙頭機第二個沖煮頭的狀態（new_twin；單頭機是 None）
        self._in_twin = False                    # 正在 on_twin() 裡
        self.stats = Stats()
        store.apply_upgrades(self.stats.data["owned"])      # 商店買過的咖啡機升級
        if not self.machine_open(self.machine.key):          # 還沒解鎖的設備（例如重新遊玩後）：退回 Lv.1 的
            self.machine = MACHINES[DEFAULT_MACHINE]
        if not self.method_open(self.method) or not self.drink_open(self.drink):
            self.drink, self.method = "espresso", "espresso"
        self.toasts = []                         # 暫時取代狀態列的通知：(文字, 開始, 結束, 樣式 "trophy"／"info")
        self.notice = None                       # 狀態列的臨時提示：(文字, 結束時間)
        self.records_dlg = self.store_dlg = self.layout_dlg = None
        self.about_dlg = None
        self.intro_dlg = None
        self.sync_bag()
        dnames = {f.name for f in fields(DrinkParams)}
        self.dp = DrinkParams(**{k: v for k, v in self.cfg.get("drink_params", {}).items() if k in dnames})
        if self.dp.art not in ART_NEED:
            self.dp.art = "auto"
        if self.dp.milk_kind not in MILK_KINDS:
            self.dp.milk_kind = "dairy"
        self.lang = self.cfg.get("lang", "zh")
        set_lang(self.lang)
        self.order_mode = self.cfg.get("order_mode", False)
        if self.order_mode:
            self.auto = False                    # 營業模式時咖啡師自己接單，自動模式關著（模式三選一）
        self.order = None                        # 目前的訂單
        pre = self.cfg.get("pre_business")
        self.pre_biz = pre if isinstance(pre, dict) and isinstance(pre.get("params"), dict) else None
        self._restore_biz = bool(self.pre_biz) and not self.order_mode   # 上次關營業後還沒還原就關了程式
        self.order_no = int(self.cfg.get("order_no", 0))   # 今天第幾杯（點單紙左上角；換日從 0 重算，order_day）
        self.order_day = self.cfg.get("order_day", "")
        self.next_order_at = time.perf_counter() + 2.5
        self.queue = []                          # 營業模式：排在目前訂單後面的客人
        self.arrive_in = 3.0                     # 營業模式：下一位客人幾秒後到（模擬時間）
        self.rush = False                        # 營業模式：排滿 QUEUE_MAX 位後還沒有人離開（尖峰時刻成就）
        self.ready = []                          # 營業模式做好、在出餐架上等同一張單其他杯子的飲品（render/shop.py）
        self.pending_deliveries = []             # 整張單都好了、等著帶到櫃檯的
        self.seated = []                         # 營業模式：坐著的內用客人還要坐幾秒（模擬時間，一杯一位）
        self.delivery = None                     # 正在櫃檯交付（櫃檯畫面）
        self.checkout = None                     # 接單時在櫃檯結帳（櫃檯畫面）
        self.counter_view = False                # 畫面切到櫃檯（不顯示咖啡機）
        self.view_lock = self.cfg.get("view_lock", "follow")        # 營業模式的畫面：follow 跟隨咖啡師、counter 鎖定櫃檯、machine 鎖定咖啡機
        if self.view_lock not in VIEW_LOCKS:
            self.view_lock = "follow"
        self.reg_floats = []                     # 結帳時往上飄的金額
        self.cup_away = False                    # 營業中這杯送去收銀台了：沖煮頭下沒有杯子（下一杯 reset_cup 換上新杯）
        self.report_card = None                  # 打烊日報收據：{"data", "t0"}
        self._today = festivals.today().isoformat()
        self._report_due = None                  # 啟動時補看上一個營業日的日報：幾點顯示（perf_counter）
        self._welcome_due = None                 # 第一次啟動：幾秒後提示「右鍵選營業開店」
        self.order_alpha = 0.0
        self.last_cocoa = 0.0
        self.last_milk = None
        self.last_dp = None
        self._last_customer = None
        self.cup = Cup(DRINKS[self.drink]["cup"], *self.cup_anchor(), fit=cup_fit(self.drink))
        self.result = None
        self.last_drink = self.drink
        self.last_art = None
        self._art_cache = None
        self.contents = {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0}
        self.syrup_kind = "choc"
        self.topping = {}                        # 杯面配料：cocoa／whip／caramel（0–1）
        self.icecream = None                     # 阿芙佳朵的冰淇淋球
        self.ice = []
        self.shot_frac = 1.0                     # 濃縮有多少在杯子裡（營業模式先萃取到量杯，倒進來才算；其他時候 1）
        self.condense = 0.0
        self.mix_t = 0.0
        self.mix_clock = 0.0
        self.vortex = 0.0
        self.frother_fill = 0.42
        self.wand_angle = 0.0
        self.art_alpha = 0.0
        self.art_show_until = 0.0

        self.ui = pick_family(("Microsoft JhengHei UI", "Microsoft JhengHei", "PingFang TC",
                               "Noto Sans CJK TC", "Noto Sans TC"), "Sans Serif")
        self.mono = pick_family(("Consolas", "Menlo", "DejaVu Sans Mono"), "Monospace")

        self.sound = SoundBank()
        self.sound.master = self.cfg.get("volume", 0.65)
        self.sound.set_on(self.cfg.get("sound", True))
        self.ambience = self.cfg.get("ambience")             # 環境音：None／cafe／rain
        if self.ambience not in AMBIENCE:
            self.ambience = None
        self.amb_level = self.cfg.get("amb_level", 0.3)
        self.break_min = self.cfg.get("break_min", 0)        # 休息提醒：每幾分鐘（0＝關閉）
        self.break_t = 0.0                                   # 距離上次提醒過了幾秒（真實時間，睡眠不算）
        self.update_check = self.cfg.get("update_check", True)
        self.update_job = None                               # 進行中的 update.Checker
        self._update_at = time.perf_counter() + UPDATE_DELAY
        latest = self.cfg.get("update_latest", "")
        self.update_info = ({"tag": latest, "url": update.RELEASES_URL}
                            if self.update_check and update.is_newer(latest) else None)

        # 畫面本身是子元件，放在外層承載視窗（host.py）裡；視窗化模式由 paint_window_backdrop 畫不透明背景
        self.setMouseTracking(True)
        self.host = None
        self.apply_scale()
        scr = QApplication.primaryScreen().availableGeometry()
        x = self.cfg.get("x", scr.right() - self.width() - 30)
        y = self.cfg.get("y", scr.bottom() - self.height() - 30)
        if "y" in self.cfg and self.cfg.get("top_pad") != TOP_PAD:
            y -= (TOP_PAD - self.cfg.get("top_pad", 0)) * self.scale_f   # 舊設定：讓咖啡機留在原位
        self.cfg["top_pad"] = TOP_PAD
        self.build_host(int(x), int(y), show=False)

        # 動態狀態
        self.shot = None
        self.workflow = None
        self.pf_used = self.cfg.get("pf_used", False)     # 把手裡有沒有上一杯的粉餅
        self.boiler = Boiler(self.params.temp)
        self.apply_traits()
        self.boiler.temp = self.params.temp - WARMUP
        self.warming = True
        self._last_set = self.params.temp
        self.gauge, self.gauge_v = 0.0, 0.0
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.last_flow = 0.0
        self.drops, self.splash, self.ripples, self.steam, self.bubbles = [], [], [], [], []
        self.crema_h = 0.0
        self.film_h = 0.0
        self.swirl = 0.0
        self.anim_t = 0.0
        self.idle_since = time.perf_counter()
        self.next_idle_event = time.perf_counter() + random.uniform(20, 40)
        self.barista = Barista()
        seen = self.cfg.get("growth_seen")
        if not isinstance(seen, dict):           # 第一次有成長系統：舊紀錄往回算，不補發升級通知
            seen = {"level": self.shop_level(), "rank": growth.rank_of(self.stats.data["total"])}
        self.growth_seen = seen
        if not self.cfg.get("welcomed"):
            if self.stats.data["total"] == 0:            # 真的是新玩家才提示；舊玩家直接記成看過
                self._welcome_due = time.perf_counter() + 2.5
            else:
                self.cfg["welcomed"] = True
        last = growth.last_business_day(self.stats, self._today)
        if last and last > self.cfg.get("report_seen", "") and                 (festivals.today() - datetime.date.fromisoformat(last)).days <= 7:
            self._report_due = (last, time.perf_counter() + 3.0)
        self.card_alpha = 0.0
        self.hover = False
        self.hover_since = 0.0
        self.status_hover = False                # 滑鼠在咖啡機（沖煮台）上：透明擺件時才顯示狀態列
        self.status_alpha = 1.0
        self._ripple_clock = 0.0
        self._log_clock = 0.0
        self.twin = self.new_twin()
        self._last_relay = 0.0
        self._press = None
        self._frame = None
        self.settings_dlg = None
        rnd = random.Random(42)
        self.speckles = [(math.sqrt(rnd.random()), rnd.random() * 6.283, rnd.uniform(0.5, 1.6),
                          rnd.random() < 0.6) for _ in range(80)]
        self.update_light(force=True)

        self.music = music.Music(self.cfg.get("music"), on_change=self.music_changed, on_skip=self.music_skipped)
        self.icon = load_icon()
        self.host.setWindowIcon(self.icon)
        self.build_menu()
        self.build_tray()
        self._last_tip_ms = 0
        self.clock = QElapsedTimer()
        self.clock.start()
        self.last_ms = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FRAME_ACTIVE)

    # ───────────── 設定檔 ─────────────
    @staticmethod
    def load_config():
        return config.load()                 # 含舊版設定沿用與格式遷移（config.py）

    def save_config(self):
        self.cfg.update(params=asdict(self.params), x=self.host.geometry().x(), y=self.host.geometry().y(), auto=self.auto,
                        interval=self.interval, speed=self.speed, topmost=self.topmost, windowed=self.windowed,
                        scale=self.scale_f, sound=self.sound.user_on, volume=self.sound.master,
                        light_mode=self.light_mode, chart=self.chart_on, flip_clock=self.clock_cfg, showcase=self.showcase,
                        pf_used=self.pf_used, machine=self.machine.key, bean_bag=self.bag, bean_shelf=self.shelf, maintenance=self.maint_all,
                        drink=self.drink, drink_params=asdict(self.dp), order_mode=self.order_mode, lang=self.lang,
                        order_no=self.order_no, order_day=self.order_day, cold_drip=self.cold,
                        ambience=self.ambience, amb_level=self.amb_level, break_min=self.break_min,
                        update_check=self.update_check, growth_seen=self.growth_seen, music=self.music.state(),
                        pending_bag=self.pending_bag, pre_business=self.pre_biz, auto_buy_beans=self.auto_buy,
                        auto_buy_ingredients=self.auto_ing)
        config.save(self.cfg)

    # ───────────── 視窗 ─────────────
    def build_host(self, x, y, show=True):
        """建立全新的外層視窗並把畫面搬進去（無邊框／視窗化、置頂切換都走這裡，避免殘留邊框）"""
        old = self.host
        host = HostWindow(self, self.is_windowed(), self.topmost)
        if hasattr(self, "icon"):
            host.setWindowIcon(self.icon)
        self.setParent(host)
        self.move(0, 0)
        host.setFixedSize(self.size())
        host.setGeometry(x, y, self.width(), self.height())    # 以內容區域定位（不含標題列）
        self.host = host
        self.show()
        if old is not None:
            old.retired = True
            old.hide()
            old.close()
            old.deleteLater()
        if show:
            host.show()
            host.raise_()
            host.activateWindow()

    def rebuild_host(self):
        if self.host is None:
            return
        visible = self.host.isVisible()
        pos = self.host.geometry().topLeft()       # 以內容區域為準，切換時咖啡機不跳位
        self.build_host(pos.x(), pos.y(), show=visible)
        self.set_frame_interval(FRAME_ACTIVE)

    def is_windowed(self):
        """實際要不要視窗化：營業模式一律是（客人點單、櫃檯要完整背景）；手動／自動照使用者的設定"""
        return self.windowed or self.order_mode

    def toggle_windowed(self, v):
        """右鍵「視窗化顯示」：營業中一律視窗化，點了不改設定、保持勾選"""
        if self.order_mode:
            self.update_menu_locks()
            self.show_notice(T("營業中一律視窗化，離開營業後才能切換"))
            return
        self.set_windowed(v)

    def set_windowed(self, v):
        before = self.is_windowed()
        self.windowed = v
        if self.is_windowed() != before:
            self.rebuild_host()
        self.save_config()
        self.update()

    def show_window(self):
        self.host.show()

    def apply_scale(self):
        self._scene_w = self.scene_width()          # 視窗寬度（手沖／冰滴也跟咖啡機一樣寬）
        self.setFixedSize(round(self._scene_w * self.scale_f), round((WIN_H + TOP_PAD) * self.scale_f))
        if self.host is not None:
            self.host.setFixedSize(self.size())
        self.bg_layer = self.front_layer = None      # 下一次繪圖時重建
        self._frame = None
        self._bean_cache = None

    # ───────────── 選單 ─────────────
    def build_menu(self):
        old = getattr(self, "menu", None)
        if old is not None:
            old.deleteLater()
        m = QMenu(self)
        theme.apply_menu(m)                          # 紙張風格（子選單一起）
        if self.update_info:                         # 有新版本：放在最上面
            m.addAction(T("⬆ 下載新版 {tag}…", tag=self.update_info["tag"]), self.open_update_page)
            m.addSeparator()
        self.act_brew = m.addAction(T("開始沖煮"), self.manual_brew)
        self.act_params = m.addAction(T("參數設定…"), self.open_settings)
        m.addSeparator()
        self.mode_slot = m.addSeparator()             # 模式三選一插在這裡（下面建好選單後才加，見 add_mode_actions）
        self.method_menu = m.addMenu(T("沖煮方式"))
        grp = QActionGroup(self.method_menu)
        self.method_actions = {}
        for key, name in brew.METHODS.items():
            ok = self.method_open(key)
            act = self.method_menu.addAction(T(name) + ("" if ok else T("（Lv.{n} 解鎖）", n=growth.METHOD_LEVEL[key])))
            act.setCheckable(True)
            act.setEnabled(ok)
            act.setChecked(key == self.method)
            act.triggered.connect(lambda _=False, k=key: self.set_method(k))
            grp.addAction(act)
            self.method_actions[key] = act
        self.machine_menu = m.addMenu(T("咖啡機"))
        grp = QActionGroup(self.machine_menu)
        self.machine_actions = {}
        for key, mach in MACHINES.items():
            ups = [T(n) for n in store.upgrade_names(key, self.stats.data["owned"])]
            ok = self.machine_open(key)
            act = self.machine_menu.addAction(T(mach.name) + (" ★" if ups else "")
                                              + ("" if ok else T("（Lv.{n} 解鎖）", n=growth.MACHINE_LEVEL[key])))
            act.setEnabled(ok)
            act.setCheckable(True)
            act.setChecked(key == self.machine.key)
            act.setToolTip(T(mach.traits.summary) + ("\n" + T("已升級：{names}", names=T("、").join(ups)) if ups else ""))
            act.triggered.connect(lambda _=False, k=key: self.set_machine(k))
            grp.addAction(act)
            self.machine_actions[key] = act
        self.machine_menu.setToolTipsVisible(True)
        self.drink_menu = m.addMenu(T("飲品"))
        grp = QActionGroup(self.drink_menu)
        self.drink_actions = {}
        fd = festivals.festival_drink()
        order = list(DRINK_ORDER) + ([None, fd] if fd else [])
        for key in order:
            if key is not None and method_of(key) != self.method:
                continue                                 # 不是這個沖煮方式能做的飲品
            if key is None:
                self.drink_menu.addSeparator()
                continue
            name = T(DRINKS[key]["name"])
            if key == fd:
                name = T("季節限定：{name}", name=name)
            act = self.drink_menu.addAction(name + self.drink_lock(key))
            act.setCheckable(True)
            act.setEnabled(self.drink_open(key))            # 依咖啡師稱號解鎖（沖煮台的飲品看店鋪等級）
            act.setChecked(key == self.drink)
            act.triggered.connect(lambda _=False, k=key: self.set_drink(k))
            grp.addAction(act)
            self.drink_actions[key] = act
        self.art_menu = m.addMenu(T("拉花圖案"))
        grp = QActionGroup(self.art_menu)
        self.art_actions = {}
        for key, label in ART_CHOICES:
            act = self.art_menu.addAction(T(label))
            act.setCheckable(True)
            act.setChecked(key == self.dp.art)
            act.triggered.connect(lambda _=False, k=key: self.set_art(k))
            grp.addAction(act)
            self.art_actions[key] = act
        # 豆子：目前這包的資訊、開新包（選產地）
        self.bean_menu = m.addMenu(T("豆子"))
        self.bean_menu.aboutToShow.connect(self.fill_bean_menu)
        self.ing_menu = m.addMenu(T("食材"))
        self.ing_menu.aboutToShow.connect(self.fill_ing_menu)
        # 清潔保養
        self.maint_menu = m.addMenu(T("清潔保養"))
        self.maint_menu.aboutToShow.connect(self.fill_maint_menu)
        m.addSeparator()
        m.addAction(T("紀錄與收集冊…"), self.open_records)
        m.addAction(T("商店…"), lambda: self.open_records("shop"))
        m.addAction(T("佈置…"), lambda: self.open_records("layout"))
        m.addSeparator()

        # 模式：練習（手動、自動合在一起）／營業 二選一，「自動做咖啡」子選單選關閉（手動，點一下做一杯）或間隔；放在「參數設定…」下面
        # （系統匣選單也有一組：二選一加一個「自動做咖啡」開關）
        self.mode_actions = self.add_mode_actions(m, before=self.mode_slot)
        self.interval_menu = QMenu(T("自動做咖啡"), m)
        m.insertMenu(self.mode_slot, self.interval_menu)
        grp = QActionGroup(self.interval_menu)
        self.interval_acts = {}
        off = self.interval_menu.addAction(T("關閉（手動，點一下做一杯）"))
        off.setCheckable(True)
        off.triggered.connect(lambda _=False: self.set_mode("manual"))
        grp.addAction(off)
        self.interval_acts[None] = off
        for value, label in ((20, T("20 秒")), (60, T("1 分鐘")), (180, T("3 分鐘")), (600, T("10 分鐘"))):
            act = self.interval_menu.addAction(T("每 {t} 做一杯", t=label))
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, v=value: self.set_auto_interval(v))
            grp.addAction(act)
            self.interval_acts[value] = act
        self.sync_mode_actions()

        main = m                                            # 休息提醒到更新都收進「設定」子選單
        m = main.addMenu(T("設定"))
        # 休息提醒：每隔一段時間提醒起來休息，咖啡師順便做一杯
        self.break_menu = m.addMenu(T("休息提醒"))
        grp = QActionGroup(self.break_menu)
        for value in self.BREAK_PRESETS:
            act = self.break_menu.addAction(T("不提醒") if value == 0 else T("每 {m} 分鐘", m=value))
            act.setCheckable(True)
            act.setChecked(value == self.break_min)
            act.triggered.connect(lambda _=False, v=value: self.set_break(v))
            grp.addAction(act)
        custom = self.break_min not in self.BREAK_PRESETS
        act = self.break_menu.addAction(T("自訂（每 {m} 分鐘）…", m=self.break_min) if custom else T("自訂…"))
        act.setCheckable(True)
        act.setChecked(custom)
        act.triggered.connect(self.custom_break)
        grp.addAction(act)
        self.break_menu.addSeparator()
        self.act_break_reset = self.break_menu.addAction("", self.reset_break)
        self.break_menu.aboutToShow.connect(self.update_break_menu)

        def radio(title, options, current, setter, parent=m):
            sub = parent.addMenu(title)
            grp = QActionGroup(sub)
            for value, label in options:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == current if isinstance(value, str) else abs(value - current) < 1e-6)
                act.triggered.connect(lambda _=False, v=value: setter(v))
                grp.addAction(act)
            return sub

        self.speed_menu = radio(T("播放速度"), [(1.0, T("1×（真實時間）")), (2.0, "2×"), (4.0, "4×")],
                                self.speed, lambda v: self.set_cfg("speed", v))
        m.addSeparator()

        # 聲音：開關、音量、環境音放在同一個子選單
        snd = m.addMenu(T("聲音"))
        a = snd.addAction(T("開啟聲音"))
        a.setCheckable(True)
        a.setChecked(self.sound.on)
        a.setEnabled(self.sound.enabled)
        a.toggled.connect(lambda v: (self.sound.set_on(v), self.music.set_mute(not v), self.save_config()))
        radio(T("音量"), [(0.3, T("小")), (0.65, T("中")), (1.0, T("大"))], self.sound.master,
              lambda v: (setattr(self.sound, "master", v), self.save_config()), parent=snd)
        amb = snd.addMenu(T("環境音"))
        amb.setEnabled(self.sound.enabled)
        grp = QActionGroup(amb)
        for value, label in ((None, T("不播放")), ("cafe", T("咖啡廳")), ("rain", T("雨天"))):
            act = amb.addAction(label)
            act.setCheckable(True)
            act.setChecked(value == self.ambience)
            act.triggered.connect(lambda _=False, v=value: self.set_cfg("ambience", v))
            grp.addAction(act)
        amb.addSeparator()
        grp = QActionGroup(amb)
        for value, label in ((0.15, T("小聲")), (0.3, T("中等")), (0.5, T("大聲"))):
            act = amb.addAction(label)
            act.setCheckable(True)
            act.setChecked(abs(value - self.amb_level) < 1e-6)
            act.triggered.connect(lambda _=False, v=value: self.set_cfg("amb_level", v))
            grp.addAction(act)
        self.music_menu = m.addMenu(T("音樂"))
        self.music_menu.aboutToShow.connect(self.fill_music_menu)
        self.fill_music_menu()
        radio(T("環境光"), [("auto", T("依時間變化")), ("day", T("白天")), ("dusk", T("黃昏")), ("night", T("夜晚"))],
              self.light_mode, self.set_light_mode)
        a = m.addAction(T("滑鼠停留顯示萃取曲線"))
        a.setCheckable(True)
        a.setChecked(self.chart_on)
        a.toggled.connect(lambda v: self.set_cfg("chart_on", v))
        radio(T("大小"), [(px / UNIFORM_W, f"{px}×{px * 9 // 16}（{px * 100 // 1920}%）") for px in WINDOW_SIZES],
              self.scale_f, self.set_scale)
        radio("Language", list(LANGS), self.lang, self.set_language)      # 不翻譯：看不懂目前語言也找得到
        a = m.addAction(T("視窗化顯示"))
        a.setCheckable(True)
        a.setChecked(self.is_windowed())                 # 營業中一律視窗化：勾起來
        a.toggled.connect(self.toggle_windowed)
        self.windowed_act = a                            # 營業中鎖住（一律視窗化，update_menu_locks）
        self.add_clock_menu(m)
        self.add_view_menu(m)
        a = m.addAction(T("視窗置頂"))
        a.setCheckable(True)
        a.setChecked(self.topmost)
        a.toggled.connect(self.set_topmost)
        m.addSeparator()
        a = m.addAction(T("縮到系統匣"), self.hide_to_tray)
        a.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        upd = m.addMenu(T("更新"))
        a = upd.addAction(T("每天自動檢查新版本"))
        a.setCheckable(True)
        a.setChecked(self.update_check)
        a.toggled.connect(self.set_update_check)
        upd.addAction(T("立即檢查更新"), lambda: self.check_update(manual=True))
        m = main
        m.addAction(T("玩法導覽…"), self.open_intro)
        m.addAction(T("關於 Café Desk…"), self.open_about)
        m.addAction(T("結束"), self.quit_app)
        self.menu = m
        self.update_menu_locks()                     # 最後才鎖：播放速度等子選單都建好了

    def build_tray(self):
        self.tray = None
        self._tray_hint_shown = False
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.icon, self)
        tray.setToolTip("Café Desk")
        tm = QMenu()
        theme.apply_menu(tm)
        tm.addAction(T("顯示咖啡機"), self.restore_from_tray)
        tm.addAction(T("開始沖煮"), self.manual_brew)
        tm.addSeparator()
        self.tray_mode_actions = self.add_mode_actions(tm)
        tm.addSeparator()
        tm.addAction(T("音樂：播放／暫停"), self.music_toggle)
        tm.addAction(T("音樂：下一首"), lambda: self.music.next())
        tm.addSeparator()
        tm.addAction(T("玩法導覽…"), self.open_intro)
        tm.addAction(T("關於 Café Desk…"), self.open_about)
        tm.addAction(T("結束"), self.quit_app)
        tray.setContextMenu(tm)
        tray.activated.connect(self.on_tray_activated)
        tray.show()
        self.tray_menu = tm        # 保留參考，避免被回收
        self.tray = tray

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide_to_tray()
            else:
                self.restore_from_tray()

    def hide_to_tray(self):
        if not self.tray:
            return
        self.save_config()
        self.host.hide()
        self.sound.set_muted(True)
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage("Café Desk", T("咖啡機在系統匣裡，點一下圖示就能叫回來。"),
                                  self.icon, 3000)

    def restore_from_tray(self):
        self.sound.set_muted(False)
        if self.host.isMinimized():
            self.host.showNormal()
        self.host.show()
        self.host.raise_()
        self.host.activateWindow()
        self.set_frame_interval(FRAME_ACTIVE)

    # ───────────── 音樂 ─────────────
    def fill_music_menu(self):
        """右鍵「音樂」：每次打開時依目前狀態重建（正在播放、播放清單會變）"""
        mm = self.music_menu
        mm.clear()
        mu = self.music
        if mu.playing:
            head = T("♪ 正在播放：{title}", title=mu.title())
        else:
            head = T("♪ 已暫停：{title}", title=mu.title()) if mu.files else T("♪ 清單是空的")
        mm.addAction(head).setEnabled(False)
        mm.addSeparator()
        mm.addAction(T("暫停") if mu.playing else T("播放"), self.music_toggle).setEnabled(bool(mu.files))
        mm.addAction(T("下一首"), lambda: mu.next()).setEnabled(bool(mu.files))
        mm.addAction(T("上一首"), mu.prev).setEnabled(len(mu.files) > 1)
        mm.addSeparator()
        plist = mm.addMenu(T("播放清單（{n} 首）", n=len(mu.files)))
        plist.setEnabled(bool(mu.files))
        lo = max(0, min(mu.index - 15, len(mu.files) - 30))          # 最多列 30 首：目前這首前後
        grp = QActionGroup(plist)
        for i in range(lo, min(len(mu.files), lo + 30)):
            act = plist.addAction(f"{i + 1}. {mu.title(mu.files[i])}")
            act.setCheckable(True)
            act.setChecked(i == mu.index)
            act.triggered.connect(lambda _=False, k=i: mu.jump(k))
            grp.addAction(act)
        mm.addAction(T("加入音檔…"), self.music_add_files)
        mm.addAction(T("加入資料夾…"), self.music_add_folder)
        mm.addAction(T("從清單移除目前這首"),
                     lambda: (mu.remove_current(), self.save_config())).setEnabled(bool(mu.files))
        mm.addAction(T("清空清單"), lambda: (mu.clear(), self.save_config())).setEnabled(bool(mu.files))
        mm.addSeparator()
        orders_ = (("loop", T("依序循環")), ("shuffle", T("隨機")), ("one", T("單曲循環")))
        levels = tuple(zip(music.LEVELS, (T("小"), T("中"), T("大"))))
        for title, options, cur, attr in ((T("播放順序"), orders_, mu.mode, "mode"), (T("音量"), levels, mu.level, "level")):
            sub = mm.addMenu(title)
            grp = QActionGroup(sub)
            for value, label in options:
                act = sub.addAction(label)
                act.setCheckable(True)
                act.setChecked(value == cur)
                act.triggered.connect(lambda _=False, v=value, k=attr: (setattr(mu, k, v), self.save_config()))
                grp.addAction(act)

    def music_toggle(self):
        if not self.music.files:
            self.show_notice(T("音樂清單是空的：右鍵「音樂」加入音檔或資料夾"))
            return
        self.music.toggle()
        if self.music.playing:
            if not self.sound.user_on:                   # 聲音關著：按播放時一起打開，不然沒聲音
                self.sound.set_on(True)
                self.build_menu()
            self.music_changed(self.music.title())
        self.save_config()

    def music_add_files(self):
        exts = " ".join("*" + e for e in music.EXTS)
        files, _ = QFileDialog.getOpenFileNames(None, T("加入音檔"), self.cfg.get("music_dir", ""),
                                                f"{T('音樂')} ({exts})")
        if files:
            self.cfg["music_dir"] = os.path.dirname(files[0])
            self.music_added(self.music.add(files))

    def music_add_folder(self):
        folder = QFileDialog.getExistingDirectory(None, T("加入資料夾"), self.cfg.get("music_dir", ""))
        if folder:
            self.cfg["music_dir"] = folder
            self.music_added(self.music.add_folder(folder))

    def music_added(self, n):
        self.show_notice(T("加入了 {n} 首", n=n) if n else T("沒有新的音檔（重複的已略過）"))
        self.save_config()

    def music_changed(self, title):
        """換歌：狀態列沒在顯示沖煮進度時短暫提示曲名"""
        if not self.busy():
            self.show_notice("♪ " + title, 3.0)

    def music_skipped(self, name):
        self.show_notice(T("找不到或無法播放 {name}，已跳過", name=name), 4.0)

    def update_tray_tip(self):
        if not self.tray:
            return
        if self.session:
            tip = T("{name}：{status}", name=T(DRINKS[self.session.drink]["name"]), status=self.session.status())
        elif self.result is None:
            tip = T("待機中")
        else:
            r = self.result
            tip = T("上一杯{name} {score:.0f} 分 · {comment}", name=retext(r.title) or T(DRINKS[r.drink]["name"]),
                    score=r.score, comment=retext(r.comment))
        if self.order is not None and self.order.state == "waiting":
            o = self.order
            tip += "\n" + T("訂單 #{no} {name}：{title}", no=o.no, name=T(o.name), title=o.title)
        elif self.auto and not self.busy() and not self.order_mode:
            tip += "\n" + T("自動模式：{sec} 秒後沖下一杯",
                             sec=max(0, int(self.interval - (time.perf_counter() - self.idle_since))))
        if self.break_min:
            tip += "\n" + T("休息提醒：還有 {m} 分鐘", m=max(1, math.ceil(self.break_min - self.break_t / 60)))
        if self.music.playing:
            tip += "\n♪ " + self.music.title()
        self.tray.setToolTip("Café Desk\n" + tip)

    def add_view_menu(self, m):
        """右鍵「畫面（營業模式）」子選單：跟隨咖啡師（沒客人時在櫃檯、做飲品時在咖啡機前，原本的樣子）／鎖定櫃檯／鎖定咖啡機"""
        sub = m.addMenu(T("畫面（營業模式）"))
        grp = QActionGroup(sub)
        self.view_actions = {}
        for key, label in (("follow", "跟隨咖啡師"), ("counter", "鎖定櫃檯"), ("machine", "鎖定咖啡機")):
            act = sub.addAction(T(label))
            act.setCheckable(True)
            act.setChecked(self.view_lock == key)
            act.triggered.connect(lambda _on, k=key: self.set_view_lock(k))
            grp.addAction(act)
            self.view_actions[key] = act

    def set_view_lock(self, mode):
        """營業模式的畫面：跟隨咖啡師／鎖定櫃檯／鎖定咖啡機；馬上換過去（交付、結帳、做飲品照樣進行，只是畫面不跟著動）"""
        if mode not in VIEW_LOCKS:
            return
        self.view_lock = mode
        if mode in self.__dict__.get("view_actions", {}):
            self.view_actions[mode].setChecked(True)
        self.cfg["view_lock"] = mode
        self.save_config()
        if self.business():
            self.set_counter_view(self.delivery is not None or self.idle_counter())
        self.update()

    def set_counter_view(self, want):
        """畫面切到櫃檯（True）或咖啡機（False）；營業模式裡依畫面設定鎖定，淡入淡出"""
        if self.business():
            want = {"counter": True, "machine": False}.get(self.view_lock, want)
        if want != self.counter_view:
            self.begin_fade()
            self.counter_view = want

    def add_clock_menu(self, m):
        """右鍵「翻頁鐘」子選單：營業模式右上角的翻頁鐘要不要顯示、顯示什麼"""
        sub = m.addMenu(T("翻頁鐘（營業模式限定）"))
        c = self.clock_cfg

        def check(label, key, value=True):
            act = sub.addAction(label)
            act.setCheckable(True)
            act.setChecked(c.get(key) == value)
            act.triggered.connect(lambda on, k=key, v=value: self.set_clock(k, v if on or v is not True else False))
            return act
        check(T("顯示翻頁鐘"), "on")
        sub.addSeparator()
        check(T("顯示秒數"), "seconds")
        check(T("12 小時制"), "hour12")
        check(T("顯示日期與星期"), "date")

    def business_machine(self):
        """營業中做濃縮系飲品用哪台：店鋪頁指定的（已解鎖）；隨機（auto）時雙頭機解鎖後用它
        （後面有同類的就兩杯一起做），否則隨機一台已解鎖的"""
        if self.showcase in MACHINES and self.machine_open(self.showcase):
            return self.showcase
        if self.business() and self.machine_open("duo"):
            return "duo"
        return random.choice([k for k in MACHINES if self.machine_open(k)])

    def set_showcase(self, key):
        """店鋪頁：營業用咖啡機（auto＝隨機）；做飲品和櫃檯後檯都用這台"""
        self.showcase = key
        self.save_config()
        self.update()

    def set_cfg(self, key, v):
        setattr(self, key, v)
        self.save_config()

    def set_auto(self, v):
        self.auto = v
        self.idle_since = time.perf_counter()
        self.save_config()

    def fill_bean_menu(self):
        menu = self.bean_menu
        menu.clear()
        b = self.bag
        info = menu.addAction(T("目前：{name}（{roast}）", name=T(beans.bag_name(b)), roast=T(beans.bag_roast(b))))
        info.setEnabled(False)
        info2 = menu.addAction(T("烘焙後第 {days} 天 · 剩 {g:.0f} g · {flavor}", days=beans.bag_age(b), g=b["left"],
                                 flavor=T(beans.bag_flavor(b))))
        info2.setEnabled(False)
        if self.pending_bag:
            menu.addAction(T("待換上：{name}（這杯做完換）", name=T(beans.ORIGINS[self.pending_bag][0]))).setEnabled(False)
        menu.addSeparator()
        sub = menu.addMenu(T("換豆子（庫存 {n} 包）", n=self.bean_stock()))
        for key in beans.ORIGINS:
            name, roast, flavor, _ = beans.ORIGINS[key]
            n = self.bean_stock(key)
            part = self.shelf.get(key)                      # 開過還沒用完：倒回去接著用，不用開新包
            label = T("{name}（{roast}）· 已開 剩 {g:.0f} g", name=T(name), roast=T(roast), g=part["left"]) if part else                 T("{name}（{roast}）· 庫存 {n}", name=T(name), roast=T(roast), n=n)
            act = sub.addAction(label)
            act.setToolTip(T(flavor))
            act.setEnabled(n > 0 or part is not None)
            act.triggered.connect(lambda _=False, k=key: self.request_bag(k))
        sub.setToolTipsVisible(True)
        rnd = menu.addAction(T("隨機換一種"), lambda: self.request_bag(None))
        rnd.setEnabled(self.bean_stock() > 0 or bool(self.shelf))
        menu.addAction(T("買豆子…"), lambda: self.open_records("shop"))

    def fill_ing_menu(self):
        """右鍵「食材」：目前庫存、買食材、自動補貨（勾選的食材營業中沒庫存就自動買一包）"""
        menu = self.ing_menu
        menu.clear()
        for key, (name, per, price, _d) in ingredients.ITEMS.items():
            menu.addAction(T("{name} · 庫存 {n} 份", name=T(name), n=self.ing_stock(key))).setEnabled(False)
        menu.addSeparator()
        menu.addAction(T("買食材…"), lambda: self.open_records("ingredients"))

    def fill_maint_menu(self):
        menu = self.maint_menu
        menu.clear()
        st = self.maint
        due = maintenance.due(st)
        units = {"backflush": T("已沖 {n:.0f} 杯"), "wand": T("已打 {n:.0f} 次奶"),
                 "drip": T("{n:.0f} ml"), "knock": T("{n:.0f} 個粉餅")}
        for key in maintenance.TASKS:
            label = T(maintenance.task_name(key, self.machine.traits))
            text = T("{name}（{roast}）", name=label, roast=units[key].format(n=st.get(key, 0)))
            if key in due:
                text = "⚠ " + text
            act = menu.addAction(text, lambda k=key: self.start_job(k))
            act.setEnabled(not self.busy())

    def open_records(self, tab=None):
        """紀錄與收集冊、商店（"shop"／"ingredients"）、佈置（"layout"）是三個獨立視窗，各自一個、再開就重建"""
        tab = tab if isinstance(tab, str) else None
        name = {"shop": "store_dlg", "ingredients": "store_dlg", "layout": "layout_dlg"}.get(tab, "records_dlg")
        old = getattr(self, name, None)
        if old is not None:
            old.close()
            old.deleteLater()
        dlg = RecordsDialog(self, tab)
        setattr(self, name, dlg)
        dlg.show()
        dlg.raise_()

    def open_intro(self):
        if self.intro_dlg is not None:             # 每次重建：語言是最新的，也從第一頁開始
            self.intro_dlg.close()
            self.intro_dlg.deleteLater()
        self.intro_dlg = IntroDialog(self)
        self.intro_dlg.show()
        self.intro_dlg.raise_()
        self.intro_dlg.activateWindow()

    def open_about(self):
        if self.about_dlg is not None:             # 每次重建：語言與檔案狀態都是最新的
            self.about_dlg.close()
            self.about_dlg.deleteLater()
        self.about_dlg = AboutDialog(self)
        self.about_dlg.show()
        self.about_dlg.raise_()
        self.about_dlg.activateWindow()

    def set_art(self, v):
        self.dp.art = v
        if v in self.art_actions:
            self.art_actions[v].setChecked(True)
        if self.settings_dlg is not None:
            self.settings_dlg.sync_art()
        self.save_config()

    @property
    def maint(self):
        """目前這台咖啡機的清潔保養計數（每台各自計算）"""
        return self.maint_all[self.machine.key]

    def business(self):
        """營業模式＝顧客點單：客人排隊、有耐心、咖啡師自己接單、算營業額（跟自動模式無關）"""
        return self.order_mode

    def shop_level(self):
        """店鋪等級（累積營業額，從紀錄資料庫算）"""
        return growth.level_of(self.stats.data["revenue_total"])

    def skill(self, drink=None):
        """咖啡師手感誤差倍率（總杯數越多越穩）；給 drink 且已經是大師時再乘上這種飲品的專精（growth.mastery_k）"""
        k = growth.skill(self.stats.data["total"])
        if drink is not None:
            k *= growth.mastery_k(self.mastery(drink))
        return k

    def mastery(self, drink):
        """這種飲品的專精星級（大師之前一律 0）"""
        if not growth.mastery_open(self.stats.data["total"]):
            return 0
        return growth.mastery_stars(self.stats.data["collection"]["drinks"].get(drink))

    def check_mastery(self):
        """飲品專精星級升了就通知；第一次只記下目前的，不補發"""
        if not growth.mastery_open(self.stats.data["total"]):
            return
        stars = {k: growth.mastery_stars(v) for k, v in self.stats.data["collection"]["drinks"].items()}
        seen = self.cfg.get("mastery_seen")
        self.cfg["mastery_seen"] = stars
        if not isinstance(seen, dict):
            return
        for k, n in stars.items():
            if n > seen.get(k, 0) and k in DRINKS:
                self.toast(T("專精：{drink} {stars}", drink=T(DRINKS[k]["name"]), stars="★" * n + "☆" * (5 - n)), kind="trophy")

    def reset_progress(self):
        """重新遊玩：刪掉紀錄資料庫（每一杯、成就、商店購買），等級、稱號、錢包、清潔計數、豆子、冰滴從頭開始。
        參數設定、聲音與音樂清單、語言、視窗位置保留。無法復原（關於視窗按鈕會先確認）；咖啡師在忙時回傳 False"""
        if self.busy():
            return False
        if self.order_mode:
            self.order_mode = False                      # 直接關營業模式：不出打烊日報、不算流失
            self.set_order_mode(False)
            self.sync_mode_actions()
        for dlg in ("records_dlg", "store_dlg", "layout_dlg"):
            d = getattr(self, dlg)
            if d is not None:
                d.close()
                d.deleteLater()
                setattr(self, dlg, None)
        if self.stats.db is not None:
            self.stats.db.close()
        try:
            os.remove(db_path())
        except OSError:
            pass
        self.stats = Stats()
        store.apply_upgrades([])
        self.apply_traits()
        self.growth_seen = {"level": 1, "rank": 0}
        self.cfg["report_seen"] = ""
        self.cfg.pop("stars_seen", None)
        self.cfg.pop("mastery_seen", None)
        self.cfg.pop("decor", None)
        self.cfg.pop("challenge_set", None)
        self.order_no, self.order_day = 0, ""
        self.order, self.queue = None, []
        self.maint_all = {key: maintenance.default_state() for key in MACHINES}
        self.bag = beans.new_bag("house")
        self.shelf = {}
        self.pending_bag = None
        self.pre_biz, self._restore_biz = None, False
        self.sync_bag()
        self.cold = None
        self.barista = Barista()
        self.pf_used = False
        if not self.method_open(self.method):
            self.set_method("espresso")
        if not self.drink_open(self.drink):
            self.set_drink("espresso")
        if not self.machine_open(self.machine.key):
            self.set_machine(DEFAULT_MACHINE)
        self.reset_cup(self.drink)
        self.result = self.last_brew_res = self.report_card = None
        self.toasts.clear()
        self.ready.clear()
        self.pending_deliveries.clear()
        self.delivery, self.checkout, self.counter_view = None, None, False
        self.reg_floats.clear()
        self._report_due = None
        self.build_menu()
        self.save_config()
        self.toast(T("已重新開始：紀錄、等級與錢包都清空了"))
        return True

    def machine_open(self, key):
        """這台咖啡機已經依店鋪等級解鎖了嗎"""
        return growth.machine_open(key, self.shop_level())

    def set_back_gear(self, key, on):
        """「佈置」分頁：櫃檯畫面 POS 後方擺不擺這項設備（設定檔 back_gear_off 記關掉的）"""
        off = [k for k in self.cfg.get("back_gear_off", []) if k != key]
        if not on:
            off.append(key)
        self.cfg["back_gear_off"] = off
        self.save_config()
        self.update()

    def method_open(self, method):
        return growth.method_open(method, self.shop_level())

    def drink_open(self, key):
        """這杯飲品能做嗎：沖煮方式依店鋪等級、飲品依咖啡師稱號"""
        return self.method_open(method_of(key)) and \
            growth.rank_of(self.stats.data["total"]) >= growth.drink_rank(key)

    def drink_lock(self, key):
        """還沒解鎖時加在名稱後面的說明（已解鎖是空字串）"""
        m = method_of(key)
        if not self.method_open(m):
            return T("（Lv.{n} 解鎖）", n=growth.METHOD_LEVEL[m])
        if not self.drink_open(key):
            return T("（{rank}解鎖）", rank=T(growth.rank_name(growth.drink_rank(key))))
        return ""

    def wallet(self):
        """錢包餘額（累積營業額 − 商店花掉的錢）"""
        return store.balance(self.stats)

    def buy_upgrade(self, key):
        """商店：買咖啡機升級；回傳是否成功"""
        _targets, name, _desc, price, _change = store.UPGRADES[key]
        if key in self.stats.data["owned"] or not self.upgrade_open(key) or not self.stats.record_purchase(key, price):
            return False
        store.apply_upgrades(self.stats.data["owned"])
        self.apply_traits()
        self.sound.once("coin", 0.5)
        text = T("{machine} 升級：{name}", machine=T(store.target_name(key)), name=T(name))
        self.toast(text)
        self.build_menu()
        self.save_config()
        return True

    def upgrade_open(self, key):
        """升級的對象解鎖了嗎（沖煮台要先解鎖手沖；好幾台共用的有一台解鎖就能買）"""
        targets = store.UPGRADES[key][0]
        if targets == store.STATION:
            return self.method_open("pourover")
        return any(self.machine_open(k) for k in targets if k in MACHINES)

    def buy_beans(self, key, auto=False):
        """商店：買一包豆子（一般豆、精品豆都要買）放進庫存；開包在右鍵「豆子」，自動模式與營業中的咖啡師會自己從庫存開。
        auto：自動購買（庫存沒有時自己買）"""
        if key not in beans.ORIGINS or not self.stats.record_bean_buy(key, beans.price_of(key)):
            return False
        self.sound.once("coin", 0.5)
        name = T(beans.ORIGINS[key][0])
        self.toast(T("自動購買：{name}（{m}）", name=name, m=money(beans.price_of(key))) if auto
                   else T("買了一包{name}（庫存 {n} 包）", name=name, n=self.bean_stock(key)))
        return True

    def set_auto_buy(self, key, on):
        """右鍵「豆子」→「自動購買」：勾選的豆子，庫存沒有時自動買一包"""
        if key not in beans.ORIGINS:
            return
        if on and key not in self.auto_buy:
            self.auto_buy.append(key)
        elif not on and key in self.auto_buy:
            self.auto_buy.remove(key)
        if on:
            self.restock_beans()                 # 勾選就先買一包放著
        self.save_config()

    def restock_beans(self):
        """自動購買勾選的豆子，庫存隨時留一包（沒有就買，買得起才買；開一包後也會補）"""
        for key in self.auto_buy:
            if self.bean_stock(key) <= 0 and beans.price_of(key) <= self.wallet():
                self.buy_beans(key, auto=True)

    def auto_buy_candidates(self):
        """自動購買勾選、而且錢包買得起的豆子"""
        wallet = self.wallet()
        return [k for k in self.auto_buy if beans.price_of(k) <= wallet]

    def auto_buy_bag(self):
        """庫存沒有時，從自動購買勾選的豆子隨機買一包；沒勾選或錢不夠回傳 False（錢不夠會提醒）"""
        if not self.auto_buy:
            return False
        cands = self.auto_buy_candidates()
        if not cands:
            now = time.perf_counter()
            if now >= getattr(self, "_autobuy_hint_at", 0.0):
                self._autobuy_hint_at = now + 20.0
                self.toast(T("錢包不夠，沒辦法自動購買咖啡豆"), 5.0)
            return False
        return self.buy_beans(random.choice(cands), auto=True)

    def ing_stock(self, key=None):
        """食材庫存的份數（指定食材，或全部加起來）"""
        stock = self.stats.data["ing_stock"]
        return stock.get(key, 0) if key else sum(stock.values())

    def buy_ingredient(self, key, auto=False):
        """商店：買一包食材（份數見 ingredients.ITEMS）；auto：營業中庫存沒有時自動補貨"""
        if not self.stats.record_ing_buy(key):
            return False
        self.sound.once("coin", 0.5)
        if key in ingredients.DESSERTS:
            self.announce(self.stats.check(None, ()))            # 甜點的成就（櫥窗滿滿）
        name = T(ingredients.ALL[key][0])
        self.toast(T("自動補貨：{name}（{m}）", name=name, m=money(ingredients.price_of(key))) if auto
                   else T("進了一盤{name}（庫存 {n} 個）", name=name, n=self.ing_stock(key)) if key in ingredients.DESSERTS
                   else T("買了一包{name}（庫存 {n} 份）", name=name, n=self.ing_stock(key)))
        return True

    def set_auto_ing(self, key, on):
        """右鍵「食材」→「自動補貨」：勾選的食材，營業中庫存沒有時自動買一包"""
        if key not in ingredients.ALL:
            return
        if on and key not in self.auto_ing:
            self.auto_ing.append(key)
        elif not on and key in self.auto_ing:
            self.auto_ing.remove(key)
        if on:
            self.restock_ingredients()           # 勾選就先買一包放著
        self.save_config()

    def restock_ingredients(self):
        """自動補貨：勾選而庫存沒有的食材，錢包買得起就買一包（沒錢提醒一次）"""
        for key in self.auto_ing:
            if self.ing_stock(key) > 0:
                continue
            if not self.buy_ingredient(key, auto=True):
                now = time.perf_counter()
                if now >= getattr(self, "_auto_ing_hint_at", 0.0):
                    self._auto_ing_hint_at = now + 20.0
                    self.toast(T("錢包不夠，沒辦法自動補貨：{name}", name=T(ingredients.ALL[key][0])), 5.0)

    def use_ingredients(self, o):
        """營業中客人點單時，扣掉這杯要用的食材；用完的那樣提醒一次（沒有庫存客人就不會點需要它的飲品）"""
        for key, n in ingredients.needs(o.drink, o.mods).items():
            if self.stats.record_ing_use(key, n) and self.ing_stock(key) == 0 and key not in self.auto_ing:
                self.toast(T("{name}用完了：客人不會點需要它的飲品，到商店「食材」補貨", name=T(ingredients.ITEMS[key][0])), 6.0)
        self.restock_ingredients()                               # 自動補貨：用完馬上補一包，庫存隨時留一份
        self.announce(self.stats.check(None, ()))                # 消耗食材的成就

    def refund_order(self, o):
        """客人沒取餐（等太久離開、打烊、切換模式）：下單時扣掉的食材與加購的甜點退回庫存，賣出量與用掉量也減回去"""
        if o.refunded:
            return
        o.refunded = True
        for key, n in ingredients.needs(o.drink, o.mods).items():
            self.stats.record_ing_refund(key, n)
        if o.dessert:
            self.stats.record_ing_refund(o.dessert, 1)
            o.price -= o.dessert_price
            o.dessert, o.dessert_price = "", 0
        self.restock_ingredients()

    def dessert_stock(self):
        """櫥窗裡有貨的甜點 {key: 份數}（照 ingredients.DESSERTS 的順序）"""
        return {k: self.ing_stock(k) for k in ingredients.DESSERTS if self.ing_stock(k) > 0}

    def pick_dessert(self):
        """營業中這位客人要不要加購甜點：櫥窗有貨才可能，回傳甜點 key 或 None（還沒扣庫存，add_dessert 才扣）"""
        stock = self.dessert_stock()
        if not stock or random.random() >= ingredients.DESSERT_P:
            return None
        return random.choice(list(stock))

    def add_dessert(self, o, key):
        """這一杯加購一份甜點：扣庫存、折價後的售價算進這張單；賣完了提醒一次"""
        if not self.stats.record_ing_use(key, 1):
            return
        o.dessert, o.dessert_price = key, ingredients.dessert_price(key)
        o.price += o.dessert_price
        self.restock_ingredients()
        if self.ing_stock(key) == 0 and key not in self.auto_ing:
            self.toast(T("{name}賣完了：到商店「甜點」進貨，櫥窗有甜點才會有人加購", name=T(ingredients.DESSERTS[key][0])), 6.0)

    def ing_avail(self, drink, mods=()):
        """庫存夠不夠做這杯（營業模式才看，其他模式不消耗食材）"""
        return ingredients.available(drink, self.stats.data["ing_stock"], mods)

    def bean_choices(self):
        """客人能指定的精品豆：店裡右下櫥窗擺出來的（有庫存的、加上正在用的那包），沒有的客人不會點"""
        cur = self.bag["origin"]
        return [k for k in beans.PREMIUM if self.bean_stock(k) > 0 or k == cur or k in self.shelf]

    def bean_stock(self, origin=None):
        """豆子庫存的包數（指定產地，或全部加起來）"""
        stock = self.stats.data["bean_stock"]
        return stock.get(origin, 0) if origin else sum(stock.values())

    def out_of_beans(self, need=21.0):
        """目前這包不夠做一杯、庫存也沒有（自動購買買得起的也沒有）：咖啡師沒豆子可用，要去商店買"""
        return self.bag["left"] < need and not self.bean_stock() and not self.shelf and not self.auto_buy_candidates()

    def open_next_bag(self):
        """開下一包：排著要換的那種（庫存有的話），沒有就從庫存隨機挑一種；都沒有回傳 False"""
        if self.pending_bag and self.bean_stock(self.pending_bag):
            return self.open_bag(self.take_pending_bag())
        return self.open_bag(None)

    def beans_hint(self):
        """沒豆子了：提醒去商店買（每 20 秒最多一次）"""
        now = time.perf_counter()
        if now >= getattr(self, "_beans_hint_at", 0.0):
            self._beans_hint_at = now + 20.0
            self.toast(T("豆子用完了，到「紀錄與收集冊」→「商店」買豆子"), 6.0)
            self.sound.once("ding_lo", 0.4)

    def decor_sel(self):
        """目前選用的店面裝潢（decor.selection）"""
        return decor.selection(self.cfg.get("decor"), self.stats.data["owned"])

    def stamps_free(self):
        """還沒用掉的挑戰章數（集點換限定裝潢）"""
        return challenges.stamps_of(self.stats.data["challenges"]) - self.stats.data["stamps_spent"]

    def buy_decor(self, key):
        """商店：買一款裝潢（營業額，或限定款用挑戰章數兌換）；買了不會自動套用，要到紀錄的「佈置」分頁換上；回傳是否成功"""
        slot, name, price, stamps, _desc = decor.ITEMS[key]
        if f"decor_{key}" in self.stats.data["owned"] or decor.is_default(key):
            return False
        ok = (self.stats.record_stamp_purchase(f"decor_{key}", stamps, self.stamps_free()) if stamps
              else self.stats.record_purchase(f"decor_{key}", price))
        if not ok:
            return False
        self.sound.once("coin", 0.5)
        self.toast(T("新裝潢：{name}（到「佈置」分頁擺上）", name=T(name)))
        return True

    def use_decor(self, key):
        """換上（單選欄位）或擺上／拿下（掛畫、植物）一款買過的裝潢；沒買的不行"""
        if key not in decor.owned_keys(self.stats.data["owned"]):
            return False
        slot = decor.ITEMS[key][0]
        sel = decor.selection(self.cfg.get("decor"), self.stats.data["owned"])
        if slot in decor.MULTI:
            cur = sel[slot]
            if key in cur:
                cur.remove(key)
            else:
                limit = decor.MAX_PAINTINGS if slot == "paintings" else decor.MAX_PLANTS
                if len(cur) >= limit:
                    cur.pop(0)                                  # 位置滿了：最早擺的換下來
                cur.append(key)
        else:
            sel[slot] = key
        self.cfg["decor"] = sel
        self.save_config()
        return True

    def together_open(self):
        """咖啡師到「職人」：萃取的同時打奶（drinks.Session 用；單鍋爐不適用由 Session 判斷）"""
        return growth.rank_of(self.stats.data["total"]) >= growth.TOGETHER_RANK

    def challenge_set(self):
        """今天的每日挑戰與本週的每週挑戰（產生後存在設定檔，當天不因升級或解鎖而變）"""
        day = festivals.today().isoformat()
        cs = self.cfg.get("challenge_set")
        if not isinstance(cs, dict):
            cs = {}
        if cs.get("day") != day or cs.get("level") is None:
            pool = [k for k in DRINK_KEYS if method_of(k) == "espresso" and self.drink_open(k) and k in orders.ORDER_WEIGHTS
                    and not DRINKS[k].get("festival")]
            lv = self.shop_level()
            cs = {"day": day, "level": lv,
                  "daily": challenges.daily_set(day, lv, pool, festivals.festival_drink()),
                  "week": challenges.week_start(day), "weekly": cs.get("weekly") if cs.get("week") == challenges.week_start(day) else None}
            if cs["weekly"] is None:
                cs["weekly"] = challenges.weekly_set(day, lv)
            self.cfg["challenge_set"] = cs
        return cs

    def check_challenges(self):
        """每日／每週挑戰完成就蓋章並通知；集滿章數換稱號"""
        day = festivals.today().isoformat()
        cs = self.challenge_set()
        for it in cs["daily"] + cs["weekly"]:
            if it["id"] in self.stats.data["challenges"] or not challenges.done(it, self.stats, day):
                continue
            before = challenges.stamps_of(self.stats.data["challenges"])
            if not self.stats.record_challenge(it["id"]):
                continue
            after = challenges.stamps_of(self.stats.data["challenges"])
            self.toast(T("挑戰完成：{text}（集點 +{n}）", text=challenges.text_of(it, lambda k: DRINKS[k]["name"]), n=after - before),
                       kind="trophy")
            self.sound.once("ding_hi", 0.5)
            old, new = challenges.title_index(before), challenges.title_index(after)
            if new > old:
                self.toast(T("獲得稱號：{name}！", name=T(challenges.TITLES[new][1])), kind="trophy")

    def star_rating(self):
        return growth.star_rating(self.stats, festivals.today().isoformat(), self.shop_level())

    def check_stars(self):
        """店鋪星等（四捨五入到整顆星）升降時通知；第一次評鑑出來只記下，不通知"""
        r = self.star_rating()
        if r is None:
            return
        now, old = int(round(r)), self.cfg.get("stars_seen")
        self.cfg["stars_seen"] = now
        if old is None or now == old:
            return
        if now > old:
            self.toast(T("店鋪評鑑升到 {n} 星！", n=now), kind="trophy")
            self.sound.once("ding_hi", 0.5)
        else:
            self.toast(T("店鋪評鑑掉到 {n} 星…客人的評價下滑了", n=now))

    def check_growth(self):
        """店鋪升級、咖啡師換稱號時通知（同一級只通知一次）"""
        self.check_stars()
        self.check_mastery()
        self.check_challenges()
        lv, rank = self.shop_level(), growth.rank_of(self.stats.data["total"])
        seen = self.growth_seen
        if lv > seen.get("level", 1):
            text = T("店鋪升級：Lv.{n} {name}！", n=lv, name=T(growth.level_name(lv)))
            self.toast(text, kind="trophy")
            self.tray_message(text)
            self.sound.once("ding_hi", 0.5)
        if rank > seen.get("rank", 0):
            text = T("咖啡師晉升：{name}！手感更穩了", name=T(growth.rank_name(rank)))
            self.toast(text, kind="trophy")
            self.tray_message(text)
            self.sound.once("ding_hi", 0.5)
            names = [T(DRINKS[k]["name"]) for r in range(seen.get("rank", 0) + 1, rank + 1)
                     for k in growth.drinks_at_rank(r)]
            if rank >= growth.FESTIVAL_RANK > seen.get("rank", 0) and festivals.festival_drink():
                names.append(T(DRINKS[festivals.festival_drink()]["name"]))
            if names:
                self.toast(T("解鎖新飲品：{names}", names=T("、").join(names)))
            if rank >= growth.TOGETHER_RANK > seen.get("rank", 0):
                self.toast(T("新技能：萃取的同時打奶（單鍋爐機除外），熱牛奶飲品快約三成"))
            self.build_menu()
            if self.settings_dlg is not None:
                self.settings_dlg.refresh_locks()
        if lv > seen.get("level", 1):
            names = []
            for k in range(seen.get("level", 1) + 1, lv + 1):
                names += [T(MACHINES[key].name) if kind == "machine" else T(brew.METHODS[key])
                          for kind, key in growth.unlocked_at(k)]
            if names:
                self.toast(T("解鎖新設備：{names}", names=T("、").join(names)))
            self.build_menu()
            if self.settings_dlg is not None:
                self.settings_dlg.refresh_locks()
        if (lv, rank) != (seen.get("level"), seen.get("rank")):
            self.growth_seen = {"level": max(lv, seen.get("level", 1)), "rank": max(rank, seen.get("rank", 0))}
            self.save_config()

    def update_menu_locks(self):
        """顧客點單時沖煮方式、咖啡機、飲品、拉花圖案、豆子、食材、清潔保養整組隱藏（照訂單做，咖啡師自己清）；
        咖啡機、拉花圖案、清潔保養另外只在義式咖啡機畫面可用"""
        free = not self.order_mode
        espresso = self.method == "espresso"
        self.method_menu.setEnabled(free)
        self.machine_menu.setEnabled(free and espresso)
        self.drink_menu.setEnabled(free)
        self.art_menu.setEnabled(free and espresso)
        self.bean_menu.setEnabled(True)                  # 營業中也能換豆子（這杯做完才換，request_bag）
        self.maint_menu.setEnabled(espresso and free)    # 點單時咖啡師該清就自己清
        for menu in (self.method_menu, self.machine_menu, self.drink_menu, self.art_menu, self.bean_menu,
                     self.ing_menu, self.maint_menu):
            menu.menuAction().setVisible(free)           # 營業模式整組隱藏（咖啡師照訂單做）；手動、自動才顯示
        self.act_brew.setVisible(free)                   # 開始沖煮、參數設定也只有手動、自動才顯示
        self.act_params.setVisible(free)
        self.interval_menu.setEnabled(free)                  # 營業中用不到（咖啡師自己接單）
        self.speed_menu.setEnabled(free)                     # 營業中固定 1 倍（客人的耐心、來店照真實時間）
        self.speed_menu.setTitle(T("播放速度") if free else T("播放速度（營業中固定 1×）"))
        act = getattr(self, "windowed_act", None)
        if act is not None:                              # 營業中一律視窗化；手動／自動可以切換
            act.blockSignals(True)                       # 勾選顯示實際狀態：營業中勾起來並反灰，離開營業回到使用者的設定
            act.setChecked(self.is_windowed())
            act.blockSignals(False)
            act.setEnabled(free)
            act.setText(T("視窗化顯示") if free else T("視窗化顯示（營業中固定）"))
        if self.settings_dlg is not None:
            self.settings_dlg.sync_lock()

    # ───────────── 模式：手動／自動／營業 ─────────────
    MODES = (("practice", "練習：手動點一下做一杯，或定時自動做"), ("business", "營業：客人點單、賺營業額"))

    def mode(self):
        return "business" if self.order_mode else ("auto" if self.auto else "manual")

    def add_mode_actions(self, menu, before=None):
        """在選單裡加練習／營業二選一（右鍵、系統匣各一組，勾選狀態由 sync_mode_actions 同步）；before：插在這個項目前面。
        系統匣那組（before 是 None）多一個「自動做咖啡」開關（右鍵選單用子選單 interval_menu）"""
        grp = QActionGroup(menu)
        acts = {}
        for key, label in self.MODES:
            act = QAction(T(label), menu)
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self.set_mode(k))
            grp.addAction(act)
            if before is not None:
                menu.insertAction(before, act)
            else:
                menu.addAction(act)
            acts[key] = act
        if before is None:
            auto = QAction(T("自動做咖啡"), menu)
            auto.setCheckable(True)
            auto.triggered.connect(lambda on=False: self.set_mode("auto" if on else "manual"))
            menu.addAction(auto)
            acts["auto"] = auto
        return acts

    def sync_mode_actions(self):
        cur = self.mode()
        for acts in (getattr(self, "mode_actions", {}), getattr(self, "tray_mode_actions", {})):
            for key, act in acts.items():
                act.blockSignals(True)
                if key == "auto":
                    act.setChecked(cur == "auto")
                    act.setEnabled(cur != "business")
                else:
                    act.setChecked((key == "business") == (cur == "business"))
                act.blockSignals(False)
        for value, act in getattr(self, "interval_acts", {}).items():
            act.blockSignals(True)
            act.setChecked(abs(value - self.interval) < 1e-6 if (value is not None and cur == "auto") else (value is None and cur != "auto"))
            act.blockSignals(False)

    def set_mode(self, mode):
        """切換模式：manual／auto（都是「練習」）、business；"practice"＝練習（保留目前的自動開關）。從營業切走時照樣出打烊日報"""
        if mode == "practice":
            mode = "auto" if self.auto else "manual"
        if mode != "business" and self.order_mode:
            self.set_order_mode(False)
        if mode == "business":
            self.set_order_mode(True)
        else:
            self.set_auto(mode == "auto")
        self.sync_mode_actions()
        self.update_menu_locks()

    def set_auto_interval(self, seconds):
        """「自動做咖啡」子選單：選一個間隔就開始自動（營業中不能選）"""
        self.set_cfg("interval", seconds)
        self.set_mode("auto")

    def unserved_orders(self):
        """還沒取餐（還在等、在做，或做好了沒公布分數）的所有訂單：目前這張、排隊、出餐架、等交付與交付中的（切換模式中止時用）"""
        found = [self.order] + list(self.queue) + [c["order"] for c in self.ready]
        for d in self.pending_deliveries + (self.delivery["parties"][self.delivery["i"]:] if self.delivery else []):
            found += d["orders"]
        out = []
        for o in found:
            if o is not None and (not o.revealed or o.state in ("waiting", "making")) and all(o is not x for x in out):
                out.append(o)
        return out

    def abort_animation(self):
        """立刻中止目前所有動畫與進行中的單：正在做的飲品（含雙頭機第二杯）、清潔、換機器等待、櫃檯結帳與交付、
        出餐架與排隊的客人；杯子換成空杯、聲音停掉（切換練習／營業模式時用；中止的單不算紀錄，扣掉的食材與甜點退回庫存）"""
        for o in self.unserved_orders():
            self.refund_order(o)
        self.session = self.pair = self.workflow = self.job = self._switch_wait = None
        self.shot = None
        self.delivery = self.checkout = None
        self.pending_deliveries, self.ready = [], []
        if hasattr(self, "reg_floats"):
            self.reg_floats = []
        self.order, self.queue, self.order_alpha = None, [], 0.0
        self.twin = None
        self._in_twin = False
        self.machine.g = 0
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.wand_angle = 0.0
        self.frother_fill = 0.42
        self.cup_away = False
        self.sound.stop_all()
        self.reset_cup(self.drink)
        self.twin = self.new_twin()
        self.set_frame_interval(FRAME_AMBIENT)

    def set_order_mode(self, v):
        """營業模式（顧客點單）：咖啡師自己接單，自動模式關掉；關掉營業後是手動（要自動就再選「自動」）。
        營業中咖啡師會自己調參數、換咖啡機與飲品：開營業前記下你的設定，離開營業、手上那杯做完後還原"""
        if bool(v) != self.order_mode:
            self.abort_animation()                   # 練習⇄營業：手上正在做的、櫃檯交付的動畫立刻中止
        if v and not self.order_mode:
            self.pre_biz = {"params": asdict(self.params), "machine": self.machine.key, "drink": self.drink}
            self._restore_biz = False
        elif not v and self.order_mode and self.pre_biz:
            self._restore_biz = True                 # 等手上那杯做完（step 裡還原）
        if not v:
            self._switch_wait = None
        auto = False
        closing = self.order_mode and not v
        opening = v and not self.order_mode
        was_windowed = self.is_windowed()
        self.order_mode = v
        if self.is_windowed() != was_windowed:          # 營業一律視窗化；離開營業回到使用者的設定
            self.rebuild_host()
        if closing and self.stats.day()["orders"]:      # 打烊：今天有接過單就出日報
            self.show_report(growth.report(self.stats, self._today))
        if auto != self.auto:
            self.set_auto(auto)
        if not v and self.order is not None and self.order.state != "making":
            if self.order.state == "waiting":
                self.refund_order(self.order)
            self.order = None
        if not v:
            for q in self.queue:                     # 打烊：排隊還沒做的客人走了，食材與甜點退回
                self.refund_order(q)
            self.queue.clear()
            self.seated = []                         # 打烊：坐著的客人也走了
        self.arrive_in = 3.0
        self.next_order_at = time.perf_counter() + 1.5
        self.idle_since = time.perf_counter()
        self.update_menu_locks()
        if (opening or closing) and self.method == "espresso":   # 營業模式咖啡機右邊多一段出杯台（視窗寬度通常不變，杯子要換位置）
            self.begin_fade()
            self.apply_scale()
            if not self.busy():
                self.reset_cup(self.drink)           # 杯子換到出杯台（或換回沖煮頭下）
        self.save_config()

    def set_language(self, v):
        """切換介面語言：重建右鍵選單、系統匣選單與設定視窗"""
        if v == self.lang:
            return
        self.lang = v
        set_lang(v)
        self.build_menu()
        if self.tray:
            self.tray.hide()
            self.tray.deleteLater()
        self.build_tray()
        if self.settings_dlg is not None:
            visible = self.settings_dlg.isVisible()
            self.settings_dlg.close()
            self.settings_dlg.deleteLater()
            self.settings_dlg = None
            if visible:
                self.open_settings()
        self.save_config()
        self.update()

    def set_light_mode(self, v):
        self.light_mode = v
        self.update_light(force=True)
        self.save_config()
        self.update()

    def set_topmost(self, v):
        self.topmost = v
        self.rebuild_host()
        self.save_config()

    def set_scale(self, v):
        self.scale_f = v
        self.apply_scale()
        self.save_config()

    def quit_app(self):
        self.flush_unpaid()                          # 還沒結帳的杯子也寫進紀錄
        self.save_config()
        self.sound.stop_all()
        self.music.stop()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def open_settings(self):
        if self.settings_dlg is None:
            self.settings_dlg = SettingsDialog(self)
        self.settings_dlg.show()
        self.settings_dlg.raise_()

    # ───────────── 滑鼠 ─────────────
    def logical(self, e):
        """滑鼠位置換成場景座標（扣掉上方透明區）"""
        pos = e.position()
        return pos.x() / self.scale_f - self.scene_dx(), pos.y() / self.scale_f - TOP_PAD

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.menu.exec(e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton:
            self._press = (e.globalPosition().toPoint(), self.host.pos(), self.logical(e))
            self._moved = False

    def mouseMoveEvent(self, e):
        x, y = self.logical(e)
        over = self.method == "espresso" and _inside(x, y, self.machine.hover_area)
        if over and not self.hover:
            self.hover_since = time.perf_counter()
        self.hover = over
        self.status_hover = over or (self.method != "espresso" and 0 <= x <= self.scene_extent()[0] and 0 <= y <= WIN_H)
        if not self._press:
            return
        g0, p0, _ = self._press
        d = e.globalPosition().toPoint() - g0
        if abs(d.x()) + abs(d.y()) > 4:
            self._moved = True
        if self._moved:
            self.host.move(p0 + d)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or not self._press:
            return
        if self._moved:
            self.save_config()
        elif self.report_alpha() > 0.05:                 # 日報顯示中：點一下收起（不開始沖煮）
            self.dismiss_report()
        else:
            x, y = self._press[2]
            m = self.machine
            if self.method != "espresso":
                if y >= 0:                                 # 手沖／冰滴：點畫面任何地方
                    self.manual_brew()
            elif _inside(x, y, m.machine_hit) or _inside(x, y, m.grinder_hit):
                self.manual_brew()
        self._press = None

    def leaveEvent(self, _):
        self.hover = self.status_hover = False

    # ───────────── 沖煮控制 ─────────────
    def brewing(self):
        return self.shot is not None and self.shot.phase != "done"

    def busy(self):
        return self.making() or self.delivery is not None or self.checkout is not None or bool(self.pending_deliveries)

    def idle_counter(self):
        """營業中咖啡師空著（沒在做、沒有要交付的）：畫面退回櫃檯，客人點單時 POS 在等；要做飲品才切回咖啡機"""
        if self.checkout is not None:
            return True                                                     # 接單結帳中
        return self.business() and not self.making() and not self.pending_deliveries and not self.ready  # 同一張單還沒做完：留在咖啡機前

    def making(self):
        """咖啡師正在做飲品、清潔或換機器（不含櫃檯交付）"""
        return (self.session is not None or self.workflow is not None or self.brewing() or self.job is not None
                or self._switch_wait is not None or self.pair is not None)

    def cup_volume(self):
        """杯中內容物總量（g）：決定液面高度；冰塊被液體淹到的部分也佔體積"""
        c = self.contents
        liquid = self.cup_espresso() + c["water"] + c["milk"] + c["syrup"]
        ice = sum(1 for cube in self.ice if cube["landed"]) * ICE_VOL * clamp(liquid / 60, 0, 1)
        ic = self.icecream
        melted = ic["g"] * ic["melt"] * 0.8 if ic else 0.0       # 冰淇淋融化成液體的部分
        return liquid + c["foam"] + ice + melted

    def scale_weight(self):
        """磅秤讀數：杯中所有東西的重量（杯子送走了是 0）；營業模式杯子在出杯台，磅秤上是量杯"""
        if self.side_on():
            ss = self.session
            return self.shot.weight * (1 - self.shot_frac) if (ss and ss.jigger and self.shot) else 0.0
        if self.cup_away and not self._in_twin:
            return 0.0
        c = self.contents
        ic = self.icecream
        return (self.cup_espresso() + c["water"] + c["milk"] + c["syrup"] + len(self.ice) * 14
                + (ic["g"] if ic and ic["landed"] else 0.0))

    def cup_espresso(self):
        """杯子裡的濃縮（g）：營業模式萃取到量杯時，倒進杯子的才算"""
        return self.shot.weight * self.shot_frac if self.shot else 0.0

    def jigger_level(self):
        """量杯拿在沖煮頭下接濃縮時，液面的 y（機身座標）；沒有在接時 None（流柱、水滴落到杯子）"""
        ss = self.session
        v = ss.jigger if ss else None
        if not v or v.get("pour", 0) > 0 or v["tilt"] > 0.5:
            return None
        k = vessels.JIGGER_K
        return v["y"] - self.machine.my + (50 - 46 * v.get("content", 0.0)) * k

    def set_method(self, method):
        """換沖煮方式：義式咖啡機／手沖／冰滴各有自己的畫面與飲品"""
        if method == self.method:
            return
        if self.busy():
            self.method_actions[self.method].setChecked(True)
            return
        self.hover = self.status_hover = False           # 畫面換了：滑鼠還沒動之前不算停在機器上（不然萃取曲線會留在沖煮台上）
        self.begin_fade()
        self.method = method
        if method_of(self.drink) != method:
            self.drink = next(k for k in DRINK_ORDER if k and method_of(k) == method)
        self.steam.clear()                               # 上一個畫面的蒸氣、水滴不要帶過去
        self.drops.clear()
        self.brew_zoom = 1.0 if self.brew_focus() else 0.0    # 切過去時直接是該有的遠近
        self.reset_cup(self.drink)
        self.apply_scale()
        self.build_menu()
        if self.settings_dlg is not None:
            self.settings_dlg.sync_drink()
        self.save_config()
        self.set_frame_interval(FRAME_ACTIVE)

    def set_drink(self, key):
        if not self.drink_open(key):
            m = method_of(key)
            if not self.method_open(m):
                self.show_notice(T("{name}要店鋪 Lv.{n} 才解鎖", name=T(brew.METHODS[m]), n=growth.METHOD_LEVEL[m]))
            else:
                self.show_notice(T("{name}要咖啡師「{rank}」才解鎖", name=T(DRINKS[key]["name"]),
                                   rank=T(growth.rank_name(growth.drink_rank(key)))))
            if self.settings_dlg is not None:
                self.settings_dlg.sync_drink()
            return
        if method_of(key) != self.method and not self.busy():
            self.drink = key
            self.set_method(method_of(key))
            return
        self.drink = key
        if not self.busy():
            self.reset_cup(key)
        if self.settings_dlg is not None and self.settings_dlg.drink.currentData() != key:
            self.settings_dlg.sync_drink()
        self.save_config()

    def reset_cup(self, drink, to_go=False, size="M"):
        """換上這個飲品的空杯子；營業模式外帶的熱飲用紙杯（cups.paper_kind），大中小杯跟著縮放"""
        kind = DRINKS[drink]["cup"]
        self.cup = Cup(paper_kind(kind) if to_go else kind, *self.cup_anchor(), size=size,
                       fit=cup_fit(drink, size))                 # 杯子依這杯的量縮放，約九成滿
        self.cup.sized = self.business() and drink in orders.SIZE_DRINKS     # 紙杯上印 S／M／L
        self.shot_frac = 1.0
        self.contents = {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0}
        self.topping = {}
        self.icecream = None
        self.ice = []
        self.condense = 0.0
        self.mix_t = 0.0
        self.shot = None
        self.result = None
        self.last_drink = drink
        self.last_art = None
        self.last_milk = None
        self.steam.clear()
        self.bubbles.clear()
        self.crema_h = self.film_h = 0.0
        if not self._in_twin:
            self.cup_away = False
            if self.pair is None:                        # 換杯子時第二個沖煮頭下的杯子也收走
                self.twin = self.new_twin()
        self.update()

    # ───────────── 雙頭機的第二杯 ─────────────
    def new_twin(self):
        """第二個沖煮頭的狀態（TWIN_FIELDS；單頭機回傳 None）。cup 是 None＝第二個沖煮頭下面沒有杯子"""
        m = self.machine
        if m.traits.groups < 2:
            return None
        old = self.twin or {}
        return {"session": None, "cup": None, "contents": {"water": 0.0, "milk": 0.0, "foam": 0.0, "syrup": 0.0},
                "syrup_kind": "choc", "topping": {}, "icecream": None, "ice": [], "condense": 0.0, "mix_t": 0.0,
                "mix_clock": 0.0, "shot": None, "stream": [{"head": 0.0, "tail": 0.0} for _ in m.spouts],
                "last_flow": 0.0, "drops": [], "splash": [], "ripples": [], "bubbles": [], "crema_h": 0.0,
                "film_h": 0.0, "swirl": 0.0, "pf_used": old.get("pf_used", False), "workflow": None,
                "gauge": old.get("gauge", 0.0), "gauge_v": old.get("gauge_v", 0.0), "_log_clock": 0.0,
                "_ripple_clock": 0.0, "last_drink": self.drink, "shot_frac": 1.0, "wand_angle": 0.0,
                "card_alpha": 0.0, "art_alpha": 0.0, "last_art": None, "last_milk": None, "art_show_until": 0.0,
                "_art_cache": None}

    @contextmanager
    def on_twin(self):
        """暫時換成第二個沖煮頭：每杯各一份的狀態跟 self.twin 對調、機器的 g 設成 1，離開時換回來。
        單頭機（沒有 twin）或已經在裡面時什麼都不做"""
        tw = self.twin
        if tw is None or self._in_twin:
            yield
            return
        keep = {k: getattr(self, k) for k in TWIN_FIELDS}
        for k in TWIN_FIELDS:
            setattr(self, k, tw[k])
        self._in_twin = True
        self.machine.g = 1
        try:
            yield
        finally:
            for k in TWIN_FIELDS:
                tw[k] = getattr(self, k)
            for k, v in keep.items():
                setattr(self, k, v)
            self.machine.g = 0
            self._in_twin = False

    def twin_live(self):
        """第二個沖煮頭下面有杯子（要推進、要畫）"""
        return self.twin is not None and self.twin["cup"] is not None

    def twin_get(self, key):
        """第二杯的某個狀態（不管現在有沒有換過去）"""
        if self._in_twin:
            return getattr(self, key)
        return self.twin[key] if self.twin is not None else 0.0

    def on_focus(self):
        """狀態列、卡片、聲音看哪一杯：成對做兩杯、正在做第二杯時看第二杯"""
        return self.on_twin() if (self.pair is not None and self.pair.focus_b) else nullcontext()

    def drop_icecream(self, grams, x, y):
        """阿芙佳朵：冰淇淋球從勺子掉進杯裡（機身座標）"""
        r = 23.0 * (grams / 70) ** (1 / 3)
        cup = self.cup
        self.icecream = {"g": grams, "r": r, "x": x, "y": y, "vy": 0.0, "landed": False, "melt": 0.0,
                         "rest": cup.liquid_bottom - r * 0.78, "rot": random.uniform(0, 6.28)}
        self.set_frame_interval(FRAME_ACTIVE)

    def apply_traits(self):
        t = self.machine.traits
        self.boiler.HEAT = t.boiler_heat
        self.boiler.DRAW = t.boiler_draw

    def set_machine(self, key):
        if key == self.machine.key:
            return
        if self.busy():                      # 沖煮中不能換機器
            self.machine_actions[self.machine.key].setChecked(True)
            return
        self.begin_fade()
        self.machine = MACHINES[key]
        self.apply_traits()
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.wand_angle = 0.0
        self.reset_cup(self.drink)
        self.apply_scale()
        self.save_config()
        self.set_frame_interval(FRAME_ACTIVE)

    def start_session(self, drink, full_flow, dp=None, order=None):
        if self.busy():
            return
        self.sync_bag()
        dp = dp or self.dp
        if self.cold is not None and not self.cold.get("done") and brew.cold_progress(self.cold) >= 1:
            self.finish_cold()
        if drink == "cold_drip" and self.cold is not None and not self.cold.get("done"):
            self.show_notice(T("冰滴還在滴，大約 {m} 分鐘後好", m=brew.cold_remaining_min(self.cold)))
            self.sound.once("ding_lo", 0.3)
            return False
        need = self.brew_dose(drink, dp)
        if self.bag["left"] < need:                  # 豆子不夠：自動模式、營業中從庫存自己開新包，手動就提醒
            if self.pending_bag or self.auto or self.order_mode or self.auto_buy:
                self.open_next_bag()
            if self.bag["left"] < need:              # 沒有庫存（手動模式要自己開）：沒豆子可用
                if self.business():
                    self.beans_hint()
                else:
                    self.show_notice(T("豆子用完了，右鍵「豆子」開一包新的（庫存沒有就到商店買）"))
                    self.sound.once("ding_lo", 0.4)
                return False
        if method_of(drink) != self.method:
            self.set_method(method_of(drink))
        if drink in self.drink_actions:
            self.drink_actions[drink].setChecked(True)
        self.drink = drink
        biz_order = order is not None and self.business()
        self.reset_cup(drink, to_go=bool(biz_order and order.to_go), size=order.size if biz_order else "M")
        if is_milk(drink) and self.machine.traits.milk == "frother":
            self.frother_fill = clamp(0.42 * milk_plan(drink, dp)[0] / 150, 0.08, 0.6)
        self.session = Session(self, drink, full_flow, dp)
        if order is not None:
            self.session.order = order
            order.state, order.t = "making", 0.0
        self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def brew_dose(self, drink, dp):
        """這杯要用多少豆子"""
        if drink == "pour_over":
            return dp.po_dose
        if drink == "moka_pot":
            return dp.mk_dose
        if drink == "siphon":
            return dp.sy_dose
        if drink == "cold_drip":
            return 0.0 if self.cold is not None else dp.cd_dose
        from .drinks import shot_params
        return shot_params(drink, self.params)[0].dose

    def use_beans(self, grams):
        self.bag["left"] = max(0.0, self.bag["left"] - grams)
        self.hopper = clamp(self.bag["left"] / self.bag["size"], 0.0, 1.0)

    def finish_cold(self):
        """冰滴滴完：可以做 COLD_SERVINGS 杯"""
        self.cold.update(done=True, servings=brew.COLD_SERVINGS)
        self.show_notice(T("冰滴滴完了，可以做 {n} 杯冰滴咖啡", n=brew.COLD_SERVINGS))
        self.sound.once("ding_hi", 0.4)
        self.announce(self.stats.unlock("cold_drip"))
        self.save_config()

    def finish_session(self):
        ss = self.session
        self.session = None
        if ss.cold_setup:                              # 冰滴塔架好了：開始在背景滴
            p = self.params
            self.cold = brew.new_cold_batch(ss.dp, p.roast, p.bean_age, self.bag["origin"])
            self.show_notice(T("冰滴開始了，大約 {m} 分鐘後滴完（關掉程式也會繼續滴）", m=int(brew.COLD_DUR // 60)))
            self.idle_since = time.perf_counter()
            self.save_config()
            return
        if ss.family in STATION_FAMILIES:
            self.last_brew_res = ss.brew_res
        if is_milk(ss.drink):
            self.maint["wand"] += 1
        r = ss.result                                  # 手藝：咖啡師稱號越低，85 分以上的部分打越多折
        rank = growth.rank_of(self.stats.data["total"])
        capped = growth.skill_score(r.score, rank)
        if capped < r.score - 0.05:
            ss.result = type(r)(r.drink, capped, T("{comment} · {rank}手感（實力 {raw:.0f} 分）", comment=r.comment,
                                                     rank=T(growth.rank_name(rank)), raw=r.score), r.milk, r.title)
        pen, notes = maintenance.penalty(self.maint, is_milk(ss.drink))
        if pen > 0:                                    # 太久沒清潔：扣分並在評語提醒
            r = ss.result
            words = [T(maintenance.task_name(n, self.machine.traits)) for n in notes]
            ss.result = type(r)(r.drink, max(0.0, r.score - pen),
                                T("{comment} · 該{task}了", comment=r.comment, task=T("、").join(words)), r.milk, r.title)
        shown = self.result                            # 營業模式：狀態列先維持上一位客人的結果
        self.result = ss.result
        self.last_drink = ss.drink
        self.last_cocoa = ss.cocoa
        later = False
        if ss.order is not None and self.machine.traits.groups == 1 and any(isinstance(st, Together) for st in ss.stages):
            self.announce(self.stats.unlock("together"))   # 職人：單頭機萃取的同時打奶
        if ss.order is not None:
            o = ss.order
            orders.finish(o, ss, ss.result)
            r = ss.result
            self.result = type(r)(r.drink, o.score, T("{name}：{text}", name=T(o.name), text=o.reaction), r.milk, o.title)
            if self.business():                        # 營業模式：整張單到櫃檯結帳完才公布分數、寫進紀錄（reveal_party）
                later = True
                o.revealed, o.result, o.rec = False, self.result, self.cup_record(ss)
                self.result = shown
                self.take_cup(o)                       # 整張單都好了就帶到櫃檯交付（咖啡師要等）；還沒好的放出餐架
        self.last_dp = ss.dp
        self.last_milk = ss.milk
        if ss.milk is not None:
            t = self.topping
            self.last_art = (ss.milk.art, 1.0, ss.milk.art_q, ss.art_seed, dict(t))
            self.art_show_until = time.perf_counter() + 6
            self.frother_fill = 0.04 if self.machine.traits.milk == "frother" else self.frother_fill
        self.idle_since = time.perf_counter()
        if not later:
            self.sound.once("ding_hi" if self.result.score >= 80 else "ding_lo", 0.55)
            self.record_cup(ss)
        if ss.family == "colddrip" and self.cold is not None:
            self.cold["servings"] -= 1
            if self.cold["servings"] <= 0:              # 這壺倒完：收起冰滴塔
                self.cold = None
        self.save_config()

    def record_cup(self, ss):
        """寫進每日紀錄與收集冊，檢查成就"""
        self.save_cup(self.cup_record(ss))

    def cup_record(self, ss):
        """這一杯要寫進紀錄的內容（營業模式先存在訂單上，結帳後才 save_cup）"""
        r, m, sh = self.result, ss.milk, self.shot
        cup = {"drink": ss.drink, "title": r.title or ss.drink, "score": r.score, "comment": r.comment,
               "machine": self.machine.key if ss.family not in STATION_FAMILIES else None, "milk": ss.dp.milk_kind if (m is not None or ss.drink == "iced_latte") else None,
               "origin": self.bag["origin"], "bean_age": sh.p.bean_age if sh else 0, "dose": sh.p.dose if sh else 0,
               "festival": DRINKS[ss.drink].get("festival")}
        if ss.family == "pourover":
            cup.update(bean_age=self.params.bean_age, dose=ss.dp.po_dose, bloom_ok=brew.bloom_ok(ss.dp))
        elif ss.family in ("moka", "siphon"):
            cup.update(bean_age=self.params.bean_age, dose=self.brew_dose(ss.drink, ss.dp))
        elif ss.family == "colddrip" and self.cold is not None:
            cup.update(bean_age=self.cold["bean_age"], dose=self.cold["dose"] / brew.COLD_SERVINGS,
                       origin=self.cold["origin"])
        if m is not None:
            cup.update(art=m.art, art_q=m.art_q, seed=ss.art_seed, art_note=m.art_note)
        if ss.order is not None:
            o = ss.order
            cup.update(order=True, mods=len(o.mods), match=o.match, price=o.price, tip=o.tip,
                       wait=round(o.wait, 1) if o.patience > 0 else None, to_go=o.to_go, size=o.size,
                       inspector=o.inspector, customer=o.name)
        return cup

    def save_cup(self, cup):
        new = self.stats.record(cup, [k for k in DRINKS if k not in FESTIVAL_DRINKS])
        self.announce(new)
        self.stats.save()
        self.check_growth()

    def announce(self, keys):
        names = {k: n for k, n, _ in ACHIEVEMENTS}
        now = time.perf_counter()
        for i, k in enumerate(keys):
            start = max(now, self.toasts[-1][2] if self.toasts else now) + (0.6 if i or self.toasts else 0.8)
            name = T(names[k])
            if k in TIER_OF:                         # 分級成就：前面加上銅／銀／金獎牌
                name = f"{TIER_ICONS[tier_rank(k)]} {name}"
            self.toasts.append((T("成就解鎖：{name}", name=name), start, start + 4.0, "trophy"))
        if keys:
            self.sound.once("ding_hi", 0.45)
            self.set_frame_interval(FRAME_AMBIENT)

    def show_notice(self, text, sec=5.0):
        self.notice = (text, time.perf_counter() + sec)
        self.set_frame_interval(FRAME_AMBIENT)

    def toast(self, text, sec=6.0, kind="info"):
        """暫時取代狀態列的通知（沖煮中也看得到），排在已有的通知後面。
        kind：trophy＝金框加小獎盃（成就、店鋪升級、咖啡師晉升）；info＝一般通知（重新遊玩、購買、休息提醒、新版本）"""
        now = time.perf_counter()
        start = max(now, self.toasts[-1][2] + 0.6) if self.toasts else now
        self.toasts.append((text, start, start + sec, kind))
        self.set_frame_interval(FRAME_AMBIENT)

    def tray_message(self, text, ms=6000):
        if self.tray:
            self.tray.showMessage("Café Desk", text, self.icon, ms)

    # ───────────── 休息提醒 ─────────────
    BREAK_PRESETS = (0, 25, 45, 60)

    def custom_break(self):
        """休息提醒「自訂…」：問幾分鐘；取消時維持原本的設定"""
        minutes = self.ask_break_minutes()
        if minutes:
            self.set_break(minutes)
        self.build_menu()                                # 選單的勾選與「自訂（每 n 分鐘）」文字跟著更新

    def ask_break_minutes(self):
        """跳出輸入框（5–240 分鐘）；取消回傳 None（測試會換掉這個函式）"""
        dlg = QInputDialog()
        theme.apply_dialog(dlg)
        dlg.setWindowTitle(T("休息提醒"))
        dlg.setLabelText(T("每幾分鐘提醒一次？（5–240）"))
        dlg.setInputMode(QInputDialog.IntInput)
        dlg.setIntRange(5, 240)
        dlg.setIntStep(5)
        dlg.setIntValue(self.break_min or 30)
        dlg.setOkButtonText(T("確定"))
        dlg.setCancelButtonText(T("取消"))
        return dlg.intValue() if dlg.exec() else None

    def play_speed(self):
        """播放速度只對手動、自動有效；營業中固定 1 倍"""
        return 1.0 if self.business() else self.speed

    def set_break(self, minutes):
        self.break_min = minutes
        self.break_t = 0.0
        self.save_config()

    def reset_break(self):
        self.break_t = 0.0

    def update_break_menu(self):
        a = self.act_break_reset
        if self.break_min:
            left = max(1, math.ceil(self.break_min - self.break_t / 60))
            a.setText(T("重新計時（還有 {m} 分鐘）", m=left))
        else:
            a.setText(T("重新計時"))
        a.setEnabled(bool(self.break_min))

    def update_break(self, dt):
        """真實時間累計（dt 每個 tick 最多 0.5 秒，所以電腦睡眠的時間不算）；時間到就提醒，咖啡師順便做一杯"""
        if not self.break_min:
            return
        self.break_t += dt
        if self.break_t < self.break_min * 60:
            return
        self.break_t = 0.0
        text = T("休息一下：起來走走、喝杯咖啡吧（已經 {m} 分鐘了）", m=self.break_min)
        self.toast(text, 8.0)
        self.tray_message(text)
        self.sound.once("ding_hi", 0.5)
        drink = self.auto_drink()                    # 冰滴還在滴就只提醒、不做
        if drink and not self.busy() and not self.order_mode:
            self.start_session(drink, True)

    # ───────────── 檢查更新 ─────────────
    def set_update_check(self, v):
        self.update_check = v
        if not v and self.update_info:               # 關掉就不再顯示「下載新版」
            self.update_info = None
            self.build_menu()
        self.save_config()

    def check_update(self, manual=False):
        if update.disabled() or (self.update_job is not None and self.update_job.result is None):
            return
        self.update_job = update.Checker(manual)
        self._update_at = time.perf_counter() + UPDATE_RETRY
        if manual:
            self.show_notice(T("檢查新版本中…"), 3.0)

    def poll_update(self, now):
        """主執行緒取走背景查詢的結果；每天自動查一次（失敗的話一小時後再試）"""
        job = self.update_job
        if job is None:
            today = datetime.date.today().isoformat()
            if self.update_check and now >= self._update_at and self.cfg.get("update_checked") != today:
                self.check_update()
            return
        res = job.result
        if res is None:
            return
        self.update_job = None
        if res["error"]:
            if job.manual:
                self.show_notice(T("無法檢查更新（請確認網路連線）"))
            return
        self.cfg["update_checked"] = datetime.date.today().isoformat()
        self.cfg["update_latest"] = res["tag"]
        if res["newer"]:
            first = res["tag"] != self.cfg.get("update_seen")
            self.update_info = res
            self.cfg["update_seen"] = res["tag"]
            self.build_menu()
            if first or job.manual:                  # 同一版只主動提醒一次，之後留在右鍵選單最上面
                text = T("有新版本 {tag}：右鍵選單最上面「下載新版」", tag=res["tag"])
                self.toast(text, 8.0)
                self.tray_message(text)
        else:
            if self.update_info:
                self.update_info = None
                self.build_menu()
            if job.manual:
                self.show_notice(T("已經是最新版本（{v}）", v=update.__version__))
        self.save_config()

    def open_update_page(self):
        QDesktopServices.openUrl(QUrl(self.update_info["url"] if self.update_info else update.RELEASES_URL))

    # ───────────── 豆子 ─────────────
    def sync_bag(self):
        """沖煮參數的烘焙度、產地、養豆天數跟著目前這包豆子（養豆天數依真實日期）"""
        b = self.bag
        self.params.roast = beans.bag_roast(b)
        self.params.origin = b["origin"]
        self.params.bean_age = float(beans.bag_age(b))
        self.hopper = clamp(b["left"] / b["size"], 0.0, 1.0)

    def request_bag(self, origin):
        """換一包庫存的豆子（origin 是 None＝從庫存隨機挑）：咖啡師沒在忙就馬上開；正在做飲品就等這杯做完再換（營業中也能換）。
        庫存沒有時不行；回傳是否接受"""
        if origin is None:
            have = [k for k in beans.ORIGINS if self.bean_stock(k) > 0 or k in self.shelf]
            origin = random.choice(have) if have else None
        if origin is None or (self.bean_stock(origin) <= 0 and origin not in self.shelf):
            self.toast(T("庫存沒有這種豆子，到商店買"), 4.0)
            return False
        if not self.busy():
            return self.open_bag(origin)
        self.pending_bag = origin
        name = T(beans.ORIGINS[origin][0])
        # 沖煮中狀態列顯示步驟，一般提示看不到：用通知（一般樣式）
        self.toast(T("這杯做完換上{name}", name=name), 4.0)
        self.save_config()
        return True

    def take_pending_bag(self):
        origin, self.pending_bag = self.pending_bag, None
        return origin

    def stash_bag(self, nxt):
        """換成 nxt 這種豆子前，現在這包還有剩的收進 self.shelf（不浪費；太少、不夠做一杯的就用掉不留；同一種開新包時舊的剩的不留）"""
        b = self.bag
        if b["origin"] != nxt and b["left"] >= beans.MIN_LEFT:
            self.shelf[b["origin"]] = b

    def open_bag(self, origin):
        """開一包庫存的豆子（origin 是 None＝從庫存隨機挑一種）；沒有庫存回傳 False，不會有免費的豆子"""
        if self.busy() and origin is not None:
            return False
        if origin is None:
            part = [k for k, b in self.shelf.items() if b["left"] >= beans.MIN_LEFT]
            if part and not self.bean_stock():
                origin = random.choice(part)         # 庫存沒有了：先把開過還有剩的倒回來用
            else:
                if not self.bean_stock():
                    self.auto_buy_bag()              # 庫存沒有：自動購買勾選的豆子
                have = [k for k in beans.ORIGINS if self.bean_stock(k) > 0]
                origin = random.choice(have) if have else (random.choice(part) if part else None)
        if origin is not None and origin in self.shelf and origin != self.bag["origin"]:
            self.stash_bag(origin)                   # 這種豆子開過還有剩：換下現在這包（剩的收起來），把剩下的倒回磨豆機，不用再開新包
            self.bag = self.shelf.pop(origin)
            self.sync_bag()
            if self.business():
                self.barista.shake_up(self.params)
            self.sound.once("tap", 0.4)
            self.show_notice(T("換回已開的豆子：{name}（剩 {g:.0f} g）", name=T(beans.bag_name(self.bag)), g=self.bag["left"]))
            if self.settings_dlg is not None:
                self.settings_dlg.sync_bean()
            self.save_config()
            return True
        if origin is None or not self.stats.record_bean_use(origin):
            return False
        self.stash_bag(origin)
        self.bag = beans.new_bag(origin)
        self.sync_bag()
        if self.business():                          # 營業中的咖啡師換了豆子會重新找參數；自動模式照使用者的設定
            self.barista.shake_up(self.params)
        self.sound.once("tap", 0.4)
        self.show_notice(T("開了一包新豆子：{name}（{roast}，{flavor}）", name=T(beans.bag_name(self.bag)),
                           roast=T(beans.bag_roast(self.bag)), flavor=T(beans.bag_flavor(self.bag))))
        if self.settings_dlg is not None:
            self.settings_dlg.sync_bean()
        self.announce(self.stats.record_bag(self.bag["origin"]))
        self.restock_beans()                         # 自動購買：開走一包，馬上補一包庫存
        self.save_config()
        return True

    # ───────────── 清潔保養 ─────────────
    def start_job(self, kind):
        if self.busy() or self.method != "espresso":      # 手沖／冰滴畫面看不到咖啡機
            return False
        self.job = maintenance.Job(kind)
        if kind == "wand":
            if self.machine.traits.milk == "wand":
                self.purge_wand()
                self.sound.once("hiss", 0.45)
            else:
                self.frother_fill = 0.0
                self.sound.once("click", 0.4)
        elif kind == "drip":
            self.sound.once("tap", 0.4)
        elif kind == "knock":
            self.sound.once("knock", 0.5)
        elif kind == "backflush":
            # 逆洗要換盲碗、先拿走杯子：畫面淡出杯子（連同上一杯），洗完再放回空杯
            self.begin_fade()
            shot, result = self.shot, self.result
            self.reset_cup(self.drink)
            self.shot, self.result = shot, result
            self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def finish_job(self):
        kind = self.job.kind
        if kind == "backflush":
            self.begin_fade()                            # 空杯淡入
        self.job = None
        self.maint[kind] = 0.0
        if kind == "wand" and self.machine.traits.milk == "frother":
            self.frother_fill = 0.42
        self.sound.once("ding_hi", 0.3)
        self.idle_since = time.perf_counter()
        self.announce(self.stats.record_clean(kind))
        self.stats.save()
        self.save_config()

    def cupless(self):
        """逆洗中杯子拿走了，或營業中這杯送去收銀台了（背景與前景圖層不畫杯子）；只管第一杯，第二杯看 twin_live()"""
        return self.backflushing() or self.cup_away

    def backflushing(self):
        return self.job is not None and self.job.kind == "backflush"

    def job_status(self):
        j = self.job
        if j.kind == "backflush":
            return T("逆洗沖煮頭（第 {n}/5 次）…", n=j.cycle)
        if j.kind == "wand":
            return T("清洗奶泡機…") if self.machine.traits.milk == "frother" else T("清潔蒸氣管…")
        return T(maintenance.TASKS[j.kind][3])

    def auto_drink(self):
        """自動模式：照設定重複做目前選的飲品（參數不變）；冰滴還在滴就先等，回傳 None"""
        if self.drink == "cold_drip" and self.cold is not None and not self.cold.get("done"):
            return None
        return self.drink

    def manual_brew(self):
        """手動沖煮：一律跑完整流程（義式從取把手、敲渣、磨豆開始；手沖、冰滴本來就從磨豆開始）"""
        if self.busy():
            return
        if self.order_mode:
            self.make_order()
            return
        self.start_session(self.drink, True)

    def make_order(self):
        """點單模式：照目前的訂單做（還沒有訂單就叫下一位客人）"""
        o = self.order
        if o is None or o.state in ("done", "leaving"):
            if self.queue:
                self.next_customer()
            else:
                self.new_order()
            o = self.order
        if o is None:
            self.show_notice(T("冰滴還在滴，大約 {m} 分鐘後好", m=brew.cold_remaining_min(self.cold))
                             if self.cold else T("現在沒有可以點的飲品"))
            return
        if o.state != "waiting":
            return
        machine, method = self.machine.key, self.method
        if method_of(o.drink) == "espresso":
            self.set_machine(self.business_machine())
        self.set_method(method_of(o.drink))
        if (self.machine.key, self.method) != (machine, method):
            self._switch_wait = [o, FADE_T + SWITCH_PAUSE]     # 換了畫面：漸變完、再停一下才開始做（update_order 倒數）
            return
        self.start_order(o)

    def start_order(self, o):
        dp = orders.order_params(o, self.dp, skill=self.skill(o.drink))
        if method_of(o.drink) != "espresso":
            dp = brew.barista_dial(dp, self.params.roast, skill=self.skill(o.drink))     # 咖啡師依烘焙度調手沖／冰滴
        q = self.duo_partner(o)
        if q is not None:
            dq = orders.order_params(q, self.dp, skill=self.skill(q.drink))
            if pair_compat(o.drink, dp, q.drink, dq, self.machine.traits.dual_wand) and self.start_pair(o, dp, q, dq):
                return
        self.start_session(o.drink, True, dp, order=o)        # 營業中也跑完整備粉

    def duo_partner(self, o):
        """營業中、目前是雙頭機：排隊裡第一位可以跟 o 一起做的客人（任何義式飲品都行，見 drinks.pair_compat）"""
        if not self.business() or self.twin is None:
            return None
        return next((q for q in self.queue if q.state == "waiting" and self.orders_pair(o, q)), None)

    def orders_pair(self, o, q):
        """兩張訂單能不能一起做：兩杯都要打奶時，有「雙打奶泡」（第二支蒸氣管）就各打各的、什麼奶都行；
        沒有就要共用一壺（同一種奶；客人點的卡布奇諾預設撒可可粉，要說「不要可可粉」才共用）"""
        def shared(x):
            return pair_kind(x.drink) == "milk" and not (x.drink == "cappuccino" and x.has("cocoa") != "no")
        if method_of(o.drink) != "espresso" or method_of(q.drink) != "espresso":
            return False
        if base_of(o.drink) == "milk" and base_of(q.drink) == "milk":
            if self.machine.traits.dual_wand:
                return True
            return shared(o) and shared(q) and o.has("milk") == q.has("milk")
        return True

    def start_pair(self, o, dp, q, dq):
        """雙頭機成對做兩杯：o 在左邊沖煮頭（self.session），q 在右邊（self.twin）；豆子不夠兩杯時回傳 False"""
        if self.busy() or self.twin is None:
            return False
        self.sync_bag()
        need = shot_params(o.drink, self.params)[0].dose + shot_params(q.drink, self.params)[0].dose
        if self.bag["left"] < need:                      # 營業中：從庫存自己開新包
            self.open_next_bag()
            if self.bag["left"] < need:
                return False
        if o.drink in self.drink_actions:
            self.drink_actions[o.drink].setChecked(True)
        self.drink = o.drink
        self.reset_cup(o.drink, o.to_go, o.size)         # 也換一份新的 twin
        with self.on_twin():
            self.reset_cup(q.drink, q.to_go, q.size)
            cup = self.cup
            m = self.machine
            handoff = (m.mx + cup.TR + 24, m.my + cup.T - 76)    # 拉花杯倒完第一杯後停在第二杯右上方
            gb = milk_plan(q.drink, dq)[0] if pair_kind(q.drink, dq) == "milk" else 0.0
        ga = milk_plan(o.drink, dp)[0] if pair_kind(o.drink, dp) == "milk" else 0.0
        shared = pair_shared_milk(o.drink, dp, q.drink, dq) and not self.machine.traits.dual_wand   # 兩杯都是熱牛奶：一壺兩杯份（有第二支蒸氣管就各打各的）；否則各自做自己的
        a = Session(self, o.drink, True, dp, pair=("a", gb if shared else None, handoff))
        a.tag, a.order = "①", o
        self.session = a
        with self.on_twin():
            b = Session(self, q.drink, True, dq, pair=("b", handoff if shared else None, ga), start=False)
            b.tag, b.order = "②", q
            self.session = b
        for x in (o, q):
            x.state, x.t = "making", 0.0
        self.pair = Pair(a, b)
        self.sound.once("click", 0.4)
        self.set_frame_interval(FRAME_ACTIVE)
        return True

    def new_order(self):
        """來一位客人：營業模式下前面還有人就去排隊。營業模式一位客人可能點 1–3 杯（同一張單：每杯一張 Order，
        共用 party list、名字、內用／外帶與耐心，全部做好才一起交付）"""
        biz = self.business()
        n = orders.party_size() if biz else 1
        party = []
        dessert = self.pick_dessert() if biz else None      # 櫥窗有甜點：比較多人內用，加購甜點的幾乎都內用
        to_go_p = (ingredients.DESSERT_BUYER_TO_GO_P if dessert else ingredients.DESSERT_TO_GO_P if self.dessert_stock()
                   else orders.TO_GO_P)
        to_go = random.random() < to_go_p if biz else False
        if biz and not to_go and self.free_seats() < n:  # 想內用但空位不夠：只好外帶
            to_go = True
        day = festivals.today().isoformat()
        if day != self.order_day:                        # 換日：點單紙的杯數從 1 重算
            self.order_no, self.order_day = 0, day
        inspect = (biz and n == 1 and self.shop_level() >= growth.MAX_LEVEL
                   and not any(x.inspector for x in [self.order] + self.queue if x is not None)
                   and random.random() < growth.INSPECTOR_P)
        for _ in range(n):
            self.order_no += 1
            if biz and not party:                        # 營業模式：熟客常回來，還會點「老樣子」
                custs = self.stats.data["customers"]
                who = regulars.pick_name(random, custs, orders.CUSTOMERS, self._last_customer)
                lvl = regulars.level_of(custs.get(who))
                fav = regulars.favorite(custs.get(who)) if lvl else None
            elif party:
                who, lvl, fav = party[0].name, party[0].regular, None
            else:
                who, lvl, fav = None, 0, None
            if biz:
                self.restock_ingredients()               # 自動補貨：食材沒了先買（買得起的話）
            o = orders.make_order(self.order_no, last_name=self._last_customer, exclude=self.order_exclude(),
                                  name=who, favorite=fav, bean_p=orders.BEAN_ASK_P if biz and not party else 0.0,
                                  bean_pool=self.bean_choices(), avail=self.ing_avail if biz else None)
            if o is not None:
                o.regular = lvl
            if o is None:                                # 這個沖煮方式現在沒有可以點的（冰滴還在滴）
                self.order_no -= 1
                break
            if party:
                o.name = party[0].name
            if inspect:
                o.name, o.inspector = "評鑑員", True
            if biz:
                self.use_ingredients(o)                  # 這杯要用的食材從庫存扣掉
            if beans.is_premium(self.bag) or o.has("bean"):   # 精品豆（或客人指定精品豆）：這杯比較貴
                o.price = int(round(o.price * beans.PREMIUM_PRICE_K))
            if biz:
                o.patience = orders.patience(method=method_of(o.drink), level=self.shop_level()) * regulars.patience_k(o.regular)   # 手沖久、名店，客人比較願意等
                o.to_go = to_go
                o.size = orders.pick_size(o.drink)       # 大中小杯
                o.paid = False                           # 咖啡師接單時在 POS 結帳
                o.price += orders.SIZE_PRICE[o.size]
                if dessert and not party:                # 甜點加在這張單的第一杯
                    self.add_dessert(o, dessert)
            if biz and self.order is not None and self.order.state in ("waiting", "making"):
                self.queue.append(o)
            else:
                self.order = o
            party.append(o)
        if not party:
            self.next_order_at = time.perf_counter() + 6.0
            return
        self._last_customer = party[0].name
        if party[0].inspector:
            self.toast(T("評鑑員上門了！這杯的分數在星級評鑑裡算兩倍"), 6.0)
        if len(party) > 1:                               # 點好幾杯：耐心依杯數加長，大家一起等
            patience = max(o.patience for o in party) * (1 + orders.PARTY_PATIENCE * (len(party) - 1))
            for o in party:
                o.party, o.patience = party, patience
        self.sound.once("ding_hi", 0.25)
        self.set_frame_interval(FRAME_AMBIENT)

    def seats(self):
        return growth.seats(self.shop_level())

    def dine_reserved(self):
        """還沒交付的內用杯數（點了、在做、在出餐架、等著或正在櫃檯交付）：先保留座位"""
        live = [x for x in [self.order] + self.queue if x is not None and x.state in ("waiting", "making")]
        live += [c["order"] for c in self.ready]
        for d in self.pending_deliveries + (self.delivery["parties"][self.delivery["i"]:] if self.delivery else []):
            live += d["orders"]
        seen = []
        for x in live:
            if not x.to_go and all(x is not y for y in seen):
                seen.append(x)
        return len(seen)

    def free_seats(self):
        return self.seats() - len(self.seated) - self.dine_reserved()

    def people(self):
        """營業模式：店裡在等或正在做的客人數（點好幾杯的算一位）"""
        seen = set()
        for x in [self.order] + self.queue:
            if x is not None and x.state in ("waiting", "making"):
                seen.add(id(x.party) if x.party else id(x))
        return len(seen)

    def order_exclude(self):
        """現在不能點的飲品：冰滴沒有滴好，或剩下的都被前面的客人點走了
        （其他飲品不分沖煮方式都能點，做的時候 start_session 會自動切過去）"""
        pending = [x for x in [self.order] + self.queue if x is not None and x.state in ("waiting", "making")]
        ready = self.cold["servings"] if (self.cold and self.cold.get("done")) else 0
        left = ready - sum(1 for x in pending if x.drink == "cold_drip")
        locked = tuple(k for k in DRINKS if not self.drink_open(k))   # 還沒解鎖的飲品（稱號）與沖煮方式（店鋪等級）
        no_stock = tuple(k for k in DRINKS if k not in locked and not self.ing_avail(k)) if self.business() else ()   # 食材用完了的
        return locked + no_stock + (() if left > 0 else ("cold_drip",))

    def same_party_next(self, o):
        """o 是同一張單、前面的杯子已經做好的下一杯：咖啡師直接接著做，不停下來"""
        return bool(o.party) and any(x is not o and x.state in ("done", "leaving") for x in o.party)

    def next_customer(self):
        """排隊的下一位走到櫃台"""
        self.order = self.queue.pop(0)
        self.order.t = 0.0

    def update_queue(self, sdt):
        """營業模式：等待中的客人累計等待時間，耐心用完就離開；依間隔來新客人（排滿就不來）"""
        o = self.order
        waiting = ([o] if o is not None and o.state == "waiting" else []) + [
            q for q in self.queue if q.state == "waiting"]          # 雙頭機一起做的第二位已經在做了，不會走
        for w in waiting:
            w.wait += sdt
            if w.patience > 0 and w.wait >= w.patience and not w.paid:   # 沒設耐心（0）的、已經付錢的不會走
                self.walk_out(w)
        self.seated = [t - sdt for t in self.seated if t > sdt]      # 內用客人喝完離座
        self.arrive_in -= sdt
        if self.arrive_in <= 0:
            lv = self.shop_level()
            self.arrive_in = orders.arrival_gap(level=lv) * orders.PARTY_GAP    # 一位客人平均點 1.3 杯、交付要等：來客少一點
            if self.machine_open("duo"):             # 雙頭機解鎖：出杯快，客人也更多（成對做兩杯才常出現）
                self.arrive_in *= growth.DUO_ARRIVAL_K
            present = self.people()
            if present < growth.queue_max(lv, orders.QUEUE_MAX):        # 店鋪等級高，排隊上限多 1–2 位
                self.new_order()
        o = self.order
        present = self.people()
        if present >= orders.QUEUE_MAX:
            self.rush = True                         # 尖峰：排滿了；之後沒人離開、隊伍清空就解鎖成就
        elif present == 0 and self.rush:
            self.rush = False
            self.announce(self.stats.unlock("rush"))

    def walk_out(self, o):
        """等太久離開：點好幾杯的客人，還沒開始做的那幾杯一起取消（已經在做或做好的照樣交付）"""
        gone = [x for x in (o.party or [o]) if x.state == "waiting"] or [o]
        for x in gone:
            if x is self.order:
                x.state, x.t = "leaving", 0.0
            else:
                self.queue = [q for q in self.queue if q is not x]
        if o.party:
            o.party[:] = [x for x in o.party if all(x is not g for g in gone)]
            if o.party:
                self.check_party(o.party)            # 剩下的杯子都做好了：一起交付
        self.rush = False
        # 用通知不用狀態列提示：營業中咖啡師九成時間在做飲品，狀態列被製作進度蓋住，客人走了都看不到
        self.toast(T("{name} 等太久，先走了", name=T(o.name)), 4.0)
        self.sound.once("ding_lo", 0.3)
        for x in gone:
            self.refund_order(x)
            self.announce(self.stats.record_walkout(x.drink))

    def start_brew(self, params=None, style=None, preset=False):
        if self.brewing():
            return
        self.shot = Shot((params or self.params).copy(), self.machine.traits, style)
        self.shot.preset = preset
        self.bag["left"] = max(0.0, self.bag["left"] - self.shot.p.dose)     # 用掉這杯的豆子
        self.hopper = clamp(self.bag["left"] / self.bag["size"], 0.0, 1.0)
        self.maint["backflush"] += 1
        self.maint["drip"] += maintenance.DRIP_PER_SHOT
        self.stream = [{"head": 0.0, "tail": 0.0} for _ in self.machine.spouts]
        self.drops.clear()
        self.splash.clear()
        self.ripples.clear()
        self.bubbles.clear()
        self.crema_h = self.film_h = 0.0
        self._log_clock = 0.0
        self.pf_used = True
        self.sound.once("click", 0.5)
        self.set_frame_interval(FRAME_ACTIVE)

    def barista_dial_in(self):
        self.barista.skill = self.skill(self.drink)
        self.barista.dial_in(self.params, self.shot)

    # ───────────── 主迴圈 ─────────────
    def tick(self):
        ms = self.clock.elapsed()
        dt = min(0.5, (ms - self.last_ms) / 1000.0)
        dt_real = dt
        self.last_ms = ms
        self.anim_t += dt
        while dt > 1e-6:                     # 切成小步推進，幀率高低都得到同樣的模擬結果
            step = min(SIM_STEP, dt)
            self.step(step, step * self.play_speed())
            dt -= step

        with self.on_focus():                    # 成對做兩杯、正在做第二杯：聽第二杯的
            self.tick_sounds()
        self.sound.ambience(self.ambience, self.amb_level)
        self.music.update(self.sound.enabled and self.sound.user_on)
        self.update_break(dt_real)
        self.update_clock()                          # 翻頁鐘：數字變了就開始翻
        if ms - self._last_tip_ms > 500:
            self._last_tip_ms = ms
            self.update_tray_tip()
            self.update_light()
            self.poll_update(time.perf_counter())
        if self.isVisible():
            self.update()
        self.set_frame_interval(self.wanted_interval())

    def tick_sounds(self):
        """跟著目前這杯的循環音效：幫浦、磨豆、蒸氣、水聲、爐火…"""
        s = self.shot
        if (s and s.phase == "brew") or (self.job and self.job.pumping):
            self.sound.loop("pump", 0.10 + 0.45 * clamp(self.gauge / 9, 0, 1.2))
        else:
            self.sound.loop("pump", 0.0)
        stream_vis = any(st["head"] > 0 and st["tail"] < 0.9 for st in self.stream)
        pour_vol = clamp(self.last_flow / 2.4, 0, 1) * 0.4 if stream_vis else 0.0
        ss = self.session
        station_phase = getattr(ss.stage, "phase", "") if (ss and ss.family in STATION_FAMILIES) else ""
        st_ = ss.station if station_phase else None    # 冰滴倒杯（加冰、倒冰滴壺）沒有沖煮台狀態：是 None
        grinding = (self.workflow and self.workflow.grinding) or bool(st_ and st_.get("grinding"))
        self.sound.loop("grinder", 0.45 if grinding else 0.0)
        steaming = bool(ss and ss.stage_name == "steam" and self.machine.traits.milk == "wand"
                        and getattr(ss.stage, "phase", "") == "run")
        self.sound.loop("steam", 0.35 if steaming else 0.0)
        self.sound.loop("chirp", 0.3 if (steaming and ss.stretching) else 0.0)
        self.sound.loop("frother", 0.4 if (ss and ss.frother_on) else 0.0)
        vessel_pour = bool(ss and any(v and v.get("pour", 0) > 0 for v in (ss.vessel, ss.jigger)))
        if vessel_pour:
            pour_vol = max(pour_vol, 0.3)
        if station_phase in ("bloom_pour", "pulse") and ss.station["kettle"]["pour"] > 0:
            pour_vol = max(pour_vol, 0.16)             # 細口壺：細細的水聲
        elif station_phase == "water":
            pour_vol = max(pour_vol, 0.3)              # 冰滴塔加冰水
        self.sound.loop("pour", pour_vol)
        # 摩卡壺：爐火、咕嚕聲；虹吸壺：下壺沸騰、咖啡被吸下去（st_ 在上面取過）
        fam = ss.family if st_ else ""
        self.sound.loop("flame", 0.3 * st_["flame"] if fam == "moka" else 0.0)
        gurgle = 0.0
        if fam == "moka" and station_phase in ("brew", "sputter"):
            gurgle = 0.22 + 0.35 * st_["sputter"]
        elif fam == "siphon" and station_phase == "drawdown":
            gurgle = 0.18
        self.sound.loop("gurgle", gurgle)
        self.sound.loop("boil", 0.1 + 0.3 * st_["boil"] if fam == "siphon" and st_["boil"] > 0.02 else 0.0)

    def step(self, dt, sdt):
        """推進一個模擬子步：dt 是真實時間，sdt 是乘上播放速度後的沖煮時間"""
        now = time.perf_counter()
        queue_sdt = sdt                          # 客人來店與耐心照原本的時間走
        if self.business():                      # 店鋪等級高：出杯比較快（growth.work_k）
            sdt *= growth.work_k(self.shop_level())
        if self.cold is not None and not self.cold.get("done") and brew.cold_progress(self.cold) >= 1:
            self.finish_cold()
        if self.method != "espresso":
            self.update_zoom(dt)
        if self.pending_deliveries and self.delivery is None and not self.making():
            self.start_delivery()                    # 做完了：帶到櫃檯交付
        if self.checkout is not None:
            self.update_checkout(sdt)
        if self.delivery is not None or self.reg_floats:
            self.update_delivery(sdt)
        if self.delivery is None:
            self.set_counter_view(self.idle_counter())   # 營業中沒客人等著做：退回櫃檯；開始做或打烊：切回咖啡機（畫面鎖定時不動）
        if self.pending_bag and not self.busy() and self.bean_stock(self.pending_bag):   # 這杯做完了：換上排好的那包豆子（庫存有才換）
            self.open_bag(self.take_pending_bag())
        if self._restore_biz and not self.order_mode and not self.busy():
            self.restore_after_business()
        self.update_day(now)

        self.step_prep(sdt, now)
        if self.twin_live():                     # 雙頭機的第二杯
            with self.on_twin():
                self.step_prep(sdt, now)

        # 飲品流程
        if self.pair is not None:
            self.update_pair(sdt)
        else:
            self.run_session(sdt)
        if self.job:
            self.job.update(sdt)
            if self.job.done:
                self.finish_job()
        idle_ok = now - self.idle_since >= min(self.interval, 8.0)
        if self.method == "espresso" and not self.busy() and (self.order_mode or (self.auto and idle_ok)):
            todo = maintenance.due(self.maint)
            if todo:                                     # 自動模式閒下來先清；營業中做完一杯、接下一張單前先清
                self.start_job(todo[0])
        if not self.order_mode and self.order is not None and self.order.state != "making":
            self.order, self.order_alpha = None, 0.0     # 離開營業：做完（或還沒做）的那張單收掉，點單紙不留在畫面上
        if self.order_mode:
            self.update_order(dt, now, queue_sdt)
        elif self.auto and not self.busy() and now - self.idle_since >= self.interval:
            drink = self.auto_drink()
            if drink is None:                            # 冰滴還在滴：等滴完
                self.idle_since = now
            else:
                self.start_session(drink, True)          # 照設定再做一杯（跑完整流程）
        s = self.shot

        # 鍋爐水溫（雙頭機兩杯一起萃取時兩邊的流量都算）
        flow = s.flow if (s and s.phase in ("brew", "tail")) else 0.0
        if self.twin_live():
            s2 = self.twin["shot"]
            flow += s2.flow if (s2 and s2.phase in ("brew", "tail")) else 0.0
        if self.params.temp - self._last_set > 3:          # 設定水溫大幅調高：重新預熱
            self.warming = True
        self._last_set = self.params.temp
        if self.warming and self.boiler.temp >= self.params.temp - 0.5:
            self.warming = False
        mode = self.session.boiler_mode if self.session else self.idle_boiler_mode()
        setpoint = self.machine.traits.steam_temp if mode == "steam" else self.params.temp
        if mode != "cool" and self.boiler.update(sdt, setpoint, flow) and self.isVisible() \
                and self.method == "espresso" and now - self._last_relay > 2:
            self._last_relay = now
            self.sound.once("relay", 0.12)

        self.step_cup(dt, sdt, True)
        if self.twin_live():
            glow = getattr(self, "steam_intensity", 0.0)
            with self.on_twin():
                self.step_cup(dt, sdt, False)
            self.steam_intensity = max(glow, self.steam_intensity)    # 杯子冒的煙：兩杯取比較濃的

        # 待機時偶爾放氣或滴水
        if not self.busy() and self.isVisible() and now >= self.next_idle_event and self.method == "espresso":
            self.idle_event()                            # 手沖／冰滴看不到咖啡機：不放氣、不滴水
            self.next_idle_event = now + random.uniform(25, 60)

        if self.twin_live():                     # 兩個沖煮頭下面都有杯子：兩杯各自一組曲線卡片與拉花卡片
            self.update_cards(dt, now)
            with self.on_twin():
                self.update_cards(dt, now)
        else:
            with self.on_focus():                # 成對做兩杯、正在做第二杯：卡片看第二杯
                self.update_cards(dt, now)

    def update_cards(self, dt, now):
        """曲線卡片、拉花卡片淡入淡出"""
        show_card = (self.chart_on and self.hover and not self._press and self.method == "espresso"
                     and now - self.hover_since > 0.35)              # 萃取曲線只在義式畫面（沖煮台的器具比較高，會疊在一起）
        self.card_alpha += ((1.0 if show_card else 0.0) - self.card_alpha) * min(1.0, dt * 8)
        show_status = self.is_windowed() or self.status_hover        # 透明擺件：滑鼠停在咖啡機上才顯示狀態列
        self.status_alpha += ((1.0 if show_status else 0.0) - self.status_alpha) * min(1.0, dt * 8)
        ss = self.session
        pouring_art = bool(ss and ss.milk is not None and (
            (ss.stage_name == "pour" and getattr(ss.stage, "art", False)) or ss.stage_name in ("whip", "cocoa", "caramel")
            or (ss.drink == "caramel_macchiato" and ss.stage_name == "brew")))
        show_art = (pouring_art or now < self.art_show_until or
                    (show_card and (self.last_art is not None or (ss and ss.milk is not None))))
        self.art_alpha += ((1.0 if show_art else 0.0) - self.art_alpha) * min(1.0, dt * 6)
        if self.counter_view:                        # 櫃檯畫面不顯示曲線卡片與拉花卡片
            self.card_alpha = self.art_alpha = 0.0

    def step_prep(self, sdt, now):
        """一杯的備粉流程與萃取（雙頭機的第二杯在 on_twin() 裡呼叫）"""
        wf = self.workflow
        if wf:
            wf.update(sdt)
            for ev in wf.events:
                self.on_workflow_event(ev)
            wf.events.clear()

        s = self.shot
        if s and s.phase != "done":
            s.update(sdt)
            self._log_clock += sdt
            if self._log_clock >= LOG_STEP or not s.log:
                self._log_clock = 0.0
                s.log.append((s.t, self.gauge, s.flow, s.weight))
            if s.phase == "done":
                self.mix_clock = now

    def run_session(self, sdt):
        """推進一杯的飲品流程，做完就收尾"""
        ss = self.session
        if ss:
            ss.update(sdt)
            for ev in ss.events:
                self.on_session_event(ev)
            ss.events.clear()
            if ss.done:
                self.finish_session()

    def update_pair(self, sdt):
        """雙頭機成對做兩杯：兩杯各自推進，走到停的地方（Session.waiting）就照 Pair 的順序放行下一段"""
        pr = self.pair
        self.run_session(sdt)
        with self.on_twin():
            self.run_session(sdt)
        a, b = pr.a, pr.b
        ready_a, ready_b = a.waiting or a.done, b.waiting or b.done
        if pr.phase == "a_pre" and ready_a:              # 第一杯備好粉：換第二杯備粉
            pr.phase = "b_pre"
            with self.on_twin():
                b.release()
        elif pr.phase == "b_pre" and ready_b:            # 兩杯都備好：一起萃取（第一杯同時打奶）
            pr.phase = "brew"
            a.release()
            with self.on_twin():
                b.release()
        elif pr.phase == "brew" and ready_a and ready_b:
            pr.phase = "a_post"
            a.release()
        if pr.phase == "a_post" and a.done:              # 第一杯倒完：拉花杯移到第二杯接著倒
            pr.phase = "b_post"
            with self.on_twin():
                b.release()
        if pr.phase == "b_post" and b.done:
            self.pair = None
            self.announce(self.stats.unlock("duo_pair"))

    def step_cup(self, dt, sdt, job):
        """一杯的壓力錶、流柱、crema、粒子、杯中效果（雙頭機的第二杯在 on_twin() 裡呼叫，job＝False）"""
        s = self.shot
        # 壓力錶：彈簧阻尼，會稍微衝過頭再回穩
        target = s.pressure_target() if s else 0.0
        if job and self.job and self.job.pumping:        # 逆洗：盲碗加壓到 9 bar 再洩掉
            target = 9.0
        if s and s.phase == "brew" and s.t > s.t_drip:
            target += random.uniform(-1, 1) * (0.05 + s.res.channeling * 0.9)
        self.gauge_v += ((target - self.gauge) * 38 - self.gauge_v * 8) * dt
        self.gauge = max(0.0, self.gauge + self.gauge_v * dt)

        # 流柱生長／收回（收尾時流速遞減，低於門檻才斷成水滴）
        on = bool(s and s.phase in ("brew", "tail") and s.flow >= 0.55)
        if s and s.flow > 0:
            self.last_flow = s.flow
        for st in self.stream:
            if on:
                st["head"] = min(1.0, st["head"] + sdt * 6)
                st["tail"] = 0.0
            elif st["head"] > 0:
                st["tail"] = min(1.0, st["tail"] + sdt * 5)
                if st["tail"] >= 1.0:
                    st["head"] = st["tail"] = 0.0

        self.update_crema(dt, sdt)
        self.film_h = max(self.film_h, self.crema_h * 0.8)
        self.update_particles(dt, sdt)
        self.update_drink_fx(dt, sdt)

    def update_order(self, dt, now, sdt):
        """點單模式：客人來點單 →（自動模式下咖啡師接單）→ 完成後顯示反應 → 離開 → 下一位

        營業模式（＝顧客點單）：客人照 arrival_gap 的間隔進來排隊，排隊的人走到櫃台後才顯示點單紙"""
        if self.business():
            self.update_queue(sdt)
        sw = self._switch_wait
        if sw is not None:                               # 換了咖啡機／沖煮方式：倒數完才開始做這張
            if sw[0] is not self.order or sw[0].state != "waiting":
                self._switch_wait = None                 # 客人等不及走了
            else:
                sw[1] -= dt
                if sw[1] <= 0:
                    self._switch_wait = None
                    self.start_order(sw[0])
        o = self.order
        if o is not None:
            o.t += dt
        if o is None and not self.queue and self.business() and not self.busy():
            self.auto_cold_setup()
        o = self.order
        if o is None:
            if self.queue:
                self.next_customer()
            elif not self.business() and not self.busy() and now >= self.next_order_at:
                self.new_order()
        elif o.state == "waiting":
            if not self.busy() and o.t >= (0.0 if self.same_party_next(o) else 2.5):   # 咖啡師自己接單（同一張單的下一杯直接做）
                if self.business() and self.out_of_beans():
                    self.beans_hint()                    # 沒豆子可用：客人乾等，要去商店買
                elif self.business() and not o.paid:
                    self.start_checkout()                # 先在櫃檯結帳，結完才開始做
                else:
                    self.barista_dial_in()
                    self.make_order()
                    if o.state != "waiting":             # 真的開始做了才存檔（沒做成時下一個 tick 會再試，不能每個 tick 都寫檔）
                        self.save_config()
        elif o.state == "done" and o.t >= (orders.SHOW_DONE if not self.queue else (0.0 if o.party and self.queue[0].party is o.party
                                                                                  else 4.0)) and (o.revealed or self.queue):
            # 後面有人排隊就早點讓位；營業模式要等結帳公布分數（reveal_party 把 t 歸零）
            o.state, o.t = "leaving", 0.0
        elif o.state == "leaving" and o.t >= 0.7:
            self.order = None
            gap = self.interval if self.auto else 6.0
            self.next_order_at = now + gap
            self.idle_since = now
        show = o is not None and not (o.state == "leaving")
        self.order_alpha += ((1.0 if show else 0.0) - self.order_alpha) * min(1.0, dt * 6)

    def auto_cold_setup(self):
        """營業中：冰滴解鎖了又沒有在滴的批次，咖啡師趁沒有客人時去架冰滴塔（滴好後客人才會點冰滴）"""
        if self.cold is not None or not self.method_open("colddrip"):
            return
        dp = brew.barista_dial(self.dp, self.params.roast, skill=self.skill())
        if self.start_session("cold_drip", True, dp):
            self.toast(T("沒有客人：咖啡師去架冰滴塔"), 4.0)

    def restore_after_business(self):
        """還原開營業前的參數、咖啡機、飲品（烘焙度、產地、養豆天數仍跟著目前這包豆子）"""
        pre, self.pre_biz, self._restore_biz = self.pre_biz, None, False
        if not pre:
            return
        names = {f.name for f in fields(Params)}
        self.params = Params(**{k: v for k, v in pre["params"].items() if k in names})
        self.sync_bag()
        if pre.get("machine") in MACHINES and self.machine_open(pre["machine"]):
            self.set_machine(pre["machine"])
        if pre.get("drink") in DRINKS and self.drink_open(pre["drink"]):
            self.set_drink(pre["drink"])
            if pre["drink"] in self.drink_actions:
                self.drink_actions[pre["drink"]].setChecked(True)
        if self.settings_dlg is not None:
            self.settings_dlg.close()
            self.settings_dlg.deleteLater()
            self.settings_dlg = None                 # 下次打開時顯示還原後的參數
        self.save_config()

    def update_day(self, now):
        """跨過午夜：前一天有接單就出日報；啟動時補看上一個營業日的日報"""
        if self._welcome_due is not None and now >= self._welcome_due and self.isVisible():
            self._welcome_due = None
            self.cfg["welcomed"] = True
            self.save_config()
            self.open_intro()
        due = self._report_due
        if due is not None and now >= due[1] and self.isVisible():
            self._report_due = None
            self.show_report(growth.report(self.stats, due[0]))
        day = festivals.today().isoformat()
        if day != self._today:
            old, self._today = self._today, day
            if self.stats.data["days"].get(old, {}).get("orders") and old > self.cfg.get("report_seen", ""):
                self.show_report(growth.report(self.stats, old))

    def idle_boiler_mode(self):
        """單鍋爐打完奶，閒置時鍋爐仍停在蒸氣溫度，直到下一杯先降溫"""
        t = self.machine.traits
        if t.steam_heatup and self.boiler.temp > self.params.temp + 3 and is_milk(self.last_drink):
            return "hold"
        return "brew"

    def on_session_event(self, ev):
        if ev == "grind":                              # 手沖台磨豆：從這包扣粉量
            self.use_beans(self.brew_dose(self.session.drink, self.session.dp))
        elif ev == "cold_grind":
            self.use_beans(self.session.dp.cd_dose)
        elif ev == "ignite":                           # 點火：旋鈕「喀」、瓦斯「噗」
            self.sound.once("click", 0.4)
            self.sound.once("hiss", 0.15)
        elif ev == "flame_off":
            self.sound.once("click", 0.35)
        elif ev in ("stir", "tap"):
            self.sound.once("tap", 0.2)
        elif ev == "sputter":
            self.sound.once("hiss", 0.2)
        elif ev == "kettle_start":
            self.sound.once("tap", 0.12)
        elif ev == "valve":
            self.sound.once("click", 0.4)
        elif ev == "pour_start":
            self.sound.once("tap", 0.2)
        elif ev == "steam_start":
            self.sound.once("hiss", 0.35)
        elif ev == "purge":
            self.purge_wand()
            self.sound.once("hiss", 0.45)
        elif ev == "frother_start":
            self.sound.once("click", 0.4)
        elif ev == "frother_stop":
            self.sound.once("beep", 0.4)
        elif ev == "vent":
            vx, vy = self.machine.vent
            for i in range(5):
                self.steam.append({"x": vx + random.uniform(-1, 1), "y": vy - 2, "vx": random.uniform(4, 14),
                                   "vy": random.uniform(-38, -24), "age": -i * 0.05,
                                   "life": random.uniform(1.0, 1.6), "ph": random.random() * 6.28,
                                   "boost": 70, "s0": 2, "s1": 12})
            self.sound.once("hiss", 0.2)

    def on_workflow_event(self, ev):
        if ev == "lock":
            self.sound.once("lock", 0.5)
        elif ev in ("knock", "knock2"):
            self.sound.once("knock", 0.55)
            if ev == "knock":
                self.maint["knock"] += 1
        elif ev == "thud":
            self.sound.once("tamp", 0.25)
        elif ev in ("tap", "tap2"):
            self.sound.once("tap", 0.45)
        elif ev == "tamp":
            self.sound.once("tamp", 0.6)
        elif ev == "grind_start":
            pass                                # 豆子在萃取開始時從這包扣掉（start_brew）

    # ───────────── 自動幀率 ─────────────
    def wanted_interval(self):
        if not self.isVisible() or self.host.isMinimized():
            return FRAME_HIDDEN
        if (self._fade is not None or self.delivery is not None or self.checkout is not None or self.reg_floats
                or self.clock_flipping()):
            return FRAME_ACTIVE                    # 換咖啡機／沖煮方式的漸變、櫃檯結帳與交付
        if self.report_card is not None:
            return FRAME_AMBIENT                   # 打烊日報
        tw = self.twin if self.twin_live() else None    # 雙頭機第二杯的水滴、流柱
        if (self.busy() or self.drops or self.splash or self.ripples
                or any(st["head"] > 0 for st in self.stream)
                or (tw and (tw["drops"] or tw["splash"] or any(st["head"] > 0 for st in tw["stream"])))):
            return FRAME_ACTIVE
        if self.drink_kind() == "espresso_tonic" and self.contents["water"] > 0:
            return FRAME_AMBIENT                   # 通寧水的氣泡一直往上冒
        if self.icecream and self.icecream["melt"] < 0.98 and self.shot:
            return FRAME_AMBIENT                   # 冰淇淋慢慢融化
        if self.method != "espresso" and (0.0 < self.brew_zoom < 1.0 or self.brew_focus() != (self.brew_zoom >= 1.0)):
            return FRAME_AMBIENT                   # 手沖／冰滴畫面正在拉近或拉遠
        card_moving = (0.01 < self.card_alpha < 0.99 or (self.card_alpha > 0.5 and not self.hover)
                       or 0.01 < self.status_alpha < 0.99
                       or 0.01 < self.art_alpha < 0.99 or (self.art_alpha > 0.5 and not self.hover)
                       or any(not c["landed"] for c in self.ice)
                       or 0.01 < self.order_alpha < 0.99 or (self.order and self.order.state == "done")
                       or bool(self.toasts))                # 成就通知淡入淡出
        if (self.steam or self.bubbles or card_moving or (self.ice and self.mix_t < 60)
                or abs(self.gauge) > 0.02 or abs(self.gauge_v) > 0.05):
            return FRAME_AMBIENT
        return FRAME_IDLE

    def set_frame_interval(self, ms):
        if self.timer.interval() != ms:
            self.timer.setInterval(ms)

    # ───────────── 繪圖 ─────────────
    def portafilter_state(self):
        """把手位置與濾杯內容：流程中由流程決定，否則扣在沖煮頭上"""
        wf = self.workflow
        if not wf:
            gx, gy = self.machine.pf_group_scene
            return {"x": gx, "y": gy, "handle": HANDLE_FULL, "tilt": 0.0}, None, self.machine.tamper_rest
        contents = None
        if wf.name not in ("unlock", "lock"):
            contents = {"puck": wf.has_puck, "grounds": wf.ground_g, "dose": wf.p.dose,
                        "level": wf.level, "tamped": wf.tamped, "uneven": wf.unevenness}
        return wf.pf, contents, wf.tamper

    def paintEvent(self, _):
        dpr = self.devicePixelRatioF()
        espresso = self.method == "espresso"
        tc = self.twin["cup"] if self.twin_live() else None
        key = (dpr, self.machine.key, self.cup.kind, self.cup.z, self.cup.sized, self._scene_w, self.method,
               (tc.kind, tc.z, tc.sized) if tc else None, self.decor_look()[0]["machine"],   # 咖啡機烤漆顏色
               self.cupless())      # 大中小杯、依量縮小：同一種杯子也要重畫；最後一項是 cupless
        if self.bg_layer is None or getattr(self, "_layer_key", None) != key:
            self._layer_key = key
            self.bg_layer = self.render_layer(self.paint_background if espresso else self.paint_brew_background, dpr)
            self.front_layer = self.render_layer(self.paint_front if espresso else self.paint_brew_front, dpr)
        w, h = int(self.width() * dpr), int(self.height() * dpr)
        if self._frame is None or self._frame.width() != w or self._frame.height() != h:
            self._frame = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
            self._frame.setDevicePixelRatio(dpr)
        self._frame.fill(Qt.transparent)

        s = self.scale_f
        fp = QPainter(self._frame)
        fp.setRenderHint(QPainter.Antialiasing)
        fp.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.counter_view:                    # 櫃檯畫面：不顯示咖啡機
            fp.scale(s, s)
            fp.translate(0, TOP_PAD)
            self.paint_counter(fp)
            self.paint_ambient(fp)
            fp.end()
            self.paint_overlays()
            return
        if espresso:
            fp.drawPixmap(QPointF(0, TOP_PAD * s), self.bg_layer)
        fp.scale(s, s)
        dx = self.scene_dx()                     # 咖啡機（沖煮台）在視窗正中間
        fp.translate(dx, TOP_PAD)
        m = self.machine
        if not espresso:
            self.paint_brew_frame(fp)
            fp.end()
            self.paint_overlays()
            return
        self.paint_pass_cups(fp)               # 出餐架上等著的杯子
        self.paint_rack_items(fp)              # 配料架上的配料（做飲品用到的從架上拿走）
        if m.traits.grinder == "external":
            self.paint_grinder_dynamic(fp)
        with self.machine_tint(m):
            m.paint_dynamic_scene(self, fp)
        if m.traits.milk == "frother":
            self.paint_frother(fp)
        fp.save()
        fp.translate(m.mx, m.my)
        with self.machine_tint(m):
            m.paint_dynamic(self, fp)
        self.paint_drip_water(fp)
        m.paint_needles(self, fp)
        if not self.cupless():                 # 逆洗中杯子拿走了、營業中這杯送去櫃檯了：不畫杯中液體
            self.paint_cup_dynamic(fp)
        if self.twin_live() and not self.backflushing():   # 雙頭機：第二個沖煮頭下的杯子
            with self.on_twin():
                self.paint_cup_dynamic(fp)
        fp.restore()
        tamper, pucks = None, []
        # 雙頭機：沒在動的那支把手先畫，正在備粉、移動的那支畫在最上面
        groups = [False, True] if self.twin is not None else [False]
        if self.twin is not None and self.workflow is not None:
            groups.reverse()
        for second in groups:
            with self.on_twin() if second else nullcontext():
                pf, contents, rest = self.portafilter_state()
                self.paint_portafilter(fp, pf, contents)
                fp.save()
                fp.translate(m.mx, m.my)
                m.paint_collar(self, fp, pf)           # 環座蓋住濾杯上緣：看起來是鎖進沖煮頭
                fp.restore()
                if self.workflow and self.workflow.puck:
                    pucks.append(self.workflow.puck)
                if tamper is None or self.workflow is not None:
                    tamper = rest                      # 填壓器：跟著正在備粉的那一杯
        fp.save()
        fp.translate(m.mx, m.my)
        m.paint_overlay(self, fp)
        fp.restore()
        for puck in pucks:
            self.paint_puck(fp, puck)
        self.paint_tamper(fp, tamper)
        fp.resetTransform()
        fp.drawPixmap(QPointF(0, TOP_PAD * s), self.front_layer)
        fp.scale(s, s)
        fp.translate(m.mx + dx, m.my + TOP_PAD)
        if not self.cupless():
            self.paint_condensation(fp)
        self.paint_steam(fp)
        self.paint_lcd(fp)
        if self.twin is not None:
            with self.on_twin():
                if self.cup is not None and not self.backflushing():
                    self.paint_condensation(fp)
                self.paint_lcd(fp)
        fp.translate(-m.mx, -m.my)
        for second in ((False, True) if self.twin is not None else (False,)):
            with self.on_twin() if second else nullcontext():
                ss = self.session
                self.paint_vessel(fp, ss.jigger if ss else None)      # 營業模式的量杯
                self.paint_vessel(fp, ss.vessel if ss else None)
        self.paint_ambient(fp)
        fp.end()
        self.paint_overlays()

    def paint_cup_dynamic(self, fp):
        """一杯的液體、冰塊、流柱、倒的水柱、道具、水滴（機身座標）"""
        self.paint_liquid(fp)
        self.paint_ice(fp)
        self.paint_streams(fp)
        self.paint_pour_stream(fp)
        self.paint_tool(fp)
        self.paint_particles(fp)

    def paint_brew_frame(self, fp):
        """手沖／冰滴的畫面（場景座標）：器具 → 杯中液體 → 杯子前景 → 倒的壺"""
        s, m = self.scale_f, self.machine
        cup_a = self.cup_alpha()                     # 拉近看沖煮器具時杯子淡出
        if cup_a > 0.01:
            fp.save()
            fp.resetTransform()
            fp.setOpacity(cup_a)
            fp.drawPixmap(QPointF(0, TOP_PAD * s), self.bg_layer)
            fp.restore()
        self.paint_station(fp)
        fp.save()
        fp.setOpacity(cup_a)
        fp.translate(m.mx, m.my)
        if not self.cup_away:
            self.paint_liquid(fp)
            self.paint_ice(fp)
        self.paint_pour_stream(fp)
        self.paint_particles(fp)
        fp.restore()
        fp.resetTransform()
        fp.setOpacity(cup_a)
        fp.drawPixmap(QPointF(0, TOP_PAD * s), self.front_layer)
        fp.scale(s, s)
        fp.translate(m.mx + self.scene_dx(), m.my + TOP_PAD)
        if not self.cup_away:
            self.paint_condensation(fp)
        self.paint_steam(fp)
        fp.setOpacity(1.0)
        fp.translate(-m.mx, -m.my)
        self.paint_vessel(fp, self.session.vessel if self.session else None)
        self.paint_ambient(fp)

    def begin_fade(self):
        """換咖啡機／沖煮方式前先留下目前的畫面，接下來 FADE_T 秒讓它淡出、新畫面淡入"""
        if self._frame is not None and self.isVisible():
            self._fade = (self._frame.copy(), time.perf_counter())

    def fade_amount(self):
        """漸變進度 0–1（沒有在漸變時是 None）"""
        if self._fade is None:
            return None
        k = (time.perf_counter() - self._fade[1]) / FADE_T
        if k >= 1:
            self._fade = None
            return None
        return k

    def paint_overlays(self):
        """把畫好的畫面貼到視窗，再疊上狀態列與卡片"""
        s = self.scale_f
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.is_windowed():
            self.paint_window_backdrop(p)
        k = self.fade_amount()
        if k is None:
            p.drawImage(0, 0, self._frame)
        else:                                        # 換咖啡機／沖煮方式：舊畫面淡出、新畫面淡入
            p.setOpacity(1 - k)
            p.drawImage(0, 0, self._fade[0])
            p.setOpacity(k)
            p.drawImage(0, 0, self._frame)
            p.setOpacity(1.0)
        p.scale(s, s)
        with self.on_focus():                        # 成對做兩杯、正在做第二杯：狀態列、卡片看第二杯
            if not self.counter_view:                # 櫃檯畫面不畫狀態列（客人點了什麼、評分都在 POS 上）
                p.save()
                p.translate(0, TOP_PAD)
                self.paint_status(p)
                p.restore()
            if not self.twin_live():
                self.paint_chart(p)
                self.paint_art_card(p)
        if self.twin_live():                         # 兩個沖煮頭下面都有杯子：兩杯各自一組（左邊那杯的在左、右邊那杯的在右）
            self.paint_chart(p)
            self.paint_art_card(p)
            with self.on_twin():
                self.paint_chart(p)
                self.paint_art_card(p)
        if not self.counter_view:                    # 櫃檯畫面：客人點了什麼顯示在 POS 上，不畫點單紙
            self.paint_order_card(p)
        self.paint_clock(p)
        self.paint_toasts(p)
        self.paint_report(p)
        p.end()

    def render_layer(self, fn, dpr):
        pm = QPixmap(round(self._scene_w * self.scale_f * dpr), round(WIN_H * self.scale_f * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.scale_f, self.scale_f)
        p.translate(self.scene_dx(), 0)              # 咖啡機（沖煮台）在視窗正中間
        fn(p)
        p.end()
        return pm

    def paint_window_backdrop(self, p):
        """視窗化模式的背景：深色暖調漸層 + 檯面 + 暗角，取代桌面透出來的透明背景"""
        w, h, s = self.width(), self.height(), self.scale_f
        sel, pal = self.decor_look()                  # 牆面、後檯櫃子的裝潢也換到操作畫面的背景（預設款維持原本的顏色）
        wall = pal["wall"] if sel["wall"] != decor.DEFAULTS["wall"] else None
        cab = pal["cab"] if sel["cabinet"] != decor.DEFAULTS["cabinet"] else None
        g = QLinearGradient(0, 0, 0, h)
        if wall:
            g.setColorAt(0, QColor(wall[0]).darker(150))
            g.setColorAt(0.75, QColor(wall[1]).darker(170))
            g.setColorAt(1, QColor(wall[1]).darker(260))
        else:
            g.setColorAt(0, QColor("#2b2522"))
            g.setColorAt(0.75, QColor("#1b1715"))
            g.setColorAt(1, QColor("#120f0e"))
        p.fillRect(self.rect(), g)
        counter = (TOP_PAD + FLOOR) * s               # 檯面：磨豆機在後、咖啡機較靠前（底部較低）
        c = QLinearGradient(0, counter, 0, h)
        if cab:
            c.setColorAt(0, QColor(cab[0]))
            c.setColorAt(0.04, QColor(cab[0]).darker(115))
            c.setColorAt(1, QColor(cab[1]).darker(150))
        else:
            c.setColorAt(0, QColor("#4a3a30"))
            c.setColorAt(0.04, QColor("#3a2d25"))
            c.setColorAt(1, QColor("#1e1814"))
        p.fillRect(0, int(counter), w, h - int(counter), c)
        v = QRadialGradient(w / 2, h * 0.45, max(w, h) * 0.75)
        v.setColorAt(0.55, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 120))
        p.fillRect(self.rect(), v)

