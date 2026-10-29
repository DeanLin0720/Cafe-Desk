"""營業用雙頭機：萃取時同時打奶、營業中成對做兩杯、第二杯的狀態對調（on_twin）"""
import random

import pytest

from cafe_desk import growth
from cafe_desk.machines import duo as duo_mod
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


def test_black_pair_and_milk_rules(desk, unlocked):
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
    assert desk.pair is not None and o4.state == "making", "冰飲也能配對：一杯打奶、一杯加冰倒冷牛奶"
    run_until_idle(desk)
    assert o3.state == "done" and o4.state == "done" and desk.pair is None
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


def test_second_cup_still_drawn_after_first_leaves(desk, unlocked):
    """成對做不同飲品、不同大小：第一杯先做好送走（cup_away）時，第二個杯位的杯子照樣畫（以前玻璃不見、只剩液體）；
    雙頭機往左移讓出右邊倒入的空間，但不切到機身"""
    desk.set_machine("duo")
    o1, o2 = _business_pair(desk, "latte", "cappuccino", [("cocoa", "no")])
    o2.size = "S"
    desk.start_order(o1)
    assert desk.pair is not None
    n = 0
    while not (desk.cup_away and desk.twin_live()):
        desk.step(0.05, 0.25)
        n += 1
        assert n < 8000, "第一杯先送走、第二杯還在做"
    drawn = []
    cup2 = desk.twin["cup"]
    orig = cup2.paint_back
    cup2.paint_back = lambda p: (drawn.append(1), orig(p))
    desk.bg_layer = None
    desk.host.grab()
    assert drawn, "第二杯的杯子要畫"
    assert desk.machine.hover_area[0] + desk.scene_dx() >= 11.9, "機身往左移讓出右邊倒入的空間，但不切到機身"


MIXED = [("espresso", "latte"), ("latte", "espresso"), ("americano", "mocha"), ("iced_americano", "cappuccino"),
         ("affogato", "flat_white"), ("espresso_tonic", "caramel_macchiato"), ("mocha", "iced_latte"),
         ("cortado", "doppio")]


@pytest.mark.parametrize("d1, d2", MIXED)
def test_mixed_pairs_make_both_drinks(desk, unlocked, d1, d2):
    """凡是義式飲品都能成對：不同類的兩杯各自做前置與後製，各自評分、各自記一杯"""
    desk.set_machine("duo")
    o1, o2 = _business_pair(desk, d1, d2, [("cocoa", "no")] if "cappuccino" in (d1, d2) else ())
    desk.start_order(o1)
    assert desk.pair is not None and o2.state == "making"
    phases, n = [], 0
    while desk.busy():
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.5)
        if desk.pair is not None and (not phases or phases[-1] != desk.pair.phase):
            phases.append(desk.pair.phase)
        n += 1
        if n % 80 == 0:
            desk.host.grab()
        assert n < 12000, "卡住了"
    assert phases == ["a_pre", "b_pre", "brew", "a_post", "b_post"]
    assert o1.state in ("done", "leaving") and o2.state in ("done", "leaving")
    assert o1.score > 0 and o2.score > 0 and desk.stats.data["order_total"] == 2


def test_two_milk_drinks_need_shared_pitcher(desk, unlocked):
    """蒸氣管只有一支：兩杯都要打奶時，能共用一壺（拿鐵＋馥列白）才配對；摩卡＋拿鐵、不同的奶都不配對"""
    desk.set_machine("duo")
    for d1, d2, mods2, ok in (("latte", "flat_white", (), True), ("mocha", "latte", (), False),
                              ("latte", "latte", [("milk", "oat")], False), ("caramel_macchiato", "mocha", (), False)):
        desk.queue.clear()
        desk.order = None
        o1, o2 = _business_pair(desk, d1, d2, mods2)
        desk.start_order(o1)
        assert (desk.pair is not None) == ok, (d1, d2)
        run_until_idle(desk)


def _dual(desk):
    from cafe_desk import store
    desk.stats.data["owned"].append("duo_dualwand")
    store.apply_upgrades(desk.stats.data["owned"])
    desk.apply_traits()


def test_dual_wand_upgrade_lets_two_milk_drinks_pair(desk, unlocked):
    """「雙打奶泡」（第二支蒸氣管）：兩杯熱牛奶飲品各用一支蒸氣管同時打奶，摩卡＋燕麥拿鐵這種共用不了一壺的也能一起做"""
    from cafe_desk import store
    desk.set_machine("duo")
    assert not desk.machine.traits.dual_wand
    o1, o2 = _business_pair(desk, "mocha", "latte", [("milk", "oat")])
    desk.start_order(o1)
    assert desk.pair is None, "沒有升級：只有一支蒸氣管，不能一起打"
    run_until_idle(desk)
    desk.queue.clear()
    desk.order = None
    before = desk.stats.data["order_total"]
    _dual(desk)
    try:
        assert desk.machine.traits.dual_wand and store.UPGRADES["duo_dualwand"][3] > 0
        left, right = desk.machine.wand_steam, None
        with desk.on_twin():
            right = desk.machine.wand_steam
        assert right[0] > left[0] and right[0] == 20 + duo_mod.R - left[0], "第二支在右邊（鏡射）"
        o1, o2 = _business_pair(desk, "mocha", "latte", [("milk", "oat")])
        desk.start_order(o1)
        assert desk.pair is not None and o2.state == "making"
        both, n = False, 0
        while desk.busy():
            desk.step(0.05, 0.5)
            desk.update_order(0.05, 0, 0.5)
            a, b = desk.pair.a if desk.pair else None, desk.pair.b if desk.pair else None
            if a and b and a.stage_name == "steam" and b.stage_name == "steam":
                both = True
            n += 1
            if n % 80 == 0:
                desk.host.grab()
            assert n < 12000
        assert both, "兩支蒸氣管同時打奶"
        assert o1.score > 0 and o2.score > 0 and desk.stats.data["order_total"] == before + 2
        assert desk.twin["wand_angle"] == 0.0 and desk.wand_angle == 0.0
    finally:
        from cafe_desk import store as st
        st.apply_upgrades([])


def test_single_wand_still_animates_for_second_cup(desk, unlocked):
    """只有一支蒸氣管：第二杯要打奶時（第一杯是黑咖啡）那支蒸氣管也會動——角度每杯各一份之後，畫的時候取兩杯較大的"""
    desk.set_machine("duo")
    o1, o2 = _business_pair(desk, "espresso", "latte")
    desk.start_order(o1)
    assert desk.pair is not None
    seen, n = 0.0, 0
    while desk.busy():
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.5)
        seen = max(seen, desk.twin["wand_angle"])
        n += 1
        if n % 60 == 0:
            desk.host.grab()
        assert n < 12000
    assert seen > 0.9


def test_duo_uses_a_separate_commercial_grinder(desk, unlocked):
    """營業用雙頭機的磨豆機是獨立的一台（營業用外觀、兩頭共用），不是內建的：備粉走獨立磨豆機的流程，兩杯依序用同一台磨豆機"""
    from cafe_desk import store
    from cafe_desk.machines import MACHINES
    m = MACHINES["duo"]
    assert m.traits.grinder == "external" and m.grinder_style == "commercial"
    assert not hasattr(m, "hopper") and m.knock_box == MACHINES["desk01"].knock_box, "沒有內建豆倉；敲渣盒跟其他獨立磨豆機一樣"
    desk.set_machine("duo")
    assert desk._grinder_style() == "commercial"
    assert m.mx > 100, "機身右移讓出左邊的磨豆機"
    desk.set_machine("desk01")
    assert desk._grinder_style() == "standard"
    desk.set_machine("duo")
    grinding = []
    o1, o2 = _business_pair(desk, "latte", "americano")
    desk.start_order(o1)
    assert desk.pair is not None
    n = 0
    while desk.busy():
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.5)
        wf1 = desk.workflow
        wf2 = desk.twin_get("workflow")
        if (wf1 and wf1.grinding) or (wf2 and wf2.grinding):
            grinding.append(bool(wf1 and wf1.grinding) + bool(wf2 and wf2.grinding))
        n += 1
        if n % 60 == 0:
            desk.host.grab()
        assert n < 12000
    assert grinding and max(grinding) == 1, "兩杯依序磨豆，沒有同時用同一台磨豆機"
    assert o1.score > 0 and o2.score > 0
    assert store.UPGRADES["duo_burr"][0] == store.COMMERCIAL and "duo" in store.COMMERCIAL
    assert store.target_name("duo_burr") == "營業用磨豆機"


def test_commercial_grinder_upgrade_still_applies_to_the_duo(desk):
    from cafe_desk import store
    from cafe_desk.machines import MACHINES
    base = type(MACHINES["duo"]).traits.channel_add
    store.apply_upgrades(["duo_burr"])
    try:
        assert abs(MACHINES["duo"].traits.channel_add - (base - 0.04)) < 1e-9
        assert store.upgraded("duo", ["duo_burr"]) and not store.upgraded("allinone", ["duo_burr"])
        assert store.upgrade_names("duo", ["duo_burr"]) == ["營業級平刀盤"]
    finally:
        store.apply_upgrades([])


def test_duo_layout_has_gaps_and_ingredient_rack(desk, unlocked, monkeypatch):
    """磨豆機（連敲渣盒）不壓到機身；出杯台的玻璃杯離機身遠一點；上方的架子是配料架、做好的杯子不再放那裡"""
    from cafe_desk.machines import MACHINES
    from cafe_desk.render import shop
    m = MACHINES["duo"]
    kb = m.knock_box
    assert m.mx + 16 >= kb[2], "機身底座左緣在敲渣盒右邊，不重疊"
    assert m.side_gap > MACHINES["desk01"].side_gap
    desk.set_machine("duo")
    desk.set_order_mode(True)
    x0 = desk.side_spot(0)[0]
    assert x0 - m.scene_w == m.side_gap and desk.side_spot(1)[0] - x0 == shop.SIDE_W2
    assert desk.scene_dx() >= -1, "磨豆機不會被視窗切掉"
    racks = []
    orig = shop.paint_ingredient_rack
    monkeypatch.setattr(shop, "paint_ingredient_rack", lambda *a, **k: (racks.append(a[1:]), orig(*a, **k)))
    desk.bg_layer = None
    desk.host.grab()
    assert racks and racks[0][2] == shop.SHELF_Y, "出杯台上方是配料架"
    pass_cups = []
    desk.ready = [{"img": None}]
    monkeypatch.setattr(desk, "paint_ready_cup", lambda *a, **k: pass_cups.append(1))
    from PySide6.QtGui import QImage, QPainter
    img = QImage(1100, 600, QImage.Format_ARGB32_Premultiplied)
    pt = QPainter(img)
    desk.paint_pass_cups(pt)
    pt.end()
    desk.ready = []
    assert not pass_cups, "咖啡機畫面不再把做好的杯子放在上面的架子"


def test_finished_cups_wait_on_the_counter(desk, qapp, monkeypatch):
    """多杯的單做好一杯：杯子先放在櫃檯上等（櫃檯畫面看得到），整張單都好了才交付"""
    from cafe_desk.render import shop
    desk.set_order_mode(True)
    for _ in range(40):
        desk.step(0.05, 0.05)
    desk.counter_view = True
    drawn = []
    monkeypatch.setattr(desk, "paint_ready_cup", lambda p, c, x, base, alpha=1.0: drawn.append((c["tag"], x, base)))
    cup = {"img": None, "off": (0, 0), "top": 70, "h": 80, "to_go": False, "handle": True, "paper": None, "iced": False,
           "z": (1, 1), "order": None, "tag": 1}
    desk.ready = [dict(cup, tag=1), dict(cup, tag=2)]
    desk.host.grab()
    assert [d[0] for d in drawn] == [1, 2] and drawn[0][1:] == (0.0, 0.0), "兩杯從左邊排起、縮小站在櫃檯上"
    drawn.clear()
    desk.ready = []
    desk.host.grab()
    assert not drawn


def test_counter_back_scene_keeps_machine_view_proportions(desk, qapp):
    """櫃檯畫面的後檯：獨立磨豆機、咖啡機、右邊的配料架照咖啡機畫面的比例畫成同一張圖再整張縮小（不是各畫各的）"""
    from cafe_desk.machines import MACHINES
    from cafe_desk.render import gear_icons
    from cafe_desk.render.shop import SHELF_Y, SIDE_W, SIDE_W2
    for key in ("duo", "desk01", "allinone"):
        m = MACHINES[key]
        img, mach, ground = gear_icons.scene_image(desk, m)
        assert mach.y() < ground <= mach.y() + mach.height(), "站在桌上的線在機身範圍內（磨豆機底座比機身底低一點）"
        assert img.rect().contains(mach) and mach.height() > 200
        if m.traits.grinder == "external":
            assert mach.x() > 80, "磨豆機在機身左邊"
        side = SIDE_W + (SIDE_W2 if m.traits.groups > 1 else 0) + (m.side_gap - 66)
        assert img.width() >= mach.x() + mach.width() + side * 0.8, "機身右邊有配料架那麼寬"
        assert img.height() < gear_icons.SCENE_H
    img = desk.showcase_image(MACHINES["duo"])[0]
    assert desk.showcase_image(MACHINES["duo"])[0] is img, "快取"


@pytest.mark.parametrize("key", ["desk01", "lever", "compact", "allinone", "duo"])
def test_every_showcase_machine_stands_on_the_back_counter(desk, qapp, key):
    """櫃檯畫面後檯：每一台咖啡機（與它的磨豆機）都站在桌面上（桌面 bt～bt+10），不浮在上面也不沉進抽屜，也不蓋到窗與 POS"""
    from cafe_desk.machines import MACHINES
    from cafe_desk.render import shop
    m = MACHINES[key]
    W, bt = desk._scene_w, shop.COUNTER_TOP - 64
    sel = desk.decor_look()[0]
    img, rect = desk.showcase_place(m, sel, W, bt)
    _img, mach, ground = desk.showcase_image(m)
    k = rect.width() / img.width()
    machine_bottom = rect.top() + (mach.y() + mach.height() - 4) * k
    base_line = rect.top() + ground * k
    assert bt <= base_line <= bt + 10, "站在桌面上的那條線（磨豆機底座的底／沒有磨豆機的機身底）在桌面範圍內"
    assert bt <= machine_bottom <= bt + 14, "機身底座也在桌面上（比磨豆機底座稍低一點，像在前面）"
    assert rect.left() >= 140 and rect.right() <= desk.pos_x(W) - 75, "不蓋到窗，也不蓋到 POS 螢幕"
    assert rect.height() * 1.0 < bt + 20, "不會頂到上面的菜單看板"


@pytest.mark.parametrize("key, base_bottom", [("desk01", 364), ("lever", 364), ("compact", 364), ("allinone", 366), ("duo", 366)])
def test_every_machine_base_stands_on_the_cup_plane(key, base_bottom):
    """咖啡機畫面：機身底座的底（機身座標 base_bottom）、出杯台杯子的墊子、奶泡機都在桌面 FLOOR 這個平面上，不是比杯子更靠前"""
    from cafe_desk.layout import FLOOR
    from cafe_desk.machines import MACHINES
    assert MACHINES[key].my + base_bottom == FLOOR


def test_cards_follow_the_group_being_made(desk, unlocked):
    """萃取曲線與拉花卡片在正在做的那個沖煮頭的杯子上方：做第二杯時往右移"""
    desk.set_machine("duo")
    left = desk.chart_rect().center().x()
    with desk.on_twin():
        right = desk.chart_rect().center().x()
    assert right - left > 150


def test_two_cups_show_two_chart_and_art_cards(desk, unlocked, monkeypatch):
    """兩個沖煮頭都有杯子：兩杯各一組曲線卡片與拉花卡片（窄版，左邊那杯的在左、右邊那杯的在右，不互相重疊）"""
    import time
    from cafe_desk.render import overlay
    desk.set_machine("duo")
    o1, o2 = _business_pair(desk, "latte", "flat_white")
    random.seed(4)
    desk.make_order()
    seen = False
    for n in range(6000):
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.5)
        desk.hover, desk.hover_since = True, time.perf_counter() - 5
        if desk.pair is not None and desk.pair.phase == "a_post" and desk.card_alpha > 0.9:
            left = [desk.chart_rect(), desk.art_rect(True)]
            with desk.on_twin():
                right = [desk.chart_rect(), desk.art_rect(True)]
                assert desk.card_alpha > 0.5, "第二杯也有自己的卡片"
            assert left[1].right() < right[0].left(), "兩組不重疊"
            desk.host.grab()
            seen = True
            break
        if not desk.busy():
            break
    assert seen
