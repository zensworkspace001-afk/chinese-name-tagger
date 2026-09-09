# -*- coding: utf-8 -*-
"""本機常駐 API server，給 macOS 選單列工具／Windows 系統匣工具呼叫。

跟 streamlit_app/app.py（Flask 網頁版）用同一套 predict_bert.py，但這裡
只出 JSON API，不出網頁 UI，並且監聽獨立的 port（5111），避免跟本機測試
用的 app.py（5050）衝突。

模型不包在安裝檔裡，是執行期間從 GitHub Release 下載、快取到使用者
資料夾（見 model_downloader.py 開頭的說明），所以這裡多了 /status（列出
「目錄」裡有哪些模型、各自有沒有下載）跟 /download_model（觸發下載）
兩個端點；/tag 如果選到的模型還沒下載，回傳明確的錯誤，不會自己在
request 裡面悶著頭下載（下載可能要一段時間，讓呼叫端自己決定要不要
顯示進度、要不要背景做）。
"""
import glob
import os
import re
import sys
import threading

from flask import Flask, jsonify, request

# 模型名稱只給英數字/底線/連字號，不接受路徑分隔符或 ".."——get_model()
# 會直接拿這個字串去 os.path.join 組路徑，沒有這層檢查的話，/tag 的
# model 欄位（純使用者輸入，這支 server 沒有任何驗證/CORS/CSRF 保護，
# 同機器上其他 process、甚至瀏覽器頁面的 blind cross-origin POST 都打得
# 到 127.0.0.1:5111）可以塞 "../../../某路徑" 之類的字串做路徑穿越，
# 誘騙這支程式把任意目錄當模型載入。
_SAFE_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# PyInstaller 打包後，資源檔案會被解到 sys._MEIPASS；開發時直接用這個
# 檔案所在目錄。（模型本身不在這裡面，是執行期間下載到使用者資料夾。）
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

from predict_bert import (  # noqa: E402
    load_model,
    predict_document,
    split_sentences_keep_punct,
)
import model_downloader  # noqa: E402
import license_check  # noqa: E402
from index_html import INDEX_HTML  # noqa: E402

DEFAULT_MODEL = "model_bert_colab_v5"
PORT = 5111

app = Flask(__name__)
_model_cache = {}

# 下載進度共享狀態：{model_name: {"downloaded": int, "total": int, "done": bool, "error": str|None}}。
# 之前的做法（/download_model）是整個請求同步阻塞到下載+解壓縮都做完才
# 回應，呼叫端（不管是選單列原生選單、還是設定面板的網頁）拿不到任何
# 中途進度，使用者體驗上就是一段時間完全沒有回饋，看起來像卡住。改成
# 背景執行緒下載、進度寫進這個 dict，讓 HTTP 端（/download_progress
# 輪詢）跟同行程內的呼叫端（menubar_app.py 直接呼叫 get_download_progress）
# 都能拿到即時進度。單純的 dict 讀寫在 CPython 因為 GIL 是原子的，這裡
# 只是拿來顯示進度用，不是正確性攸關的臨界區，不需要額外上鎖。
_download_progress = {}


def start_download(name):
    """啟動背景下載執行緒。回傳 True 表示真的啟動了一個新的下載，
    False 表示同一個模型已經有一個下載在跑（避免使用者連續點兩次觸發
    兩個平行下載，浪費頻寬又互相覆蓋同一個目的地資料夾）。

    HTTP 端點（/download_model_async）跟 menubar_app.py 的原生選單／
    設定面板共用這個函式，不要各自兜一份下載+進度追蹤邏輯，也不要
    在 Flask 的 request thread 裡直接同步呼叫 download_and_extract——
    那樣會讓進度完全回報不出來，等於白做了進度追蹤機制。"""
    entry = _manifest_entry(name)
    if entry is None:
        raise ValueError(f"找不到模型 {name}（manifest 抓不到或沒有這個名字）")

    existing = _download_progress.get(name)
    if existing and not existing.get("done"):
        return False

    _download_progress[name] = {
        "downloaded": 0,
        "total": entry.get("size_bytes") or 0,
        "done": False,
        "error": None,
    }

    def on_progress(downloaded, total):
        state = _download_progress.get(name)
        if state is None:
            return
        state["downloaded"] = downloaded
        if total:
            state["total"] = total

    def run():
        try:
            model_downloader.download_and_extract(
                entry, model_downloader.get_cache_dir(), progress_cb=on_progress,
            )
            _model_cache.pop(name, None)
            _download_progress[name]["done"] = True
            if _menubar_bridge is not None:
                _menubar_bridge.on_download_complete(name, success=True)
        except Exception as e:
            print(f"[start_download] failed: {e!r}", flush=True)
            _download_progress[name]["error"] = str(e)
            _download_progress[name]["done"] = True
            if _menubar_bridge is not None:
                _menubar_bridge.on_download_complete(name, success=False, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return True


def get_download_progress(name):
    return _download_progress.get(name)
_manifest_cache_path = os.path.normpath(
    os.path.join(model_downloader.get_cache_dir(), "..", "models_manifest_cache.json")
)

# menubar_app.py 的 TaggerMenuBarApp 實例——「模型版本／快捷鍵／開機自動
# 啟動」這些設定的實際狀態（settings.json、全域快捷鍵監聽、NSMenuItem
# 打勾狀態）都活在那支程式裡，這支 server.py 本身沒有也不該重複一份。
# 頁面上設定齒輪區塊要讀寫這些設定時，靠這個 bridge 呼叫回去，而不是把
# 設定邏輯搬進 Flask 這邊重寫一次。獨立執行 server.py（沒有選單列 App）
# 時 bridge 是 None，/settings 系列端點會退回成唯讀/回報錯誤，不影響
# /tag 等核心功能。
_menubar_bridge = None


def set_menubar_bridge(bridge):
    global _menubar_bridge
    _menubar_bridge = bridge


def get_catalog():
    """回傳 manifest 裡的模型清單（線上抓不到就退回上次成功抓到的快取，
    再抓不到就從本機資料夾裡有什麼算什麼），每筆加上 downloaded 欄位。"""
    import json

    manifest = None
    try:
        manifest = model_downloader.fetch_manifest()
        with open(_manifest_cache_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
    except Exception as e:
        print(f"[get_catalog] fetch_manifest failed: {e!r}", flush=True)
        try:
            with open(_manifest_cache_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = None

    cache_dir = model_downloader.get_cache_dir()
    if manifest is None:
        # 連快取的 manifest 都沒有（第一次用就沒網路）：至少把本機資料夾
        # 裡已經有的模型列出來，能用就先用。
        dirs = sorted(glob.glob(os.path.join(cache_dir, "model_bert*")))
        return [
            {
                "name": os.path.basename(d),
                "label": os.path.basename(d),
                "downloaded": True,
                "default": os.path.basename(d) == DEFAULT_MODEL,
            }
            for d in dirs
            if os.path.isfile(os.path.join(d, "config.json"))
        ]

    catalog = []
    for entry in manifest.get("models", []):
        catalog.append(
            {
                "name": entry["name"],
                "label": entry.get("label", entry["name"]),
                "downloaded": model_downloader.is_downloaded(entry, cache_dir),
                "default": bool(entry.get("default")),
                "size_bytes": entry.get("size_bytes"),
            }
        )
    return catalog


def _manifest_entry(name):
    manifest = model_downloader.fetch_manifest()
    for entry in manifest.get("models", []):
        if entry["name"] == name:
            return entry
    return None


def get_model(name):
    if not name or not _SAFE_MODEL_NAME_RE.match(name):
        raise FileNotFoundError(name)
    if name not in _model_cache:
        path = os.path.join(model_downloader.get_cache_dir(), name)
        if not os.path.isfile(os.path.join(path, "config.json")):
            raise FileNotFoundError(name)
        _model_cache[name] = load_model(path)
    return _model_cache[name]


@app.route("/")
def index():
    return INDEX_HTML


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/status")
def api_status():
    catalog = get_catalog()
    default = next(
        (m["name"] for m in catalog if m["default"]),
        (catalog[0]["name"] if catalog else None),
    )
    return jsonify({"models": catalog, "default": default})


@app.route("/models")
def api_models():
    # 保留舊路徑相容（回傳「已下載」的模型名單），新的用法建議用 /status。
    catalog = get_catalog()
    downloaded = [m["name"] for m in catalog if m["downloaded"]]
    default = DEFAULT_MODEL if DEFAULT_MODEL in downloaded else (
        downloaded[0] if downloaded else None
    )
    return jsonify({"models": downloaded, "default": default})


@app.route("/download_model", methods=["POST"])
def api_download_model():
    if _menubar_bridge is not None and not _menubar_bridge.is_licensed():
        return jsonify({"error": "請先輸入授權碼才能下載模型", "license_required": True}), 402

    data = request.get_json(force=True) or {}
    name = data.get("model")
    if not name:
        return jsonify({"error": "沒有指定 model"}), 400

    entry = _manifest_entry(name)
    if entry is None:
        return jsonify({"error": f"找不到模型 {name}（manifest 抓不到或沒有這個名字）"}), 404

    try:
        model_downloader.download_and_extract(entry, model_downloader.get_cache_dir())
    except Exception as e:
        print(f"[/download_model] failed: {e!r}", flush=True)
        return jsonify({"error": str(e)}), 500

    _model_cache.pop(name, None)  # 逼下次 get_model 重新載入剛下載的版本
    return jsonify({"ok": True, "model": name})


@app.route("/download_model_async", methods=["POST"])
def api_download_model_async():
    """跟 /download_model 做同一件事，差別是立刻回應、不等下載完成——
    網頁面板改用這個端點，搭配 /download_progress 輪詢，才做得出真正的
    進度條。舊的 /download_model（同步阻塞版）繼續保留，不動它的行為。"""
    if _menubar_bridge is not None and not _menubar_bridge.is_licensed():
        return jsonify({"error": "請先輸入授權碼才能下載模型", "license_required": True}), 402

    data = request.get_json(force=True) or {}
    name = data.get("model")
    if not name:
        return jsonify({"error": "沒有指定 model"}), 400

    try:
        started = start_download(name)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({"ok": True, "downloading": True, "already_running": not started})


@app.route("/delete_model", methods=["POST"])
def api_delete_model():
    """刪除已下載的模型，釋放磁碟空間。擋掉刪除「目前使用中」的模型——
    刪掉那個會讓 /tag 立刻失去可用模型，而且使用者當下不會意識到是
    這個原因，寧可讓使用者先切換到別的已下載模型再刪。"""
    data = request.get_json(force=True) or {}
    name = data.get("model")
    if not name:
        return jsonify({"error": "沒有指定 model"}), 400

    if _menubar_bridge is not None and _menubar_bridge.settings.get("model") == name:
        return jsonify({"error": "這是目前使用中的模型，請先在「預設模型」切換成其他已下載的模型，再回來刪除這個"}), 400

    try:
        model_downloader.delete_model(name, model_downloader.get_cache_dir())
    except Exception as e:
        print(f"[/delete_model] failed: {e!r}", flush=True)
        return jsonify({"error": str(e)}), 500

    _model_cache.pop(name, None)
    _download_progress.pop(name, None)
    if _menubar_bridge is not None:
        _menubar_bridge.on_model_deleted(name)
    return jsonify({"ok": True})


@app.route("/download_progress")
def api_download_progress():
    name = request.args.get("model", "")
    state = get_download_progress(name)
    if state is None:
        return jsonify({"downloaded": 0, "total": 0, "done": False, "error": None, "not_started": True})
    return jsonify(state)


@app.route("/settings")
def api_get_settings():
    if _menubar_bridge is None:
        return jsonify(
            {"model": DEFAULT_MODEL, "models": get_catalog(), "hotkey": None,
             "hotkeyOptions": [], "autostart": False}
        )
    return jsonify(_menubar_bridge.get_settings_payload())


@app.route("/settings/model", methods=["POST"])
def api_set_default_model():
    if _menubar_bridge is None:
        return jsonify({"error": "設定功能只能在選單列 App 裡使用"}), 503
    data = request.get_json(force=True) or {}
    name = data.get("model")
    if not name:
        return jsonify({"error": "沒有指定 model"}), 400
    return jsonify(_menubar_bridge.select_default_model(name, confirmed=bool(data.get("confirmed"))))


@app.route("/settings/hotkey", methods=["POST"])
def api_set_hotkey():
    if _menubar_bridge is None:
        return jsonify({"error": "設定功能只能在選單列 App 裡使用"}), 503
    data = request.get_json(force=True) or {}
    combo = data.get("hotkey")
    if not combo:
        return jsonify({"error": "沒有指定 hotkey"}), 400
    return jsonify(_menubar_bridge.select_hotkey(combo))


@app.route("/settings/autostart", methods=["POST"])
def api_set_autostart():
    if _menubar_bridge is None:
        return jsonify({"error": "設定功能只能在選單列 App 裡使用"}), 503
    data = request.get_json(force=True) or {}
    return jsonify(_menubar_bridge.set_autostart(bool(data.get("enabled"))))


@app.route("/license")
def api_get_license_status():
    if _menubar_bridge is None:
        # 沒有選單列 App（直接跑這支 server.py 開發測試）時不擋——生產環境
        # 一律經過 menubar_app.py，bridge 一定會被設好，這裡放行純粹是
        # 為了開發方便，不影響實際上架後的行為。
        return jsonify({"licensed": True, "standalone": True})
    return jsonify({"licensed": _menubar_bridge.is_licensed()})


@app.route("/license/activate", methods=["POST"])
def api_activate_license():
    if _menubar_bridge is None:
        return jsonify({"error": "授權功能只能在選單列 App 裡使用"}), 503
    data = request.get_json(force=True) or {}
    key = data.get("key") or ""
    return jsonify(_menubar_bridge.activate_license(key))


@app.route("/tag", methods=["POST"])
def api_tag():
    if _menubar_bridge is not None and not _menubar_bridge.is_licensed():
        return jsonify({"error": "請先輸入授權碼才能使用標記功能", "license_required": True}), 402

    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    model_name = data.get("model") or DEFAULT_MODEL
    use_diffusion = bool(data.get("diffusion", True))

    print(f"[/tag] received text (len={len(text)}): {text[:80]!r}", flush=True)

    if not text:
        print("[/tag] empty text -> 400", flush=True)
        return jsonify({"error": "文字是空的"}), 400

    try:
        model, tokenizer = get_model(model_name)
    except FileNotFoundError:
        print(f"[/tag] model {model_name!r} not downloaded -> 400", flush=True)
        return (
            jsonify({"error": f"模型 {model_name} 還沒下載", "model_not_downloaded": model_name}),
            400,
        )

    sentences = split_sentences_keep_punct(text)
    if not sentences:
        # split_sentences_keep_punct 找不到句尾標點（。！？；）就會回傳空
        # list——例如貼一整段沒有標點的文字、或用其他標點/純換行分段的
        # 文章。這種情況不能直接把整段原文丟給模型：BERT 有 512 token
        # 的長度上限，中文字大致 1 字 ~= 1 token，長文章很容易超過，
        # 會在 embeddings 那層直接丟 RuntimeError（tensor 維度對不上）
        # 讓 /tag 整支 500。改成照字數硬切成安全大小的區塊。
        chunk_size = 150
        sentences = [
            text[i : i + chunk_size] for i in range(0, len(text), chunk_size)
        ] or [text[:chunk_size]]
        print(
            f"[/tag] no punctuation-based sentences found, "
            f"falling back to {len(sentences)} fixed-size chunk(s)",
            flush=True,
        )
    print(f"[/tag] split into {len(sentences)} sentence(s)", flush=True)

    rounds = 2 if use_diffusion else 0
    results = predict_document(sentences, model, tokenizer, rounds=rounds)

    names, seen = [], set()
    for _, _, sent_entities in results:
        for ent in sent_entities:
            if ent["type"] == "CN":
                if not (ent["sur"] and ent["giv"]):
                    continue
                key = "CN:" + ent["text"]
                if key in seen:
                    continue
                seen.add(key)
                names.append({"type": "CN", "sur": ent["sur"], "giv": ent["giv"], "text": ent["text"]})
            else:
                key = f"{ent['type']}:{ent['text']}"
                if key in seen:
                    continue
                seen.add(key)
                names.append({"type": ent["type"], "text": ent["text"]})

    print(f"[/tag] result names: {names}", flush=True)

    sentences_payload = [
        {"sentence": s, "tagged": tagged, "names": sent_names}
        for s, tagged, sent_names in results
    ]
    return jsonify({"names": names, "sentences": sentences_payload})


if __name__ == "__main__":
    print("模型目錄:", get_catalog())
    print(f"啟動於 http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
