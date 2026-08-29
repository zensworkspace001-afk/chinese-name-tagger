# -*- coding: utf-8 -*-
"""Windows 系統匣（tray）常駐工具，概念跟 macOS 選單列版一樣：在背景執行緒
跑 backend/server.py 的 Flask app，系統匣圖示顯示服務狀態。

Windows 作業系統沒有「任意 App 裡選取文字」的右鍵服務機制（只有檔案總管
的檔案右鍵可以自訂），所以用**全域快捷鍵**（預設 Ctrl+Alt+N）作為功能
對等的替代方案：選字後按快捷鍵 -> 模擬 Ctrl+C 複製選取範圍 -> 讀剪貼簿
-> 呼叫本機 API -> 用訊息框顯示標出的人名，並把剪貼簿還原成使用者原本
的內容。
"""
import ctypes
import json
import os
import sys
import threading
import time
import urllib.request

import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

import server as backend_server  # noqa: E402

PORT = backend_server.PORT
HOTKEY = "ctrl+alt+n"
MB_ICONINFORMATION = 0x40

_status = {"ready": False}


def start_server():
    def run():
        backend_server.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

    threading.Thread(target=run, daemon=True).start()


def make_icon_image(ready):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (46, 160, 67, 255) if ready else (201, 143, 32, 255)
    d.ellipse([4, 4, size - 4, size - 4], fill=color)
    d.text((22, 18), "名", fill=(255, 255, 255, 255))
    return img


def watch_health(icon):
    while True:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as resp:
                ok = resp.status == 200
        except Exception:
            ok = False
        _status["ready"] = ok
        icon.icon = make_icon_image(ok)
        icon.title = "中文人名標示 - " + ("就緒（快捷鍵 Ctrl+Alt+N）" if ok else "啟動中…")
        time.sleep(3)


def show_message(title, message):
    ctypes.windll.user32.MessageBoxW(0, message, title, MB_ICONINFORMATION)


def tag_selected_text():
    if not _status["ready"]:
        show_message("標記人名", "服務尚未啟動，請稍後再試一次（可能剛開機，服務正在啟動中）。")
        return

    try:
        previous_clip = pyperclip.paste()
    except Exception:
        previous_clip = None

    keyboard.send("ctrl+c")
    time.sleep(0.2)

    try:
        text = pyperclip.paste()
    except Exception:
        text = ""

    if not text or not text.strip():
        show_message("標記人名", "沒有偵測到選取的文字，請先選取一段文字再按 Ctrl+Alt+N。")
        return

    try:
        body = json.dumps(
            {"text": text, "model": "model_bert_colab_v5", "diffusion": True}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/tag",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        show_message("標記人名", f"連線失敗：{e}")
        return
    finally:
        if previous_clip is not None:
            try:
                pyperclip.copy(previous_clip)
            except Exception:
                pass

    if data.get("error"):
        show_message("標記人名", "錯誤：" + data["error"])
        return

    names = data.get("names", [])
    if not names:
        show_message("標記人名", "沒有標示到任何人名。")
        return

    seen = set()
    parts = []
    for sur, giv in names:
        full = sur + giv
        if full not in seen:
            seen.add(full)
            parts.append(full)
    show_message("標記人名", "、".join(parts))


def quit_app(icon, _item):
    icon.stop()
    os._exit(0)


def main():
    start_server()
    icon = pystray.Icon(
        "chinese_name_tagger",
        make_icon_image(False),
        "中文人名標示 - 啟動中…",
        menu=pystray.Menu(
            pystray.MenuItem("標記人名（快捷鍵 Ctrl+Alt+N）", lambda icon, item: tag_selected_text()),
            pystray.MenuItem("結束", quit_app),
        ),
    )
    threading.Thread(target=watch_health, args=(icon,), daemon=True).start()
    keyboard.add_hotkey(HOTKEY, tag_selected_text)
    icon.run()


if __name__ == "__main__":
    main()
