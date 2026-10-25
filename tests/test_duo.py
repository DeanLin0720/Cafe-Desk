"""營業用雙頭機：萃取時同時打奶、營業中成對做兩杯、第二杯的狀態對調（on_twin）"""
import random

import pytest

from cafe_desk import growth
from cafe_desk.drinks import DrinkParams, pair_kind
from cafe_desk.orders import Order

from conftest import run_until_idle


def test_unlocks_at_level_9(desk):
    assert growth.MACHINE_LEVEL["duo"] == 9 and growth.unlocked_at(9) == [("machine", "duo")]
    assert not desk.machine_open("duo")


def test_pair_kind():
    assert pair_kind("espresso") == pair_kind("americano") == "black"
    assert pair_kind("latte") == pair_kind("flat_white") == pair_kind("macchiato") == "milk"
    for k in ("iced_latte", "mocha", "caramel_macchiato", "affogato", "espresso_tonic", "pour_over"):
        assert pair_kind(k) is None, k
    dp = DrinkParams()
    dp.cocoa = True
    assert pair_kind("cappuccino", dp) is None, "要撒可可粉的卡布奇諾不配對"
    dp.cocoa = False
    assert pair_kind("cappuccino", dp) == "milk"


def test_on_twin_swaps_and_restores(desk, unlocked):
    desk.set_machine("duo")
    assert desk.twin is not None and desk.twin["cup"] is None
    cup, contents = desk.cup, desk.contents
    a_x = desk.cup_anchor()[0]
    with desk.on_twin():
        assert desk.machine.g == 1 and desk.cup is None
        assert desk.cup_anchor()[0] > a_x, "第二杯在右邊的沖煮頭下"
        desk.reset_cup("latte")
        twin_cup = desk.cup
    assert desk.machine.g == 0 and desk.cup is cup and desk.contents is contents
    assert desk.twin["cup"] is twin_cup, "在 on_twin 裡換的杯子留在 twin"
    desk.set_machine("desk01")
    assert desk.twin is None, "單頭機沒有第二個沖煮頭"


def test_single_cup_steams_while_brewing(desk, unlocked):
    """雙頭機做一杯拿鐵：萃取的同時打奶，比單頭機快"""
    def timed(machine):
        desk.set_machine(machine)
        desk.boiler.temp = desk.params.temp
        assert desk.start_session("latte", True)
        n, both = 0, False
        while desk.busy():
            desk.step(0.05, 0.5)
            n += 1
            ss = desk.session
            if ss and desk.brewing() and ss.stage_name == "steam":
                both = True
            assert n < 8000
        desk.host.grab()
        return n, both
    n_lever, both_lever = timed("lever")
    n_duo, both_duo = timed("duo")
    assert both_duo and not both_lever
    assert n_duo < n_lever * 0.8
    assert desk.stats.data["collection"]["machine_best"].get("duo"), "紀錄記在雙頭機名下"


def _business_pair(desk, d1, d2, mods2=()):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9                              # 測試中不來新客人
    desk.queue.clear()
    o1 = Order(1, "Amy", d1, [], price=120, patience=999)
    o2 = Order(2, "Ken", d2, list(mods2), price=120, patience=999)
    desk.order = o1
    desk.queue.append(o2)
    return o1, o2


def test_business_prefers_duo_and_makes_two(desk, unlocked):
    desk.set_machine("desk01")
    o1, o2 = _business_pair(desk, "latte", "flat_white")
    random.seed(4)
    desk.make_order()                                  # 後面有人點同類：換雙頭機
    assert desk.machine.key == "duo" and desk._switch_wait is not None
    phases = []
    n = 0
    while desk.busy():
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.5)
        if desk.pair is not None and (not phases or phases[-1] != desk.pair.phase):
            phases.append(desk.pair.phase)
        n += 1
        if n % 60 == 0:
            desk.host.grab()
        assert n < 8000, "卡住了"
    assert phases == ["a_pre", "b_pre", "brew", "a_post", "b_post"]
    assert o1.state in ("done", "leaving") and o2.state in ("done", "leaving")
    assert o2.wait == o1.wait, "一起做的第二位開始做之後不再累計等待"
    cups = desk.stats.data["order_total"]
    assert cups == 2
    assert desk.twin["contents"]["milk"] > 50 and desk.contents["milk"] > 50, "兩杯都倒好奶"
    assert desk.cup_away and desk.twin["cup"] is None, "營業中做好的兩杯都送去收銀台"
    assert desk.delivery is None and not desk.pending_deliveries and desk.counter_view == desk.idle_counter(), "兩杯都交付了"
    assert desk.stats.unlocked("duo_pair")


def test_business_always_uses_duo_once_unlocked(desk, unlocked):
    """解鎖後營業中點義式一律用雙頭機，後面沒有同類的客人也一樣（一次一杯）"""
    desk.set_machine("lever")
    desk.set_order_mode(True)
    desk.queue.clear()
    o = Order(1, "Amy", "espresso", [], price=70, patience=999)
    desk.order = o
    desk.make_order()
    assert desk.machine.key == "duo"
    run_until_idle(desk)
    assert o.state == "done" and desk.pair is None


def test_more_customers_once_duo_unlocked(desk, monkeypatch):
    """雙頭機解鎖後來客間隔乘 DUO_ARRIVAL_K"""
    from cafe_desk import orders
    monkeypatch.setattr(orders, "arrival_gap", lambda rnd=None, level=1: 100.0)
    desk.set_order_mode(True)
    desk.busy = lambda: True                          # 咖啡師不接單，只看來客
    desk.arrive_in = 0.0
    desk.update_queue(0.0)
    base = 100.0 * orders.PARTY_GAP                   # 一位客人平均點 1.3 杯、交付要等：間隔跟著拉長
    assert desk.arrive_in == pytest.approx(base)
    monkeypatch.setitem(growth.MACHINE_LEVEL, "duo", 1)
    desk.arrive_in = 0.0
    desk.update_queue(0.0)
    assert desk.arrive_in == pytest.approx(base * growth.DUO_ARRIVAL_K) and desk.arrive_in < base


def test_black_pair_and_no_pair_for_iced(desk, unlocked):
    desk.set_machine("duo")
    o1, o2 = _business_pair(desk, "espresso", "americano")
    desk.start_order(o1)
    assert desk.pair is not None and o2.state == "making"
    run_until_idle(desk)
    assert o1.state == "done" and o2.state == "done" and desk.pair is None
    desk.queue.clear()
    desk.order = None
    o3, o4 = _business_pair(desk, "latte", "iced_latte")
    desk.start_order(o3)
    assert desk.pair is None and o4.state == "waiting", "冰飲不配對，照舊一次一杯"
    run_until_idle(desk)
    desk.queue.clear()
    desk.order = None
    o5, o6 = _business_pair(desk, "latte", "cappuccino")
    desk.start_order(o5)
    assert desk.pair is None, "客人點的卡布奇諾要撒可可粉，不配對"
    run_until_idle(desk)
    desk.queue.clear()
    desk.order = None
    o7, o8 = _business_pair(desk, "latte", "cappuccino", [("cocoa", "no")])
    desk.start_order(o7)
    assert desk.pair is not None, "不要可可粉的卡布奇諾可以一起做"
    run_until_idle(desk)


def test_station_width_capped(desk, unlocked):
    """視窗一律 UNIFORM_W（16:9）；沖煮台最寬 STATION_W（不跟著雙頭機變寬），置中；雙頭機開營業也塞得下"""
    from cafe_desk.render.station import UNIFORM_W, STATION_W
    desk.set_machine("duo")
    assert desk._scene_w == UNIFORM_W
    desk.set_method("pourover")
    assert desk._scene_w == UNIFORM_W and desk.station_w() == STATION_W, "手沖器具不跟著雙頭機變寬"
    assert desk.scene_dx() == (UNIFORM_W - STATION_W) / 2, "沖煮台置中"
    desk.set_method("espresso")
    assert desk._scene_w == UNIFORM_W
    desk.set_mode("business")
    from cafe_desk.render.station import POUR_PAD
    assert desk._scene_w == UNIFORM_W, "16:9 塞得下雙頭機＋兩個杯位的出杯台"
    assert desk.scene_dx() + desk.machine.scene_w + desk.side_extra() + POUR_PAD <= UNIFORM_W + 1e-6


@pytest.mark.parametrize("key, ok", [("desk01", True), ("lever", True), ("allinone", True), ("compact", False)])
def test_master_barista_steams_while_brewing(desk, unlocked, monkeypatch, key, ok):
    """咖啡師「職人」以上：單頭機也萃取的同時打奶；單鍋爐要先加熱，不適用；還沒到職人照舊"""
    from cafe_desk.drinks import Together
    desk.set_machine(key)
    desk.start_session("latte", False)
    assert not any(isinstance(st, Together) for st in desk.session.stages), "新手照舊一步一步來"
    run_until_idle(desk)
    monkeypatch.setattr(desk, "together_open", lambda: True)
    desk.start_session("latte", False)
    assert any(isinstance(st, Together) for st in desk.session.stages) == ok
    run_until_idle(desk)
    assert desk.result is not None and desk.contents["milk"] > 0


def test_together_rank_is_master():
    assert growth.rank_name(growth.TOGETHER_RANK) == "職人"


def test_caramel_macchiato_steams_while_brewing_in_business(desk, monkeypatch):
    """營業模式（濃縮先到量杯）：焦糖瑪奇朵也萃取的同時打奶，先倒牛奶、最後才把量杯的濃縮倒在上面（分層不變）；
    手動模式濃縮直接進杯子，照舊先奶後咖啡"""
    from cafe_desk.drinks import Together, PourStage
    from cafe_desk.orders import Order
    monkeypatch.setattr(desk, "together_open", lambda: True)
    desk.start_session("caramel_macchiato", False)
    assert not any(isinstance(st, Together) for st in desk.session.stages)
    run_until_idle(desk)
    desk.set_order_mode(True)
    desk.arrive_in = 1e9
    o = Order(1, "Amy", "caramel_macchiato", [], price=140, patience=999)
    desk.order = o
    desk.start_order(o)
    st = desk.session.stages
    ti = next(i for i, s in enumerate(st) if isinstance(s, Together))
    milk = next(i for i, s in enumerate(st) if isinstance(s, PourStage) and s.vessel in ("pitcher", "jug"))
    jig = next(i for i, s in enumerate(st) if isinstance(s, PourStage) and s.vessel == "jigger")
    assert ti < milk < jig, "同時萃取與打奶 → 倒牛奶 → 量杯的濃縮倒在上面"
    n = 0
    while o.state in ("waiting", "making"):
        desk.step(0.05, 0.25)
        n += 1
        assert n < 8000
    assert o.score > 0


def test_chart_card_hidden_on_brew_station(desk, unlocked):
    """滑鼠停在咖啡機上時換到冰滴（滑鼠沒動）：萃取曲線卡片收起來，不會疊在冰滴塔上"""
    import time
    desk.hover, desk.hover_since = True, time.perf_counter() - 5
    for _ in range(20):
        desk.step(0.05, 0.05)
    assert desk.card_alpha > 0.5
    desk.set_drink("cold_drip")
    for _ in range(40):
        desk.step(0.05, 0.05)
    assert desk.method == "colddrip" and desk.card_alpha < 0.05
