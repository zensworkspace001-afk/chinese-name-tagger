# -*- coding: utf-8 -*-
"""選單列（menu bar）小工具，跟 Clipy 一樣常駐在螢幕右上角。

在背景執行緒跑 backend/server.py 的 Flask app（同一個 process，不用另外
開子行程），選單列顯示一個圖示，狀態不同顯示不同符號：
  🈶  服務正常、可以使用
  ⏳  剛啟動、模型還在載入
  ⚠️  啟動失敗

用法（跟 Clipy 一樣，用全域快捷鍵，不是右鍵選單——macOS 沒有官方管道能
從程式碼可靠地產生「Automator 服務」右鍵選單項目，實測 Automator 手刻
的 .workflow bundle 沒辦法通過系統的 Spotlight 掃描而無法註冊進右鍵選
單，改用全域快捷鍵才是穩定可行的做法）：
  1. 在任何 App 選取一段中文文字，自己按 Cmd+C 複製
  2. 按快捷鍵（預設 ⌘⌥N），或點選單列圖示裡的「標記剪貼簿內容」
  3. 跳出視窗顯示標出的人名；如果有標到人名，會自動把結果（例如
     「陳美玲、林志豪」）複製到剪貼簿，方便直接貼到別的地方用

（這支程式**不會**幫你模擬 Cmd+C 去複製選取的文字——之前試過用 pynput
模擬按鍵，但如果修飾鍵（Cmd）沒有確實在按下 C 之前生效，OS 可能會誤判
成只按了單獨的 "c"，這樣在有文字被選取的情況下就會直接把選取內容覆蓋
/刪除成字母 c，等於誤刪使用者的文字。這風險太高，所以改成完全不模擬
按鍵，複製這個動作永遠由使用者自己按 Cmd+C 完成，這支程式只負責讀剪貼
簿、標記、把結果寫回剪貼簿。）

這支程式同時做了「單一執行個體」保護：啟動時會檢查是不是已經有一份在
跑，如果是就跳出提醒然後直接結束，不會重複開出好幾份、搶同一個 port。

選單列有「設定」子選單可以調整：
  - 模型版本（哪個 BERT 模型來標記——模型不包在安裝檔裡，是選了以後才從
    網路下載、快取到 Application Support，見 model_downloader.py 開頭的
    說明；選單裡沒下載過的模型會標「未下載，~XXX MB」，點下去會先跳確認
    再下載）
  - 快捷鍵（幾組預先挑過、不會跟系統/常用 App 衝突的組合鍵）
  - 開機自動啟動（勾選/取消勾選登入時是否自動啟動這支程式）
設定會存在 ~/Library/Application Support/ChineseNameTagger/settings.json，
重開程式會記得上次的選擇。

第一次使用快捷鍵功能時，macOS 可能會跳出「輸入監控」的授權提示（監聽
全域快捷鍵需要這個權限，跟 Clipy 一樣），照著提示到「系統設定 > 隱私權
與安全性 > 輸入監控」打勾允許即可；這支程式不模擬按鍵，所以不需要
「輔助使用」權限。
"""
import fcntl
import json
import os
import plistlib
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import rumps
from pynput import keyboard

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

import server as backend_server  # noqa: E402

# launchd 啟動的 GUI App 沒有繼承使用者 shell 的 LANG/LC_ALL locale。
# pbpaste/pbcopy 本身會依照 locale 把剪貼簿內容轉碼，locale 沒設好的話
# pbpaste 會直接把中文字轉成一堆 "?" 才輸出（不是 Python 這邊解碼錯誤，
# 是 pbpaste 自己輸出的 bytes 就已經是 "?" 了）。所以呼叫 pbpaste/pbcopy
# 時要自己塞一個明確的 UTF-8 locale 進子行程的環境變數。
_UTF8_ENV = dict(os.environ, LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8")

PORT = backend_server.PORT
APP_SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/ChineseNameTagger")
LOCK_PATH = os.path.join(APP_SUPPORT_DIR, ".instance.lock")
SETTINGS_PATH = os.path.join(APP_SUPPORT_DIR, "settings.json")
LAUNCH_AGENT_LABEL = "com.zens.chinesetagger"
LAUNCH_AGENT_PLIST_PATH = os.path.expanduser(
    f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist"
)
LOG_DIR = os.path.expanduser("~/Library/Logs/ChineseNameTagger")

# 快捷鍵只給預先挑過、跟系統/Safari/Finder常用快捷鍵不衝突的組合，不開放
# 自由輸入——上一版用 ⌘⇧N 結果撞到 Safari「新增私密視窗」/ Finder「新增
# 檔案夾」，開放亂打容易再撞到別的快捷鍵。
HOTKEY_OPTIONS = [
    ("⌘⌥N（預設）", "<cmd>+<alt>+n"),
    ("⌘⌥T", "<cmd>+<alt>+t"),
    ("⌘⌥M", "<cmd>+<alt>+m"),
    ("⌘⇧⌥N", "<cmd>+<shift>+<alt>+n"),
    ("⌃⌥N（Control+Option+N）", "<ctrl>+<alt>+n"),
]
DEFAULT_HOTKEY = HOTKEY_OPTIONS[0][1]

# 三種狀態各用一張簡化過的向量圖示（見 _build_status_icons.py），剪影
# 差異夠大：放射狀星芒（就緒）vs. 三個小圓點（啟動中）vs. 三角驚嘆號
# （錯誤），縮到選單列大小還分得出來是哪個狀態。
STATUS_READY_ICON = os.path.join(BASE_DIR, "status_ready_icon.png")
STATUS_STARTING_ICON = os.path.join(BASE_DIR, "status_starting_icon.png")
STATUS_ERROR_ICON = os.path.join(BASE_DIR, "status_error_icon.png")

# 全域參考，避免 lock file object 被 GC 掉導致鎖被提早釋放
_instance_lock_file = None


def acquire_single_instance_lock():
    global _instance_lock_file
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    f = open(LOCK_PATH, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _instance_lock_file = f
    return True


def load_settings():
    defaults = {"model": backend_server.DEFAULT_MODEL, "hotkey": DEFAULT_HOTKEY}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        defaults.update({k: v for k, v in saved.items() if v})
    except Exception:
        pass
    return defaults


def save_settings(settings):
    try:
        os.makedirs(APP_SUPPORT_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[save_settings] exception: {e!r}", flush=True)


def is_autostart_enabled():
    return os.path.exists(LAUNCH_AGENT_PLIST_PATH)


def enable_autostart():
    os.makedirs(os.path.dirname(LAUNCH_AGENT_PLIST_PATH), exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [sys.executable],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": os.path.join(LOG_DIR, "server.log"),
        "StandardErrorPath": os.path.join(LOG_DIR, "server.log"),
        "ProcessType": "Background",
    }
    with open(LAUNCH_AGENT_PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(
        ["/bin/launchctl", "load", LAUNCH_AGENT_PLIST_PATH], capture_output=True
    )


def disable_autostart():
    # 不對「目前正在跑」的 process 呼叫 launchctl unload——如果這支程式
    # 本身就是被這個 LaunchAgent 啟動的，unload 會直接把自己關掉，使用者
    # 只是想取消「下次登入自動啟動」而已，不是想現在關程式。單純把 plist
    # 檔刪掉，下次登入 launchd 就找不到它、不會再自動啟動；這次登入期間
    # 目前這份程式繼續正常跑，不受影響。
    if os.path.exists(LAUNCH_AGENT_PLIST_PATH):
        try:
            os.remove(LAUNCH_AGENT_PLIST_PATH)
        except Exception as e:
            print(f"[disable_autostart] exception: {e!r}", flush=True)


def get_clipboard():
    # 不能用 subprocess.run(text=True)：launchd 啟動的 GUI App 沒有繼承
    # 使用者 shell 的 LANG/LC_ALL locale，text=True 會退回用 ASCII 解碼
    # pbpaste 的輸出，把中文字全部變成 "?"。改成拿原始 bytes 自己用
    # UTF-8 解碼，不依賴 locale。
    try:
        result = subprocess.run(
            ["/usr/bin/pbpaste"], capture_output=True, timeout=5, env=_UTF8_ENV
        )
        text = result.stdout.decode("utf-8", errors="replace")
        print(
            f"[get_clipboard] returncode={result.returncode} len={len(text)} "
            f"preview={text[:60]!r} stderr={result.stderr[:200]!r}",
            flush=True,
        )
        return text
    except Exception as e:
        print(f"[get_clipboard] exception: {e!r}", flush=True)
        return ""


def set_clipboard(text):
    try:
        subprocess.run(
            ["/usr/bin/pbcopy"], input=text.encode("utf-8"), timeout=5, env=_UTF8_ENV
        )
    except Exception as e:
        print(f"[set_clipboard] exception: {e!r}", flush=True)


def show_dialog(message):
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display dialog "{escaped}" buttons {{"好"}} default button 1 '
        f'with title "標記人名"'
    )
    subprocess.run(["/usr/bin/osascript", "-e", script])


def confirm_dialog(message, yes_label="下載", no_label="取消"):
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display dialog "{escaped}" buttons {{"{no_label}", "{yes_label}"}} '
        f'default button "{yes_label}" with title "標記人名"'
    )
    result = subprocess.run(
        ["/usr/bin/osascript", "-e", script], capture_output=True, text=True
    )
    return yes_label in result.stdout


def call_tag_api(text, model_name):
    body = json.dumps({"text": text, "model": model_name, "diffusion": True})
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/tag",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # /tag 對「模型還沒下載」這種可預期的情況回 400 + JSON body（不是
        # 純粹的連線失敗），把 body 解析出來一起回傳，讓呼叫端可以判斷
        # 是不是 model_not_downloaded、要不要跳確認下載。
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            raise e


def fetch_status():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/status", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[fetch_status] exception: {e!r}", flush=True)
        return None


def download_model_api(name):
    body = json.dumps({"model": name})
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/download_model",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    # 模型檔案不小，下載可能要一段時間，timeout 抓寬鬆一點。
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def names_to_message(data):
    if data.get("error"):
        return "錯誤：" + data["error"]
    names = data.get("names", [])
    if not names:
        return "沒有標示到任何人名。"
    seen, parts = set(), []
    for sur, giv in names:
        full = sur + giv
        if full not in seen:
            seen.add(full)
            parts.append(full)
    return "、".join(parts)


class TaggerMenuBarApp(rumps.App):
    def __init__(self):
        super().__init__(
            "ChineseNameTagger",
            icon=STATUS_STARTING_ICON,
            template=True,
            quit_button=None,
        )
        self.settings = load_settings()

        self.status_item = rumps.MenuItem("狀態：啟動中…")

        self.model_menu = rumps.MenuItem("模型版本")
        self.model_items = {}

        self.hotkey_menu = rumps.MenuItem("快捷鍵")
        self.hotkey_items = {}
        for label, combo in HOTKEY_OPTIONS:
            item = rumps.MenuItem(label, callback=self._make_hotkey_callback(combo))
            item.state = 1 if combo == self.settings["hotkey"] else 0
            self.hotkey_items[combo] = item
            self.hotkey_menu.add(item)

        self.autostart_item = rumps.MenuItem(
            "開機自動啟動", callback=self.toggle_autostart
        )
        self.autostart_item.state = 1 if is_autostart_enabled() else 0

        settings_menu = rumps.MenuItem("設定")
        settings_menu.add(self.model_menu)
        settings_menu.add(self.hotkey_menu)
        settings_menu.add(self.autostart_item)

        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem("標記剪貼簿內容", callback=self.tag_clipboard),
            settings_menu,
            None,
            rumps.MenuItem("重新啟動服務", callback=self.restart_service),
            rumps.MenuItem("結束", callback=self.quit_app),
        ]

        self._ready = False
        self._catalog_by_name = {}
        self.start_server()
        threading.Thread(target=self._watch_health, daemon=True).start()
        threading.Thread(target=self._populate_model_menu, daemon=True).start()
        self._start_hotkey_listener(self.settings["hotkey"])

    def _model_item_label(self, entry):
        if entry["downloaded"]:
            return entry["label"]
        size = entry.get("size_bytes")
        size_str = f"{size / 1e6:.0f}MB" if size else "?"
        return f"{entry['label']}（未下載，{size_str}）"

    def _populate_model_menu(self):
        # 模型目錄要問 server（背景執行緒跑 Flask app 起來後才問得到，
        # 而且 server 第一次還要去抓線上的 manifest），所以另開一個 thread
        # 輪詢，拿到後再動態把選單建出來。
        status = None
        for _ in range(60):
            status = fetch_status()
            if status and status.get("models"):
                break
            time.sleep(1)
        if not status:
            return
        self._catalog_by_name = {m["name"]: m for m in status["models"]}
        if self.settings["model"] not in self._catalog_by_name:
            self.settings["model"] = status.get("default") or next(
                iter(self._catalog_by_name)
            )
        for name, entry in self._catalog_by_name.items():
            item = rumps.MenuItem(
                self._model_item_label(entry), callback=self._make_model_callback(name)
            )
            item.state = 1 if name == self.settings["model"] else 0
            self.model_items[name] = item
            self.model_menu.add(item)

        # 目前選到的模型如果還沒下載（例如第一次使用），主動在背景下載，
        # 不用等使用者按標記才發現要下載、還得先跳確認。
        selected = self._catalog_by_name.get(self.settings["model"])
        if selected and not selected["downloaded"]:
            threading.Thread(
                target=self._download_model, args=(self.settings["model"], False),
                daemon=True,
            ).start()

    def _download_model(self, name, ask_first):
        entry = self._catalog_by_name.get(name)
        if entry is None:
            return False
        if ask_first:
            size = entry.get("size_bytes")
            size_str = f"（約 {size / 1e6:.0f}MB）" if size else ""
            if not confirm_dialog(f"模型 {entry['label']} 還沒下載{size_str}，現在下載嗎？"):
                return False

        item = self.model_items.get(name)
        if item:
            item.title = f"{entry['label']}（下載中…）"
        rumps.notification("中文人名標示", "", f"正在下載模型 {entry['label']}…")
        try:
            download_model_api(name)
        except Exception as e:
            print(f"[_download_model] exception: {e!r}", flush=True)
            show_dialog(f"模型下載失敗：{e}\n\n請檢查網路連線，稍後可以再從選單列「模型版本」重試。")
            if item:
                item.title = self._model_item_label(entry)
            return False

        entry["downloaded"] = True
        if item:
            item.title = self._model_item_label(entry)
        rumps.notification("中文人名標示", "", f"模型 {entry['label']} 下載完成")
        return True

    def _make_model_callback(self, name):
        def callback(_):
            threading.Thread(
                target=self._select_model, args=(name,), daemon=True
            ).start()

        return callback

    def _select_model(self, name):
        entry = self._catalog_by_name.get(name)
        if entry and not entry["downloaded"]:
            if not self._download_model(name, ask_first=True):
                return
        for other_name, item in self.model_items.items():
            item.state = 1 if other_name == name else 0
        self.settings["model"] = name
        save_settings(self.settings)

    def _make_hotkey_callback(self, combo):
        def callback(_):
            for other_combo, item in self.hotkey_items.items():
                item.state = 1 if other_combo == combo else 0
            self.settings["hotkey"] = combo
            save_settings(self.settings)
            self._start_hotkey_listener(combo)

        return callback

    def toggle_autostart(self, _):
        if self.autostart_item.state:
            disable_autostart()
            self.autostart_item.state = 0
        else:
            enable_autostart()
            self.autostart_item.state = 1

    def _start_hotkey_listener(self, combo):
        old = getattr(self, "_hotkey_listener", None)
        if old is not None:
            old.stop()
        self._hotkey_listener = keyboard.GlobalHotKeys({combo: self._on_hotkey})
        self._hotkey_listener.start()

    def start_server(self):
        def run():
            backend_server.app.run(
                host="127.0.0.1", port=PORT, debug=False, use_reloader=False
            )

        threading.Thread(target=run, daemon=True).start()

    def _watch_health(self):
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/health", timeout=2
                ) as resp:
                    ok = resp.status == 200
            except Exception:
                ok = False
            self._ready = ok
            self.icon = STATUS_READY_ICON if ok else STATUS_STARTING_ICON
            self.title = ""
            hotkey_label = next(
                (l for l, c in HOTKEY_OPTIONS if c == self.settings["hotkey"]),
                "快捷鍵",
            )
            self.status_item.title = (
                f"狀態：就緒（快捷鍵 {hotkey_label}）"
                if ok
                else "狀態：啟動中…（模型載入可能要 30-40 秒）"
            )
            time.sleep(3)

    def _on_hotkey(self):
        threading.Thread(target=self._tag_clipboard_thread, daemon=True).start()

    def tag_clipboard(self, _):
        threading.Thread(target=self._tag_clipboard_thread, daemon=True).start()

    def _tag_clipboard_thread(self):
        if not self._ready:
            show_dialog("服務尚未啟動，請稍後再試一次。")
            return
        self._tag_and_show(get_clipboard())

    def _tag_and_show(self, text):
        print(f"[_tag_and_show] text len={len(text) if text else 0}", flush=True)
        if not text or not text.strip():
            show_dialog("沒有偵測到文字，請先選取一段中文文字、按 Cmd+C 複製後再試一次。")
            return
        try:
            data = call_tag_api(text, self.settings["model"])
        except Exception as e:
            print(f"[_tag_and_show] call_tag_api exception: {e!r}", flush=True)
            show_dialog(f"連線失敗：{e}")
            return

        pending_model = data.get("model_not_downloaded")
        if pending_model:
            if self._download_model(pending_model, ask_first=True):
                self._tag_and_show(text)  # 下載完成後直接重試一次
            return

        message = names_to_message(data)
        print(f"[_tag_and_show] message={message!r}", flush=True)
        if data.get("names"):
            set_clipboard(message)
            show_dialog(message + "\n\n（已複製到剪貼簿）")
        else:
            show_dialog(message)

    def restart_service(self, _):
        rumps.notification("中文人名標示", "", "重新啟動服務中…")
        self.start_server()

    def quit_app(self, _):
        rumps.quit_application()


if __name__ == "__main__":
    if not acquire_single_instance_lock():
        show_dialog("中文人名標示已經在執行了（選單列應該已經有圖示，不用重複開啟）。")
        sys.exit(0)
    TaggerMenuBarApp().run()
