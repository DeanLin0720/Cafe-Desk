"""檢查新版本：到 GitHub Releases 查最新版，有新版就在狀態列與系統匣提示

用 Python 的 urllib 在背景執行緒查詢（打包時拿掉了 Qt 的 TLS 外掛，QNetworkAccessManager 連不了 https）。
結果放在 Checker.result，由主執行緒的 tick 取走，不跨執行緒碰 Qt 物件。
環境變數 CAFE_DESK_NO_UPDATE=1 可完全停用（測試用）。
"""
import json
import os
import re
import threading
import urllib.request

from . import __version__

REPO = "DeanLin0720/Cafe-Desk"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 10


def disabled():
    return os.environ.get("CAFE_DESK_NO_UPDATE") == "1"


def parse_version(text):
    """'v1.2.0'、'1.2.0'、'v1.0.0-beta.8'、'1.0.0b8' → 可比較的 tuple；正式版排在同號的 Beta 之後。認不得回傳 None"""
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(a|alpha|b|beta|rc)\.?(\d+))?\s*$", text or "", re.I)
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if m.group(4):
        rank = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}[m.group(4).lower()]
        return (major, minor, patch, rank, int(m.group(5)))
    return (major, minor, patch, 3, 0)


def is_newer(tag, current=__version__):
    new, cur = parse_version(tag), parse_version(current)
    return new is not None and cur is not None and new > cur


def fetch_latest():
    """查詢最新正式版（GitHub 的 latest 不含 Pre-release），回傳 (tag, 網址)；失敗丟例外"""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"CafeDesk/{__version__}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("tag_name", ""), data.get("html_url") or RELEASES_URL


class Checker:
    """一次查詢。result：None＝還在查；否則是 dict（tag、url、newer、error）"""

    def __init__(self, manual=False):
        self.manual = manual                 # 使用者手動按的：查完不管有沒有新版都要回報
        self.result = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            tag, url = fetch_latest()
            self.result = {"tag": tag, "url": url, "newer": is_newer(tag), "error": None}
        except Exception as exc:            # 沒網路、被擋、GitHub 限流：安靜失敗，下次再查
            self.result = {"tag": "", "url": RELEASES_URL, "newer": False, "error": str(exc) or type(exc).__name__}
