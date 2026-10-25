"""商店：錢包、有簽章的購買紀錄、咖啡機升級、精品豆"""
import random

from cafe_desk import beans, stats, store
from cafe_desk.machines import MACHINES
from conftest import run_until_idle


def _earn(st, amount):
    st.record({"drink": "latte", "title": "拿鐵", "score": 90, "comment": "", "order": True, "price": amount,
               "tip": 0}, [])


def test_wallet_and_signed_purchase(cfg_path):
    s = stats.Stats()
    _earn(s, 20000)
    assert store.balance(s) == 20000
    assert not s.record_purchase("compact_pid", 25000), "餘額不夠"
    assert s.record_purchase("allinone_burr", 20000)
    assert store.balance(s) == 0 and s.data["owned"] == ["allinone_burr"]
    assert s.data["revenue_total"] == 20000, "花錢不影響累積營業額（店鋪等級）"
    s.load()
    assert s.data["spent"] == 20000 and s.data["owned"] == ["allinone_burr"]
    s.db.execute("UPDATE events SET value='allinone_burr:1' WHERE kind='purchase'")   # 想改成只花 $1
    s.db.commit()
    s.load()
    assert s.tampered >= 1 and "allinone_burr" not in s.data["owned"]
    s.db.close()


def test_upgrades_change_traits():
    base = MACHINES["compact"].traits.temp_noise
    store.apply_upgrades(["compact_pid", "desk01_frother"])
    try:
        assert MACHINES["compact"].traits.temp_noise == 0.4
        assert MACHINES["desk01"].traits.frother_q == 0.72
        assert MACHINES["allinone"].traits.channel_add == type(MACHINES["allinone"]).traits.channel_add
        assert store.upgraded("compact", ["compact_pid"]) and not store.upgraded("lever", ["compact_pid"])
    finally:
        store.apply_upgrades([])
    assert MACHINES["compact"].traits.temp_noise == base


def test_buy_upgrade_from_desk(desk, unlocked):
    _earn(desk.stats, 30000)
    desk.set_machine("allinone")
    assert desk.buy_upgrade("allinone_burr")
    assert desk.machine.traits.channel_add == 0.0 and desk.wallet() == 10000
    assert not desk.buy_upgrade("allinone_burr"), "買過不能再買"
    assert not desk.buy_upgrade("compact_pid"), "餘額不夠"
    assert desk.machine_actions["allinone"].text().endswith("★")


def test_upgrades_restored_on_start(qapp, cfg_path):
    from cafe_desk.desk import CafeDesk
    s = stats.Stats()
    _earn(s, 20000)
    s.record_purchase("lever_collar", 12000)
    s.db.close()
    store.apply_upgrades([])
    w = CafeDesk()
    try:
        assert MACHINES["lever"].traits.temp_noise == 0.2
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()
        store.apply_upgrades([])


def test_random_bags_never_premium():
    rnd = random.Random(3)
    assert not any(beans.is_premium(beans.new_bag(None, rnd)) for _ in range(300))
    assert beans.is_premium(beans.new_bag("geisha")) and beans.valid_bag(beans.new_bag("kona"))


def test_buy_beans_and_premium_price(desk):
    _earn(desk.stats, 1000)
    assert desk.buy_beans("bluemountain")
    assert desk.bag["origin"] == "bluemountain" and desk.wallet() == 300
    assert not desk.buy_beans("geisha"), "餘額不夠"
    desk.set_order_mode(True)
    desk.new_order()
    o = desk.order
    from cafe_desk.orders import price_of
    assert o.price == round(price_of(o.drink) * beans.PREMIUM_PRICE_K)


def test_store_tab_buy_refreshes(desk):
    from cafe_desk.records import RecordsDialog
    _earn(desk.stats, 20000)
    dlg = RecordsDialog(desk, "shop")
    assert dlg.tabs.currentIndex() == 2
    dlg.buy(desk.buy_upgrade, "desk01_frother")
    assert "desk01_frother" in desk.stats.data["owned"] and dlg.tabs.currentIndex() == 2
    dlg.grab()
    dlg.close()
    store.apply_upgrades([])


def test_reset_progress(desk, tmp_path):
    """重新遊玩：紀錄、成就、等級、錢包、升級、清潔計數、豆子、冰滴歸零；參數與音樂清單保留"""
    from cafe_desk import config
    _earn(desk.stats, 30000)
    desk.buy_upgrade("compact_pid")
    desk.maint["backflush"] = 20
    desk.params.grind_um = 260.0
    desk.music.add([str(tmp_path / "a.mp3")])
    desk.set_order_mode(True)
    desk.new_order()
    assert desk.stats.data["total"] == 1 and desk.stats.unlocked("first_cup")
    assert desk.reset_progress()
    st = desk.stats.data
    assert st["total"] == 0 and st["revenue_total"] == 0 and st["spent"] == 0 and not st["achievements"]
    assert desk.wallet() == 0 and desk.shop_level() == 1 and MACHINES["compact"].traits.temp_noise == 1.4
    assert all(v["backflush"] == 0 for v in desk.maint_all.values())
    assert not desk.order_mode and desk.order is None and desk.report_card is None, "直接關營業，不出日報"
    assert desk.bag["origin"] == "house" and desk.bag["left"] == beans.BAG_G and desk.cold is None
    assert desk.params.grind_um == 260.0 and len(desk.music.files) == 1
    cfg = config.load()
    assert cfg["growth_seen"] == {"level": 1, "rank": 0} and cfg["order_no"] == 0
    desk.stats.load()
    assert desk.stats.data["total"] == 0, "資料庫真的清空了"


def test_reset_refused_while_busy(desk):
    assert desk.start_session("espresso", False)
    assert not desk.reset_progress()


def test_about_has_reset_button(desk):
    from PySide6.QtWidgets import QPushButton
    desk.open_about()
    labels = [b.text() for b in desk.about_dlg.findChildren(QPushButton)]
    assert "重新遊玩…" in labels
    desk.about_dlg.close()


def test_reset_toast_is_not_achievement_style(desk):
    """重新遊玩的通知是一般樣式（沒有獎盃）；成就、店鋪升級才用獎盃樣式"""
    assert desk.reset_progress()
    assert desk.toasts[-1][3] == "info"
    desk.announce(["first_cup"])
    assert desk.toasts[-1][3] == "trophy"
    desk.toasts[0] = (desk.toasts[0][0], 0.0, 10 ** 9, "info")
    desk.host.grab()


def test_grinder_upgrades():
    """平刀盤：三台用獨立磨豆機的咖啡機通道效應都降低（一體機不受影響）；鬼齒刀盤：沖煮台更乾淨、更甜"""
    from cafe_desk import brew
    from cafe_desk.drinks import DrinkParams
    base = {k: m.traits.channel_add for k, m in MACHINES.items()}
    before = brew.simulate_pourover(DrinkParams(), "中焙", 10, "house").score
    store.apply_upgrades(["grinder_flat", "station_ghost"])
    try:
        for k in store.EXTERNAL:
            assert MACHINES[k].traits.channel_add == base[k] - 0.04
        assert MACHINES["allinone"].traits.channel_add == base["allinone"]
        assert brew.FINES_K < 1 and brew.CLARITY > 0
        assert brew.simulate_pourover(DrinkParams(), "中焙", 10, "house").score > before + 2
        assert store.upgrade_names("lever", ["grinder_flat"]) == ["平刀盤"]
        assert store.target_name("station_ghost") == "手沖用磨豆機"
    finally:
        store.apply_upgrades([])
    assert brew.FINES_K == 1.0 and brew.CLARITY == 0.0


def test_station_grinder_needs_pourover(desk):
    """鬼齒刀盤要先解鎖手沖（Lv.2）才能買；平刀盤 Lv.1 就能買（DESK·01 用獨立磨豆機）"""
    _earn(desk.stats, 2000)                                   # 還在 Lv.1
    assert not desk.upgrade_open("station_ghost") and desk.upgrade_open("grinder_flat")
    _earn(desk.stats, 30000)
    assert desk.buy_upgrade("station_ghost") and desk.buy_upgrade("grinder_flat")
    assert desk.machine_actions["desk01"].text().endswith("★")


def test_beans_swap_after_current_drink(desk):
    """營業中（咖啡師在忙）買精品豆、開新豆子：這杯做完才換；付了錢的那包在等時不能再買"""
    _earn(desk.stats, 2000)
    assert desk.start_session("espresso", False)
    assert desk.buy_beans("kona")
    assert desk.bag["origin"] != "kona" and desk.pending_bag == "kona" and desk.wallet() == 1200
    assert not desk.buy_beans("geisha"), "已經有一包精品豆在等"
    assert not desk.request_bag("kenya"), "不能用一般豆蓋掉付了錢的精品豆"
    run_until_idle(desk)
    desk.step(0.05, 0.05)
    assert desk.bag["origin"] == "kona" and desk.pending_bag is None
    assert desk.start_session("espresso", False)
    assert desk.request_bag("kenya") and desk.pending_bag == "kenya"
    run_until_idle(desk)
    desk.step(0.05, 0.05)
    assert desk.bag["origin"] == "kenya"


def test_beans_open_now_when_idle(desk):
    _earn(desk.stats, 1000)
    assert desk.buy_beans("bluemountain") and desk.bag["origin"] == "bluemountain" and desk.pending_bag is None


def test_pending_bag_survives_restart(qapp, cfg_path):
    """付了錢、還沒換上就關程式：下次開啟直接換上"""
    import json
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "pending_bag": "geisha"}, f)
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    try:
        assert w.bag["origin"] == "geisha" and w.pending_bag is None
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.host.close()


def test_duo_upgrades_stack():
    """雙頭機的四項升級疊加：通道效應兩項相加，其他照設定"""
    from cafe_desk.machines import MACHINES
    base = type(MACHINES["duo"]).traits
    try:
        store.apply_upgrades(["duo_burr", "duo_steam", "duo_preinfuse", "duo_boiler"])
        t = MACHINES["duo"].traits
        assert abs(t.channel_add - (base.channel_add - 0.06)) < 1e-9
        assert t.steam_power == 1.9 and t.sweet_add == 0.3 and t.boiler_heat == 1.0 and t.boiler_draw == 0.05
        assert MACHINES["allinone"].traits == type(MACHINES["allinone"]).traits, "只改雙頭機"
    finally:
        store.apply_upgrades([])
