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
from index_html import INDEX_HTML  # noqa: E402

DEFAULT_MODEL = "model_bert_colab_v5"
PORT = 5111

app = Flask(__name__)
_model_cache = {}
_manifest_cache_path = os.path.normpath(
    os.path.join(model_downloader.get_cache_dir(), "..", "models_manifest_cache.json")
)


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


@app.route("/tag", methods=["POST"])
def api_tag():
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
    for _, _, sent_names in results:
        for sur, giv in sent_names:
            if not (sur and giv):
                continue
            key = sur + giv
            if key in seen:
                continue
            seen.add(key)
            names.append([sur, giv])

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
