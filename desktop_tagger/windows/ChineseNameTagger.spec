# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：把 tray_app.py（系統匣常駐工具，含全域快捷鍵
Ctrl+Alt+N）打包成 ChineseNameTagger.exe（含 Python + torch +
transformers + 兩個 BERT 模型，使用者端不需要自己安裝 Python）。

只能在 Windows 上跑（PyInstaller 不能跨平台編譯），用法見
.github/workflows/build-windows.yml：

    pyinstaller ChineseNameTagger.spec --noconfirm

輸出在 desktop_tagger/windows/dist/ChineseNameTagger/
"""
import os

block_cipher = None

WIN_DIR = os.path.dirname(os.path.abspath(SPEC))
BACKEND_DIR = os.path.abspath(os.path.join(WIN_DIR, "..", "backend"))

a = Analysis(
    [os.path.join(WIN_DIR, "tray_app.py")],
    pathex=[BACKEND_DIR, WIN_DIR],
    binaries=[],
    datas=[
        (os.path.join(BACKEND_DIR, "predict_bert.py"), "."),
        (os.path.join(BACKEND_DIR, "surnames.py"), "."),
        (os.path.join(BACKEND_DIR, "server.py"), "."),
        (os.path.join(BACKEND_DIR, "models", "model_bert_v4"), "models/model_bert_v4"),
        (os.path.join(BACKEND_DIR, "models", "model_bert_colab_v5"), "models/model_bert_colab_v5"),
    ],
    hiddenimports=["transformers", "torch", "pystray", "keyboard", "pyperclip", "PIL"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter"],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ChineseNameTagger",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ChineseNameTagger",
)
