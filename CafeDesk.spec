# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包設定（等同 pyinstaller -D -w --name CafeDesk --icon logo/cafe_desk.ico --add-data "logo;logo"）

    pyinstaller --noconfirm CafeDesk.spec

輸出 dist/CafeDesk/CafeDesk.exe（資料夾模式、沒有主控台）。
    · logo/ 打包進 _internal/logo
    · sound/、cafe_desk.json、cafe_desk_records.db、cafe_desk.log 第一次執行時在 exe 旁產生（不打包）
    · exe 的檔案內容（版本、產品名稱）由 cafe_desk/__init__.py 的 __version__ 產生
"""
import os
import re

ROOT = os.path.abspath(SPECPATH)

with open(os.path.join(ROOT, "cafe_desk", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)
# Windows 的檔案版本只能是四個數字：1.0.0b8 → (1, 0, 0, 8)、1.0.0 → (1, 0, 0, 0)
_nums = [int(n) for n in re.findall(r"\d+", VERSION)][:4]
VERSION_TUPLE = tuple(_nums + [0] * (4 - len(_nums)))

from PyInstaller.utils.win32.versioninfo import (VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
                                                  StringStruct, VarFileInfo, VarStruct)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
    kids=[
        StringFileInfo([StringTable("040404b0", [
            StringStruct("ProductName", "Café Desk"),
            StringStruct("FileDescription", "Café Desk 桌上咖啡吧"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("InternalName", "CafeDesk"),
            StringStruct("OriginalFilename", "CafeDesk.exe"),
            StringStruct("LegalCopyright", "DeanLin"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0404, 1200])]),
    ],
)

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "logo"), "logo")],
    hiddenimports=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CafeDesk",
    icon=os.path.join(ROOT, "logo", "cafe_desk.ico"),
    version=version_info,
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="CafeDesk",
    upx=False,
)
