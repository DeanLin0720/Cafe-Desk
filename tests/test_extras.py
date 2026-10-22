"""環境音、休息提醒、檢查新版本"""
import json

from cafe_desk import config, sound, update
from conftest import run_until_idle


# ───────────── 版本比較 ─────────────
def test_parse_version():
    assert update.parse_version("v1.2.0") == (1, 2, 0, 3, 0)
    assert update.parse_version("1.2") == (1, 2, 0, 3, 0)
    assert update.parse_version("v1.0.0-beta.8") == (1, 0, 0, 1, 8)
    assert update.parse_version("1.0.0b8") == (1, 0, 0, 1, 8)
    assert update.parse_version("nightly") is None
    assert update.parse_version("") is None


def test_is_newer():
    assert update.is_newer("v1.3.0", "1.2.0")
    assert update.is_newer("v1.2.10", "1.2.9")
    assert update.is_newer("v1.0.0", "1.0.0b8")             # 正式版比同號的 Beta 新
    assert not update.is_newer("v1.2.0", "1.2.0")
    assert not update.is_newer("v1.1.2", "1.2.0")
    assert not update.is_newer("garbage", "1.2.0")


class FakeJob:
    def __init__(self, result, manual=False):
        self.result, self.manual = result, manual


def test_update_found_adds_menu_item(desk):
    desk.update_job = FakeJob({"tag": "v99.0.0", "url": update.RELEASES_URL, "newer": True, "error": None})
    desk.poll_update(0.0)
    assert desk.update_info["tag"] == "v99.0.0"
    assert any("v99.0.0" in a.text() for a in desk.menu.actions())
    assert desk.toasts                                        # 第一次發現：通知
    with open(desk_cfg(desk), encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["update_latest"] == "v99.0.0" and saved["update_seen"] == "v99.0.0"

    desk.toasts.clear()                                       # 同一版第二次查到：不再通知
    desk.update_job = FakeJob({"tag": "v99.0.0", "url": update.RELEASES_URL, "newer": True, "error": None})
    desk.poll_update(0.0)
    assert not desk.toasts

    desk.set_update_check(False)                              # 關掉自動檢查：選單項目拿掉
    assert desk.update_info is None
    assert not any("v99.0.0" in a.text() for a in desk.menu.actions())


def test_update_up_to_date_and_error(desk):
    desk.update_job = FakeJob({"tag": "v0.9.0", "url": "", "newer": False, "error": None}, manual=True)
    desk.poll_update(0.0)
    assert desk.update_info is None and desk.notice is not None
    desk.notice = None
    desk.cfg.pop("update_checked")
    desk.update_job = FakeJob({"tag": "", "url": "", "newer": False, "error": "offline"})
    desk.poll_update(0.0)                                     # 自動檢查失敗：安靜
    assert desk.notice is None and "update_checked" not in desk.cfg


def test_saved_newer_version_shows_on_start(qapp, cfg_path):
    config.save({"update_latest": "v99.0.0"})
    from cafe_desk.desk import CafeDesk
    w = CafeDesk()
    try:
        assert w.update_info and any("v99.0.0" in a.text() for a in w.menu.actions())
    finally:
        w.timer.stop()
        w.stats.db and w.stats.db.close()
        w.tray and w.tray.hide()
        w.host.close()


def desk_cfg(w):
    from cafe_desk import paths
    return paths.CONFIG_PATH


# ───────────── 休息提醒 ─────────────
def test_break_reminder_makes_a_cup(desk):
    desk.set_break(25)
    desk.update_break(25 * 60 - 1)
    assert desk.session is None and not desk.toasts
    desk.update_break(1.5)
    assert desk.break_t == 0.0
    assert desk.toasts and desk.session is not None           # 提醒＋咖啡師做一杯
    run_until_idle(desk)
    desk.update_break_menu()
    assert "25" in desk.act_break_reset.text()


def test_break_reminder_off_and_orders(desk):
    desk.update_break(10 ** 6)                                # 預設關閉
    assert not desk.toasts
    desk.set_break(45)
    desk.set_order_mode(True)
    desk.update_break(45 * 60)
    assert desk.toasts and desk.session is None               # 營業中只提醒，不插單


# ───────────── 環境音 ─────────────
def test_ambience_synth_seamless():
    for kind, fn in sound.AMBIENCE.items():
        s = fn()
        assert max(abs(x) for x in s) < 0.95, kind
        steps = sorted(abs(s[i + 1] - s[i]) for i in range(len(s) - 1))
        assert abs(s[-1] - s[0]) <= steps[int(len(steps) * 0.995)], kind    # 循環接縫不比一般相鄰取樣跳得大


def test_ambience_setting_saved(desk):
    desk.set_cfg("ambience", "rain")
    desk.set_cfg("amb_level", 0.5)
    desk.tick()                                               # 沒有音訊模組時照樣不出錯
    with open(desk_cfg(desk), encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["ambience"] == "rain" and saved["amb_level"] == 0.5


def test_custom_break_interval(desk, monkeypatch):
    """休息提醒「自訂…」：輸入分鐘數；取消維持原設定；選單顯示自訂的值"""
    monkeypatch.setattr(desk, "ask_break_minutes", lambda: 35)
    desk.custom_break()
    assert desk.break_min == 35
    texts = [a.text() for a in desk.break_menu.actions()]
    assert any("35" in t and t.endswith("…") for t in texts)
    monkeypatch.setattr(desk, "ask_break_minutes", lambda: None)
    desk.custom_break()
    assert desk.break_min == 35, "取消：不變"
    from cafe_desk import config
    desk.save_config()
    assert config.load()["break_min"] == 35


def test_speed_only_outside_business(desk):
    """播放速度只對手動、自動有效；營業中固定 1 倍，選單反灰"""
    desk.speed = 4.0
    assert desk.play_speed() == 4.0 and desk.speed_menu.isEnabled()
    desk.set_mode("business")
    assert desk.play_speed() == 1.0 and not desk.speed_menu.isEnabled()
    assert "1×" in desk.speed_menu.title()
    desk.set_mode("auto")
    assert desk.play_speed() == 4.0 and desk.speed_menu.isEnabled()
