"""外層承載視窗

Windows 上，視窗建立之後再改「透明背景」或在有框／無框之間切換，原生視窗會殘留 DWM 邊框與圓角。
所以咖啡機畫面（CafeDesk）做成子元件放在這個外層視窗裡；切換模式或置頂時，
直接建立一個全新的外層視窗（顯示前就設定好透明屬性與視窗類型），把畫面搬過去，再關掉舊的。

視窗化模式可以拖邊框自由調整大小：拖曳時（WM_SIZING）把框鎖在 16:9，放開後畫面照新的寬度縮放（desk.resize_to）。
全螢幕（fullscreen）：無邊框蓋滿整個螢幕，畫面照 16:9 縮到放得下、置中，螢幕不是 16:9 時兩邊補黑（desk.fit_fullscreen）。
"""
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget

WM_SIZING = 0x0214
ASPECT = 16 / 9
MIN_W = 640                     # 最小的內容寬度（邏輯像素）


def fit_sizing_rect(rect, edge, frame_w, frame_h, ratio, lo):
    """WM_SIZING：rect（整個視窗、實體像素，原地修改）鎖成內容區 ratio（寬÷高）。edge 是拖的那一邊（WMSZ_*）：
    拖上下邊照高度算寬，其他照寬度算高；固定的是對面那一邊。lo：內容區最小寬（實體像素）"""
    cw = rect.right - rect.left - frame_w
    ch = rect.bottom - rect.top - frame_h
    if edge in (3, 6):                                   # 上、下：照高度
        cw = max(lo, round(ch * ratio))
    else:
        cw = max(lo, cw)
    ch = round(cw / ratio)
    if edge in (1, 4, 7):                                # 左、左上、左下：右邊固定
        rect.left = rect.right - cw - frame_w
    else:
        rect.right = rect.left + cw + frame_w
    if edge in (3, 4, 5):                                # 上、左上、右上：下邊固定
        rect.top = rect.bottom - ch - frame_h
    else:
        rect.bottom = rect.top + ch + frame_h


class HostWindow(QWidget):
    def __init__(self, desk, windowed, topmost, fullscreen=False):
        if fullscreen:
            flags = Qt.Window | Qt.FramelessWindowHint
        elif windowed:
            flags = (Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
                     Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        else:
            flags = Qt.FramelessWindowHint | Qt.Tool | Qt.NoDropShadowWindowHint
        if topmost:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.desk = desk
        self.retired = False
        self.resizable = windowed and not fullscreen
        self.fullscreen = fullscreen
        # 一定要在第一次顯示前設定；之後不再更動
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setWindowTitle("Café Desk")

    def fit(self, size):
        """跟著畫面的大小：視窗化可以拖邊框（只設最小值），桌面擺件沒有邊框（固定大小）"""
        if self.resizable:
            self.setMinimumSize(MIN_W, round(MIN_W / ASPECT))
            self.setMaximumSize(16777215, 16777215)
            self.resize(size)
        else:
            self.setFixedSize(size)

    def nativeEvent(self, event_type, message):
        if self.resizable and sys.platform == "win32" and event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_SIZING:
                rect = wintypes.RECT.from_address(msg.lParam)
                dpr = self.devicePixelRatioF()
                fg, g = self.frameGeometry(), self.geometry()
                fit_sizing_rect(rect, msg.wParam, round((fg.width() - g.width()) * dpr),
                                round((fg.height() - g.height()) * dpr), ASPECT, round(MIN_W * dpr))
                return True, 1
        return super().nativeEvent(event_type, message)

    def moveEvent(self, e):
        if not self.retired and self.desk.host is self and self.isVisible():
            self.desk.window_dragging()                  # 拖動主視窗時暫停繪圖（大視窗一格要畫幾十毫秒，拖起來會一頓一頓的）
        super().moveEvent(e)

    def resizeEvent(self, e):
        if not self.retired and self.desk.host is self:
            self.desk._drag_until = 0.0                  # 拖左邊／上邊框改大小也會移動視窗：改大小時要照常畫
            if self.fullscreen:
                self.desk.fit_fullscreen(e.size())
            elif self.resizable:
                self.desk.resize_to(e.size())
        super().resizeEvent(e)

    def paintEvent(self, e):
        if self.fullscreen:                              # 螢幕不是 16:9 時畫面兩邊（或上下）的黑邊
            p = QPainter(self)
            p.fillRect(self.rect(), QColor("#000000"))
            p.end()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange and not self.retired:
            self.desk.sound.set_muted(self.isMinimized())      # 最小化時暫停聲音
        super().changeEvent(e)

    def closeEvent(self, e):
        """視窗化模式按標題列的關閉鈕：結束程式（被替換掉的舊視窗則只是安靜關閉）"""
        if not self.retired:
            self.desk.quit_app()
        e.accept()
