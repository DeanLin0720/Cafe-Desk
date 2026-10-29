"""店面裝潢：款式資料、買（營業額／挑戰章數）、換上、畫面與商店頁、圖鑑收集"""
import pytest

from cafe_desk import decor, stats
from cafe_desk.i18n import EN


def _cash(desk, n=100000):
    desk.stats.data["revenue_total"] += n


def _stamps(desk, n):
    desk.stats.data["challenges"] += [f"d:x:{i}" for i in range(n)]


def test_items_are_consistent():
    for slot in decor.SINGLE:
        assert slot in decor.DEFAULTS and decor.is_default(decor.DEFAULTS[slot])
        assert sum(1 for v in decor.ITEMS.values() if v[0] == slot and v[2] == v[3] == 0) == 1, "每個欄位剛好一個預設款"
    for k, (slot, name, price, stamps, desc) in decor.ITEMS.items():
        assert slot in decor.SLOTS and not (price and stamps), "一款只能用錢或章數其中一種買"
        assert name in EN and desc in EN, k
        if slot in decor.MULTI:
            assert price or stamps, "掛畫與植物沒有預設款"
    assert all(s in EN for s in decor.SLOT_NAME.values())
    assert all(k in decor.LOOK or decor.ITEMS[k][0] in ("machine", "lighting", "cup", "pos", "paintings", "plants")
               or decor.is_default(k) for k in decor.ITEMS)
    assert all(k in decor.POS_LOOK for k, v in decor.ITEMS.items() if v[0] == "pos" and not decor.is_default(k))
    assert all(k in decor.MACHINE_TINT for k, v in decor.ITEMS.items() if v[0] == "machine" and not decor.is_default(k))


def test_selection_ignores_unowned_and_wrong_slot():
    assert decor.selection(None, []) == {**decor.DEFAULTS, "paintings": [], "plants": []}
    raw = {"counter": "marble", "floor": "marble", "wall": "nonsense", "paintings": ["art_beans", "art_beans", "plant_pot"]}
    sel = decor.selection(raw, [])
    assert sel["counter"] == "wood" and sel["floor"] == "wood_floor" and sel["paintings"] == [], "沒買的、放錯欄位的退回預設"
    sel = decor.selection(raw, ["decor_marble", "decor_art_beans", "decor_plant_pot"])
    assert sel["counter"] == "marble" and sel["floor"] == "wood_floor" and sel["paintings"] == ["art_beans"]
    assert decor.selection("garbage", []) == decor.selection({}, [])


def test_palette_and_helpers():
    from cafe_desk.render.shop import STORE
    sel = decor.selection({}, [])
    assert decor.palette(STORE, sel)["front"] == STORE["front"] and decor.machine_tint(sel) is None
    sel = dict(sel, counter="marble", wall="brick", board="neon", machine="red_m", cup="dots")
    pal = decor.palette(STORE, sel)
    assert pal["front"] != STORE["front"] and pal["wall_pat"] == "brick" and pal["neon"] and pal["board_light"] is False
    assert decor.machine_tint(sel) and decor.cup_style(sel)[0] == "dots"
    assert decor.collection([]) == (0, sum(1 for k in decor.ITEMS if not decor.is_default(k)))
    assert decor.collection(["decor_marble", "decor_tile"])[0] == 2


def test_buy_with_money(desk):
    assert not desk.buy_decor("marble"), "錢包不夠"
    _cash(desk)
    bal = desk.wallet()
    assert desk.buy_decor("marble") and "decor_marble" in desk.stats.data["owned"]
    assert desk.wallet() == bal - decor.price_of("marble")
    assert desk.decor_sel()["counter"] == "wood", "買了不會自動套用"
    assert desk.use_decor("marble") and desk.decor_sel()["counter"] == "marble"
    assert not desk.buy_decor("marble") and not desk.buy_decor("wood"), "不能重複買、預設款不用買"
    assert desk.use_decor("wood") and desk.decor_sel()["counter"] == "wood"
    assert not desk.use_decor("tile"), "沒買的不能用"
    desk.stats.load()                                          # 重讀資料庫（有簽章的購買紀錄）
    assert "decor_marble" in desk.stats.data["owned"] and desk.stats.tampered == 0


def test_buy_with_stamps(desk):
    assert decor.stamps_of("neon") and not decor.price_of("neon")
    _cash(desk)
    assert not desk.buy_decor("neon"), "限定款只收章數、不收錢"
    _stamps(desk, decor.stamps_of("neon") - 1)
    assert desk.stamps_free() == decor.stamps_of("neon") - 1 and not desk.buy_decor("neon")
    _stamps(desk, 1)
    assert desk.buy_decor("neon") and desk.stamps_free() == 0 and desk.decor_sel()["board"] == "chalk", "買了不會自動套用"
    assert desk.use_decor("neon") and desk.decor_sel()["board"] == "neon"
    assert desk.wallet() == stats.START_FUNDS + desk.stats.data["revenue_total"], "沒花到錢"
    desk.stats.load()
    assert desk.stats.data["stamps_spent"] == decor.stamps_of("neon") and desk.stats.tampered == 0


def test_multi_slots_toggle_and_limit(desk):
    _cash(desk)
    _stamps(desk, 20)
    for k in ("art_beans", "art_latte", "art_hills", "art_photo"):
        assert desk.buy_decor(k) and desk.use_decor(k)
    assert desk.decor_sel()["paintings"] == ["art_beans", "art_latte", "art_hills", "art_photo"]
    assert desk.use_decor("art_latte") and "art_latte" not in desk.decor_sel()["paintings"], "再按一次拿下來"
    assert desk.use_decor("art_latte") and desk.decor_sel()["paintings"][-1] == "art_latte"
    for k in ("plant_pot", "plant_vase", "plant_hang", "plant_cactus", "plant_fern"):
        desk.buy_decor(k)
        desk.use_decor(k)
    assert len(desk.decor_sel()["plants"]) == decor.MAX_PLANTS
    assert desk.buy_decor("art_poster") and desk.use_decor("art_poster") and len(desk.decor_sel()["paintings"]) == decor.MAX_PAINTINGS, "掛畫位置滿了：最早擺的換下來"
    assert "art_beans" not in desk.decor_sel()["paintings"] and desk.decor_sel()["paintings"][-1] == "art_poster"


def test_counter_paints_with_every_item(desk, qapp):
    """每一款都換上去畫一次櫃檯（含霓虹、吊燈、紅磚牆、咖啡機上色），不會出錯"""
    desk.set_order_mode(True)
    for _ in range(40):
        desk.step(0.05, 0.05)
    desk.counter_view = True
    _cash(desk, 10 ** 6)
    _stamps(desk, 100)
    for k in decor.ITEMS:
        if not decor.is_default(k):
            assert desk.buy_decor(k), k
        desk.use_decor(k)
        desk.host.grab()
    assert desk.decor_sel()["paintings"] and desk.decor_sel()["plants"]


def test_store_and_book_show_decor(desk, qapp):
    from PySide6.QtWidgets import QLabel, QPushButton
    _cash(desk)
    desk.open_records("shop")                              # 商店是獨立視窗
    store = desk.store_dlg
    buttons = [b.text() for b in store.findChildren(QPushButton)]
    assert any("12" in b and "章" in b for b in buttons), "限定款顯示要幾個章"
    n = decor.collection([])[1]
    assert any(f"（0/{n}）" in lab.text() for lab in store.findChildren(QLabel)), "商店有收集進度"
    store.close()
    desk.open_records()
    dlg = desk.records_dlg
    texts = [lab.text() for lab in dlg.findChildren(QLabel)]
    assert any("店面裝潢" in t for t in texts) and any(f"（0/{n}）" in t for t in texts), "圖鑑也有收集進度"
    dlg.close()
    desk.buy_decor("tile")
    desk.open_records()
    texts = [lab.text() for lab in desk.records_dlg.findChildren(QLabel)]
    assert any(f"（1/{n}）" in t for t in texts)
    desk.records_dlg.close()
    desk.open_records("shop")
    assert any(f"（1/{n}）" in lab.text() for lab in desk.store_dlg.findChildren(QLabel))
    desk.store_dlg.close()


def test_reset_clears_decor(desk):
    _cash(desk)
    desk.buy_decor("tile")
    desk.use_decor("tile")
    assert desk.cfg.get("decor")
    assert desk.reset_progress()
    assert "decor" not in desk.cfg and desk.decor_sel()["floor"] == "wood_floor"


def test_store_keeps_scroll_position_after_buying(desk, qapp):
    """買完東西重畫商店分頁，捲動位置不跳回最上面"""
    _cash(desk)
    desk.open_records("shop")
    dlg = desk.store_dlg
    dlg.resize(760, 400)
    dlg.store_sub.setCurrentIndex(1)                       # 店面裝潢分頁
    qapp.processEvents()
    bar = dlg.store_sub.currentWidget().verticalScrollBar()
    assert bar.maximum() > 300, "裝潢頁夠長才捲得動"
    bar.setValue(300)
    dlg.buy(desk.buy_decor, "tile")
    qapp.processEvents()
    assert dlg.store_sub.currentIndex() == 1 and dlg.store_sub.currentWidget().verticalScrollBar().value() == 300
    dlg.close()


def test_remap_changes_only_paint_colors():
    from cafe_desk.machines import MACHINES
    spec = decor.MACHINE_TINT["green_m"]
    steel = decor.make_remap(MACHINES["desk01"], spec)
    assert steel("#b7bdc3") != "#b7bdc3" and steel("#ffffff") == "#ffffff" and steel("#000000") == "#000000"
    assert steel("#ffb050") == "#ffb050" and steel("#1a1b1d") == "#1a1b1d", "彩色的燈號與很暗的縫隙不換"
    copper = decor.make_remap(MACHINES["lever"], spec)
    assert copper("#c4703e") != "#c4703e" and copper("#c9ced3") == "#c9ced3", "拉桿機換的是銅色、鍍鉻不動"
    speck = decor.make_remap(MACHINES["duo"], spec)
    from cafe_desk.machines import duo
    assert speck(duo.BODY[1]) != duo.BODY[1] and speck(duo.BODY[1]) != steel(duo.BODY[1]), "雙頭機的烤漆顏色也換"
    black = decor.make_remap(MACHINES["desk01"], decor.MACHINE_TINT["black"])
    r, g, b = (int(black("#b7bdc3")[i:i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) < 0xb7 and max(r, g, b) - min(r, g, b) < 12, "霧黑：變暗、不帶顏色"


@pytest.mark.parametrize("key", ["desk01", "lever", "compact", "allinone", "duo"])
def test_machine_paint_color_changes_the_operating_screen(desk, unlocked, key):
    """咖啡機配色換的是操作畫面上那台機器（不只是櫃檯後檯）：每台機器換了色畫面都不一樣，換回銀色就一樣"""
    from cafe_desk import gfx
    desk.set_machine(key)
    for _ in range(3):
        desk.step(0.05, 0.05)
    def shot():                                                # 不含最下面的狀態列；買東西的通知也先收掉（它會讓狀態列淡出）
        desk.toasts.clear()
        for _ in range(3):
            desk.step(0.05, 0.05)
        im = desk.host.grab().toImage()
        return im.copy(0, 0, im.width(), int(im.height() * 0.8))
    def diff(x, y):
        return sum(1 for yy in range(0, x.height(), 2) for xx in range(0, x.width(), 2) if x.pixel(xx, yy) != y.pixel(xx, yy))
    plain = shot()
    _cash(desk)
    assert desk.buy_decor("green_m") and desk.use_decor("green_m") and desk.decor_sel()["machine"] == "green_m"
    for _ in range(3):
        desk.step(0.05, 0.05)
    tinted = shot()
    assert diff(tinted, plain) > 1000, "圖層快取要跟著烤漆顏色重畫"
    assert gfx._remap is None, "換色只在畫咖啡機的時候有效，之後要還原"
    desk.use_decor("silver")
    for _ in range(3):
        desk.step(0.05, 0.05)
    assert diff(shot(), plain) < diff(tinted, plain) / 5, "換回銀色：只剩指針、溫度這些會動的小差異"


@pytest.mark.parametrize("day, key", [("2026-02-10", "valentine"), ("2026-10-25", "halloween"), ("2026-12-20", "christmas"),
                                      ("2026-08-01", None)])
def test_festival_decorations_follow_the_date(desk, qapp, monkeypatch, day, key):
    """情人節、萬聖節、聖誕節期間櫃檯畫面掛節日裝飾（可以在右鍵選單關掉），平常日子什麼都沒有"""
    from cafe_desk.render import shop
    monkeypatch.setenv("CAFE_DESK_DATE", day)
    calls = []
    monkeypatch.setattr(shop, "paint_festival_wall", lambda p, k, *a: calls.append(("wall", k)))
    monkeypatch.setattr(shop, "paint_festival_front", lambda p, k, *a: calls.append(("front", k)))
    desk.set_order_mode(True)
    for _ in range(40):
        desk.step(0.05, 0.05)
    desk.counter_view = True
    assert desk.festival_decor_key() == key
    desk.host.grab()
    assert calls == ([("wall", key), ("front", key)] if key else [])
    if key:
        calls.clear()
        desk.cfg["festival_decor"] = False
        desk.host.grab()
        assert not calls and desk.festival_decor_key() is None


@pytest.mark.parametrize("day", ["2026-02-10", "2026-10-25", "2026-12-20"])
def test_festival_decorations_really_paint(desk, qapp, monkeypatch, day):
    monkeypatch.setenv("CAFE_DESK_DATE", day)
    desk.set_order_mode(True)
    for _ in range(40):
        desk.step(0.05, 0.05)
    desk.counter_view = True
    with_decor = desk.host.grab().toImage()
    desk.cfg["festival_decor"] = False
    without = desk.host.grab().toImage()
    assert with_decor != without


def test_layout_tab_changes_decor_and_back_counter(desk, qapp):
    """紀錄視窗的「佈置」分頁：預覽畫得出來；換已買的款式、後檯設備核取會改到設定檔，選單的核取同步；切分頁不會無限重畫"""
    from PySide6.QtWidgets import QToolButton
    _cash(desk)
    assert desk.buy_decor("marble") and desk.buy_decor("art_poster") and desk.buy_decor("pos_black")
    desk.use_decor("art_poster")
    desk.open_records("layout")
    dlg = desk.layout_dlg
    assert dlg.windowTitle() == "佈置" and dlg.tabs.count() == 1 and dlg.tabs.currentWidget() is dlg.layout_page
    from PySide6.QtWidgets import QCheckBox
    fest = next(c for c in dlg.layout_page.findChildren(QCheckBox) if "節日" in c.text())
    fest.setChecked(False)
    assert desk.cfg["festival_decor"] is False, "節日裝飾的開關在佈置分頁"
    qapp.processEvents()

    def tiles():
        return {b.toolTip(): b for b in dlg.layout_page.findChildren(QToolButton)}
    t = tiles()
    assert t["大理石"].isEnabled() and not t["大理石"].isChecked() and t["暖木"].isChecked(), "圖片選項：選中的框起來"
    t["大理石"].click()
    qapp.processEvents()
    assert desk.decor_sel()["counter"] == "marble" and tiles()["大理石"].isChecked()
    assert "art_poster" in desk.decor_sel()["paintings"] and tiles()["復古海報"].isChecked()
    tiles()["復古海報"].click()                              # 掛畫是開關：再點一次拿下來
    qapp.processEvents()
    assert "art_poster" not in desk.decor_sel()["paintings"] and not tiles()["復古海報"].isChecked()
    desk.build_menu()
    assert not hasattr(desk, "back_gear_acts"), "後檯設備只在佈置分頁調整"
    assert "設定" in [a.text() for a in desk.menu.actions()]
    dlg.close()


def test_pos_look_follows_selection(desk, qapp):
    _cash(desk)
    assert decor.pos_look(desk.decor_sel())["screen"] == decor.POS_BASE["screen"]
    assert desk.buy_decor("pos_black") and desk.use_decor("pos_black")
    look = decor.pos_look(desk.decor_sel())
    assert look["screen"] == decor.POS_LOOK["pos_black"]["screen"] and look["stand"] == decor.POS_BASE["stand"]
    desk.set_order_mode(True)
    desk.counter_view = True
    desk.host.grab()


def test_machine_icons_follow_machine_color(desk):
    """換了咖啡機配色，佈置與圖鑑的咖啡機圖也跟著換"""
    from cafe_desk.machines import MACHINES
    from cafe_desk.render import gear_icons
    m = MACHINES["desk01"]
    before = gear_icons.machine_icon(desk, m, 96, 72, False, 1.0).toImage()
    _cash(desk)
    assert desk.buy_decor("green_m") and desk.use_decor("green_m")
    after = gear_icons.machine_icon(desk, m, 96, 72, False, 1.0).toImage()
    assert before != after


def test_machine_screen_backdrop_follows_wall_and_cabinet(desk, qapp):
    """牆面、後檯櫃子換了，操作畫面（咖啡機畫面）的背景也跟著換"""
    desk.counter_view = False
    desk.host.grab()
    before = desk.host.grab().toImage()
    _cash(desk)
    assert desk.buy_decor("pink") and desk.use_decor("pink")
    mid = desk.host.grab().toImage()
    assert mid != before, "牆面"
    assert desk.buy_decor("cab_navy") and desk.use_decor("cab_navy")
    assert desk.host.grab().toImage() != mid, "後檯櫃子"
