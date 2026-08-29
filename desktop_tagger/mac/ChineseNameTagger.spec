# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：把 menubar_app.py（選單列常駐 App，跟 Clipy 一樣顯示
在螢幕右上角）打包成 ChineseNameTagger.app（含 Python + torch +
transformers，使用者端不需要自己安裝 Python）。

模型「不」包在這個安裝檔裡——會在執行期間從 GitHub Release 下載、快取到
Application Support（見 backend/model_downloader.py）。這樣以後要換模型
版本，不用重新打包/簽章/公證整個 App，只要上傳新的模型 zip、更新
models_manifest.json 就好。

用法：
    cd desktop_tagger/mac
    ./build_venv/bin/pyinstaller ChineseNameTagger.spec --noconfirm

輸出在 desktop_tagger/mac/dist/ChineseNameTagger.app
"""
import os

block_cipher = None

MAC_DIR = os.path.dirname(os.path.abspath(SPEC))
BACKEND_DIR = os.path.abspath(os.path.join(MAC_DIR, "..", "backend"))

a = Analysis(
    [os.path.join(MAC_DIR, "menubar_app.py")],
    pathex=[BACKEND_DIR, MAC_DIR],
    binaries=[],
    datas=[
        (os.path.join(BACKEND_DIR, "predict_bert.py"), "."),
        (os.path.join(BACKEND_DIR, "surnames.py"), "."),
        (os.path.join(BACKEND_DIR, "server.py"), "."),
        (os.path.join(BACKEND_DIR, "model_downloader.py"), "."),
        (os.path.join(MAC_DIR, "status_ready_icon.png"), "."),
        (os.path.join(MAC_DIR, "status_starting_icon.png"), "."),
        (os.path.join(MAC_DIR, "status_error_icon.png"), "."),
    ],
    hiddenimports=["transformers", "torch", "rumps", "Foundation", "AppKit", "objc"],
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
    argv_emulation=False,
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

app = BUNDLE(
    coll,
    name="ChineseNameTagger.app",
    icon=os.path.join(MAC_DIR, "AppIcon.icns"),
    bundle_identifier="com.zens.chinesetagger",
    info_plist={
        "LSUIElement": True,
        "CFBundleName": "中文人名標示",
        "CFBundleDisplayName": "中文人名標示",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
