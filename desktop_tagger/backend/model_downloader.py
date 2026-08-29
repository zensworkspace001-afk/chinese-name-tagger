# -*- coding: utf-8 -*-
"""模型不包在安裝檔裡（那樣每次要更新模型都要重新打包+簽章+公證整個
App），改成執行期間才從 GitHub Release 下載，快取到使用者資料夾。之後
要換新版模型，只要上傳新的 zip、更新 models_manifest.json，使用者端
會自動抓到新版本，不需要重新發一次 App。

manifest 格式（models_manifest.json，放在 GitHub repo 裡，用 raw.
githubusercontent.com 讀，每次都抓最新版，不快取進安裝檔）：
{
  "models": [
    {
      "name": "model_bert_colab_v5",
      "label": "colab_v5（目前最佳版本）",
      "version": 1,
      "url": "https://github.com/.../releases/download/models-v1/model_bert_colab_v5.zip",
      "sha256": "...",
      "size_bytes": 406740000,
      "default": true
    },
    ...
  ]
}

快取位置：
  macOS   ~/Library/Application Support/ChineseNameTagger/models/<name>/
  Windows %LOCALAPPDATA%\\ChineseNameTagger\\models\\<name>\\
每個模型資料夾裡會有一個 .version 檔記錄目前快取的是 manifest 裡的哪個
version，跟 manifest 對不上（表示有新版）就需要重新下載。
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile

# 跟 server.py 的 _SAFE_MODEL_NAME_RE 同一個限制：模型名稱只給英數字/
# 底線/連字號，避免 manifest 裡的 "name" 欄位（雖然目前是我們自己維護，
# 但 manifest 是放在 GitHub 上、透過網路抓的，多一層檢查總是比較保險）
# 被拿去 os.path.join 組出跳出 cache_dir 的路徑。
_SAFE_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

MANIFEST_URL = (
    "https://raw.githubusercontent.com/zensworkspace001-afk/"
    "chinese-name-tagger/main/desktop_tagger/models_manifest.json"
)


def get_cache_dir():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/ChineseNameTagger")
    elif os.name == "nt":
        base = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "ChineseNameTagger",
        )
    else:
        base = os.path.expanduser("~/.chinesenametagger")
    path = os.path.join(base, "models")
    os.makedirs(path, exist_ok=True)
    return path


def fetch_manifest(timeout=10):
    req = urllib.request.Request(
        MANIFEST_URL, headers={"User-Agent": "ChineseNameTagger"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _version_marker_path(model_dir):
    return os.path.join(model_dir, ".version")


def get_local_version(model_dir):
    path = _version_marker_path(model_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None


def is_downloaded(model_entry, cache_dir):
    model_dir = os.path.join(cache_dir, model_entry["name"])
    if not os.path.isfile(os.path.join(model_dir, "config.json")):
        return False
    local_version = get_local_version(model_dir)
    return local_version == model_entry.get("version")


def _safe_extract(zf, dest_dir):
    """解壓前先確認 zip 裡每個項目解開後都還在 dest_dir 底下，擋掉
    zip-slip（zip 裡塞 "../../somewhere" 這種項目、藉著解壓縮寫到目標
    資料夾以外的地方）。Python 的 zipfile.extractall 對這個問題有做一些
    處理，但版本間行為不完全一致，這裡自己再明確檢查一次比較保險。"""
    dest_real = os.path.realpath(dest_dir)
    for member in zf.namelist():
        target = os.path.realpath(os.path.join(dest_real, member))
        if target != dest_real and not target.startswith(dest_real + os.sep):
            raise ValueError(f"zip 檔內容可疑（疑似 zip-slip）：{member!r}")
    zf.extractall(dest_real)


def download_and_extract(model_entry, cache_dir, progress_cb=None):
    """下載 model_entry 描述的模型 zip，驗證 sha256，解壓到
    cache_dir/<name>/，成功後寫入版本標記檔。progress_cb(downloaded, total)
    在下載過程中會被反覆呼叫（total 可能是 0，表示伺服器沒給
    Content-Length，這時就沒辦法算百分比，只能顯示已下載的量）。"""
    name = model_entry["name"]
    if not _SAFE_MODEL_NAME_RE.match(name):
        raise ValueError(f"模型名稱格式不合法：{name!r}")
    url = model_entry["url"]
    expected_sha256 = model_entry["sha256"]
    model_dir = os.path.join(cache_dir, name)

    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        hasher = hashlib.sha256()
        req = urllib.request.Request(url, headers={"User-Agent": "ChineseNameTagger"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

        actual_sha256 = hasher.hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"checksum 對不上（下載可能損毀）：預期 {expected_sha256}，"
                f"實際 {actual_sha256}"
            )

        if os.path.isdir(model_dir):
            shutil.rmtree(model_dir)
        os.makedirs(model_dir, exist_ok=True)
        with zipfile.ZipFile(tmp_path) as zf:
            _safe_extract(zf, model_dir)

        with open(_version_marker_path(model_dir), "w", encoding="utf-8") as f:
            f.write(str(model_entry.get("version", 1)))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
