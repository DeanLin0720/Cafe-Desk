"""音樂播放：清單、上一首／下一首、隨機與單曲循環、找不到檔案、存讀設定、右鍵選單（無頭環境沒有播放器，只測邏輯）"""
import json
import os
import random
import wave

from cafe_desk import music


def _wav(path, sec=0.2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * sec))
    return str(path)


def _songs(tmp_path, n=3):
    d = tmp_path / "songs"
    (d / "sub").mkdir(parents=True)
    files = [_wav(d / f"{i:02d} song.wav") for i in range(n - 1)] + [_wav(d / "sub" / "zz last.wav")]
    (d / "notes.txt").write_text("not music")
    return d, files


def test_add_skips_duplicates_and_non_audio(tmp_path):
    d, files = _songs(tmp_path)
    m = music.Music()
    assert m.add_folder(str(d)) == 3                       # 含子資料夾，略過 .txt
    assert m.add(files) == 0                               # 重複的略過
    assert m.add([str(d / "notes.txt")]) == 0
    assert [os.path.basename(f) for f in m.files] == ["00 song.wav", "01 song.wav", "zz last.wav"]
    assert m.title() == "00 song"


def test_next_prev_and_modes(tmp_path):
    _, files = _songs(tmp_path, 4)
    m = music.Music()
    m.add(files)
    changed = []
    m.on_change = changed.append
    m.next()
    assert m.index == 1 and m.playing and changed == ["01 song"]
    m.prev()
    assert m.index == 0
    m.prev()
    assert m.index == 3, "第一首的上一首是最後一首"
    m.mode = "one"
    m.next(auto=True)
    assert m.index == 3, "單曲循環：播完重播同一首"
    m.next()
    assert m.index == 0, "單曲循環時手動按下一首還是會換"
    m.mode = "shuffle"
    random.seed(1)
    seen = []
    for _ in range(6):
        before = m.index
        m.next()
        assert m.index != before
        seen.append(before)
    m.prev()
    assert m.index == seen[-1], "隨機播放的上一首是剛剛那首"


def test_missing_file_skipped(tmp_path):
    _, files = _songs(tmp_path)
    m = music.Music()
    m.add([files[0], str(tmp_path / "gone.mp3"), files[1]])
    skipped = []
    m.on_skip = skipped.append
    m.jump(1)
    assert skipped == ["gone.mp3"] and m.index == 2 and m.playing


def test_all_missing_stops(tmp_path):
    m = music.Music()
    m.add([str(tmp_path / f"gone{i}.mp3") for i in range(500)])
    m.play()
    assert not m.playing


def test_remove_and_clear(tmp_path):
    _, files = _songs(tmp_path)
    m = music.Music()
    m.add(files)
    m.jump(2)
    m.remove_current()
    assert len(m.files) == 2 and m.index == 1 and m.playing
    m.clear()
    assert m.files == [] and not m.playing and m.title() == ""


def test_mute_pauses_and_resumes(tmp_path):
    _, files = _songs(tmp_path)
    m = music.Music()
    m.add(files)
    m.play()
    m.set_mute(True)
    assert not m.playing and m.paused_by_mute
    m.set_mute(False)
    assert m.playing
    m.pause()
    m.set_mute(True)
    m.set_mute(False)
    assert not m.playing, "自己按暫停的，打開聲音時不會自動播"


def test_volume_stays_at_level():
    """音量一直是使用者選的大小（做咖啡時不自動降低）；「開啟聲音」關掉時是 0"""
    class Out:
        v = None
        def setVolume(self, v):
            self.v = v
    m = music.Music()
    m.out, m.level = Out(), 0.8
    for _ in range(50):
        m.update(True)
        assert m.out.v == 0.8
    m.update(False)
    assert m.out.v == 0.0


def test_state_roundtrip_no_autoplay(tmp_path):
    _, files = _songs(tmp_path)
    m = music.Music()
    m.add(files)
    m.jump(1)
    m.mode, m.level = "shuffle", music.LEVELS[2]
    m.pause()
    m.pos = 42.0
    st = json.loads(json.dumps(m.state()))
    m2 = music.Music(st)
    assert (m2.files, m2.index, m2.pos, m2.mode, m2.level) == (files, 1, 42.0, "shuffle", music.LEVELS[2])
    assert not m2.playing, "開程式不會自動播"
    assert music.Music({"files": "壞掉", "mode": "x", "level": 9}).files == []


def test_desk_menu_and_config(desk, tmp_path):
    from cafe_desk import config
    _, files = _songs(tmp_path)
    desk.music_toggle()                                    # 空清單：提示，不會壞
    assert desk.notice and not desk.music.playing
    desk.music.add(files)
    desk.fill_music_menu()
    texts = [a.text() for a in desk.music_menu.actions()]
    assert any("清單是空的" not in t and "已暫停" in t for t in texts)
    desk.sound.set_on(False)
    desk.music_toggle()
    assert desk.music.playing and desk.sound.user_on, "按播放時把聲音一起打開"
    desk.fill_music_menu()
    assert any("正在播放" in a.text() for a in desk.music_menu.actions())
    desk.update_tray_tip()
    desk.step(0.05, 0.05)
    desk.save_config()
    assert config.load()["music"]["files"] == files


def test_quiet_ffmpeg_is_safe():
    """關掉 ffmpeg 主控台訊息：找得到 avutil 就設好（Windows 的 PySide6 有附），找不到也不會出錯"""
    assert isinstance(music.quiet_ffmpeg(), bool)
