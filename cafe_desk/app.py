"""程式進入點：建立 QApplication、處理命令列參數"""
import sys

from PySide6.QtWidgets import QApplication

from .desk import CafeDesk
from .logo import load_icon, make_logo_files


def main():
    app = QApplication(sys.argv)
    if "--make-logo" in sys.argv:
        make_logo_files()
        return
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(load_icon())
    w = CafeDesk()
    w.show_window()
    sys.exit(app.exec())
