"""音樂播放：使用者自己選的本機音檔，一份播放清單（右鍵「音樂」）

播放用 QMediaPlayer＋QAudioOutput（打包本來就有 Qt Multimedia 與 ffmpeg）；設 CAFE_DESK_NO_AUDIO=1 時沒有播放器，
清單、上一首／下一首、存讀設定照樣運作（測試用）。設定存在設定檔的 "music"：檔案路徑、第幾首、播到第幾秒、順序、音量。
開程式不會自動播；縮到系統匣繼續播；「開啟聲音」關掉時暫停，打開時接著播。
"""
import os
import random

from PySide6.QtCore import QUrl

from .util import clamp

PLAYER = None
if "1" not in (os.environ.get("CAFE_DESK_NO_AUDIO"), os.environ.get("ESPRESSO_DESK_NO_AUDIO")):
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
        PLAYER = QMediaPlayer
    except Exception:                       # 沒有多媒體模組：只有清單，沒有聲音
        PLAYER = None


def quiet_ffmpeg():
    """Qt Multimedia 內建的 ffmpeg 播放時會列舉 Windows 的影片編碼器，把「could not find any MFT」「MFT name: …」
    之類的訊息直接印到主控台（不經過 Qt 的記錄，QT_LOGGING_RULES 擋不掉）。播音樂用不到編碼器，
    把 ffmpeg 的記錄層級設成只留致命錯誤；找不到 avutil（不同版本、打包方式）就算了，不影響播放"""
    try:
        import ctypes
        import glob
        import PySide6
        for path in glob.glob(os.path.join(os.path.dirname(PySide6.__file__), "avutil-*.dll")):
            ctypes.CDLL(path).av_log_set_level(8)          # AV_LOG_FATAL
            return True
    except Exception:
        pass
    return False

EXTS = (".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav")
MAX_FILES = 2000
MODES = ("loop", "shuffle", "one")         # 依序循環、隨機、單曲循環
LEVELS = (0.25, 0.5, 0.8)                  # 音量：小、中、大


def is_audio(path):
    return os.path.splitext(path)[1].lower() in EXTS


def scan_folder(folder):
    """資料夾（含子資料夾）裡的音檔，依路徑排序"""
    found = []
    for root, _dirs, files in os.walk(folder):
        found += [os.path.join(root, f) for f in files if is_audio(f)]
        if len(found) > MAX_FILES:
            break
    return sorted(found, key=lambda p: p.lower())[:MAX_FILES]


def base_title(path):
    return os.path.splitext(os.path.basename(path))[0]


class Music:
    def __init__(self, cfg=None, on_change=None, on_skip=None):
        cfg = cfg if isinstance(cfg, dict) else {}
        files = cfg.get("files")
        self.files = [f for f in files if isinstance(f, str)][:MAX_FILES] if isinstance(files, list) else []
        try:
            self.pos = float(cfg.get("pos", 0.0)) if self.files else 0.0     # 上次播到第幾秒（開始播放時接著播）
            self.index = int(clamp(cfg.get("index", 0), 0, max(0, len(self.files) - 1)))
        except (TypeError, ValueError):
            self.pos, self.index = 0.0, 0
        self.mode = cfg.get("mode", "loop") if cfg.get("mode") in MODES else "loop"
        self.level = cfg.get("level", 0.5) if cfg.get("level") in LEVELS else 0.5
        self.playing = False
        self.paused_by_mute = False         # 「開啟聲音」關掉時暫停的，打開時要接著播
        self.titles = {}                    # 路徑 → 檔案裡的標題（載入過才知道）
        self.history = []                   # 隨機播放時的上一首
        self.on_change = on_change          # 換歌時呼叫 on_change(標題)
        self.on_skip = on_skip              # 跳過播不了的檔案時呼叫 on_skip(檔名)
        self._fails = 0
        self._seek = None                   # 載入後要跳到的秒數
        self.player = self.out = None
        if PLAYER is not None:
            quiet_ffmpeg()
            try:
                self.player = QMediaPlayer()
                self.out = QAudioOutput()
                self.player.setAudioOutput(self.out)
                self.player.mediaStatusChanged.connect(self._status)
                self.player.errorOccurred.connect(lambda *_: self._failed())
                self.out.setVolume(0.0)
            except Exception:
                self.player = self.out = None

    # ───────────── 清單 ─────────────
    @property
    def current(self):
        return self.files[self.index] if self.files else None

    def title(self, path=None):
        path = path or self.current
        if not path:
            return ""
        return self.titles.get(path) or base_title(path)

    def add(self, paths):
        """加入音檔（略過重複與不是音檔的）；回傳實際加入幾首"""
        have = {os.path.normcase(os.path.abspath(f)) for f in self.files}
        n = 0
        for p in paths:
            key = os.path.normcase(os.path.abspath(p))
            if len(self.files) >= MAX_FILES:
                break
            if is_audio(p) and key not in have:
                self.files.append(p)
                have.add(key)
                n += 1
        return n

    def add_folder(self, folder):
        return self.add(scan_folder(folder))

    def remove_current(self):
        if not self.files:
            return
        was = self.playing
        self.stop()
        self.files.pop(self.index)
        self.history = [i - (i > self.index) for i in self.history if i != self.index]
        self.index = min(self.index, max(0, len(self.files) - 1))
        self.pos = 0.0
        if was and self.files:
            self.play()

    def clear(self):
        self.stop()
        self.files, self.index, self.pos, self.history = [], 0, 0.0, []

    # ───────────── 播放 ─────────────
    def play(self):
        if not self.files:
            return False
        self.playing = True
        self.paused_by_mute = False
        self._load(self.pos)
        return True

    def pause(self):
        if self.player is not None and self.playing:
            self.pos = self.player.position() / 1000.0
            self.player.pause()
        self.playing = False

    def stop(self):
        if self.player is not None:
            self.player.stop()
        self.playing = False

    def toggle(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def jump(self, i, push=True):
        """跳到第 i 首並播放"""
        if not self.files:
            return
        if push and i != self.index:
            self.history.append(self.index)
            self.history = self.history[-50:]
        self.index = i % len(self.files)
        self.pos = 0.0
        self.playing = True
        self.paused_by_mute = False
        self._load(0.0)
        if self.on_change:
            self.on_change(self.title())

    def next(self, auto=False):
        """下一首：auto 是播完自動換（單曲循環時重播同一首）"""
        if not self.files:
            return
        if auto and self.mode == "one":
            self.jump(self.index, push=False)
        elif self.mode == "shuffle" and len(self.files) > 1:
            self.jump(random.choice([i for i in range(len(self.files)) if i != self.index]))
        else:
            self.jump(self.index + 1)

    def prev(self):
        if not self.files:
            return
        if self.mode == "shuffle" and self.history:
            self.jump(self.history.pop(), push=False)
        else:
            self.jump(self.index - 1, push=False)

    def set_mute(self, muted):
        """「開啟聲音」關掉：正在播就暫停；再打開時接著播"""
        if muted and self.playing:
            self.pause()
            self.paused_by_mute = True
        elif not muted and self.paused_by_mute:
            self.play()

    def position(self):
        if self.player is not None and self.playing:
            return self.player.position() / 1000.0
        return self.pos

    def _load(self, seek):
        path = self.current
        if not os.path.exists(path):
            self._failed()
            return
        if self.player is None:
            return
        if self.player.source() != QUrl.fromLocalFile(path):
            self._seek = seek if seek > 0.5 else None
            self.player.setSource(QUrl.fromLocalFile(path))
        elif seek > 0.5:
            self.player.setPosition(int(seek * 1000))
        self.player.play()

    def _failed(self):
        """檔案不見或播不了：提示一次、跳下一首；整份清單都播不了就停"""
        name = os.path.basename(self.current or "")
        self._fails += 1
        if self.on_skip:
            self.on_skip(name)
        n = len(self.files)
        if self._fails < n:                 # 播不了的檔案不會無限重試：連續失敗一整輪就停
            for step in range(1, n):        # 找下一個還在的檔案（不用遞迴，清單很長也不會爆）
                i = (self.index + step) % n
                if os.path.exists(self.files[i]):
                    self.jump(i, push=False)
                    return
        self._fails = 0
        self.stop()

    def _status(self, status):
        S = QMediaPlayer.MediaStatus
        if status in (S.LoadedMedia, S.BufferedMedia):
            self._fails = 0
            md = self.player.metaData()
            t = md.stringValue(QMediaMetaData.Key.Title)
            a = md.stringValue(QMediaMetaData.Key.ContributingArtist) or md.stringValue(QMediaMetaData.Key.AlbumArtist)
            if t:
                self.titles[self.current] = f"{t} - {a}" if a else t
            if self._seek:
                self.player.setPosition(int(self._seek * 1000))
                self._seek = None
        elif status == S.EndOfMedia and self.playing:
            self.next(auto=True)
        elif status == S.InvalidMedia:
            self._failed()

    def update(self, on=True):
        """每個 tick：音量就是使用者選的 level（做咖啡時不自動降低）；「開啟聲音」關掉時是 0"""
        if self.out is not None:
            self.out.setVolume(self.level if on else 0.0)

    def state(self):
        """存進設定檔的內容"""
        return {"files": list(self.files), "index": self.index, "pos": round(self.position(), 1),
                "mode": self.mode, "level": self.level}
