"""營業模式：大中小杯、一張單點好幾杯（一起交付）"""
from cafe_desk import orders
from cafe_desk.orders import Order, order_params


def _biz(desk):
    desk.set_order_mode(True)
    desk.arrive_in = 1e9                              # 測試中不來新客人
    desk.queue.clear()


def test_sizes_scale_cup_milk_and_shot(desk):
    _biz(desk)
    small = order_params(Order(1, "Amy", "latte", [], size="S"), desk.dp)
    large = order_params(Order(2, "Ken", "latte", [], size="L"), desk.dp)
    assert small.milk_g < desk.dp.milk_g < large.milk_g
    assert order_params(Order(3, "Joe", "espresso", [], size="L"), desk.dp).milk_g == desk.dp.milk_g, "濃縮沒有杯量"
    assert Order(4, "Mia", "latte", [], size="L").title.startswith("大杯")
    o = Order(5, "Ivy", "latte", [], price=140, patience=999, size="L")
    desk.order = o
    desk.start_order(o)
    assert desk.cup.size == "L" and desk.session.params.dose == 21.0, "大杯多一份濃縮"
    big_top = desk.cup.TR - desk.cup.TL
    while desk.making():
        desk.step(0.05, 0.5)
    desk.reset_cup("latte")
    assert desk.cup.TR - desk.cup.TL < big_top


def test_party_delivered_together(desk):
    _biz(desk)
    a = Order(1, "Amy", "latte", [], price=120, patience=999)
    b = Order(2, "Amy", "americano", [], price=90, patience=999)
    a.party = b.party = [a, b]
    desk.order = a
    desk.queue.append(b)
    desk.start_order(a)
    shelf = deliveries = 0
    n = 0
    while desk.busy() or b.state == "waiting":
        if desk.ready:
            shelf = max(shelf, len(desk.ready))
        if desk.delivery is not None and desk.delivery["phase"] == "place":
            deliveries = max(deliveries, sum(len(p["cups"]) for p in desk.delivery["parties"]))
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.0)
        n += 1
        if n % 60 == 0:
            desk.host.grab()
        assert n < 12000
    assert shelf == 1, "第一杯放出餐架等第二杯"
    assert deliveries == 2, "兩杯一起到櫃檯"
    assert b.state in ("done", "leaving") and desk.stats.data["order_total"] == 2


def test_party_walks_out_together(desk):
    _biz(desk)
    a = Order(1, "Amy", "latte", [], price=120, patience=10, paid=False)
    b = Order(2, "Amy", "latte", [], price=120, patience=10, paid=False)
    c = Order(3, "Ken", "espresso", [], price=70, patience=999, paid=False)
    a.party = b.party = [a, b]
    desk.order = a
    desk.queue += [b, c]
    desk.busy = lambda: True
    desk.update_queue(20.0)
    assert a.state == "leaving" and desk.queue == [c], "兩杯一起取消"
    assert desk.people() == 1


def test_party_size_mean():
    assert 1.2 < orders.PARTY_MEAN < 1.4


def test_seats_grow_with_level_and_force_to_go_when_full(desk, monkeypatch):
    """座位依店鋪等級增加；坐滿了想內用的新客人只能外帶，交付後內用客人去坐"""
    from cafe_desk import growth, orders
    assert growth.seats(1) == 4 and growth.seats(growth.MAX_LEVEL) == 16
    assert all(growth.seats(lv) % 2 == 0 for lv in range(1, growth.MAX_LEVEL + 1)), "兩人桌：一律雙數"
    assert all(growth.seats(lv) <= growth.seats(lv + 1) for lv in range(1, growth.MAX_LEVEL))
    desk.set_mode("business")
    desk.queue.clear()
    desk.order = None
    desk.seated = [999.0] * desk.seats()
    monkeypatch.setattr(orders, "TO_GO_P", 0.0)        # 每位都想內用
    desk.new_order()
    assert all(o.to_go for o in desk.order.party or [desk.order]), "坐滿了只能外帶"
    desk.seated = []
    desk.order = None
    desk.new_order()
    assert not desk.order.to_go
    assert desk.free_seats() == desk.seats() - len(desk.order.party or [desk.order])   # 還沒交付的內用先保留座位


def test_to_go_cups_paper_hot_plastic_iced_dine_in_glass(desk):
    """外帶熱飲紙杯、外帶冰飲塑膠杯；內用一律玻璃杯"""
    from cafe_desk.cups import CUP_KINDS, paper_kind
    assert paper_kind("latte").startswith("paper_") and paper_kind("iced") == "plastic_iced"
    assert CUP_KINDS["plastic_iced"]["cap"] == CUP_KINDS["iced"]["cap"]
    desk.set_mode("business")
    desk.reset_cup("iced_latte", to_go=True)
    assert desk.cup.plastic and not desk.cup.paper
    desk.reset_cup("iced_latte", to_go=False)
    assert desk.cup.kind == "iced" and not desk.cup.plastic
    desk.reset_cup("latte", to_go=False)
    assert not desk.cup.paper and not desk.cup.plastic


def test_score_revealed_after_checkout(desk):
    """營業模式：做好時先不評分（點單紙寫等待結帳、不記紀錄），到櫃檯結帳完才公布分數並寫進紀錄；好幾杯看平均"""
    _biz(desk)
    a = Order(1, "Amy", "latte", [], price=120, patience=999)
    b = Order(2, "Amy", "americano", [], price=90, patience=999)
    a.party = b.party = [a, b]
    desk.order = a
    desk.queue.append(b)
    desk.start_order(a)
    before = desk.result
    seen_hidden = False
    n = 0
    while desk.busy() or b.state == "waiting":
        if a.state in ("done", "leaving") and not a.revealed:
            seen_hidden = True
            assert desk.stats.data["order_total"] == 0, "結帳前不記紀錄"
            assert desk.result is before, "結帳前狀態列不顯示這杯的分數"
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.0)
        n += 1
        assert n < 12000
    assert seen_hidden and a.revealed and b.revealed
    assert desk.stats.data["order_total"] == 2
    assert abs(desk.result.score - (a.score + b.score) / 2) < 0.01, "好幾杯：狀態列顯示平均"


def test_cup_layer_redraws_for_size(desk):
    """同一種杯子換了大中小也要重畫圖層（快取鍵含杯量）"""
    _biz(desk)
    desk.reset_cup("latte", to_go=True, size="L")
    desk.host.grab()
    big = desk._layer_key
    desk.reset_cup("latte", to_go=True, size="S")
    desk.host.grab()
    assert desk._layer_key != big
    s, l = __import__("cafe_desk.cups", fromlist=["Cup"]).Cup("latte", 0, 100, "S"), \
        __import__("cafe_desk.cups", fromlist=["Cup"]).Cup("latte", 0, 100, "L")
    assert (l.B - l.T) / (s.B - s.T) > 1.4, "大杯比小杯高很多，一眼看得出來"


def test_review_hides_after_a_while(desk):
    """營業模式：客人的評價在狀態列顯示一陣子就收起來，回到等待客人點單"""
    import time
    from cafe_desk.render.shop import RESULT_SHOW
    _biz(desk)
    a = Order(1, "Amy", "latte", [], price=120, patience=999)
    desk.order = a
    desk.start_order(a)
    n = 0
    while desk.busy():
        desk.step(0.05, 0.5)
        n += 1
        assert n < 12000
    assert a.revealed and any("Amy" in t for t, _c in desk.status_parts())
    desk.result_until = time.perf_counter() - 1       # 時間到了
    assert desk.status_parts()[0][0] != desk.result.comment and "Amy" not in desk.status_parts()[0][0]
    assert RESULT_SHOW >= 5


def test_party_stays_at_machine_between_cups(desk):
    """一張單好幾杯：第一杯做好放出餐架後，咖啡師留在咖啡機前直接做下一杯，不切回櫃檯"""
    _biz(desk)
    a = Order(1, "Amy", "latte", [], price=120, patience=999)
    b = Order(2, "Amy", "americano", [], price=90, patience=999)
    a.party = b.party = [a, b]
    desk.order = a
    desk.queue.append(b)
    desk.start_order(a)
    gap = n = 0
    while desk.busy() or b.state == "waiting":
        if a.state in ("done", "leaving") and b.state == "waiting":
            gap += 1
            assert not desk.counter_view, "同一張單還沒做完：留在咖啡機前"
        desk.step(0.05, 0.5)
        desk.update_order(0.05, 0, 0.0)
        n += 1
        assert n < 12000
    assert gap * 0.05 < 2.0, "下一杯直接接著做（不等 4 秒讓位＋2.5 秒接單）"


def test_counter_showcase_machine_and_pending_pos(desk, unlocked):
    """營業用咖啡機：指定的那台做飲品也畫在後檯（auto＝隨機，後檯畫目前的）；客人剛點單時 POS 顯示點了什麼，不畫點單紙"""
    _biz(desk)
    desk.set_showcase("lever")
    assert desk.showcase_machine().key == "lever"
    assert all(desk.business_machine() == "lever" for _ in range(20)), "指定的營業用咖啡機：做飲品也用這台"
    desk.set_showcase("auto")
    assert desk.showcase_machine() is desk.machine
    o = Order(1, "Amy", "latte", [], price=120, patience=999, paid=False)
    desk.order = o
    pend = desk.pos_pending()
    assert pend and pend["orders"] == [o] and pend["price"] == 120
    for _ in range(3):
        desk.step(0.05, 0.05)
    assert desk.counter_view
    desk.host.grab()


def test_checkout_before_making_and_paid_customers_stay(desk):
    """先點單付錢：咖啡師接單時先在櫃檯結帳（排隊裡還沒付的一組一組刷卡），結完才開始做；付了錢的客人不會等不及走掉"""
    _biz(desk)
    desk.arrive_in = 1e9
    a = Order(1, "Amy", "latte", [], price=120, patience=999, paid=False)
    b = Order(2, "Ken", "espresso", [], price=70, patience=30, paid=False)
    desk.order = a
    desk.queue.append(b)
    seen_ck, floats, n = False, False, 0
    while a.state == "waiting":
        if desk.checkout is not None:
            seen_ck = True
            assert desk.counter_view and not desk.making(), "結帳時在櫃檯，還沒開始做"
        floats = floats or bool(desk.reg_floats)
        desk.step(0.05, 0.05)
        n += 1
        assert n < 4000
    assert seen_ck and floats and a.paid and b.paid, "排隊的那一組也一起結帳"
    desk.update_queue(60.0)
    assert b in desk.queue and b.state == "waiting", "付了錢就不會走"


def test_order_number_counts_cups_today(desk, monkeypatch):
    """點單紙左上角是今天第幾杯：同一天接著數，換日從 1 重算"""
    _biz(desk)
    desk.order, desk.queue = None, []
    desk.order_no, desk.order_day = 5, "2026-07-31"
    desk.new_order()
    first = desk.order
    assert first.no == 1, "換日從 1 開始"
    n = len(first.party or [first])
    desk.order = None
    desk.new_order()
    assert desk.order.no == n + 1, "同一天接著數"
    monkeypatch.setenv("CAFE_DESK_DATE", "2026-08-02")
    desk.order = None
    desk.new_order()
    assert desk.order.no == 1 and desk.order_day == "2026-08-02"
