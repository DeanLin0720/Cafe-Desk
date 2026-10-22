"""1.3.0 已知小問題的修正：滴水盤水位、英文長品名、逆洗時拿走杯子、紀錄時間戳"""
import datetime

from PySide6.QtGui import QFont, QFontMetricsF, QImage, QPainter

from cafe_desk import stats
from cafe_desk.drinks import DRINKS
from cafe_desk.i18n import set_lang
from cafe_desk.machines import MACHINES
from cafe_desk.orders import Order
from conftest import run_until_idle


def test_drip_slots_inside_tray():
    """水位畫在格柵縫隙裡：每台的縫隙都在滴水盤範圍內、間距 7"""
    for m in MACHINES.values():
        x1, x2, _ = m.drip_area
        xs = list(m.drip_slots())
        assert xs and x1 < xs[0] and xs[-1] < x2
        assert all(b - a == 7 for a, b in zip(xs, xs[1:]))
    assert MACHINES["desk01"].drip_slots()[0] == 46          # DESK·01 自己畫的縫隙從 46 開始


def test_drip_water_paints(desk):
    desk.maint["drip"] = 360
    desk.host.grab()


def _big(desk):
    big = QFont(desk.ui, 9)
    big.setBold(True)
    return big


def _title_height(desk, text, w):
    img = QImage(400, 100, QImage.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    h = desk.fit_title(p, 0, 0, w, text, _big(desk))
    p.end()
    return h


def test_long_english_title_wraps(desk):
    """英文長品名斷成兩行；短的維持一行（高度 16，跟改版前一樣）。
    寬度依字型實際量（無頭環境沒有字型，每個字都是固定寬度的方框）"""
    w = QFontMetricsF(_big(desk)).horizontalAdvance("Spice Latte") + 1
    assert _title_height(desk, "Latte", w) == 16
    assert _title_height(desk, "拿鐵", w) == 16
    assert _title_height(desk, "Oat Pumpkin Spice Latte", w) > 16
    assert _title_height(desk, "Pumpkinspicelatte", w) == 16         # 單一個字斷不開：縮字加刪節號


def test_order_card_english(desk):
    set_lang("en")
    try:
        desk.order = Order(no=3, name="Mia", drink=next(k for k in DRINKS if "pumpkin" in k),
                           mods=[("milk", "oat"), ("temp", "low"), ("foam", "more")])
        desk.order_alpha = 1.0
        desk.host.grab()
    finally:
        set_lang("zh")


def test_backflush_takes_cup_away(desk):
    desk.contents["water"] = 30.0
    assert desk.start_job("backflush")
    assert desk.cupless() and desk.contents["water"] == 0, "逆洗時杯子（連同上一杯）拿走"
    desk.host.grab()
    assert desk._layer_key[-1] is True
    run_until_idle(desk)
    assert not desk.cupless() and desk._layer_key[-1] is False
    assert desk.maint["backflush"] == 0


def test_wand_job_keeps_cup(desk):
    desk.contents["water"] = 30.0
    assert desk.start_job("wand")
    assert not desk.cupless() and desk.contents["water"] == 30.0


def test_stamp_follows_fake_date():
    """紀錄的 ts 日期跟 day 一致（conftest 固定 2026-08-01）"""
    ts = datetime.datetime.fromisoformat(stats.stamp())
    assert ts.date() == datetime.date(2026, 8, 1)


def test_paper_theme(desk):
    """右鍵、系統匣選單與各視窗都套用紙張風格；成就頁是收據"""
    from cafe_desk import theme
    from cafe_desk.records import RecordsDialog, Receipt
    assert theme.SHEET in desk.menu.styleSheet()
    if desk.tray:
        assert theme.SHEET in desk.tray_menu.styleSheet()
    desk.open_settings()
    desk.open_about()
    assert theme.PAPER in desk.settings_dlg.styleSheet() and theme.PAPER in desk.about_dlg.styleSheet()
    dlg = RecordsDialog(desk)
    assert theme.PAPER in dlg.styleSheet() and dlg.findChild(Receipt) is not None
    dlg.grab()
    for d in (dlg, desk.settings_dlg, desk.about_dlg):
        d.close()


def test_tick_during_every_station_flow(desk):
    """每一種沖煮台流程都用 tick() 跑過（音效判斷在 tick 裡）：冰滴倒杯時 session.station 是 None 不能出錯"""
    from cafe_desk import brew
    p = desk.params
    desk.cold = brew.new_cold_batch(desk.dp, p.roast, p.bean_age, desk.bag["origin"], now=0)
    desk.cold.update(done=True, servings=brew.COLD_SERVINGS)
    for drink in ("cold_drip", "pour_over", "moka_pot", "siphon"):
        assert desk.start_session(drink, False)
        n = 0
        while desk.busy():
            desk.step(0.05, 0.5)
            desk.tick()
            n += 1
            assert n < 8000


def test_saved_text_follows_language():
    """紀錄存的是做那杯時的語言；切換語言後最近幾杯、今天最好的一杯要跟著換（兩個方向都要）"""
    from cafe_desk import orders
    from cafe_desk.i18n import retext
    set_lang("zh")
    saved = ["阿明：" + orders.reaction(70, "等有點久"), "Ivy：" + orders.reaction(70, "葉子糊糊的"),
             "阿凱：" + orders.reaction(85, "等有點久"), "Ken：" + orders.reaction(75, ""), "美式", "燕麥拿鐵"]
    try:
        set_lang("en")
        en = [retext(s) for s in saved]
        assert en == ["Ming: Took a while, it's OK.", "Ivy: The Rosetta is smudged, it's OK.",
                      "Kai: Took a while, but tasty!", "Ken: Not bad.", "Americano", "Oat Latte"]
        set_lang("zh")
        assert [retext(s) for s in en] == saved
        assert retext("沒翻譯的字") == "沒翻譯的字"
    finally:
        set_lang("zh")


def test_barista_temps_are_tidy(desk):
    """營業中咖啡師調的手沖溫度是 0.5°C 一格，狀態列不會出現 96.1161°C"""
    import random as _r
    from cafe_desk import brew
    rnd = _r.Random(5)
    for roast in ("淺焙", "中焙", "深焙"):
        for _ in range(20):
            d = brew.barista_dial(desk.dp, roast, rnd)
            assert d.po_temp * 2 == int(d.po_temp * 2)
