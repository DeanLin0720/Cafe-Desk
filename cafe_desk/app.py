"""程式進入點：建立 QApplication、處理命令列參數"""
import sys

from PySide6.QtWidgets import QApplication

from . import errlog
from .desk import CafeDesk
from .logo import load_icon, make_logo_files
from .single import SingleInstance


def main():
    errlog.install()
    app = QApplication(sys.argv)
    if "--make-logo" in sys.argv:
        make_logo_files()
        return
    single = SingleInstance()
    if not single.acquire():
        single.notify_running()            # 已經有一個在跑：叫它出來，自己結束
        return
    errlog.startup_line()
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(load_icon())
    w = CafeDesk()
    single.wake.connect(w.restore_from_tray)
    w.show_window()
    code = app.exec()
    single.release()
    sys.exit(code)
