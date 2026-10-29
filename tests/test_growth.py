"""成長系統：店鋪等級、咖啡師熟練度、小費罐、打烊日報"""
import random
import time

import pytest

from cafe_desk import growth, orders, brew, stats
from cafe_desk.drinks import DRINKS, DrinkParams, evaluate_milk
from cafe_desk.machines import MACHINES
from cafe_desk.orders import Order
from conftest import run_until_idle, until_making


def test_level_table():
    assert growth.level_of(0) == 1
    assert growth.level_of(2999) == 1 and growth.level_of(3000) == 2
    assert growth.level_of(180000) == growth.MAX_LEVEL == 10
    assert growth.level_of(10 ** 9) == 10
    lv, nxt, prog = growth.level_progress(5500)
    assert (lv, nxt) == (2, 8000) and prog == pytest.approx(0.5)
    assert growth.level_progress(200000) == (10, None, 1.0)


def test_level_effects():
    assert growth.arrival_k(1) == 1 and growth.arrival_k(10) == pytest.approx(1 - growth.ARRIVAL_K)
    assert growth.patience_k(1) == 1 and growth.patience_k(10) == pytest.approx(1 + growth.PATIENCE_K)
    assert growth.work_k(1) == 1 and growth.work_k(10) == pytest.approx(1 + growth.WORK_K)
    assert [growth.queue_max(lv) for lv in (1, 4, 5, 7, 8, 10)] == [4, 4, 5, 5, 6, 6]
    r1, r2 = random.Random(5), random.Random(5)
    assert orders.arrival_gap(r2, level=10) == pytest.approx(orders.arrival_gap(r1) * growth.arrival_k(10))
    r1, r2 = random.Random(5), random.Random(5)
    assert orders.patience(r2, level=10) == pytest.approx(orders.patience(r1) * growth.patience_k(10))


def test_rank_table():
    assert growth.rank_of(0) == 0 and growth.skill(0) == 1.0
    assert growth.rank_of(49) == 0 and growth.rank_of(50) == 1
    assert growth.rank_of(1500) == 4 and growth.skill(5000) == 0.5
    assert growth.rank_next(40) == 10 and growth.rank_next(1500) is None


def test_skill_narrows_barista_error():
    """熟練度越高，點單的打奶溫度與手沖參數誤差越小"""
    dp = DrinkParams()
    o = Order(1, "Mia", "latte", [])

    def spread(k):
        rnd = random.Random(3)
        t = [orders.order_params(o, dp, rnd, skill=k).milk_temp for _ in range(300)]
        m = sum(t) / len(t)
        return (sum((x - m) ** 2 for x in t) / len(t)) ** 0.5

    assert spread(0.5) < spread(1.0) * 0.6
    g = [brew.barista_dial(dp, "中焙", random.Random(i), skill=0.5).po_grind for i in range(200)]
    g1 = [brew.barista_dial(dp, "中焙", random.Random(i)).po_grind for i in range(200)]
    assert max(g) - min(g) < max(g1) - min(g1)


def test_skill_improves_milk_texture():
    dp = DrinkParams()
    t = MACHINES["desk01"].traits
    rookie = sum(evaluate_milk(dp, t, "wand", random.Random(i)).texture for i in range(50))
    master = sum(evaluate_milk(dp, t, "wand", random.Random(i), skill=0.5).texture for i in range(50))
    assert master > rookie


def test_revenue_total_and_shop_tier(desk):
    """累積營業額從紀錄算（含小費）；升到 Lv.3 解鎖成就、通知一次"""
    st = desk.stats
    st.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": 7000,
               "tip": 1200}, [])
    assert st.data["revenue_total"] == 8200 and desk.shop_level() == 3
    assert st.unlocked("shop_3") and not st.unlocked("shop_6")
    desk.toasts.clear()
    desk.check_growth()
    assert any("Lv.3" in t[0] for t in desk.toasts)
    assert desk.growth_seen["level"] == 3
    n = len(desk.toasts)
    desk.check_growth()
    assert len(desk.toasts) == n, "同一級只通知一次"
    st.load()                                     # 重新從資料庫算：一樣
    assert st.data["revenue_total"] == 8200


def test_old_records_count_without_spam(qapp, cfg_path):
    """第一次有成長系統：舊紀錄往回算，不補發升級通知"""
    from cafe_desk.desk import CafeDesk
    s = stats.Stats()
    for _ in range(3):
        s.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": 5000,
                  "tip": 0}, [])
    s.db.close()
    w = CafeDesk()
    try:
        assert w.shop_level() == 4 and w.growth_seen["level"] == 4
        w.toasts.clear()
        w.check_growth()
        assert not [t for t in w.toasts if "挑戰" not in t[0]]       # 挑戰用舊紀錄的營業額完成是真的，只確認沒有補發升級通知
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_counter_delivery_flow(desk):
    """營業中做完一杯：杯子在出杯台、拍成圖收起來，切到櫃檯畫面（不顯示咖啡機），客人取走後才評分（飄出小費），再切回來；
    咖啡師在交付時要等（busy）"""
    from cafe_desk.orders import Order
    desk.set_order_mode(True)
    assert desk.side_on() and desk.cup_anchor()[0] + desk.machine.mx > desk.machine.scene_w, "杯子在出杯台"
    o = Order(1, "Amy", "latte", [], price=120, patience=999, to_go=True)
    desk.order = o
    desk.start_order(o)
    phases, floats, counter = set(), False, False
    n = 0
    while desk.busy():
        if desk.delivery is not None:
            phases.add(desk.delivery["phase"])
            counter = counter or desk.counter_view
            assert not desk.making(), "交付時咖啡師沒有在做下一杯"
        floats = floats or bool(desk.reg_floats)
        desk.step(0.05, 0.25)
        n += 1
        if n % 30 == 0:
            desk.host.grab()
        assert n < 8000
    assert phases == {"in", "place", "pickup", "out"} and counter and floats
    assert desk.counter_view and desk.cup_away and desk.scale_weight() == 0, "沒有客人等著做：留在櫃檯"
    assert desk.stats.data["order_to_go"] == 1
    desk.start_session("espresso", True)                 # 下一杯換上新杯子
    assert not desk.cup_away
    desk.step(0.05, 0.05)
    assert not desk.counter_view, "開始做飲品切回咖啡機"
    for m in ("pourover", "siphon"):
        desk.set_method(m)
        desk.host.grab()


def test_side_counter_hidden_outside_business(desk):
    assert not desk.business() and not desk.side_on()
    from cafe_desk.render.station import UNIFORM_W
    assert desk._scene_w == UNIFORM_W, "視窗一律統一寬度"
    assert desk.cup_anchor() == (desk.machine.cup_cx, desk.machine.cup_base), "杯子在沖煮頭下"


def test_business_order_finishes_with_level(desk, monkeypatch):
    """高等級營業：排隊上限變大、做完一單正常記帳"""
    monkeypatch.setattr(desk, "shop_level", lambda: 10)
    monkeypatch.setattr(orders, "party_size", lambda rnd=None: 1)   # 一杯一張單：做完、結帳就記一杯
    desk.set_order_mode(True)
    desk.arrive_in = 0
    desk.step(0.05, 0.05)
    assert desk.order is not None
    desk.order.t = 3
    desk.step(0.05, 0.05)
    until_making(desk)
    run_until_idle(desk)
    assert desk.stats.day()["orders"] == 1


def test_report_on_closing(desk):
    desk.set_order_mode(True)
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 91, "comment": "好喝", "order": True,
                       "price": 120, "tip": 12, "wait": 30.0}, [])
    desk.set_order_mode(False)
    rc = desk.report_card
    assert rc is not None and rc["data"]["served"] == 1 and rc["data"]["revenue"] == 132
    assert desk.cfg["report_seen"] == "2026-08-01"
    desk.host.grab()
    desk.dismiss_report()
    rc["t0"] -= 1                                 # 淡出完
    assert desk.report_alpha() == 0 and desk.report_card is None


def test_no_report_without_orders(desk):
    desk.set_order_mode(True)
    desk.set_order_mode(False)
    assert desk.report_card is None


def test_report_contents_and_compare():
    class S:
        data = {"days": {
            "2026-07-30": {"orders": 10, "revenue": 1000, "tips": 50, "walkouts": 1, "cups": 10, "score_sum": 850,
                           "wait_sum": 300, "waited": 10, "best": None},
            "2026-07-31": {"orders": 0, "revenue": 0, "cups": 3},
            "2026-08-01": {"orders": 12, "revenue": 1500, "tips": 90, "walkouts": 0, "cups": 12, "score_sum": 1056,
                           "wait_sum": 240, "waited": 12, "best": {"drink": "latte", "title": "拿鐵", "score": 95}}},
            "achievements": {"rush": "2026-08-01"}}
    r = growth.report(S, "2026-08-01")
    assert r["served"] == 12 and r["change"] == pytest.approx(0.5) and r["avg"] == pytest.approx(88)
    assert r["achievements"] == ["rush"] and r["level"] == 1 and r["need"] == 3000 - 2500
    assert growth.report(S, "2026-07-31") is None
    assert growth.last_business_day(S, "2026-08-02") == "2026-08-01"
    assert growth.last_business_day(S, "2026-08-01") == "2026-07-30"


def test_day_rollover_shows_yesterday(desk, monkeypatch):
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 91, "comment": "", "order": True,
                       "price": 120, "tip": 0}, [])
    monkeypatch.setenv("CAFE_DESK_DATE", "2026-08-02")
    desk.step(0.05, 0.05)
    assert desk.report_card is not None and desk.report_card["data"]["day"] == "2026-08-01"
    assert desk._today == "2026-08-02"


def test_startup_shows_missed_report(qapp, cfg_path, monkeypatch):
    from cafe_desk.desk import CafeDesk
    s = stats.Stats()
    s.record({"drink": "latte", "title": "拿鐵", "score": 91, "comment": "", "order": True, "price": 120, "tip": 0}, [])
    s.db.close()
    monkeypatch.setenv("CAFE_DESK_DATE", "2026-08-03")
    w = CafeDesk()
    try:
        w.show_window()
        assert w._report_due is not None and w._report_due[0] == "2026-08-01"
        w._report_due = (w._report_due[0], time.perf_counter() - 1)
        w.step(0.05, 0.05)
        assert w.report_card is not None
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_records_shop_tab(desk):
    from cafe_desk.records import RecordsDialog
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 91, "comment": "", "order": True,
                       "price": 120, "tip": 12}, [])
    dlg = RecordsDialog(desk)
    dlg.close()


def test_business_screen_paints_in_both_languages(desk):
    """營業中的狀態列（Lv、今日營業額）、點單紙價格、小費罐、日報收據：中英文都畫得出來"""
    from cafe_desk.i18n import set_lang
    desk.set_order_mode(True)
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 91, "comment": "", "order": True,
                       "price": 120, "tip": 12, "wait": 20.0}, [])
    try:
        for lang in ("zh", "en"):
            set_lang(lang)
            desk.order = Order(5, "Mia", "latte", [], price=120, patience=200)
            desk.order_alpha = 1.0
            desk._status_cache = None
            desk.host.grab()
        desk.set_order_mode(False)
        desk.host.grab()
    finally:
        set_lang("zh")


def test_skill_score_table():
    assert growth.skill_score(80, 0) == 80, "85 分以下不變"
    assert growth.skill_score(97, 0) == pytest.approx(89.8)
    assert growth.skill_score(97, 2) == pytest.approx(93.4)
    assert growth.skill_score(97, 4) == 97
    assert len(growth.SCORE_K) == len(growth.RANKS)


def _lever_shot(desk, cups):
    desk.stats.data["total"] = cups
    desk.set_machine("lever")
    desk.boiler.temp = desk.params.temp
    assert desk.start_session("espresso", False)
    run_until_idle(desk)
    return desk.result


def test_rookie_scores_are_compressed(desk):
    """同一組參數：新手的高分被壓縮並在評語說明實力，大師不壓縮"""
    rookie = _lever_shot(desk, 0)
    assert rookie.score < 90 and "實力" in rookie.comment
    master = _lever_shot(desk, 1500)
    assert master.score > 90 and "實力" not in master.comment


def test_unlock_table():
    assert growth.machine_open("desk01", 1) and not growth.machine_open("lever", 2) and growth.machine_open("lever", 3)
    assert growth.method_open("espresso", 1) and not growth.method_open("pourover", 1)
    assert growth.method_open("siphon", 8) and not growth.method_open("siphon", 7)
    assert growth.unlocked_at(2) == [("method", "pourover")]
    assert sorted(lv for lv in list(growth.MACHINE_LEVEL.values()) + list(growth.METHOD_LEVEL.values())) == \
        [1, 1, 2, 3, 4, 5, 6, 7, 8, 9], "Lv.2–9 每一級剛好解鎖一樣"


def test_level1_only_desk01_and_espresso(desk):
    """Lv.1：選單反灰、設定視窗擋飲品、客人只點義式、只用 DESK·01"""
    assert desk.shop_level() == 1
    assert not desk.method_actions["pourover"].isEnabled() and "Lv.2" in desk.method_actions["pourover"].text()
    assert not desk.machine_actions["lever"].isEnabled() and desk.machine_actions["desk01"].isEnabled()
    desk.set_drink("pour_over")
    assert desk.drink != "pour_over" and desk.method == "espresso" and "Lv.2" in desk.notice[0]
    from cafe_desk.drinks import method_of
    assert all(method_of(k) == "espresso" for k in DRINKS if k not in desk.order_exclude())
    desk.set_order_mode(True)
    for _ in range(5):
        desk.order = None
        desk.make_order()
        assert desk.machine.key == "desk01" and method_of(desk.order.drink) == "espresso"
        desk._switch_wait = None


def test_level_up_unlocks_and_notifies(desk):
    desk.toasts.clear()
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 88, "comment": "", "order": True,
                       "price": 8000, "tip": 0}, [])                       # 直接到 Lv.3
    desk.check_growth()
    texts = [t[0] for t in desk.toasts]
    assert any("手沖" in t and "復古拉桿" in t for t in texts), "一次跳兩級：手沖、復古拉桿都通知"
    assert desk.method_actions["pourover"].isEnabled() and desk.machine_actions["lever"].isEnabled()
    desk.set_drink("pour_over")
    assert desk.method == "pourover"


def test_locked_saved_setup_falls_back(qapp, cfg_path):
    """設定檔存的是還沒解鎖的設備（例如重新遊玩後）：退回 DESK·01、義式"""
    import json
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "machine": "allinone", "drink": "siphon"}, f)
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    try:
        assert w.machine.key == "desk01" and w.method == "espresso" and w.drink == "espresso"
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_drink_icons_and_book(desk):
    """每一種飲品都有圖（含節日限定）；圖鑑做過的是彩色、沒做過的是剪影，沒解鎖的寫幾級解鎖"""
    from PySide6.QtWidgets import QLabel
    from cafe_desk.render.icons import RECIPES, drink_icon
    from cafe_desk.records import RecordsDialog
    assert set(RECIPES) == set(DRINKS), "新飲品要在 render/icons.py 的 RECIPES 加上分層"
    for k in DRINKS:
        assert not drink_icon(k, 64, True).isNull() and not drink_icon(k, 64, False).isNull()
    desk.stats.record({"drink": "latte", "title": "拿鐵", "score": 88, "comment": "", "order": True,
                       "price": 120, "tip": 0}, [])
    dlg = RecordsDialog(desk)
    texts = [lab.text() for lab in dlg.findChildren(QLabel)]
    assert any("1 杯" in t for t in texts) and any("Lv.2 解鎖" in t for t in texts)
    dlg.close()


def test_guide_tab(desk):
    """關於視窗的「說明」頁是遊戲說明；解鎖表、稱號門檻從遊戲資料產生"""
    from PySide6.QtWidgets import QLabel
    from cafe_desk.about import AboutDialog
    dlg = AboutDialog(desk)
    assert dlg.tabs.tabText(dlg.tabs.count() - 1) == "說明"
    page = dlg.tabs.widget(dlg.tabs.count() - 1)
    text = " ".join(lab.text() for lab in page.findChildren(QLabel))
    assert "遊戲說明" in text and "Lv.8：虹吸壺" in text and "大師 1500 杯" in text
    dlg.close()


def test_side_counter_only_in_business(desk):
    from cafe_desk.render.shop import SIDE_W
    w0 = desk._scene_w
    desk.set_mode("business")
    assert desk.side_on() and desk._scene_w == w0, "營業模式多了出杯台，視窗一樣大"
    assert desk.scene_dx() + desk.machine.scene_w + SIDE_W <= desk._scene_w, "出杯台放得下"
    from cafe_desk.render.station import POUR_PAD
    h = desk.machine.hover_area                       # 咖啡機置中；出杯台右邊要留倒入的空間，放不下就往左移
    centered = abs(desk.scene_dx() + (h[0] + h[2]) / 2 - desk._scene_w / 2) < 1
    room = desk._scene_w - (desk.scene_dx() + desk.machine.scene_w + SIDE_W)
    assert room >= POUR_PAD - 1e-6 and (centered or abs(room - POUR_PAD) < 1e-6)
    assert desk.cup.CX + desk.machine.mx > desk.machine.scene_w, "杯子換到出杯台"
    desk.set_method("pourover")
    assert not desk.side_on(), "沖煮台沒有出杯台"
    desk.set_mode("manual")
    desk.set_method("espresso")
    assert desk._scene_w == w0 and desk.cup.CX == desk.machine.cup_cx


def test_welcome_hint_only_for_new_players(desk, qapp, cfg_path):
    import time as _t
    assert desk._welcome_due is not None
    desk._welcome_due = _t.perf_counter() - 1
    desk.step(0.05, 0.05)
    assert desk.intro_dlg is not None and desk.intro_dlg.isVisible() and desk.cfg["welcomed"]
    desk.intro_dlg.close()


def test_no_welcome_for_existing_players(qapp, cfg_path):
    from cafe_desk.desk import CafeDesk
    s = stats.Stats()
    s.record({"drink": "latte", "title": "拿鐵", "score": 88, "comment": "", "order": False}, [])
    s.db.close()
    w = CafeDesk()
    try:
        assert w._welcome_due is None and w.cfg["welcomed"]
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_drinks_unlock_by_barista_title(desk):
    """新手只有濃縮、美式、熱拿鐵；晉升時通知解鎖了哪些；客人也只點解鎖的"""
    assert desk.drink_open("espresso") and desk.drink_open("latte") and not desk.drink_open("cappuccino")
    assert "熟手" in desk.drink_lock("cappuccino") and not desk.drink_actions["cappuccino"].isEnabled()
    desk.set_drink("mocha")
    assert desk.drink != "mocha" and "職人" in desk.notice[0]
    assert set(k for k in DRINKS if k not in desk.order_exclude()) == {"espresso", "americano", "latte"}
    desk.toasts.clear()
    desk.stats.data["total"] = 200                     # 直接到老手：熟手、老手的飲品一起通知
    desk.check_growth()
    text = " ".join(t[0] for t in desk.toasts)
    assert "卡布奇諾" in text and "馥列白" in text and "摩卡" not in text
    assert desk.drink_actions["cappuccino"].isEnabled() and not desk.drink_actions["mocha"].isEnabled()
    desk.set_drink("cappuccino")
    assert desk.drink == "cappuccino"


def test_equipment_book(desk):
    """圖鑑的設備區：5 台咖啡機、3 台磨豆機（獨立、營業用、手沖用）、4 種沖煮台；Lv.1 只有 DESK·01 與獨立磨豆機解鎖"""
    from PySide6.QtWidgets import QLabel
    from cafe_desk.records import RecordsDialog
    from cafe_desk.render import gear_icons
    for m in MACHINES.values():
        assert not gear_icons.machine_icon(desk, m, 80, 60).isNull()
    for kind in ("grinder", "pourover", "colddrip", "moka", "siphon"):
        assert not gear_icons.station_icon(desk, kind, 80, 60, locked=True).isNull()
    for style in ("standard", "commercial"):
        assert not gear_icons.grinder_icon(desk, 80, 60, False, 1.0, style).isNull()
    assert "_grinder_style_override" not in desk.__dict__, "畫圖鑑縮圖不能改到目前磨豆機的外觀"
    assert desk.method == "espresso", "畫沖煮台縮圖不能改到目前的沖煮方式"
    dlg = RecordsDialog(desk)
    texts = [lab.text() for lab in dlg.findChildren(QLabel)]
    assert "設備（2/12）" in texts and "店鋪 Lv.7 解鎖" in texts and "店鋪 Lv.9 解鎖" in texts
    dlg.close()


def test_business_brews_into_jigger_then_pours(desk):
    """營業模式：濃縮先萃取到量杯（杯子裡還沒有），照順序倒進杯子；外帶熱飲一開始就是紙杯"""
    from cafe_desk.orders import Order
    desk.set_order_mode(True)
    o = Order(1, "Amy", "latte", [], price=120, patience=999, to_go=True)
    desk.order = o
    desk.start_order(o)
    assert desk.cup.kind == "paper_latte" and desk.cup.paper == "l"
    seen_jigger = poured = False
    n = 0
    while desk.busy():
        ss = desk.session
        if ss and ss.stage_name == "brew" and ss.jigger is not None and desk.shot and desk.shot.weight > 10:
            seen_jigger = True
            assert desk.cup_espresso() == 0 and desk.jigger_level() is not None, "萃取中濃縮在量杯裡"
        if ss and ss.stage_name == "pour" and getattr(ss.stage, "vessel", "") in ("pitcher", "jug"):
            poured = poured or desk.shot_frac >= 0.999
        desk.step(0.05, 0.5)
        n += 1
        if n % 60 == 0:
            desk.host.grab()
        assert n < 8000
    assert seen_jigger and poured, "量杯倒完才倒牛奶"


def test_manual_brews_straight_into_cup(desk):
    desk.start_session("latte", True)
    assert desk.cup.kind == "latte"
    n = 0
    while desk.busy():
        assert desk.session is None or desk.session.jigger is None, "手動模式直接萃取到杯子"
        desk.step(0.05, 0.5)
        n += 1
        assert n < 8000


def test_business_always_windowed(desk):
    """營業模式一律視窗化；手動／自動照使用者的設定，可以切換"""
    desk.set_windowed(False)
    assert not desk.is_windowed()
    desk.set_mode("business")
    assert desk.is_windowed() and desk.windowed_act.isChecked(), "營業中一律視窗化：勾起來"
    assert not desk.windowed_act.isEnabled(), "營業中反灰"
    desk.windowed_act.trigger()                       # 營業中點了不改設定、保持勾選
    assert desk.windowed_act.isChecked() and desk.is_windowed() and not desk.windowed
    assert not desk.windowed, "使用者的設定不變"
    desk.set_mode("auto")
    assert not desk.is_windowed(), "回到自動模式照使用者的設定"
    assert not desk.windowed_act.isChecked()
    desk.set_windowed(True)
    assert desk.is_windowed()


def test_flip_clock_only_in_business(desk, monkeypatch):
    """右上角翻頁鐘：只在營業模式；數字變了會翻；設定可以關掉、改成營業計時"""
    assert not desk.clock_shown()
    desk.set_mode("business")
    assert desk.clock_shown()
    desk.update_clock()
    assert desk._clock and len(desk._clock["digits"]) == 4
    desk.set_clock("seconds", True)
    desk.update_clock()
    assert len(desk._clock["digits"]) == 6
    desk._clock["digits"][-1] = "x"                    # 假裝上一秒是別的數字
    desk.update_clock()
    assert desk.clock_flipping()
    desk.host.grab()
    desk.set_clock("hour12", True)
    assert 1 <= int(desk.clock_text()[:2]) <= 12
    desk.set_clock("on", False)
    desk.update_clock()
    assert desk._clock is None
    desk.set_clock("on", True)
    desk.set_mode("manual")
    desk.update_clock()
    assert desk._clock is None


def test_window_is_16_9_with_size_choices(desk):
    """視窗一律 16:9；大小選項是 960×540–1920×1080；舊版縮放換成最接近的"""
    from cafe_desk.desk import window_scale
    from cafe_desk.render.station import UNIFORM_W, WINDOW_SIZES
    from cafe_desk.layout import WIN_H, TOP_PAD
    assert abs(UNIFORM_W / (WIN_H + TOP_PAD) - 16 / 9) < 1e-9
    for px in WINDOW_SIZES:
        desk.set_scale(px / UNIFORM_W)
        assert (desk.width(), desk.height()) == (px, px * 9 // 16)
    assert window_scale(None) * UNIFORM_W == 1280
    assert round(window_scale(1.0) * UNIFORM_W) == 960, "舊版 100%（800 寬）→ 960×540"
    assert round(window_scale(1.5) * UNIFORM_W) == 1280, "舊版 150%（1200 寬）→ 1280×720"


def _days(**kw):
    class S:
        data = {"days": kw}
    return S


def test_star_rating():
    day = {"orders": 20, "walkouts": 0, "rate_sum": 20 * 95.0, "rate_n": 20, "wait_sum": 20 * 60.0, "waited": 20}
    assert growth.star_rating(_days(**{"2026-08-01": day}), "2026-08-01", 9) is None          # 還沒到 Lv.10
    assert growth.star_rating(_days(**{"2026-08-01": dict(day, orders=5)}), "2026-08-01", 10) is None   # 訂單不夠
    assert growth.star_rating(_days(**{"2026-08-01": day}), "2026-08-01", 10) == pytest.approx(5.0)
    bad = {"orders": 20, "walkouts": 10, "rate_sum": 20 * 60.0, "rate_n": 20, "wait_sum": 20 * 200.0, "waited": 20}
    assert growth.star_rating(_days(**{"2026-08-01": bad}), "2026-08-01", 10) == pytest.approx(1.0)
    # 近況變差會掉星：舊的好日子超過 7 天就不算
    both = _days(**{"2026-07-20": day, "2026-08-01": bad})
    assert growth.star_rating(both, "2026-08-01", 10) == pytest.approx(1.0)
    assert growth.star_rating(both, "2026-07-25", 10) == pytest.approx(5.0)                   # 當時 7/20 還在近 7 天內


def test_inspector_counts_double(desk):
    cup = {"drink": "latte", "title": "拿鐵", "comment": "", "order": True, "price": 100, "tip": 0, "wait": 10.0}
    desk.stats.record(dict(cup, score=60), [])
    desk.stats.record(dict(cup, score=90, inspector=True), [])
    d = desk.stats.day()
    assert d["rate_n"] == 3 and d["rate_sum"] == pytest.approx(60 + 180)
    desk.stats.load()                                          # 重讀資料庫：簽章驗證過、加權一樣
    d = desk.stats.day()
    assert d["rate_n"] == 3 and desk.stats.tampered == 0


def test_inspector_arrives_only_at_max_level(desk, monkeypatch):
    monkeypatch.setattr(growth, "INSPECTOR_P", 1.0)
    monkeypatch.setattr(orders, "party_size", lambda rnd=random: 1)
    desk.set_order_mode(True)
    desk.new_order()
    assert desk.order is not None and not desk.order.inspector          # Lv.1：不會來
    desk.order, desk.queue = None, []
    monkeypatch.setattr(desk, "shop_level", lambda: 10)
    desk.new_order()
    assert desk.order.inspector and desk.order.name == "評鑑員"


def _view_biz(desk, lock):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    desk.set_view_lock(lock)
    for _ in range(40):
        desk.step(0.05, 0.05)


def test_view_follows_barista_by_default(desk):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    for _ in range(40):
        desk.step(0.05, 0.05)
    assert desk.view_lock == "follow" and desk.counter_view, "沒客人：在櫃檯"
    o = Order(1, "Amy", "espresso", [], price=70, patience=999)
    desk.order = o
    desk.start_order(o)
    for _ in range(20):
        desk.step(0.05, 0.05)
    assert not desk.counter_view, "開始做：切到咖啡機"


def test_view_locked_on_counter_or_machine(desk):
    _view_biz(desk, "counter")
    assert desk.counter_view
    o = Order(1, "Amy", "espresso", [], price=70, patience=999)
    desk.order = o
    desk.start_order(o)
    for _ in range(30):
        desk.step(0.05, 0.05)
    assert desk.making() and desk.counter_view, "鎖定櫃檯：咖啡師在做飲品畫面也不動"
    desk.host.grab()
    run_until_idle(desk)
    assert desk.counter_view
    desk.set_view_lock("machine")
    assert not desk.counter_view, "換成鎖定咖啡機：馬上切過去"
    o2 = Order(2, "Ken", "espresso", [], price=70, patience=999)
    desk.order = o2
    desk.start_order(o2)
    run_until_idle(desk)
    assert not desk.counter_view and o2.state in ("done", "leaving"), "鎖定咖啡機：結帳、交付照樣進行，畫面不去櫃檯"
    desk.set_view_lock("follow")
    for _ in range(40):
        desk.step(0.05, 0.05)
    assert desk.counter_view and desk.cfg["view_lock"] == "follow"


def test_view_lock_saved_and_bad_value_ignored(desk):
    desk.set_view_lock("machine")
    assert desk.cfg["view_lock"] == "machine"
    desk.set_view_lock("nonsense")
    assert desk.view_lock == "machine"
