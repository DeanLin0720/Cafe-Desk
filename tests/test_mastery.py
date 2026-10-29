"""飲品專精星級：大師之後每種飲品 1–5 星，每顆星手感誤差再少一點"""
import pytest

from cafe_desk import growth


def test_stars_need_cups_and_best():
    f = growth.mastery_stars
    assert f(None) == 0 and f({"count": 9, "best": 99}) == 0
    assert f({"count": 10, "best": 79}) == 0 and f({"count": 10, "best": 80}) == 1
    assert f({"count": 250, "best": 79}) == 0                    # 杯數夠、最高分不夠
    assert f({"count": 60, "best": 99}) == 3 and f({"count": 250, "best": 97}) == 5
    assert growth.mastery_k(0) == 1 and growth.mastery_k(5) == pytest.approx(0.85)
    assert growth.mastery_open(1500) and not growth.mastery_open(1499)


def _make_master(desk, drink="latte", n=60, best=95):
    st = desk.stats.data
    st["total"] = 1500
    st["collection"]["drinks"][drink] = {"count": n, "best": best}


def test_mastery_only_after_master(desk):
    desk.stats.data["collection"]["drinks"]["latte"] = {"count": 250, "best": 99}
    assert desk.mastery("latte") == 0 and desk.skill("latte") == desk.skill()
    _make_master(desk, n=250, best=99)
    assert desk.mastery("latte") == 5
    assert desk.skill("latte") == pytest.approx(desk.skill() * 0.85)
    assert desk.skill("mocha") == desk.skill() and desk.skill() == growth.skill(1500)   # 沒專精的飲品照舊


def test_mastery_toast_only_on_increase(desk):
    _make_master(desk, n=10, best=85)                             # 1 星
    desk.check_mastery()                                          # 第一次只記下，不通知
    assert desk.cfg["mastery_seen"]["latte"] == 1 and not desk.toasts
    desk.stats.data["collection"]["drinks"]["latte"] = {"count": 30, "best": 88}
    desk.check_mastery()
    assert any("專精" in t[0] for t in desk.toasts) and desk.cfg["mastery_seen"]["latte"] == 2
    n = len(desk.toasts)
    desk.check_mastery()
    assert len(desk.toasts) == n


def test_book_shows_mastery_badge(desk, qapp):
    from PySide6.QtWidgets import QLabel
    _make_master(desk, n=60, best=95)
    desk.open_records()
    texts = [lab.text() for lab in desk.records_dlg.findChildren(QLabel)]
    assert "★★★☆☆" in texts
    desk.records_dlg.close()
