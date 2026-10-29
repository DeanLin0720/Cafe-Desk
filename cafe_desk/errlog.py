"""錯誤紀錄：未捕捉的例外與 Qt 警告寫到設定檔旁的 cafe_desk.log

打包時用 -w（沒有主控台），例外原本會無聲消失；這裡把它們寫進檔案，回報問題時附上這個檔就好。
    · sys.excepthook／threading.excepthook：Python 例外（包含 Qt slot 裡丟出的例外，程式會繼續執行）
    · qInstallMessageHandler：Qt 的 warning／critical／fatal 訊息（debug、info 不記）
    · faulthandler：原生程式當掉（segfault）時的 Python 呼叫堆疊
檔案超過 LOG_MAX 時，舊的改名成 .log.1（只保留一份）。
"""
import datetime
import faulthandler
import os
import sys
import threading
import traceback

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from . import __version__, paths

LOG_MAX = 1_000_000            # bytes
_path = None
_fault_file = None             # faulthandler 需要一直開著的檔案
_lock = threading.Lock()


def log_path():
    base, _ = os.path.splitext(paths.CONFIG_PATH)
    return base + ".log"


def write(text):
    """寫一筆紀錄（自帶時間）；寫不進去就算了，不能讓紀錄本身造成錯誤"""
    if _path is None:
        return
    stamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    try:
        with _lock, open(_path, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {text.rstrip()}\n")
    except OSError:
        pass
    if sys.stderr is not None:            # 用 python（有主控台）執行時，也印出來
        try:
            sys.stderr.write(text.rstrip() + "\n")
        except Exception:
            pass


def _rotate(path):
    try:
        if os.path.getsize(path) > LOG_MAX:
            os.replace(path, path + ".1")
    except OSError:
        pass


def _excepthook(etype, value, tb):
    if issubclass(etype, KeyboardInterrupt):
        sys.__excepthook__(etype, value, tb)
        return
    write("未捕捉的例外\n" + "".join(traceback.format_exception(etype, value, tb)))


def _thread_hook(args):
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else "?"
    write(f"執行緒 {name} 的例外\n"
          + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


_QT_LEVEL = {QtMsgType.QtWarningMsg: "Qt warning", QtMsgType.QtCriticalMsg: "Qt critical",
             QtMsgType.QtFatalMsg: "Qt fatal"}


def _qt_handler(mode, context, message):
    level = _QT_LEVEL.get(mode)
    if level is None:
        return
    where = f" ({context.file}:{context.line})" if context.file else ""
    # 附上 Python 這一側的呼叫堆疊：Qt 的警告本身看不出是哪一行程式觸發的
    stack = "".join(traceback.format_stack(limit=8)[:-1])
    write(f"{level}: {message}{where}\n{stack}")


def install():
    """程式啟動時呼叫一次（在建立 QApplication 之前或之後都可以）"""
    global _path, _fault_file
    _path = log_path()
    _rotate(_path)
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    qInstallMessageHandler(_qt_handler)
    try:
        _fault_file = open(_path, "a", encoding="utf-8")
        faulthandler.enable(_fault_file)
    except OSError:
        _fault_file = None
    return _path


def startup_line():
    """啟動時記一行版本與環境，方便對照紀錄檔"""
    import platform
    from PySide6 import __version__ as qt_ver
    frozen = " (exe)" if getattr(sys, "frozen", False) else ""
    write(f"啟動 Café Desk {__version__}{frozen} · Python {platform.python_version()} · PySide6 {qt_ver} · "
          f"{platform.platform()}")
