"""紙張風格：右鍵／系統匣選單與各視窗（紀錄、參數設定、關於）共用，跟打烊日報的收據同一套顏色

固定是米白紙底、深棕字，不跟著 Windows 深色／淺色主題變（程式裡的強調色、說明字顏色都是照紙底設計的）。
"""
from PySide6.QtGui import QColor, QPalette

PAPER = "#f7f1e3"           # 視窗底色
SHEET = "#fbf8f0"           # 分頁、輸入框、選單：較亮的紙
INK = "#3a2a1a"             # 內文
INK_DARK = "#2a1d12"        # 標題
MUTED = "#7a6a5a"           # 說明字
FAINT = "#a89a86"           # 反灰
LINE = "#c9bfa9"            # 邊框
DASH = "#b8ab92"            # 虛線
HOVER = "#ecdcc0"           # 滑過、選取
ACCENT = "#b06a2a"          # 進度條、滑桿、勾選
ACCENT_DARK = "#8a5426"



def _indicators(sel):
    """勾選框與單選記號：咖啡色的小方塊／圓點（選單與核取方塊共用）"""
    return f"""
{sel}::indicator {{ width: 11px; height: 11px; }}
{sel}::indicator:unchecked {{ border: 1px solid {FAINT}; border-radius: 2px; background: {SHEET}; }}
{sel}::indicator:checked {{ border: 1px solid {ACCENT_DARK}; border-radius: 2px; background: {ACCENT}; }}
{sel}::indicator:exclusive:unchecked {{ border-radius: 6px; }}
{sel}::indicator:exclusive:checked {{ border-radius: 6px; }}
{sel}::indicator:disabled {{ border-color: #d4c9b4; background: #f1ead8; }}
"""


MENU_QSS = f"""
QMenu {{ background: {SHEET}; color: {INK}; border: 1px solid {LINE}; padding: 5px 0; }}
QMenu::item {{ padding: 5px 26px 5px 28px; background: transparent; }}
QMenu::item:selected {{ background: {HOVER}; color: {INK_DARK}; }}
QMenu::item:disabled {{ color: {FAINT}; background: transparent; }}
QMenu::separator {{ height: 0; margin: 5px 12px; border-top: 1px dashed {DASH}; }}
QMenu::icon {{ left: 8px; }}
QMenu::right-arrow {{ width: 8px; height: 8px; right: 10px; }}
""" + _indicators("QMenu") + "QMenu::indicator { left: 9px; }"

DIALOG_QSS = f"""
QDialog {{ background: {PAPER}; }}
QWidget {{ color: {INK}; }}
QLabel {{ background: transparent; }}
QToolTip {{ background: {SHEET}; color: {INK}; border: 1px solid {LINE}; padding: 3px; }}

QTabWidget::pane {{ border: 1px solid {LINE}; background: {SHEET}; top: -1px; border-radius: 3px; }}
QTabBar::tab {{ background: #ece2cc; color: {MUTED}; padding: 5px 12px; border: 1px solid {LINE}; border-bottom: none;
               margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
QTabBar::tab:selected {{ background: {SHEET}; color: {INK_DARK}; font-weight: bold; }}
QTabBar::tab:hover:!selected {{ background: #f3ead6; }}
QAbstractScrollArea > QWidget#qt_scrollarea_viewport {{ background: {SHEET}; }}
QScrollArea {{ border: none; background: {SHEET}; }}
QWidget#page {{ background: {SHEET}; }}

QPushButton {{ background: #efe3c8; color: {INK}; border: 1px solid #c9b48e; border-radius: 4px; padding: 5px 14px; }}
QPushButton:hover {{ background: #e8d6b2; }}
QPushButton:pressed {{ background: #dcc59c; }}
QPushButton:default {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: {FAINT}; background: #f1ead8; border-color: #ddd2bc; }}

QComboBox {{ background: {SHEET}; color: {INK}; border: 1px solid {LINE}; border-radius: 3px; padding: 3px 8px;
            min-height: 18px; }}
QComboBox:hover {{ border-color: #b8a47e; }}
QComboBox:disabled {{ color: {FAINT}; background: #f1ead8; }}
QComboBox QAbstractItemView {{ background: {SHEET}; color: {INK}; border: 1px solid {LINE};
                               selection-background-color: {HOVER}; selection-color: {INK_DARK}; outline: none; }}

QSpinBox, QLineEdit {{ background: {SHEET}; color: {INK}; border: 1px solid {LINE}; border-radius: 3px; padding: 3px 6px;
                      selection-background-color: {HOVER}; selection-color: {INK_DARK}; }}
QSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}

QSlider::groove:horizontal {{ height: 4px; background: #e2d8c2; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; border-radius: 7px; background: {SHEET};
                              border: 1px solid {ACCENT_DARK}; }}
QSlider::handle:horizontal:hover {{ background: #fff6e4; }}
QSlider::sub-page:horizontal:disabled {{ background: #cdbfa6; }}
QSlider::handle:horizontal:disabled {{ border-color: {FAINT}; background: #f1ead8; }}

QCheckBox {{ spacing: 6px; background: transparent; }}
{_indicators("QCheckBox")}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #d8ccb4; border-radius: 3px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #c9b896; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame#dash {{ border: none; border-top: 1px dashed {DASH}; background: transparent; max-height: 1px; }}
QFrame#dot {{ border: none; border-top: 1px dotted #d6cbb5; background: transparent; max-height: 1px; }}
"""


def palette():
    """跟樣式表一致的調色盤：樣式表沒蓋到的地方（原生繪製的箭頭、選取色）也是紙張顏色"""
    pal = QPalette()
    for role, col in ((QPalette.Window, PAPER), (QPalette.Base, SHEET), (QPalette.AlternateBase, PAPER),
                      (QPalette.WindowText, INK), (QPalette.Text, INK), (QPalette.ButtonText, INK),
                      (QPalette.Button, "#efe3c8"), (QPalette.Highlight, HOVER), (QPalette.HighlightedText, INK_DARK),
                      (QPalette.ToolTipBase, SHEET), (QPalette.ToolTipText, INK), (QPalette.PlaceholderText, FAINT),
                      (QPalette.Light, "#ffffff"), (QPalette.Midlight, "#efe6d4"), (QPalette.Mid, LINE),
                      (QPalette.Dark, "#a89a86"), (QPalette.Shadow, "#5a4a3a")):
        pal.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(FAINT))
    return pal


def apply_dialog(w):
    """視窗套用紙張風格（裡面的子元件一起）"""
    w.setPalette(palette())
    w.setStyleSheet(DIALOG_QSS)


def apply_menu(m):
    """選單套用紙張風格；子選單是它的子物件，會一起套用"""
    m.setPalette(palette())
    m.setStyleSheet(MENU_QSS)
