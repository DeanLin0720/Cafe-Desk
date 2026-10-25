"""圖鑑的飲品說明與做法：每種飲品都有、都有英文，滑鼠停在卡片上顯示"""
from cafe_desk.drink_notes import DRINK_NOTES
from cafe_desk.drinks import DRINK_KEYS, FESTIVAL_DRINKS
from cafe_desk.i18n import EN


def test_every_drink_has_notes_and_english():
    keys = set(DRINK_KEYS) | set(FESTIVAL_DRINKS)
    assert set(DRINK_NOTES) == keys
    for k, (desc, steps) in DRINK_NOTES.items():
        assert desc and steps, k
        for text in (desc, *steps):
            assert text in EN, f"{k}：缺英文「{text}」"


def test_book_card_tooltips(desk):
    from PySide6.QtWidgets import QWidget
    from cafe_desk.records import RecordsDialog
    desk.stats.data["collection"]["drinks"]["latte"] = {"count": 1, "best": 88.0}
    dlg = RecordsDialog(desk)
    tips = [w.toolTip() for w in dlg.findChildren(QWidget) if w.toolTip()]
    assert any("做法" in t and "熱拿鐵" in t for t in tips), "做過的飲品顯示說明與做法"
    assert any(t.startswith("還沒做過") for t in tips), "沒做過的不透露"
    dlg.close()


def test_book_milk_and_origin_pictures(qapp):
    """圖鑑的牛奶盒與咖啡豆袋：每種牛奶、每個產地都有顏色；畫得出來"""
    from cafe_desk.beans import ORIGINS
    from cafe_desk.drinks import MILK_KINDS
    from cafe_desk.render.icons import MILK_LOOK, ORIGIN_LOOK, milk_icon, bean_icon
    assert set(MILK_KINDS) <= set(MILK_LOOK) and set(ORIGINS) <= set(ORIGIN_LOOK)
    for k in MILK_KINDS:
        assert not milk_icon(k, 72, True).isNull() and not milk_icon(k, 72, False).isNull()
    for k, v in ORIGINS.items():
        assert not bean_icon(k, v[1], False, 72, True).isNull()
