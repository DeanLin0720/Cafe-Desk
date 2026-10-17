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


def _add_wrap(buf, start, snd):
    """把一小段聲音疊進緩衝區，超出尾端的部分繞回開頭（讓循環沒有接縫）"""
    n = len(buf)
    for k, v in enumerate(snd):
        buf[(start + k) % n] += v


def _pump(seconds=1.0):
    """振動式幫浦（電磁活塞）：每個交流電週期一次的撞擊「噠」＋機殼低頻共鳴＋管路水流嘶聲。
    整數個週期、撞擊尾巴繞回開頭，可無縫循環。"""
    rnd = random.Random(7)
    n = int(SR * seconds)
    buf = [0.0] * n
    hz = 60
    period = SR / hz
    # 單次撞擊：低頻「咚」+ 金屬活塞的短「喀」+ 機殼共鳴
    hit_len = int(SR * 0.03)
    for c in range(int(seconds * hz)):
        start = int(c * period)
        amp = 0.8 + 0.2 * rnd.random()                 # 每下力道略有不同，聽起來才不機械
        lp, snd = 0.0, []
        for i in range(hit_len):
            t = i / SR
            lp += (rnd.uniform(-1, 1) - lp) * 0.45
            thump = math.sin(2 * math.pi * 105 * t) * math.exp(-t / 0.011)
            clack = lp * math.exp(-t / 0.0022)
            ring = math.sin(2 * math.pi * 640 * t) * math.exp(-t / 0.006) * 0.35
            snd.append((thump * 0.75 + clack * 0.9 + ring) * amp)
        _add_wrap(buf, start, snd)
    # 管路裡的水流聲：低通雜訊
    a = b = 0.0
    flow = []
    for i in range(n):
        a += (rnd.uniform(-1, 1) - a) * 0.3
        b += (a - b) * 0.04
        flow.append((a - b) * (0.8 + 0.2 * math.sin(2 * math.pi * 7 * i / SR)))
    return [math.tanh((x * 0.5 + f * 0.35) * 1.5) * 0.85 for x, f in zip(buf, flow)]


def _loop_xfade(samples, n_loop, fade):
    """把多生成的尾段交叉淡入到開頭，讓循環播放沒有接縫"""
    out = samples[:n_loop]
    for i in range(fade):
        k = i / fade
        out[i] = samples[n_loop + i] * (1 - k) + samples[i] * k
    return out


def _bubble(f0, seconds, rnd):
    """水中小氣泡的「啵」：頻率往上爬的短正弦（真實水聲的主要來源）"""
    out, ph = [], 0.0
    tau = seconds / 4
    for i in range(int(SR * seconds)):
        t = i / SR
        ph += 2 * math.pi * f0 * (1 + 2.2 * t / seconds * 0.5 + 1.4 * t) / SR
        out.append(math.sin(ph) * math.exp(-t / tau) * min(1.0, t / 0.001))
    return out


def _pour(seconds=2.0):
    """細流落進杯中：柔和的低中頻水流 + 稀疏的小氣泡（整數週期、繞回開頭，可無縫循環）"""
    rnd = random.Random(11)
    n = int(SR * seconds)
    a = a2 = b = 0.0
    buf = []
    for i in range(n):
        t = i / SR
        a += (rnd.uniform(-1, 1) - a) * 0.12          # 兩段低通：去掉刺耳的高頻
        a2 += (a - a2) * 0.35
        b += (a2 - b) * 0.02                          # 相減成帶通，約 200–1500 Hz
        mod = 0.8 + 0.1 * math.sin(2 * math.pi * 2 * t) + 0.06 * math.sin(2 * math.pi * 3 * t + 1)
        buf.append((a2 - b) * mod * 1.6)
    for _ in range(int(seconds * 9)):
        f0 = rnd.uniform(500, 1600)
        amp = rnd.uniform(0.04, 0.10)
        _add_wrap(buf, rnd.randrange(n), [x * amp for x in _bubble(f0, rnd.uniform(0.015, 0.03), rnd)])
    return [math.tanh(x) * 0.4 for x in buf]


def _drip(f0, seconds=0.16):
    """水滴落入杯底水面的「噗咚」：撞擊的短促雜訊 + 氣泡共鳴（頻率急速上揚）+ 稍晚一個小回彈"""
    rnd = random.Random(int(f0))
    n = int(SR * seconds)
    out, lp = [0.0] * n, 0.0
    ph = ph2 = 0.0
    for i in range(n):
        t = i / SR
        lp += (rnd.uniform(-1, 1) - lp) * 0.5
        tick = lp * math.exp(-t / 0.0015) * 0.4
        ph += 2 * math.pi * f0 * (0.8 + 1.6 * (1 - math.exp(-t / 0.018))) / SR
        bub = math.sin(ph) * math.exp(-t / 0.032) * min(1.0, t / 0.001)
        t2 = t - 0.045
        v2 = 0.0
        if t2 > 0:
            ph2 += 2 * math.pi * f0 * 1.45 * (0.8 + 1.6 * (1 - math.exp(-t2 / 0.012))) / SR
            v2 = math.sin(ph2) * math.exp(-t2 / 0.016) * 0.3
        out[i] = (tick + bub * 0.6 + v2) * 0.85
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
    """蒸汽棒噴氣：高速氣流的寬頻嘶聲（集中在 2–7 kHz）+ 噴嘴共鳴 + 低頻氣流轟隆 + 緩慢的壓力起伏。
    整數週期、尾段交叉淡入開頭，可無縫循環。"""
    rnd = random.Random(91)
    n_loop, fade = int(SR * seconds), int(SR * 0.15)
    out, l1, l2, r = [], 0.0, 0.0, 0.0
    ba = bb = 0.0
    for i in range(n_loop + fade):
        t = i / SR
        n = rnd.uniform(-1, 1)
        l1 += (n - l1) * 0.55
        l2 += (n - l2) * 0.12
        jet = l1 - l2                          # 約 1.5 kHz 以上的氣流
        ba += (n - ba) * 0.42
        bb += (ba - bb) * 0.30
        whistle = (ba - bb) * 1.4              # 噴嘴的窄帶共鳴
        r += (rnd.uniform(-1, 1) - r) * 0.015
        press = 0.85 + 0.1 * math.sin(2 * math.pi * 2 * t) + 0.05 * math.sin(2 * math.pi * 7 * t + 1)
        out.append((jet * 0.75 + whistle * 0.35 + r * 2.4) * press)
    out = _loop_xfade(out, n_loop, fade)
    return [math.tanh(x * 1.1) * 0.5 for x in out]


def _chirp(seconds=1.2):
    """蒸汽管插進牛奶、打入空氣：不規則的「滋滋、啵啵」——短促的氣流爆裂 + 牛奶裡的氣泡聲"""
    rnd = random.Random(93)
    n_loop, fade = int(SR * seconds), int(SR * 0.1)
    n = n_loop + fade
    out, a, b = [], 0.0, 0.0
    env, nxt = 0.0, 0
    for i in range(n):
        if i >= nxt:
            env = rnd.uniform(0.3, 1.0)
            nxt = i + int(SR * rnd.uniform(0.02, 0.07))
        env *= 0.9992
        x = rnd.uniform(-1, 1)
        a += (x - a) * 0.5
        b += (a - b) * 0.1
        out.append((a - b) * env * 0.7)
    for _ in range(int(seconds * 45)):          # 牛奶中冒出的氣泡
        f0 = rnd.uniform(350, 1400)
        _add_wrap(out, rnd.randrange(n),
                  [x * rnd.uniform(0.08, 0.22) for x in _bubble(f0, rnd.uniform(0.012, 0.035), rnd)])
    out = _loop_xfade(out, n_loop, fade)
    return [math.tanh(x * 1.2) * 0.55 for x in out]


def _frother(seconds=1.0):
    """電動奶泡機：小馬達的高速嗡鳴（含碳刷雜訊）+ 牛奶被打成漩渦的攪拌聲與細小氣泡。
    所有頻率都取整數週期、氣泡繞回開頭，可無縫循環。"""
    rnd = random.Random(95)
    n = int(SR * seconds)
    out, lp, a, b = [], 0.0, 0.0, 0.0
    for i in range(n):
        t = i / SR
        wob = 1 + 0.004 * math.sin(2 * math.pi * 3 * t)            # 轉速微幅起伏
        whine = sum(math.sin(2 * math.pi * 480 * k * t * wob) / k ** 1.3 for k in range(1, 6))
        lp += (rnd.uniform(-1, 1) - lp) * 0.5
        brush = lp * (0.5 + 0.5 * math.sin(2 * math.pi * 480 * t)) * 0.25    # 隨轉速的沙沙聲
        a += (rnd.uniform(-1, 1) - a) * 0.18
        b += (a - b) * 0.03
        swirl = (a - b) * (0.65 + 0.35 * math.sin(2 * math.pi * 5 * t))     # 漩渦起伏
        out.append(whine * 0.16 + brush + swirl * 1.1)
    for _ in range(int(seconds * 40)):
        f0 = random.Random(rnd.random()).uniform(900, 2800)
        _add_wrap(out, rnd.randrange(n),
                  [x * rnd.uniform(0.04, 0.13) for x in _bubble(f0, rnd.uniform(0.008, 0.02), rnd)])
    return [math.tanh(x * 1.3) * 0.5 for x in out]


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


SFX_VERSION = "9"          # 修改音效合成參數時遞增，舊檔會自動重新產生


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

