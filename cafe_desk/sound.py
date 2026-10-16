"""音效：用程式合成 WAV，再用 QSoundEffect 播放"""
import math
import os
import random
import struct
import sys
import tempfile
import time
import wave

from PySide6.QtCore import QUrl

from .paths import app_dir, _writable_dir
from .util import clamp

QSoundEffect = None
if "1" not in (os.environ.get("CAFE_DESK_NO_AUDIO"), os.environ.get("ESPRESSO_DESK_NO_AUDIO")):     # 設成 1 可完全停用音訊模組
    try:
        from PySide6.QtMultimedia import QSoundEffect
    except Exception:      # 沒有多媒體模組時照樣能跑，只是沒聲音
        QSoundEffect = None


SR = 22050


def _write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(clamp(s, -1, 1) * 30000)) for s in samples))


def _pump(seconds=1.0):
    """震動式幫浦：60 Hz 與諧波的嗡嗡聲 + 金屬顫動（整數週期，可無縫循環）"""
    rnd = random.Random(7)
    amps = [1, .7, .5, .45, .3, .25, .15, .1]
    phases = [rnd.random() * 6.28 for _ in amps]
    out, lp = [], 0.0
    for i in range(int(SR * seconds)):
        t = i / SR
        base = sum(a * math.sin(2 * math.pi * 60 * (n + 1) * t + ph)
                   for n, (a, ph) in enumerate(zip(amps, phases)))
        buzz = math.tanh(2.2 * base) * 0.45
        lp += (rnd.uniform(-1, 1) - lp) * 0.25
        rattle = lp * (0.5 + 0.5 * math.sin(2 * math.pi * 120 * t)) ** 4 * 0.6
        out.append((buzz + rattle) * 0.55)
    return out


def _loop_xfade(samples, n_loop, fade):
    """把多生成的尾段交叉淡入到開頭，讓循環播放沒有接縫"""
    out = samples[:n_loop]
    for i in range(fade):
        k = i / fade
        out[i] = samples[n_loop + i] * (1 - k) + samples[i] * k
    return out


def _pour(seconds=2.0):
    """細流注入杯中：帶通雜訊 + 慢速起伏（3/5/7 Hz 整數週期）"""
    rnd = random.Random(11)
    a = b = 0.0
    out = []
    n_loop, fade = int(SR * seconds), int(SR * 0.15)
    for i in range(n_loop + fade):
        t = i / SR
        n = rnd.uniform(-1, 1)
        a += (n - a) * 0.35          # 低通
        b += (a - b) * 0.05          # 更低的低通，相減成帶通
        mod = 0.65 + 0.15 * math.sin(2 * math.pi * 3 * t) + 0.12 * math.sin(2 * math.pi * 5 * t + 1) \
            + 0.08 * math.sin(2 * math.pi * 7 * t + 2)
        out.append((a - b) * mod * 1.4)
    return _loop_xfade(out, n_loop, fade)


def _drip(f0, seconds=0.13):
    """水滴「咚」：上揚的正弦 + 快速衰減"""
    out, ph = [], 0.0
    for i in range(int(SR * seconds)):
        t = i / SR
        f = f0 * (0.65 + min(1.0, t / 0.045) * 0.7)
        ph += 2 * math.pi * f / SR
        env = math.exp(-t / 0.028) * min(1.0, t / 0.002)
        out.append(math.sin(ph) * env * 0.7)
    return out


def _bell(f0, seconds=1.8, notes=(0.0,)):
    """完成提示音：鐘聲泛音，可多個音符依序"""
    partials = [(1.0, 1.0, 0.55), (2.0, 0.35, 0.35), (2.76, 0.22, 0.22), (5.4, 0.08, 0.12)]
    n = int(SR * seconds)
    out = [0.0] * n
    for k, start in enumerate(notes):
        f = f0 * (1.26 if k == 1 else 1.0)
        s0 = int(start * SR)
        for i in range(s0, n):
            t = (i - s0) / SR
            v = sum(a * math.exp(-t / d) * math.sin(2 * math.pi * f * m * t) for m, a, d in partials)
            out[i] += v * min(1.0, t / 0.003) * 0.35
    return out


def _click(seconds=0.04):
    rnd = random.Random(3)
    return [(rnd.uniform(-1, 1) * math.exp(-i / SR / 0.003)
             + math.sin(2 * math.pi * 2300 * i / SR) * math.exp(-i / SR / 0.007)) * 0.5
            for i in range(int(SR * seconds))]


def _lock(seconds=0.35):
    """扣上／轉開把手：金屬卡榫的「喀」+ 短暫金屬餘響"""
    rnd = random.Random(21)
    out = []
    for i in range(int(SR * seconds)):
        t = i / SR
        click = rnd.uniform(-1, 1) * math.exp(-t / 0.004)
        ring = (math.sin(2 * math.pi * 1870 * t) * 0.5 + math.sin(2 * math.pi * 3120 * t) * 0.3) * math.exp(-t / 0.06)
        thump = math.sin(2 * math.pi * 140 * t) * math.exp(-t / 0.03)
        out.append((click * 0.6 + ring * 0.35 + thump * 0.5) * 0.7)
    return out


def _grinder(seconds=1.0):
    """磨豆機馬達：鋸齒波嗡鳴 + 研磨顆粒雜訊（整數週期，可無縫循環）"""
    rnd = random.Random(31)
    n_loop, fade = int(SR * seconds), int(SR * 0.12)
    out, lp = [], 0.0
    for i in range(n_loop + fade):
        t = i / SR
        saw = sum(math.sin(2 * math.pi * 150 * k * t) / k for k in range(1, 9))
        lp += (rnd.uniform(-1, 1) - lp) * 0.6
        crunch = lp * (0.55 + 0.45 * math.sin(2 * math.pi * 25 * t) ** 2)
        out.append((math.tanh(saw * 0.9) * 0.35 + crunch * 0.4) * 0.6)
    return _loop_xfade(out, n_loop, fade)


def _tap(seconds=0.12):
    """布粉時輕敲濾杯"""
    rnd = random.Random(41)
    return [(rnd.uniform(-1, 1) * math.exp(-i / SR / 0.006)
             + math.sin(2 * math.pi * 620 * i / SR) * math.exp(-i / SR / 0.03)) * 0.45
            for i in range(int(SR * seconds))]


def _tamp(seconds=0.3):
    """填壓：低沉的悶響"""
    rnd = random.Random(51)
    out, lp = [], 0.0
    for i in range(int(SR * seconds)):
        t = i / SR
        lp += (rnd.uniform(-1, 1) - lp) * 0.08
        out.append((math.sin(2 * math.pi * 95 * t) * 0.8 + lp * 2.0) * math.exp(-t / 0.07) * 0.58)
    return out


def _knock(seconds=0.4):
    """敲渣：把手敲在敲渣桿上的空洞撞擊聲"""
    rnd = random.Random(61)
    out, lp = [], 0.0
    for i in range(int(SR * seconds)):
        t = i / SR
        lp += (rnd.uniform(-1, 1) - lp) * 0.3
        body = math.sin(2 * math.pi * 118 * t) * math.exp(-t / 0.09) + math.sin(2 * math.pi * 260 * t) * math.exp(-t / 0.05) * 0.5
        out.append((body * 0.8 + lp * math.exp(-t / 0.015) * 1.2) * 0.65)
    return out


def _hiss(seconds=0.9):
    """洩壓口放氣：高頻雜訊，快起慢收"""
    rnd = random.Random(71)
    out, a, b = [], 0.0, 0.0
    for i in range(int(SR * seconds)):
        t = i / SR
        n = rnd.uniform(-1, 1)
        a += (n - a) * 0.9
        b += (a - b) * 0.25
        env = min(1.0, t / 0.03) * math.exp(-t / 0.35)
        out.append((a - b) * env * 0.5)
    return out


def _relay(seconds=0.05):
    """加熱器繼電器的輕微「答」"""
    rnd = random.Random(81)
    return [(rnd.uniform(-1, 1) * math.exp(-i / SR / 0.0015)
             + math.sin(2 * math.pi * 3400 * i / SR) * math.exp(-i / SR / 0.004) * 0.4) * 0.35
            for i in range(int(SR * seconds))]


def _steam(seconds=1.5):
    """蒸氣管：寬頻嘶聲，帶一點低頻翻滾（可無縫循環）"""
    rnd = random.Random(91)
    n_loop, fade = int(SR * seconds), int(SR * 0.15)
    out, a, b, lp = [], 0.0, 0.0, 0.0
    for i in range(n_loop + fade):
        t = i / SR
        n = rnd.uniform(-1, 1)
        a += (n - a) * 0.75
        b += (a - b) * 0.12
        lp += (rnd.uniform(-1, 1) - lp) * 0.02
        roll = 0.75 + 0.25 * math.sin(2 * math.pi * 4 * t) + lp * 2.5
        out.append(((a - b) * 0.55 + lp * 0.9) * roll * 0.8)
    return _loop_xfade(out, n_loop, fade)


def _chirp(seconds=1.2):
    """打入空氣的「嘶嘶、撕紙聲」：一陣陣短促的高頻爆裂"""
    rnd = random.Random(93)
    n_loop, fade = int(SR * seconds), int(SR * 0.1)
    out, a, b = [], 0.0, 0.0
    env, nxt = 0.0, 0
    for i in range(n_loop + fade):
        if i >= nxt:
            env = rnd.uniform(0.5, 1.0)
            nxt = i + int(SR * rnd.uniform(0.012, 0.045))
        env *= 0.9986
        n = rnd.uniform(-1, 1)
        a += (n - a) * 0.95
        b += (a - b) * 0.35
        out.append((a - b) * env * 0.9)
    return _loop_xfade(out, n_loop, fade)


def _frother(seconds=1.0):
    """奶泡機：馬達嗡鳴 + 攪拌的水聲（整數週期，可無縫循環）"""
    rnd = random.Random(95)
    n_loop, fade = int(SR * seconds), int(SR * 0.1)
    out, lp = [], 0.0
    for i in range(n_loop + fade):
        t = i / SR
        hum = sum(math.sin(2 * math.pi * 220 * k * t) / k ** 1.4 for k in range(1, 6))
        lp += (rnd.uniform(-1, 1) - lp) * 0.08
        slosh = lp * (0.6 + 0.4 * math.sin(2 * math.pi * 6 * t))
        out.append((math.tanh(hum * 0.8) * 0.22 + slosh * 1.6) * 0.65)
    return _loop_xfade(out, n_loop, fade)


def _ice(seconds=0.35):
    """冰塊碰撞玻璃：不和諧的高頻泛音快速衰減"""
    rnd = random.Random(97)
    parts = [(2350, 0.06, 1.0), (3810, 0.04, 0.6), (5230, 0.03, 0.45), (1620, 0.08, 0.35)]
    out = []
    for i in range(int(SR * seconds)):
        t = i / SR
        v = sum(a * math.exp(-t / d) * math.sin(2 * math.pi * f * t) for f, d, a in parts)
        click = rnd.uniform(-1, 1) * math.exp(-t / 0.002)
        out.append((v * 0.35 + click * 0.3) * 0.8)
    return out


def _beep(seconds=0.5):
    """奶泡機完成的兩聲短嗶"""
    out = []
    for i in range(int(SR * seconds)):
        t = i / SR
        on = (t < 0.12) or (0.2 < t < 0.32)
        env = 1.0 if on else 0.0
        out.append(math.sin(2 * math.pi * 2000 * t) * env * 0.25)
    return out


SFX_VERSION = "4"          # 修改音效合成參數時遞增，舊檔會自動重新產生


def build_sounds():
    """音效存到「程式所在資料夾/sound/」；該處無法寫入（例如裝在 Program Files）時改用系統暫存資料夾"""
    d = os.path.join(app_dir(), "sound")
    if not _writable_dir(d):
        d = os.path.join(tempfile.gettempdir(), "cafe_desk_sound")
        os.makedirs(d, exist_ok=True)
    spec = {
        "pump": _pump, "pour": _pour, "click": _click,
        "drip0": lambda: _drip(1250), "drip1": lambda: _drip(1050), "drip2": lambda: _drip(1500),
        "ding_hi": lambda: _bell(1318.5, notes=(0.0, 0.16)), "ding_lo": lambda: _bell(1046.5),
        "lock": _lock, "grinder": _grinder, "tap": _tap, "tamp": _tamp, "knock": _knock,
        "hiss": _hiss, "relay": _relay,
        "steam": _steam, "chirp": _chirp, "frother": _frother, "ice": _ice, "beep": _beep,
    }
    ver_file = os.path.join(d, "version.txt")
    try:
        with open(ver_file, encoding="utf-8") as f:
            up_to_date = f.read().strip() == SFX_VERSION
    except OSError:
        up_to_date = False
    files = {}
    for name, fn in spec.items():
        path = os.path.join(d, name + ".wav")
        if not up_to_date or not os.path.exists(path):
            _write_wav(path, fn())
        files[name] = path
    if not up_to_date:
        with open(ver_file, "w", encoding="utf-8") as f:
            f.write(SFX_VERSION)
    return files


class SoundBank:
    def __init__(self):
        self.enabled = QSoundEffect is not None
        self.master = 0.65
        self.fx = {}
        self.drips = []
        self._drip_i = 0
        self._last_drip = 0.0
        if not self.enabled:
            return
        try:
            files = build_sounds()
        except Exception:
            self.enabled = False
            return

        # PySide6 的 Infinite 是列舉，setLoopCount 只收 int，所以取出數值（-2）
        inf = getattr(QSoundEffect, "Infinite", -2)
        inf = int(getattr(inf, "value", inf))

        def make(path, loop=False):
            e = QSoundEffect()
            e.setSource(QUrl.fromLocalFile(path))
            if loop:
                e.setLoopCount(inf)
            e.setVolume(0.0)
            return e

        try:
            for name in ("pump", "pour", "grinder", "steam", "chirp", "frother"):
                self.fx[name] = make(files[name], loop=True)
            for name in ("click", "ding_hi", "ding_lo", "lock", "tap", "tamp", "knock", "hiss", "relay",
                         "ice", "beep"):
                self.fx[name] = make(files[name])
            self.drips = [make(files[f"drip{i % 3}"]) for i in range(6)]
        except Exception as exc:          # 音訊初始化失敗就靜音執行，不讓程式掛掉
            print("音效初始化失敗，改為靜音：", exc, file=sys.stderr)
            self.fx, self.drips, self.enabled = {}, [], False

    def loop(self, name, vol):
        e = self.fx.get(name)
        if not e:
            return
        vol *= self.master if self.on else 0.0
        if vol > 0.005:
            e.setVolume(vol)
            if not e.isPlaying():
                e.play()
        elif e.isPlaying():
            e.stop()

    def once(self, name, vol=0.6):
        e = self.fx.get(name)
        if e and self.on:
            e.setVolume(vol * self.master)
            e.play()

    def drip(self):
        now = time.perf_counter()
        if not self.drips or not self.on or now - self._last_drip < 0.09:
            return
        self._last_drip = now
        e = self.drips[self._drip_i % len(self.drips)]
        self._drip_i += 1
        e.setVolume(random.uniform(0.18, 0.35) * self.master)
        e.play()

    @property
    def user_on(self):
        return getattr(self, "_on", True)

    @property
    def on(self):
        return self.enabled and self.user_on and not getattr(self, "_muted", False)

    def set_on(self, v):
        self._on = v
        if not v:
            self.stop_all()

    def set_muted(self, v):
        """縮到系統匣時暫時靜音，不改變使用者的聲音設定"""
        self._muted = v
        if v:
            self.stop_all()

    def stop_all(self):
        for e in list(self.fx.values()) + self.drips:
            e.stop()

