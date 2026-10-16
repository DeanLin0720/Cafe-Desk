"""檔案位置：程式所在資料夾、設定檔、資源資料夾"""
import os
import sys


def app_dir():
    """程式所在資料夾：打包後是 exe 所在位置；原始碼執行時是 main.py 所在位置（本套件的上一層）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable_dir(d):
    try:
        os.makedirs(d, exist_ok=True)
        test = os.path.join(d, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return True
    except OSError:
        return False


def _config_path():
    """設定檔放在程式旁；該處無法寫入時改放使用者資料夾"""
    d = app_dir()
    if _writable_dir(d):
        return os.path.join(d, "cafe_desk.json")
    return os.path.join(os.path.expanduser("~"), ".cafe_desk.json")


CONFIG_PATH = _config_path()
# 舊版（Espresso Desk）設定檔位置：新設定檔不存在時依序沿用，只讀不寫
OLD_CONFIG_PATHS = [os.path.join(app_dir(), "espresso_desk.json"),
                    os.path.join(os.path.expanduser("~"), ".espresso_desk.json"),
                    os.path.join(os.path.expanduser("~"), ".espresso_desk_qt.json")]


def resource_dirs():
    """logo 可能的位置：PyInstaller 解壓目錄、exe 旁、腳本旁、目前工作目錄"""
    dirs = []
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            dirs.append(sys._MEIPASS)
        dirs.append(os.path.dirname(sys.executable))
    else:
        dirs.append(app_dir())
    dirs.append(os.getcwd())
    return [os.path.join(d, "logo") for d in dirs]

