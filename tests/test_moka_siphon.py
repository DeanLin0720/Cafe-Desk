"""摩卡壺與虹吸壺：萃取模型、流程、畫面、點單、咖啡師調參、成就"""
import random

from cafe_desk import brew, orders
from cafe_desk.drinks import DrinkParams, method_of
from cafe_desk.stats import Stats

from conftest import run_until_idle, until_making


def _dp(**kw):
    dp = DrinkParams()
    for k, v in kw.items():
        setattr(dp, k, v)
    return dp


def test_moka_model():
    base = brew.simulate_moka(_dp(), "中焙", 12, "colombia")
    assert base.score >= 85
    assert brew.TDS_MOKA[0] <= base.tds <= brew.TDS_MOKA[1]
    hot = brew.simulate_moka(_dp(mk_heat=5), "中焙", 12, "")
    assert hot.time < base.time and hot.channeling > base.channeling and hot.score < base.score   # 火太大：焦苦
    coarse = brew.simulate_moka(_dp(mk_grind=600), "中焙", 12, "")
    assert coarse.ey < base.ey and coarse.score < 50
    choke = brew.simulate_moka(_dp(mk_grind=200), "中焙", 12, "")
    assert choke.channeling > base.channeling and choke.score < base.score
    assert 100 <= brew.moka_beverage(_dp()) <= 130


def test_siphon_model():
    base = brew.simulate_siphon(_dp(), "中焙", 12, "colombia")
    assert base.score >= 85
    assert brew.TDS_SIPHON[0] <= base.tds <= brew.TDS_SIPHON[1]
    short = brew.simulate_siphon(_dp(sy_steep=20), "中焙", 12, "")
    long_ = brew.simulate_siphon(_dp(sy_steep=90), "中焙", 12, "")
    assert short.ey < base.ey < long_.ey
    clog = brew.simulate_siphon(_dp(sy_grind=400), "中焙", 12, "")
    assert clog.channeling > base.channeling
    assert brew.siphon_beverage(_dp(sy_dose=17)) < 230, "最多粉量也裝得進美式杯"


def test_barista_dials_moka_and_siphon():
    user = _dp()
    for roast, origin in (("淺焙", "kenya"), ("中焙", "colombia"), ("深焙", "mandheling")):
        d = brew.barista_dial(user, roast, random.Random(2))
        assert brew.simulate_moka(d, roast, 10, origin).score >= 75, roast
        assert brew.simulate_siphon(d, roast, 10, origin).score >= 80, roast
    assert user.mk_grind == 320 and user.sy_steep == 50, "不寫回使用者設定"


def test_moka_flow(desk):
    machine_w = desk.width()
    desk.bag["left"] = 250
    assert desk.start_session("moka_pot", True)
    assert desk.method == "moka" and desk.workflow is None and desk.width() == machine_w
    phases, zoomed = set(), False
    while desk.busy():
        desk.step(0.05, 0.5)
        ss = desk.session
        if ss is not None:
            phases.add(getattr(ss.stage, "phase", ss.stage_name))
            zoomed = zoomed or desk.brew_zoom > 0.9
    assert {"grind", "assemble", "ignite", "heat", "brew", "sputter", "off"} <= phases
    assert zoomed, "煮的時候拉近看摩卡壺"
    desk.host.grab()
    assert abs(desk.contents["water"] - brew.moka_beverage(desk.dp)) < 0.5
    assert desk.bag["left"] == 250 - desk.dp.mk_dose
    assert desk.result.drink == "moka_pot" and desk.result.score >= 80
    assert "moka_85" in desk.stats.data["achievements"]


def test_siphon_flow(desk):
    desk.bag["left"] = 250
    assert desk.start_session("siphon", True)
    assert desk.method == "siphon"
    seen = {}
    while desk.busy():
        desk.step(0.05, 0.5)
        ss = desk.session
        if ss is not None and ss.station is not None and ss.stage_name == "siphon":
            st = ss.station
            seen[ss.stage.phase] = (st["upper"], st["lower"], st["dome"])
            if len(seen) % 3 == 0:
                desk.host.grab()
    assert seen["steep"][0] > 0.9 and seen["steep"][1] < 0.2, "浸泡時水都在上壺"
    assert seen["remove"][0] < 0.05 and seen["remove"][2] > 0.9, "抽完：上壺只剩粉山"
    assert abs(desk.contents["water"] - brew.siphon_beverage(desk.dp)) < 0.5
    assert desk.bag["left"] == 250 - desk.dp.sy_dose
    assert desk.result.drink == "siphon" and desk.result.score >= 80


def test_methods_menu_and_drinks(desk):
    assert {"moka", "siphon"} <= set(desk.method_actions)
    desk.set_method("moka")
    assert desk.drink == "moka_pot" and set(desk.drink_actions) == {"moka_pot"}
    desk.host.grab()                                     # 沒在煮的畫面
    desk.set_method("siphon")
    assert desk.drink == "siphon" and desk.auto_drink() == "siphon"
    desk.host.grab()
    assert method_of("moka_pot") == "moka" and method_of("siphon") == "siphon"


def test_siphon_order_in_business_mode(desk):
    """客人點虹吸：從義式畫面自動切過去，咖啡師依烘焙度調好參數"""
    desk.set_order_mode(True)
    desk.set_method("espresso")
    desk.new_order()
    o = desk.order
    o.drink, o.mods = "siphon", []
    o.price = orders.price_of("siphon")
    desk.bag["left"] = 250
    desk.make_order()
    until_making(desk)
    assert desk.method == "siphon" and o.state == "making"
    run_until_idle(desk)
    assert o.state == "done" and desk.result.drink == "siphon"
    assert desk.stats.day()["revenue"] >= orders.PRICES["siphon"]
    assert orders.PACE["siphon"] > 1 and orders.PACE["moka"] > 1, "點虹吸、摩卡壺的客人比較願意等"


def test_all_methods_achievement(cfg_path):
    st = Stats()
    try:
        cup = dict(score=80, comment="", machine=None, milk=None, origin="kenya", bean_age=10, dose=15, festival=None)
        got = set()
        for d in ("latte", "pour_over", "cold_drip", "moka_pot"):
            got |= set(st.record(dict(cup, drink=d, title=d), []))
        assert "all_methods" not in got
        assert "all_methods" in st.record(dict(cup, drink="siphon", title="siphon"), [])
    finally:
        if st.db is not None:
            st.db.close()
