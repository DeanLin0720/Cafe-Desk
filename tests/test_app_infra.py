"""錯誤紀錄與單一執行個體"""
import os
import subprocess
import sys
import time
from types import SimpleNamespace

from PySide6.QtCore import QtMsgType

from cafe_desk import errlog
from cafe_desk.single import SingleInstance

from conftest import ROOT


def test_excepthook_writes_traceback(cfg_path, monkeypatch):
    path = errlog.log_path()
    monkeypatch.setattr(errlog, "_path", path)
    monkeypatch.setattr(sys, "stderr", None)          # 模擬 pythonw／-w 打包：沒有主控台
    try:
        raise ValueError("咖啡灑了")
    except ValueError:
        errlog._excepthook(*sys.exc_info())
    errlog._qt_handler(QtMsgType.QtWarningMsg, SimpleNamespace(file="x.cpp", line=3), "小心燙")
    errlog._qt_handler(QtMsgType.QtDebugMsg, SimpleNamespace(file="", line=0), "不該被記")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    assert "ValueError: 咖啡灑了" in text and "Traceback" in text
    assert "Qt warning: 小心燙 (x.cpp:3)" in text
    assert "不該被記" not in text
    assert os.path.basename(path) == "cafe_desk.log"


def test_log_rotates(cfg_path, monkeypatch):
    path = errlog.log_path()
    with open(path, "w") as f:
        f.write("x" * (errlog.LOG_MAX + 1))
    errlog._rotate(path)
    assert os.path.exists(path + ".1") and not os.path.exists(path)


_SECOND = """
import sys
sys.path.insert(0, {root!r})
from PySide6.QtCore import QCoreApplication
app = QCoreApplication([])
from cafe_desk import paths
paths.CONFIG_PATH = {cfg!r}
from cafe_desk.single import SingleInstance
s = SingleInstance()
if s.acquire():
    print("acquired")
else:
    print("notified" if s.notify_running(3000) else "notify-failed")
"""


def test_second_instance_wakes_first(qapp, cfg_path):
    """第二個實例（另一個 process）拿不到鎖，改叫第一個顯示出來"""
    first = SingleInstance()
    assert first.acquire()
    woke = []
    first.wake.connect(lambda: woke.append(True))
    try:
        proc = subprocess.Popen([sys.executable, "-c", _SECOND.format(root=ROOT, cfg=cfg_path)],
                                stdout=subprocess.PIPE, text=True)
        deadline = time.time() + 15
        while proc.poll() is None and time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        qapp.processEvents()
        assert proc.stdout.read().strip() == "notified"
        assert woke
    finally:
        first.release()
    third = SingleInstance()                            # 第一個結束後就能再啟動
    assert third.acquire()
    third.release()


def test_other_config_location_is_independent(qapp, cfg_path, tmp_path, monkeypatch):
    from cafe_desk import paths
    a = SingleInstance()
    assert a.acquire()
    monkeypatch.setattr(paths, "CONFIG_PATH", str(tmp_path / "other" / "cafe_desk.json"))
    os.makedirs(tmp_path / "other")
    b = SingleInstance()
    try:
        assert b.acquire()
    finally:
        b.release()
        a.release()


def test_about_dialog(desk, qapp):
    from cafe_desk import __version__
    from PySide6.QtWidgets import QLabel
    desk.open_about()
    qapp.processEvents()
    dlg = desk.about_dlg
    assert dlg.isVisible()
    text = " ".join(lab.text() for lab in dlg.findChildren(QLabel))
    assert __version__ in text and "cafe_desk.json" in text
    desk.open_about()                                   # 再開一次會換成新的視窗
    assert desk.about_dlg is not dlg
    desk.about_dlg.close()


def test_new_install_defaults_to_windowed(desk):
    """沒有設定檔時預設是一般視窗（視窗化顯示）"""
    assert desk.windowed is True


def test_saved_frameless_choice_is_kept(qapp, cfg_path):
    import json
    from cafe_desk.desk import CafeDesk
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump({"schema": 3, "windowed": False}, f)
    w = CafeDesk()
    try:
        assert w.windowed is False, "已經選了透明擺件的照原本的選擇"
    finally:
        w.timer.stop()
        w.stats.db.close()
        w.deleteLater()


def test_intro_dialog_pages(desk, qapp):
    desk.open_intro()
    dlg = desk.intro_dlg
    assert dlg.isVisible() and not dlg.prev.isEnabled()
    for _ in range(len(dlg.data) - 1):
        dlg.next.click()
    assert dlg.page == len(dlg.data) - 1 and dlg.isVisible()
    dlg.next.click()                                    # 最後一頁的按鈕是「開始遊玩」：關閉
    assert not dlg.isVisible()
