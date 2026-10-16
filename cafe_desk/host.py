"""外層承載視窗

Windows 上，視窗建立之後再改「透明背景」或在有框／無框之間切換，原生視窗會殘留 DWM 邊框與圓角。
所以咖啡機畫面（CafeDesk）做成子元件放在這個外層視窗裡；切換模式或置頂時，
直接建立一個全新的外層視窗（顯示前就設定好透明屬性與視窗類型），把畫面搬過去，再關掉舊的。
"""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget


class HostWindow(QWidget):
    def __init__(self, desk, windowed, topmost):
        if windowed:
            flags = (Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
                     Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        else:
            flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if topmost:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.desk = desk
        self.retired = False
        # 一定要在第一次顯示前設定；之後不再更動
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle("Café Desk")

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange and not self.retired:
            self.desk.sound.set_muted(self.isMinimized())      # 最小化時暫停聲音
        super().changeEvent(e)

    def closeEvent(self, e):
        """視窗化模式按標題列的關閉鈕：結束程式（被替換掉的舊視窗則只是安靜關閉）"""
        if not self.retired:
            self.desk.quit_app()
        e.accept()
