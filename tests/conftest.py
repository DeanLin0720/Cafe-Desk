"""pytest 共用設定：無頭（offscreen）、不出聲、固定日期、設定檔與資料庫放在暫存資料夾

    python -m pytest            （在專案根目錄執行）
"""
import os
import random
import sys

# 這些環境變數要在 import PySide6／cafe_desk 之前設定
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["CAFE_DESK_NO_AUDIO"] = "1"
os.environ["CAFE_DESK_DATE"] = "2026-08-01"          # 沒有節日的日期，結果才穩定

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest                                         # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from cafe_desk import paths                           # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    """把設定檔（以及旁邊的資料庫、紀錄檔、鎖檔）改到暫存資料夾；舊版設定檔位置也指到不存在的地方"""
    p = str(tmp_path / "cafe_desk.json")
    monkeypatch.setattr(paths, "CONFIG_PATH", p)
    monkeypatch.setattr(paths, "OLD_CONFIG_PATHS", [str(tmp_path / "espresso_desk.json")])
    return p


@pytest.fixture
def desk(qapp, cfg_path):
    """已預熱好的咖啡機主元件"""
    from cafe_desk.desk import CafeDesk
    random.seed(7)
    w = CafeDesk()
    w.show_window()
    w.warming = False
    w.boiler.temp = w.params.temp
    yield w
    w.timer.stop()
    if w.stats.db is not None:
        w.stats.db.close()
    if w.tray:
        w.tray.hide()
    w.host.close()
    w.deleteLater()
    qapp.processEvents()


def run_until_idle(w, limit=8000):
    """一直推進模擬直到沒有在忙；回傳步數。卡住（超過 limit 步）就失敗"""
    n = 0
    while w.busy():
        w.step(0.05, 0.5)
        n += 1
        if n % 40 == 0:
            w.host.grab()                             # 偶爾觸發繪圖，繪圖錯誤也要抓到
        assert n < limit, "模擬卡住了"
    w.host.grab()
    return n


@pytest.fixture(autouse=True)
def noon(monkeypatch):
    """固定在中午：早起、夜貓子成就不會因為跑測試的時間而解鎖"""
    from cafe_desk import stats
    monkeypatch.setattr(stats, "clock_hour", lambda: 12)


def until_making(w, limit=400):
    """點單換了咖啡機／沖煮方式會先停一下：推進到真的開始做這張"""
    n = 0
    while w.session is None:
        w.step(0.05, 0.05)
        n += 1
        assert n < limit, "一直沒開始做"
