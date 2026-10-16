"""介面語言：英文對照完整、T() 的樣板與切換"""
import os
import subprocess
import sys

from cafe_desk import i18n
from cafe_desk.i18n import T, set_lang

from conftest import ROOT


def test_all_texts_translated():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "i18n_check.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, "缺英文翻譯：\n" + r.stdout


def test_t_switches_and_formats():
    try:
        set_lang("en")
        assert T("開始沖煮") == "Brew"
        assert T("沒有翻譯的字") == "沒有翻譯的字"
        assert T("{name}有點糊", name="Heart") == "Heart came out smudged"
        set_lang("zh")
        assert T("開始沖煮") == "開始沖煮"
        assert T("拉花：{art}", art="愛心") == "拉花：愛心"
        set_lang("klingon")
        assert i18n.lang() == "zh"
    finally:
        set_lang("zh")


def test_en_placeholders_match():
    """英文樣板的 {變數} 要和中文原文一樣，否則切到英文會 KeyError"""
    import string
    fmt = string.Formatter()
    for zh, en in i18n.EN.items():
        a = {f for _, f, _, _ in fmt.parse(zh) if f}
        b = {f for _, f, _, _ in fmt.parse(en) if f}
        assert a == b, (zh, en)
