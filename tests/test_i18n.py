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


def test_money_follows_language():
    """錢一律存台幣：中文顯示新台幣，英文依物價換算（20 台幣＝1 美金）顯示美金"""
    from cafe_desk import i18n
    try:
        i18n.set_lang("zh")
        assert i18n.money(120) == "NT$120" and i18n.money(180000) == "NT$180,000"
        assert i18n.money_text(i18n.T("一天營業額達 $2,000")) == "一天營業額達 NT$2,000"
        i18n.set_lang("en")
        assert i18n.money(120) == "US$6.00"
        assert i18n.money(180000) == f"US${180000 / i18n.TWD_PER_USD:,.0f}"
        assert "US$100" in i18n.money_text(i18n.T("一天營業額達 $2,000"))
        assert "$" not in i18n.T("錢包 {m}").replace("{m}", ""), "樣板裡不該再寫死 $"
    finally:
        i18n.set_lang("zh")
