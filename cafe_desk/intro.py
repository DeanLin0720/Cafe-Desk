"""玩法導覽：第一次開啟時自動跳出，之後從右鍵選單「玩法導覽…」隨時再看（完整說明在「紀錄與收集冊」的「說明」分頁）"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from . import theme, growth
from .i18n import T


def pages():
    """每頁 (標題, [要點])；數字取自遊戲資料。回傳時才 T()，切換語言立即生效"""
    return (
        (T("歡迎來到 Café Desk"), (
            T("這是一台放在桌面上的咖啡機：<b>點一下咖啡機</b>就會開始做一杯咖啡，最後給一個分數。"),
            T("左鍵拖曳可以移動視窗；<b>右鍵</b>打開選單，換飲品、咖啡機、調參數都在這裡。"),
            T("滑鼠停在機身上，會看到萃取曲線與目前的狀態。"),
        )),
        (T("三種模式"), (
            T("<b>手動</b>：點一下做一杯，想怎麼調就怎麼調。"),
            T("<b>自動</b>：照目前的飲品與參數一直做，適合當桌面擺件。"),
            T("<b>營業</b>：客人排隊點單，咖啡師自己接單、賺營業額——這是遊戲的主體。右鍵選單最上面三選一。"),
        )),
        (T("營業怎麼玩"), (
            T("客人先點單付錢，咖啡師在出杯台把飲品做好，再到櫃檯交給客人，客人拿到才評分。"),
            T("每位客人都有耐心（點單紙下緣的細條），等太久會離開，分數也會被扣。"),
            T("分數越高小費越多；離開營業或跨過午夜時，會出一張打烊日報。"),
        )),
        (T("成長與收集"), (
            T("營業額讓<b>店鋪升級</b>（最高 Lv.{n}）：客人更多、座位更多，還會解鎖新的咖啡機與沖煮方式。", n=growth.MAX_LEVEL),
            T("做過的杯數讓咖啡師晉升<b>稱號</b>，解鎖新飲品、手感也更穩。"),
            T("錢包有初始資金，營業額可以在<b>商店</b>買咖啡豆（每包都要買）、設備升級與店面裝潢；成就、拉花與飲品圖鑑會慢慢集滿。"),
            T("完整說明隨時可以在右鍵「紀錄與收集冊」→「說明」查看；想再看一次導覽，右鍵選「玩法導覽…」。"),
        )),
    )


class IntroDialog(QDialog):
    def __init__(self, app):
        super().__init__(None)
        self.app = app
        self.page = 0
        self.data = pages()
        self.setWindowTitle(T("玩法導覽"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setWindowIcon(app.icon)
        theme.apply_dialog(self)
        self.setFixedSize(460, 330)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 14)
        lay.setSpacing(8)

        self.title = QLabel()
        self.title.setStyleSheet(f"font-size:17px; font-weight:bold; color:{theme.INK_DARK};")
        lay.addWidget(self.title)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.body, 1)
        self.dots = QLabel()
        self.dots.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.dots)

        row = QHBoxLayout()
        self.skip = QPushButton(T("略過"))
        self.skip.clicked.connect(self.close)
        row.addWidget(self.skip)
        row.addStretch(1)
        self.prev = QPushButton(T("上一頁"))
        self.prev.clicked.connect(lambda: self.go(-1))
        row.addWidget(self.prev)
        self.next = QPushButton()
        self.next.setDefault(True)
        self.next.clicked.connect(lambda: self.go(1))
        row.addWidget(self.next)
        lay.addLayout(row)
        self.show_page()

    def go(self, step):
        if self.page + step >= len(self.data):
            self.close()
            return
        self.page = max(0, self.page + step)
        self.show_page()

    def show_page(self):
        title, bullets = self.data[self.page]
        self.title.setText(title)
        self.body.setText("".join(
            f"<table><tr><td style='padding-right:7px; color:{theme.ACCENT}'>●</td><td>{b}</td></tr></table>"
            f"<div style='font-size:5px'>&nbsp;</div>" for b in bullets))
        n = len(self.data)
        self.dots.setText("".join(f"<span style='color:{theme.ACCENT if i == self.page else theme.FAINT}'>●</span> "
                                  for i in range(n)))
        last = self.page == n - 1
        self.prev.setEnabled(self.page > 0)
        self.skip.setVisible(not last)
        self.next.setText(T("開始遊玩") if last else T("下一頁"))
