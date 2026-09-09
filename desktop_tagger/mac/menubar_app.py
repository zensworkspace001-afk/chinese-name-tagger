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
import ctypes
import ctypes.util
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
import pynput.keyboard._darwin as _pynput_darwin

# 實測抓到的真實當機（~/Library/Logs/DiagnosticReports 裡好幾份
# ChineseNameTagger-*.ips，同一組 call stack 出現超過一半）：pynput 在
# macOS 上收到 NSSystemDefined 事件（媒體鍵、系統定義按鍵之類）時，會在
# 它自己開的背景執行緒（不是主執行緒）呼叫 NSEvent.eventWithCGEvent_()
# 把 CGEvent 轉成 NSEvent；這支 ObjC method 在某些較新的 macOS 版本上，
# 內部會去查 Caps Lock/目前輸入法來源狀態，中間有一個
# dispatch_assert_queue 的判斷式——不是從預期的 thread/queue 呼叫就直接
# 讓整個 process 收到 SIGTRAP 死掉（是 C 層級的 trap，不是 Python
# exception，try/except 完全攔不到）。LaunchAgent 的 KeepAlive 設定會在
# crash 後自動重開，使用者實際感受到的就是選單列圖示一直起不來/閃現
# 又消失。我們的快捷鍵功能完全用不到媒體鍵事件，所以直接把這個分支
# patch 掉、跳過那個會炸的呼叫，其餘按鍵事件（真正的按下/放開、Caps
# Lock 本身）維持 pynput 原本邏輯不變，行為不受影響。
_original_pynput_handle_message = _pynput_darwin.Listener._handle_message


def _safe_pynput_handle_message(self, _proxy, event_type, event, _refcon, injected):
    if event_type == _pynput_darwin.NSSystemDefined:
        return
    return _original_pynput_handle_message(self, _proxy, event_type, event, _refcon, injected)


_pynput_darwin.Listener._handle_message = _safe_pynput_handle_message

from Foundation import NSObject, NSURL, NSURLRequest, NSMakeRect, NSMakePoint, NSUserDefaults
from Quartz import CAMediaTimingFunction, kCAMediaTimingFunctionEaseIn, kCAMediaTimingFunctionEaseOut
from AppKit import (
    NSApp,
    NSAnimationContext,
    NSAppearance,
    NSColor,
    NSEventMaskLeftMouseUp,
    NSEventMaskRightMouseUp,
    NSEventModifierFlagControl,
    NSEventTypeRightMouseUp,
    NSMenu,
    NSMenuItem,
    NSScreen,
    NSWindow,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSPopUpMenuWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorMoveToActiveSpace,
    NSWindowCollectionBehaviorTransient,
    NSViewWidthSizable,
    NSViewHeightSizable,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskMiniaturizable,
)
from WebKit import WKWebView, WKWebViewConfiguration
from PyObjCTools import AppHelper
from rumps import events as rumps_events

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

import server as backend_server  # noqa: E402
import license_check  # noqa: E402

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
    defaults = {"model": backend_server.DEFAULT_MODEL, "hotkey": DEFAULT_HOTKEY, "license_key": ""}
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
        # "Background" 告訴 launchd/kernel 這個 process 永遠不該跟前景
        # 互動式 App 搶 CPU 排程優先權（實測過：用這個值時 `ps -o pri`
        # 量到的優先權只有 4，遠低於一般前景 App 的 31，這正好可以解釋
        # 為什麼視窗（尤其是連續互動的捲動）就算 CSS 都優化過了還是卡——
        # 問題根本不在網頁內容，是整個 process 被系統當背景常駐服務在
        # 節流）。原本想改用 "Adaptive"（沒有前景視窗時當背景、有的時候
        # 自動比照前景 App），但這要系統正確偵測到「現在在幫前景使用者做
        # 事」，而這支 App 顯示視窗的方式（LSUIElement accessory + 開視窗
        # 當下暫時切成 regular policy）比較不標準，沒把握這個自動判斷一定
        # 抓得到。改用 "Interactive"，不用系統自動判斷，直接保證這個
        # process 一直照互動式前景 App 的優先權排程——代價是常駐在選單列
        # 什麼都沒做的時候也會用掉比純背景服務略多一點資源，但對這種選單
        # 列小工具來說換來可靠的視窗流暢度是值得的。
        "ProcessType": "Interactive",
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


def check_input_monitoring_granted():
    """用 IOKit 的 IOHIDCheckAccess 問系統「這個 process 有沒有輸入監控
    權限」——這是 Karabiner/Rectangle 這類需要監聽全域鍵盤事件的 App
    common 用的官方做法，不用引導使用者自己去系統設定看、也不用等使用者
    按了熱鍵才發現沒作用。回傳 True/False；判斷不出來（例如系統版本沒有
    這支 API）就回傳 None，呼叫端當作「不確定，不要主動打擾使用者」。
    kIOHIDRequestTypeListenEvent = 1；IOHIDCheckAccess 回傳值：
    0 = kIOHIDAccessTypeGranted，1 = kIOHIDAccessTypeDenied，
    2 = kIOHIDAccessTypeUnknown。
    """
    try:
        iokit = ctypes.CDLL(ctypes.util.find_library("IOKit"))
        fn = iokit.IOHIDCheckAccess
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_int]
        result = fn(1)
        if result == 0:
            return True
        if result == 1:
            return False
        return None
    except Exception as e:
        print(f"[check_input_monitoring_granted] exception: {e!r}", flush=True)
        return None


def open_input_monitoring_settings():
    # 這個 URL scheme 直接跳到「系統設定 > 隱私權與安全性 > 輸入監控」
    # 那一頁（Privacy_ListenEvent 是這個分頁在系統內部的識別碼），不用
    # 引導使用者自己在系統設定裡找路徑。
    subprocess.run(
        ["/usr/bin/open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"]
    )


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


_foreground_policy_count = 0


def _enter_foreground_policy():
    """這支 App 平常是 accessory activation policy（LSUIElement=True，
    沒有 Dock 圖示）。實測過：光靠 activateIgnoringOtherApps_(True) 在
    accessory policy 下常常不會真的把視窗變成 key/最前面（尤其是從背景
    執行緒的工作經 callAfter 觸發的情況），而且編輯選單的 Cmd+C/Cmd+V/
    Cmd+A 這些快捷鍵在 accessory policy 下也不會確實派送到 WKWebView
    裡的文字框。暫時切成 regular policy（顯示視窗/面板期間才會多一個
    Dock 圖示）是這類「常駐選單列但偶爾需要真正視窗」App 常見的做法。

    用計數器而不是直接切換，是因為現在有兩個地方（置中大視窗、選單列
    圖示彈出的面板）都可能個別開著或同時開著——如果誰關掉就直接切回
    accessory，另一個還開著的那個會跟著失去 Regular policy 才有的行為。
    """
    global _foreground_policy_count
    _foreground_policy_count += 1
    NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)


def _exit_foreground_policy():
    global _foreground_policy_count
    _foreground_policy_count = max(0, _foreground_policy_count - 1)
    if _foreground_policy_count == 0:
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)


class _ResultWebViewNavDelegate(NSObject):
    """WKNavigationDelegate：頁面（server.py 出的 /）載入完成時通知
    ResultWindowController，好知道現在能不能安全呼叫 evaluateJavaScript
    （太早呼叫的話 window.__ctApplyResult 還沒定義）。"""

    def webView_didFinishNavigation_(self, webView, navigation):
        if getattr(self, "owner", None) is not None:
            self.owner._on_did_finish_navigation()


class _ResultWindowDelegate(NSObject):
    """視窗的紅色關閉鈕改成「隱藏」而不是真的關閉/釋放，維持 singleton——
    真的關掉的話下次要嘛拿到已經 dealloc 的視窗 crash，要嘛得整頁重新
    載入、失去不閃爍的效果。"""

    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        if getattr(self, "owner", None) is not None:
            self.owner._on_window_hidden()
        return False


POPOVER_WIDTH = 640
POPOVER_HEIGHT = 420
# 彈出動畫：從「貼著圖示下方、縮小到 94%」的狀態，同時放大到 100%＋淡入，
# 感覺像從圖示那裡「長出來」——只用線性淡入淡出+位移看起來很機械，一定
# 要搭配 ease 曲線＋縮放才會有原生 App 那種「彈」的質感。收起來的動畫
# 刻意比彈出快一點（人對「東西消失」比「東西出現」更沒耐性等）。
POPOVER_SHOW_DURATION = 0.22
POPOVER_HIDE_DURATION = 0.16
POPOVER_START_SCALE = 0.94


class _PopoverPanel(NSWindow):
    """無邊框視窗預設 canBecomeKeyWindow 回 False（AppKit 假設無邊框視窗
    大多是提示框、不需要拿鍵盤焦點），面板裡的文字框會完全打不了字。
    覆寫成 True 才能讓面板正常接收鍵盤輸入，同時仍維持沒有標題列/邊框的
    外觀（跟原生選單/Claude 的彈出面板一樣）。"""

    def canBecomeKeyWindow(self):
        return True


class _PopoverWebViewNavDelegate(NSObject):
    def webView_didFinishNavigation_(self, webView, navigation):
        if getattr(self, "owner", None) is not None:
            self.owner._on_did_finish_navigation()


class _PopoverWindowDelegate(NSObject):
    """點面板外面（面板失去 key window 身份）就自動收起來，這是 popover
    最基本的互動預期——跟原本置中大視窗不同，不需要使用者自己按關閉。"""

    def windowDidResignKey_(self, notification):
        if getattr(self, "owner", None) is not None:
            self.owner._on_resign_key()


class StatusPopoverController:
    """左鍵點選單列圖示彈出的小面板：貼著圖示正下方彈出、點外面自動收起
    來，外觀/互動模仿 Claude 桌面版選單列圖示的做法。跟 ResultWindowController
    差別只在視窗本身的樣式跟顯示/隱藏邏輯——內容一樣是載入 server.py 出的
    同一個頁面（含標記人名跟設定），兩邊功能永遠一致，不用維護兩份 UI。"""

    def __init__(self, port):
        self._port = port
        self._window = None
        self._webview = None

    def _ensure_created(self):
        if self._window is not None:
            return
        rect = NSMakeRect(0, 0, POPOVER_WIDTH, POPOVER_HEIGHT)
        window = _PopoverPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        window.setReleasedWhenClosed_(False)
        window.setOpaque_(False)
        window.setHasShadow_(True)
        window.setBackgroundColor_(NSColor.clearColor())
        # NSPopUpMenuWindowLevel 讓面板浮在一般 App 視窗之上（包括全螢幕
        # 視窗），跟選單本身的層級一致——選單列小工具彈出的東西理當跟選單
        # 一樣「隨時蓋在最上面」，不會被使用者正在用的其他視窗擋住。
        window.setLevel_(NSPopUpMenuWindowLevel)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorTransient
        )

        webview = WKWebView.alloc().initWithFrame_configuration_(
            rect, WKWebViewConfiguration.alloc().init()
        )
        webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        # 圓角＋陰影：面板沒有原生視窗的標題列/邊框，這是唯一讓它看起來是
        # 「浮出來的卡片」而不是螢幕上一塊突兀方形的手段。
        webview.setWantsLayer_(True)
        webview.layer().setCornerRadius_(12)
        webview.layer().setMasksToBounds_(True)

        nav_delegate = _PopoverWebViewNavDelegate.alloc().init()
        nav_delegate.owner = self
        webview.setNavigationDelegate_(nav_delegate)

        win_delegate = _PopoverWindowDelegate.alloc().init()
        win_delegate.owner = self
        window.setDelegate_(win_delegate)
        window.setContentView_(webview)

        url = NSURL.URLWithString_(f"http://127.0.0.1:{self._port}/")
        webview.loadRequest_(NSURLRequest.requestWithURL_(url))

        self._window = window
        self._webview = webview
        self._nav_delegate = nav_delegate
        self._win_delegate = win_delegate

    def _sync_appearance(self):
        # 跟 ResultWindowController 同樣的理由：常駐選單列的視窗不會自動
        # 跟著系統深色模式切換，要每次顯示前自己讀一次目前設定再套用。
        style = NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        appearance_name = (
            "NSAppearanceNameDarkAqua" if style == "Dark" else "NSAppearanceNameAqua"
        )
        appearance = NSAppearance.appearanceNamed_(appearance_name)
        self._window.setAppearance_(appearance)
        self._webview.setAppearance_(appearance)

    def _compute_origin_below_status_item(self, status_item):
        button = status_item.button()
        if button is None or button.window() is None:
            return None
        # 選單列圖示所在的 NSStatusBarWindow，它的 frame 本身就已經是螢幕
        # 座標（跟一般 App 視窗不同，不用再另外做座標轉換），左邊界+寬度
        # 一半就是圖示中心點的 x 座標。
        button_frame = button.window().frame()
        screen = button.window().screen() or NSScreen.mainScreen()

        x = button_frame.origin.x + button_frame.size.width / 2 - POPOVER_WIDTH / 2
        y = button_frame.origin.y - POPOVER_HEIGHT - 4
        if screen is not None:
            visible = screen.visibleFrame()
            min_x = visible.origin.x + 8
            max_x = visible.origin.x + visible.size.width - POPOVER_WIDTH - 8
            x = max(min_x, min(x, max_x))
        return NSMakePoint(x, y)

    def _shrunk_frame(self, final_origin):
        """彈出動畫的起始 frame：貼著圖示下方那條邊固定不動、整個面板從
        94% 縮小、水平置中——視覺上像是從選單列圖示底下「長出來」，而不是
        整個方塊憑空位移。NSWindow 的 y 座標是左下角，頂邊 = origin.y +
        height，要讓頂邊固定，縮小後的 origin.y 要往上補回少掉的高度。"""
        start_width = POPOVER_WIDTH * POPOVER_START_SCALE
        start_height = POPOVER_HEIGHT * POPOVER_START_SCALE
        top_edge = final_origin.y + POPOVER_HEIGHT
        start_x = final_origin.x + (POPOVER_WIDTH - start_width) / 2
        start_y = top_edge - start_height
        return NSMakeRect(start_x, start_y, start_width, start_height)

    def toggle(self, status_item):
        self._ensure_created()
        if self._window.isVisible():
            self.hide()
        else:
            self.show(status_item)

    def show(self, status_item):
        self._ensure_created()
        final_origin = self._compute_origin_below_status_item(status_item)
        if final_origin is None:
            return
        self._sync_appearance()
        # rumps 常駐 App 沒有標準的應用程式選單，WKWebView 裡的文字框收不到
        # Cmd+C/Cmd+V/Cmd+A 這些標準快捷鍵（macOS 是透過選單項的 key
        # equivalent 派送到第一回應者的 -copy:/-paste:，不是 keyDown 就會
        # 自動處理）。補這個選單本身沒有副作用，先補上；但要讓這些快捷鍵在
        # accessory activation policy 下也生效，得暫時切成 regular policy，
        # 這會讓 Dock 跳出圖示、左上角出現應用程式選單——這支面板刻意選擇
        # 維持低調（不像大視窗那樣切 regular policy），所以 Cmd+C/Cmd+V/
        # Cmd+A 這幾個快捷鍵在這個面板裡目前不會生效；文字框本身輸入/選取
        # 不受影響，複製/貼上可以改用滑鼠右鍵選單（WKWebView 內建的
        # 剪貼簿操作，不經過這裡的 key equivalent 派送，不受影響）。
        _install_edit_menu()

        window = self._window
        final_frame = NSMakeRect(
            final_origin.x, final_origin.y, POPOVER_WIDTH, POPOVER_HEIGHT
        )
        window.setFrame_display_(self._shrunk_frame(final_origin), False)
        window.setAlphaValue_(0.0)
        NSApp.activateIgnoringOtherApps_(True)
        window.makeKeyAndOrderFront_(None)
        window.orderFrontRegardless()

        def changes(ctx):
            ctx.setDuration_(POPOVER_SHOW_DURATION)
            ctx.setTimingFunction_(
                CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseOut)
            )
            window.animator().setAlphaValue_(1.0)
            window.animator().setFrame_display_(final_frame, True)

        NSAnimationContext.runAnimationGroup_completionHandler_(changes, None)

    def hide(self):
        window = self._window
        if window is None or not window.isVisible():
            return
        final_origin = window.frame().origin
        start_frame = self._shrunk_frame(final_origin)

        def changes(ctx):
            ctx.setDuration_(POPOVER_HIDE_DURATION)
            ctx.setTimingFunction_(
                CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseIn)
            )
            window.animator().setAlphaValue_(0.0)
            window.animator().setFrame_display_(start_frame, True)

        def completion():
            window.orderOut_(None)
            # 復原成正常大小/全不透明，下次 show() 的 _shrunk_frame() 起點
            # 才會算得對，也不會下次 show() 一開始先閃一下縮小的畫面。
            window.setFrame_display_(
                NSMakeRect(final_origin.x, final_origin.y, POPOVER_WIDTH, POPOVER_HEIGHT),
                False,
            )
            window.setAlphaValue_(1.0)

        NSAnimationContext.runAnimationGroup_completionHandler_(changes, completion)

    def _on_resign_key(self):
        self.hide()

    def _on_did_finish_navigation(self):
        pass


class _StatusItemClickTarget(NSObject):
    """rumps 幫我們把 NSStatusItem 的 menu 設好之後，任何一種點擊（左鍵/
    右鍵）都會直接跳原生選單、不會呼叫 button 的 target/action。要做到
    「左鍵彈自訂面板、右鍵才叫原生選單」，得把 menu 從 status item 上拿
    掉，改成自己接管點擊事件、右鍵時再手動 popUpContextMenu 叫出同一個
    選單——選單本身內容/行為完全不變，只是改成手動觸發。"""

    def handleStatusItemClick_(self, sender):
        owner = getattr(self, "owner", None)
        if owner is None:
            return
        event = NSApp.currentEvent()
        is_right_click = event is not None and (
            event.type() == NSEventTypeRightMouseUp
            or bool(event.modifierFlags() & NSEventModifierFlagControl)
        )
        if is_right_click:
            owner._show_native_menu(sender)
        else:
            owner._toggle_popover()


def _install_edit_menu():
    """rumps 常駐 App 本來就沒有標準的應用程式選單（只有選單列圖示的下拉
    選單），所以 NSApp.mainMenu() 是 None——沒有「編輯」選單提供 Cmd+C/
    Cmd+V/Cmd+A 這些 key equivalent，WKWebView 裡的文字框就完全沒辦法用
    複製/貼上快捷鍵（macOS 的 Cmd+C 是透過選單項的 key equivalent 派送到
    第一回應者的 -copy:/-paste: 等等，不是 keyDown 就會自動處理）。這裡補
    一個最小的「編輯」選單，讓標準快捷鍵能正常運作。只需要建立一次。"""
    if NSApp.mainMenu() is not None:
        return

    main_menu = NSMenu.alloc().init()
    main_menu.addItem_(NSMenuItem.alloc().init())  # App 選單（留空即可）

    edit_menu = NSMenu.alloc().initWithTitle_("編輯")
    edit_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "編輯", None, ""
    )
    edit_menu_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_menu_item)

    def add(title, selector, key):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, selector, key
        )
        edit_menu.addItem_(item)

    add("復原", "undo:", "z")
    add("重做", "redo:", "Z")  # 大寫字母當 key equivalent，AppKit 會自動要求 Shift
    edit_menu.addItem_(NSMenuItem.separatorItem())
    add("剪下", "cut:", "x")
    add("拷貝", "copy:", "c")
    add("貼上", "paste:", "v")
    add("全選", "selectAll:", "a")

    NSApp.setMainMenu_(main_menu)


class ResultWindowController:
    """管理唯一一個顯示標記結果的原生視窗（NSWindow + WKWebView，載入
    server.py 出的 /）。

    重要：這個類別的所有方法都只能在主執行緒呼叫——WKWebView/NSWindow/
    NSApplication 不是執行緒安全的。呼叫端（hotkey callback、_tag_and_show
    背景執行緒）一律要透過 PyObjCTools.AppHelper.callAfter(...)，不要直接
    呼叫這裡的方法。"""

    def __init__(self, port):
        self._port = port
        self._window = None
        self._webview = None
        self._loaded = False
        self._pending = None  # (text, data)，導覽還沒完成時暫存

    def _ensure_created(self):
        if self._window is not None:
            return
        rect = NSMakeRect(0, 0, 760, 860)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        window.setTitle_("中文人名標示")
        window.setReleasedWhenClosed_(False)
        window.center()
        # 這是常駐選單列（accessory activation policy）App，沒有 Dock 圖示；
        # 視窗預設可能開在使用者當下不在的 Space、或被其他全螢幕視窗擋住，
        # 加這個讓它每次顯示時都跳到使用者目前所在的 Space。
        window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)

        webview = WKWebView.alloc().initWithFrame_configuration_(
            rect, WKWebViewConfiguration.alloc().init()
        )
        # 沒有這個的話，webview 的 frame 在 setContentView_ 之後不會跟著
        # 視窗一起縮放——拖拉調整視窗大小時，webview 還停在原本的固定
        # 大小，畫面會卡住/裂開，使用者感覺起來就是「視窗卡頓」。
        webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        nav_delegate = _ResultWebViewNavDelegate.alloc().init()
        nav_delegate.owner = self
        webview.setNavigationDelegate_(nav_delegate)

        win_delegate = _ResultWindowDelegate.alloc().init()
        win_delegate.owner = self
        window.setDelegate_(win_delegate)
        window.setContentView_(webview)

        url = NSURL.URLWithString_(f"http://127.0.0.1:{self._port}/")
        webview.loadRequest_(NSURLRequest.requestWithURL_(url))

        # 存住強參照，不然 PyObjC 可能把 delegate 提前 GC 掉。
        self._window = window
        self._webview = webview
        self._nav_delegate = nav_delegate
        self._win_delegate = win_delegate

    def show_empty(self):
        self._ensure_created()
        self._activate_and_front()

    def show_with_result(self, text, data):
        self._ensure_created()
        self._activate_and_front()
        if self._loaded:
            self._push_result(text, data)
        else:
            self._pending = (text, data)

    def _sync_appearance(self):
        # 這支 App 平常是背景常駐（LaunchAgent 啟動、accessory policy），
        # 實測發現視窗/webview 不會像一般前景 App 那樣自動跟著系統的深色
        # 模式切換——appearance 就這樣停在 Light，就算系統設定明明是深色，
        # 網頁裡的 prefers-color-scheme: dark 也不會生效（用強制設成
        # NSAppearanceNameDarkAqua 測試過，頁面 CSS 本身沒問題，純粹是
        # 視窗沒有真的拿到系統目前是深色模式這件事）。所以每次要顯示視窗
        # 之前，自己讀系統目前的深淺色設定，顯式設到 window/webview 上。
        style = NSUserDefaults.standardUserDefaults().stringForKey_("AppleInterfaceStyle")
        appearance_name = (
            "NSAppearanceNameDarkAqua" if style == "Dark" else "NSAppearanceNameAqua"
        )
        appearance = NSAppearance.appearanceNamed_(appearance_name)
        self._window.setAppearance_(appearance)
        self._webview.setAppearance_(appearance)

    def _activate_and_front(self):
        _install_edit_menu()
        self._sync_appearance()
        _enter_foreground_policy()
        NSApp.activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)
        self._window.orderFrontRegardless()

    def _on_window_hidden(self):
        _exit_foreground_policy()

    def _on_did_finish_navigation(self):
        self._loaded = True
        if self._pending is not None:
            text, data = self._pending
            self._pending = None
            self._push_result(text, data)

    def _push_result(self, text, data):
        payload = json.dumps({"text": text, "data": data}, ensure_ascii=False)
        # json.dumps 不會轉 U+2028/U+2029——這兩個在 JSON 字串裡合法，
        # 但直接內插進 JS 字串字面值會被當成換行、讓語法炸掉。剪貼簿文字
        # 常常來自 PDF/網頁，含這兩個字元不算罕見，所以要手動補轉義。
        payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        script = f"window.__ctApplyResult && window.__ctApplyResult({payload});"
        self._webview.evaluateJavaScript_completionHandler_(script, None)


class TaggerMenuBarApp(rumps.App):
    def __init__(self):
        super().__init__(
            "ChineseNameTagger",
            icon=STATUS_STARTING_ICON,
            template=True,
            quit_button=None,
        )
        self.settings = load_settings()
        self.result_window = ResultWindowController(PORT)
        self.popover = StatusPopoverController(PORT)
        self._click_target = None
        self._native_menu = None

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
        settings_menu.add(
            rumps.MenuItem("輸入監控權限…", callback=self.open_input_monitoring_prompt)
        )

        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem("標記剪貼簿內容", callback=self.tag_clipboard),
            rumps.MenuItem("開啟視窗", callback=self.open_window),
            settings_menu,
            None,
            rumps.MenuItem("重新啟動服務", callback=self.restart_service),
            rumps.MenuItem("結束", callback=self.quit_app),
        ]

        self._ready = False
        self._catalog_by_name = {}
        backend_server.set_menubar_bridge(self)
        self.start_server()
        threading.Thread(target=self._watch_health, daemon=True).start()
        threading.Thread(target=self._populate_model_menu, daemon=True).start()
        threading.Thread(target=self._maybe_prompt_input_monitoring, daemon=True).start()
        self._start_hotkey_listener(self.settings["hotkey"])
        # NSStatusItem 要等 rumps 的 run() 呼叫 initializeStatusBar() 之後
        # 才存在，這裡先註冊，run() 裡會在 initializeStatusBar() 之後、
        # 進事件迴圈之前呼叫到。
        rumps_events.before_start(self._customize_status_item_click)

    def _customize_status_item_click(self):
        """把 rumps 預設「點了就跳原生選單」的行為拆成左鍵/右鍵分流：左鍵
        彈自訂的 popover 面板，右鍵才叫出原本那個完整的原生下拉選單。"""
        status_item = self._nsapp.nsstatusitem
        self._native_menu = status_item.menu()
        # 拿掉 menu 之後，左右鍵都會變成單純的 button 點擊事件（不會自動
        # 跳選單），右鍵時我們自己用 popUpContextMenu 手動叫出存起來的
        # 那個選單——選單內容/行為完全不變。
        status_item.setMenu_(None)
        button = status_item.button()
        self._click_target = _StatusItemClickTarget.alloc().init()
        self._click_target.owner = self
        button.setTarget_(self._click_target)
        button.setAction_("handleStatusItemClick:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp)

    def _show_native_menu(self, sender):
        if self._native_menu is None:
            return
        NSMenu.popUpContextMenu_withEvent_forView_(
            self._native_menu, NSApp.currentEvent(), sender
        )

    def _toggle_popover(self):
        self.popover.toggle(self._nsapp.nsstatusitem)

    def get_settings_payload(self):
        """給彈出面板（跟大視窗）裡的設定齒輪區塊用：模型清單/目前選擇/
        快捷鍵選項/目前選擇/開機自動啟動狀態，一次打包回傳。"""
        models = [
            {
                "name": name,
                "label": entry["label"],
                "downloaded": entry["downloaded"],
                "size_bytes": entry.get("size_bytes"),
            }
            for name, entry in self._catalog_by_name.items()
        ]
        return {
            "model": self.settings.get("model"),
            "models": models,
            "hotkey": self.settings.get("hotkey"),
            "hotkeyOptions": HOTKEY_OPTIONS,
            "autostart": bool(self.autostart_item.state),
        }

    def select_default_model(self, name, confirmed=False):
        """面板裡切換「預設模型」（快捷鍵標記剪貼簿時用的那個），跟原生
        選單「模型版本」子選單選同一個模型是同一套邏輯，只是觸發來源從
        NSMenuItem 換成 Flask 的 /settings/model。

        注意：這個方法是從 Flask 自己的 request thread 呼叫進來的（就是
        /settings/model 那個路由的 handler）。下載本身交給
        backend_server.start_download() 在背景執行緒做、立刻回應——
        不能在這裡同步等下載做完才回應：一來 Flask 內建的開發伺服器預設
        不是多執行緒，外層請求還在處理中時同一支伺服器不會去接自己發給
        自己的新連線（例如網頁那邊想輪詢進度）會直接卡死；二來就算不卡
        死，同步阻塞也等於完全放棄了進度回報——網頁那邊只能在背景執行緒
        真正跑起來、開始寫入 _download_progress 之後，才有進度可以輪詢
        （用 /download_progress，見 index_html.py）。下載完成後的「切換
        成這個模型」由 on_download_complete() 接手，不在這裡做。"""
        entry = self._catalog_by_name.get(name)
        if entry is None:
            return {"error": f"找不到模型 {name}"}
        if not entry["downloaded"] and not confirmed:
            return {
                "needs_confirm": True,
                "label": entry["label"],
                "size_bytes": entry.get("size_bytes"),
            }
        if not entry["downloaded"] and not self.is_licensed():
            return {"error": "請先輸入授權碼才能下載模型", "license_required": True}
        if not entry["downloaded"]:
            try:
                started = backend_server.start_download(name)
            except Exception as e:
                return {"error": str(e)}
            return {"ok": True, "downloading": True, "already_running": not started}
        for other_name, item in self.model_items.items():
            item.state = 1 if other_name == name else 0
        self.settings["model"] = name
        save_settings(self.settings)
        return {"ok": True}

    def on_download_complete(self, name, success, error=None):
        """backend_server.start_download() 背景執行緒下載結束時呼叫回來
        （不管是原生選單觸發、還是設定面板觸發的下載，都會走到這裡）。
        成功的話比照 select_default_model() 原本「下載完就切過去」的
        行為；失敗的話只更新選單項標籤，不跳原生 dialog——這個 callback
        可能是網頁那邊觸發的下載失敗，網頁自己會顯示 /download_progress
        裡的 error，原生 dialog 是給原生選單那條路徑用的（見
        _download_model()），這裡不重複跳一次。"""
        entry = self._catalog_by_name.get(name)
        if entry is None:
            return
        item = self.model_items.get(name)
        if not success:
            if item:
                item.title = self._model_item_label(entry)
            return
        entry["downloaded"] = True
        if item:
            item.title = self._model_item_label(entry)
        for other_name, other_item in self.model_items.items():
            other_item.state = 1 if other_name == name else 0
        self.settings["model"] = name
        save_settings(self.settings)
        rumps.notification("中文人名標示", "", f"模型 {entry['label']} 下載完成")

    def select_hotkey(self, combo):
        if combo not in self.hotkey_items:
            return {"error": f"不支援的快捷鍵組合 {combo}"}
        for other_combo, item in self.hotkey_items.items():
            item.state = 1 if other_combo == combo else 0
        self.settings["hotkey"] = combo
        save_settings(self.settings)
        self._start_hotkey_listener(combo)
        return {"ok": True}

    def set_autostart(self, enabled):
        if enabled:
            enable_autostart()
        else:
            disable_autostart()
        self.autostart_item.state = 1 if enabled else 0
        return {"ok": True, "autostart": enabled}

    def is_licensed(self):
        # 完全離線驗證（見 license_check.py 開頭說明）——每次都重新驗證存
        # 起來的授權碼，而不是額外存一個「licensed: true」的旗標，這樣
        # settings.json 被手動改過（例如清掉授權碼那一行）也不會殘留一個
        # 對不上的已授權狀態。
        return license_check.verify_license_key(self.settings.get("license_key", ""))

    def activate_license(self, key):
        if not license_check.verify_license_key(key):
            return {"ok": False, "error": "授權碼無效，請確認複製完整（包含開頭的 CNT1-）。"}
        self.settings["license_key"] = key.strip()
        save_settings(self.settings)
        return {"ok": True}

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
        # 不用等使用者按標記才發現要下載、還得先跳確認。沒授權碼就不主動
        # 下載——模型檔案本身不小（好幾百 MB），沒必要幫還沒付錢的使用者
        # 先佔頻寬/硬碟空間。
        selected = self._catalog_by_name.get(self.settings["model"])
        if selected and not selected["downloaded"] and self.is_licensed():
            threading.Thread(
                target=self._download_model, args=(self.settings["model"], False),
                daemon=True,
            ).start()

    def _download_model(self, name, ask_first):
        entry = self._catalog_by_name.get(name)
        if entry is None:
            return False
        if not self.is_licensed():
            # 跟 /tag 一樣的授權檢查，這裡額外擋一層是因為模型下載走的是
            # 獨立的 /download_model，不會經過 /tag 那個檢查點——沒授權碼
            # 不该讓使用者連模型都下載得到。這只擋得住透過這支 App 走的
            # 下載路徑：manifest.json 跟模型 zip 本身放在公開的 GitHub
            # repo/release，網址不是秘密，任何人本來就可以繞過這支 App
            # 直接用瀏覽器/curl 抓，這個檢查擋的是「透過正常管道用」的
            # 情況，不是真正的存取控制——要做到後者得把模型放到需要驗證
            # 才能存取的地方（例如私有 repo + 動態簽發的短期下載連結），
            # 那就不是純離線驗證能做到的了。
            show_dialog("這個功能需要授權碼，請先在視窗/選單列圖示的面板輸入授權碼。")
            return False
        if ask_first:
            size = entry.get("size_bytes")
            size_str = f"（約 {size / 1e6:.0f}MB）" if size else ""
            if not confirm_dialog(f"模型 {entry['label']} 還沒下載{size_str}，現在下載嗎？"):
                return False

        item = self.model_items.get(name)
        if item:
            item.title = f"{entry['label']}（下載中… 0%）"
        rumps.notification("中文人名標示", "", f"正在下載模型 {entry['label']}…")

        # start_download() 只負責啟動背景執行緒，立刻回傳——真正的下載
        # 進度靠下面輪詢 get_download_progress() 拿，不是靠這裡的回傳值。
        # 這支方法本身已經是在背景執行緒跑的（見 _make_model_callback
        # 用 threading.Thread 呼叫 _select_model），阻塞在下面的輪詢迴圈
        # 不會卡住選單列 UI。
        try:
            backend_server.start_download(name)
        except Exception as e:
            print(f"[_download_model] exception: {e!r}", flush=True)
            show_dialog(f"模型下載失敗：{e}")
            if item:
                item.title = self._model_item_label(entry)
            return False

        last_pct = -1
        while True:
            time.sleep(0.3)
            progress = backend_server.get_download_progress(name)
            if progress is None:
                break
            total = progress.get("total")
            if total and item:
                pct = int(progress.get("downloaded", 0) * 100 / total)
                if pct != last_pct:
                    last_pct = pct
                    item.title = f"{entry['label']}（下載中… {pct}%）"
            if progress.get("done"):
                if progress.get("error"):
                    show_dialog(
                        f"模型下載失敗：{progress['error']}\n\n"
                        "可以從選單列「模型版本」重試，如果同樣的錯誤反覆出現，代表不是暫時性問題。"
                    )
                    if item:
                        item.title = self._model_item_label(entry)
                    return False
                break

        # 下載成功後 entry["downloaded"]／item.title／self.settings["model"]
        # 已經由 backend_server 背景執行緒透過 on_download_complete()
        # 更新過了（同一個回呼，不管下載是原生選單還是設定面板觸發的都
        # 會走到），這裡不用重複做，避免兩邊各自更新同一份狀態導致不一致。
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
            # self.icon / self.title / self.status_item.title 底層都是
            # AppKit 物件（NSStatusItem 之類），不是執行緒安全的，但這裡
            # 是在背景執行緒（threading.Thread 跑的 _watch_health）裡每
            # 3 秒直接改——長期下來這是有問題的：任何時候（包括使用者正在
            # 拖拉調整視窗大小的當下）都可能插進來搶主執行緒的 AppKit 存
            # 取，這正是拖拉視窗偶爾會卡一下的典型成因之一。改成透過
            # AppHelper.callAfter 排到主執行緒做。
            AppHelper.callAfter(self._apply_health_status, ok)
            time.sleep(3)

    def _apply_health_status(self, ok):
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

    def _on_hotkey(self):
        threading.Thread(target=self._tag_clipboard_thread, daemon=True).start()

    def tag_clipboard(self, _):
        threading.Thread(target=self._tag_clipboard_thread, daemon=True).start()

    def _tag_clipboard_thread(self):
        if not self._ready:
            show_dialog("服務尚未啟動，請稍後再試一次。")
            return
        if not self.is_licensed():
            show_dialog("這個功能需要授權碼。請點選單列圖示開啟視窗，在裡面輸入授權碼後再試一次。")
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
        AppHelper.callAfter(self.result_window.show_with_result, text, data)

    def open_window(self, _):
        AppHelper.callAfter(self.result_window.show_empty)

    def _maybe_prompt_input_monitoring(self):
        # App 剛啟動、第一次確定「輸入監控」權限沒開的時候主動提醒一次
        # （不是每次啟動都問——問過一次就記在 settings.json 裡，之後就
        # 算權限還是沒開也不會再自動跳出來，使用者可以從「設定 > 輸入
        # 監控權限…」自己再叫出來）。IOHIDCheckAccess 剛啟動當下可能還
        # 沒真的有結果，稍微等一下比較保險。
        time.sleep(2)
        if self.settings.get("asked_input_monitoring"):
            return
        granted = check_input_monitoring_granted()
        if granted is not False:
            # True（已授權）或 None（系統版本判斷不出來）都不用主動打擾。
            return
        self.settings["asked_input_monitoring"] = True
        save_settings(self.settings)
        self._show_input_monitoring_dialog()

    def open_input_monitoring_prompt(self, _):
        threading.Thread(target=self._show_input_monitoring_dialog, daemon=True).start()

    def _show_input_monitoring_dialog(self):
        go = confirm_dialog(
            "要用全域快捷鍵（例如 ⌘⌥N）標記剪貼簿裡的文字，"
            "需要在「系統設定 > 隱私權與安全性 > 輸入監控」裡允許「中文人名標示」。\n\n"
            "按「前往設定」會直接打開那一頁，找到「中文人名標示」打勾允許，"
            "然後回到選單列用「重新啟動服務」讓它生效。\n\n"
            "如果你只想用選單列的「開啟視窗」手動貼文字分析，不需要開這個權限。",
            yes_label="前往設定",
            no_label="稍後",
        )
        if go:
            open_input_monitoring_settings()

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
