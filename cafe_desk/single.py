"""單一執行個體：同一份設定檔只允許一個程式在跑

兩個實例會同時寫同一份設定檔與紀錄資料庫（簽章鏈會互相打斷），所以：
    · QLockFile（設定檔旁的 cafe_desk.lock）判斷是不是已經有一個在跑；程式當掉留下的舊鎖會自動判定失效
    · 已經有一個在跑 → 透過 QLocalSocket 叫它把咖啡機顯示出來，自己直接結束
    · 自己是第一個 → 開 QLocalServer 等別人來叫
伺服器名稱由設定檔路徑算出來，所以放在不同資料夾的兩份程式（各自的設定檔）可以同時執行。
"""
import hashlib
import os

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import paths

WAKE = b"show"


def _names():
    base, _ = os.path.splitext(paths.CONFIG_PATH)
    key = hashlib.sha1(os.path.normcase(os.path.abspath(paths.CONFIG_PATH)).encode("utf-8")).hexdigest()[:12]
    return base + ".lock", f"CafeDesk-{key}"


class SingleInstance(QObject):
    """acquire() 回傳 True 代表自己是唯一的實例；有人來叫時發出 wake 信號"""
    wake = Signal()

    def __init__(self):
        super().__init__()
        self.lock_path, self.server_name = _names()
        self.lock = QLockFile(self.lock_path)
        self.lock.setStaleLockTime(0)          # 不用時間判斷；只看持有鎖的 process 是否還活著
        self.server = None

    def acquire(self):
        # tryLock 會自己檢查鎖檔裡的 process 是否還活著，已經結束的舊鎖直接接手
        if not self.lock.tryLock(100):
            if self.lock.error() == QLockFile.LockFailedError:
                return False
            return True                        # 鎖檔寫不進去（權限）：不擋，照常啟動
        self.server = QLocalServer(self)
        QLocalServer.removeServer(self.server_name)     # Unix 上程式當掉會留下舊的 socket 檔
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.server_name)
        return True

    def _on_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._on_read(s))
            sock.disconnected.connect(sock.deleteLater)
            self._on_read(sock)                # 對方很快就寫完斷線：資料可能在連上 readyRead 之前就到了

    def _on_read(self, sock):
        if sock.bytesAvailable() and WAKE in bytes(sock.readAll()):
            sock.disconnectFromServer()        # 告訴對方收到了（對方在等這一步才離開）
            self.wake.emit()

    def notify_running(self, timeout=1000):
        """叫已經在跑的那一個顯示出來；成功送出回傳 True"""
        sock = QLocalSocket()
        sock.connectToServer(self.server_name)
        if not sock.waitForConnected(timeout):
            return False
        sock.write(WAKE)
        sock.flush()
        sock.waitForBytesWritten(timeout)
        # 等對方讀完後斷線；先斷線的話 Windows 具名管道裡還沒讀的資料會被丟掉
        ok = sock.waitForDisconnected(timeout)
        sock.abort()
        return ok

    def release(self):
        if self.server is not None:
            self.server.close()
        self.lock.unlock()
