"""關於視窗：版本、資料檔位置、開啟資料夾"""
import os
import platform

from PySide6 import __version__ as QT_VERSION
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QMessageBox

from . import __version__, paths, errlog, theme
from .i18n import T
from .stats import db_path


DANGER = "QPushButton { color: #a8321e; border-color: #d29a86; }"     # 無法復原的動作：紅字


class AboutDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.setWindowTitle(T("關於 Café Desk"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setWindowIcon(app.icon)
        theme.apply_dialog(self)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(app.icon.pixmap(56, 56))
        head.addWidget(icon, 0, Qt.AlignTop)
        title = QLabel(f"<div style='font-size:17px; font-weight:bold;'>Café Desk</div>"
                       f"<div style='color:#7a6a5a;'>{T('桌上咖啡吧')} · {T('版本 {v}', v=__version__)}</div>")
        head.addWidget(title, 1)
        lay.addLayout(head)
        lay.addWidget(QLabel(T("放在桌面上的咖啡機擺件：點一下，做一杯咖啡。")))

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.dir = os.path.dirname(paths.CONFIG_PATH)
        rows = ((T("設定檔"), paths.CONFIG_PATH), (T("紀錄資料庫"), db_path()), (T("錯誤紀錄"), errlog.log_path()))
        for r, (label, path) in enumerate(rows):
            name = QLabel(label)
            name.setStyleSheet("color:#7a6a5a;")
            grid.addWidget(name, r, 0, Qt.AlignTop)
            val = QLabel(os.path.basename(path) + ("" if os.path.exists(path) else T("（還沒產生）")))
            val.setToolTip(path)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(val, r, 1)
        folder = QLabel(self.dir)
        folder.setWordWrap(True)
        folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        folder.setStyleSheet("color:#7a6a5a;")
        name = QLabel(T("資料夾"))
        name.setStyleSheet("color:#7a6a5a;")
        grid.addWidget(name, len(rows), 0, Qt.AlignTop)
        grid.addWidget(folder, len(rows), 1)
        lay.addLayout(grid)

        env = QLabel(f"Python {platform.python_version()} · PySide6 {QT_VERSION}<br>"
                     f"MIT License · © 2026 DeanLin")
        env.setStyleSheet("color:#9a8a7a; font-size:11px;")
        lay.addWidget(env)

        row = QHBoxLayout()
        b = QPushButton(T("開啟資料夾"))
        b.clicked.connect(self.open_folder)
        row.addWidget(b)
        reset = QPushButton(T("重新遊玩…"))
        reset.setStyleSheet(DANGER)
        reset.clicked.connect(self.confirm_reset)
        row.addWidget(reset)
        row.addStretch(1)
        close = QPushButton(T("關閉"))
        close.setDefault(True)
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)
        self.setMinimumWidth(380)

    def confirm_reset(self):
        """重新遊玩：先講清楚會刪掉什麼、保留什麼，預設按鈕是「取消」"""
        box = QMessageBox(self)
        theme.apply_dialog(box)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(T("重新遊玩"))
        box.setText(T("確定要從頭開始嗎？這個動作無法復原。"))
        box.setInformativeText(T("會刪除：每一杯的紀錄、成就、拉花收集與圖鑑、店鋪等級與咖啡師稱號、"
                                 "錢包與商店買的升級和精品豆、清潔保養計數、目前的豆子與冰滴。\n\n"
                                 "會保留：沖煮參數、聲音與音樂清單、語言、視窗位置與大小。"))
        ok = box.addButton(T("刪除並重新開始"), QMessageBox.DestructiveRole)
        ok.setStyleSheet(DANGER)
        cancel = box.addButton(T("取消"), QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() is not ok:
            return
        if not self.app.reset_progress():
            QMessageBox.information(self, T("重新遊玩"), T("咖啡師正在做飲品，等這杯做完再試一次。"))
            return
        self.close()

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.dir))
