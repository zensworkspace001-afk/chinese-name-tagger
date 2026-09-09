# -*- coding: utf-8 -*-
"""桌面版（ChineseNameTagger.app 選單列工具）用的視窗頁面。

跟 streamlit_app/../app.py（本機測試用 Flask 網頁版）用同一套視覺語言
（CSS 變數深淺色、姓=藍/名=橘標色、name-chip 清單），但這裡：
  - 是給 mac/menubar_app.py 用 PyObjC 開的原生 WKWebView 視窗載入的，
    不是給瀏覽器分頁用的，所以排版/動畫往「像正式產品」的方向再做完整一點。
  - 模型清單打 /status（不是 /models），可以標示「未下載」。
  - 沒有用到 JS 的 alert()——WKWebView 預設不實作 alert()/confirm()，
    改成頁面內的 banner。
  - 多暴露一個 window.__ctApplyResult(payload)，讓 menubar_app.py 用
    evaluateJavaScript 把剪貼簿快捷鍵已經算好的結果直接塞進頁面，不用
    使用者自己按一次「標示人名」。
"""

# App 圖示（AppIcon.iconset/icon_32x32@2x.png，64x64，塞在標題列的綠色
# 連線狀態點右邊）。用 base64 內嵌成 data URI，不用另外開 Flask 路徑，也
# 不用管 PyInstaller 打包時有沒有把額外的圖檔一起帶進去。這段字串是用
# script 直接從 icon_32x32@2x.png base64 編碼產生、寫入檔案的，沒有經過
# 手動輸入/複製，避免手動轉錄長字串時出錯把圖檔弄壞。
_APP_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAABGdBTUEAALGPC/xhBQAAACBjSFJN"
    "AAB6JgAAgIQAAPoAAACA6AAAdTAAAOpgAAA6mAAAF3CculE8AAAAeGVYSWZNTQAqAAAACAAEARoA"
    "BQAAAAEAAAA+ARsABQAAAAEAAABGASgAAwAAAAEAAgAAh2kABAAAAAEAAABOAAAAAAAAASwAAAAB"
    "AAABLAAAAAEAA6ABAAMAAAABAAEAAKACAAQAAAABAAAAQKADAAQAAAABAAAAQAAAAAATPQasAAAA"
    "CXBIWXMAAC4jAAAuIwF4pT92AAACnmlUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPHg6eG1wbWV0"
    "YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iWE1QIENvcmUgNi4wLjAiPgogICA8"
    "cmRmOlJERiB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRh"
    "eC1ucyMiPgogICAgICA8cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0iIgogICAgICAgICAgICB4"
    "bWxuczp0aWZmPSJodHRwOi8vbnMuYWRvYmUuY29tL3RpZmYvMS4wLyIKICAgICAgICAgICAgeG1s"
    "bnM6ZXhpZj0iaHR0cDovL25zLmFkb2JlLmNvbS9leGlmLzEuMC8iPgogICAgICAgICA8dGlmZjpY"
    "UmVzb2x1dGlvbj4zMDA8L3RpZmY6WFJlc29sdXRpb24+CiAgICAgICAgIDx0aWZmOllSZXNvbHV0"
    "aW9uPjMwMDwvdGlmZjpZUmVzb2x1dGlvbj4KICAgICAgICAgPHRpZmY6UmVzb2x1dGlvblVuaXQ+"
    "MjwvdGlmZjpSZXNvbHV0aW9uVW5pdD4KICAgICAgICAgPGV4aWY6UGl4ZWxZRGltZW5zaW9uPjIw"
    "NDg8L2V4aWY6UGl4ZWxZRGltZW5zaW9uPgogICAgICAgICA8ZXhpZjpQaXhlbFhEaW1lbnNpb24+"
    "MjA0ODwvZXhpZjpQaXhlbFhEaW1lbnNpb24+CiAgICAgICAgIDxleGlmOkNvbG9yU3BhY2U+MTwv"
    "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"
    "rkJggg=="
)

INDEX_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>中文人名標示</title>
<style>
  :root {
    color-scheme: light;
    --bg: #fcfcfb; --card: #ffffff; --card-2: #f7f6f3; --border: #e4e2dc;
    --text: #0b0b0b; --muted: #6b6a63; --muted-2: #918f86;
    --sur: #2a78d6; --giv: #eb6834; --for: #2e9e5b; --jpn: #8b5cf6; --accent: #2a78d6;
    --danger: #d64545; --danger-bg: #fdeceb;
    --shadow: 0 1px 2px rgba(20,18,14,0.04), 0 8px 24px -12px rgba(20,18,14,0.12);
    --shadow-lg: 0 4px 8px rgba(20,18,14,0.05), 0 20px 40px -16px rgba(20,18,14,0.18);
  }
  @media (prefers-color-scheme: dark) {
    :root { color-scheme: dark;
      --bg: #161614; --card: #201f1c; --card-2: #262521; --border: #35342f;
      --text: #f2f1ec; --muted: #9c9a90; --muted-2: #6f6d64;
      --sur: #63a6ef; --giv: #ff9a68; --for: #4ade80; --jpn: #a78bfa; --accent: #63a6ef;
      --danger: #ff6b6b; --danger-bg: #3a1f1f;
      --shadow: 0 1px 2px rgba(0,0,0,0.2), 0 8px 24px -12px rgba(0,0,0,0.5);
      --shadow-lg: 0 4px 8px rgba(0,0,0,0.25), 0 20px 40px -16px rgba(0,0,0,0.6);
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang TC", "Segoe UI", sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .topbar {
    display: flex; align-items: center; gap: 10px;
    padding: 18px 28px 14px; background: var(--bg);
    border-bottom: 1px solid var(--border);
    /* 原本是 position: sticky + backdrop-filter: blur(10px) 做「捲動時
       固定在頂端＋毛玻璃」效果，但這兩個都是要每一幀重新計算的昂貴
       運算（sticky 元素捲動/拖拉調整視窗大小時要一直重新合成位置，
       backdrop-filter 更是要即時取樣＋模糊背後內容），使用者實測捲動會
       明顯卡頓。改成跟著內容一起捲動的純色標題列，犧牲「捲動時標題列
       固定不動」這個小巧思，換取捲動流暢度。 */
  }
  .topbar h1 { font-size: 16px; margin: 0; letter-spacing: 0.01em; }
  .topbar .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--muted-2); transition: background .25s; }
  .topbar .dot.on { background: #35c268; }
  .topbar .app-icon { width: 20px; height: 20px; border-radius: 6px; display: block; }
  .topbar .status-text { font-size: 11px; color: var(--muted-2); }
  .topbar .icon-btn {
    margin-left: auto; width: 26px; height: 26px; border-radius: 8px; padding: 0;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    background: transparent; color: var(--muted); border: none; font-size: 15px;
    line-height: 1; transition: background .15s, color .15s;
  }
  .topbar .icon-btn:hover { background: var(--card-2); color: var(--text); }
  .topbar .icon-btn.active { background: var(--card-2); color: var(--accent); }

  /* 設定面板：貼著 topbar 下緣，點齒輪展開/收合——跟大視窗共用同一份
     頁面/JS，選單列圖示彈出的小面板跟置中大視窗都是同一個網址，設定
     邏輯只寫一次，兩邊行為自動保持一致。 */
  .settings-panel {
    max-height: 0; opacity: 0; overflow: hidden; background: var(--card-2);
    border-bottom: 1px solid var(--border);
    transition: max-height .25s ease, opacity .2s ease;
  }
  .settings-panel.show { max-height: 320px; opacity: 1; }
  .settings-panel .inner {
    max-width: 720px; margin: 0 auto; padding: 16px 28px 20px;
    display: flex; flex-direction: column; gap: 14px;
  }
  .settings-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .settings-row .settings-label { font-size: 13px; color: var(--text); }
  .settings-row .settings-hint { font-size: 11.5px; color: var(--muted-2); margin-top: 2px; }
  .download-progress-row { padding: 4px 0 10px; }
  .download-progress-label { font-size: 11.5px; color: var(--muted); margin-bottom: 5px; }
  .download-progress-track {
    width: 100%; height: 6px; border-radius: 999px; background: var(--card-2); overflow: hidden;
  }
  .download-progress-fill {
    height: 100%; width: 0%; background: var(--accent); border-radius: 999px;
    transition: width .2s ease;
  }
  .downloaded-models-list { display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
  .downloaded-model-chip {
    display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text);
    background: var(--card-2); border: 1px solid var(--border); border-radius: 8px;
    padding: 5px 6px 5px 10px;
  }
  .downloaded-model-chip button {
    font-family: inherit; font-size: 12px; line-height: 1; cursor: pointer;
    background: transparent; color: var(--muted); border: none; border-radius: 5px;
    padding: 4px 6px; transition: background .12s, color .12s;
  }
  .downloaded-model-chip button:hover { background: var(--danger-bg); color: var(--danger); }
  .settings-row select {
    width: auto; min-width: 160px; font-size: 12.5px; padding: 7px 10px;
  }
  .settings-toggle {
    position: relative; width: 36px; height: 21px; border-radius: 999px;
    background: var(--border); border: none; cursor: pointer; flex-shrink: 0;
    transition: background .15s;
  }
  .settings-toggle::after {
    content: ''; position: absolute; top: 2px; left: 2px; width: 17px; height: 17px;
    border-radius: 50%; background: white; transition: transform .15s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.25);
  }
  .settings-toggle.on { background: var(--accent); }
  .settings-toggle.on::after { transform: translateX(15px); }

  .wrap { max-width: 720px; margin: 0 auto; padding: 26px 28px 60px; }

  .card {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    box-shadow: var(--shadow); padding: 22px 22px 20px; margin-bottom: 22px;
    position: relative; overflow: hidden;
  }
  .card + .card { margin-top: 0; }

  .progress {
    position: absolute; top: 0; left: 0; height: 2px; width: 100%;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    background-size: 200% 100%; opacity: 0; transition: opacity .2s;
  }
  /* 動畫只在送出請求時（.on）才跑——放在base class 上的話，這個
     infinite animation 會在視窗開著的整段時間持續佔用重繪/合成，
     即使看不到（opacity:0）也一樣耗資源，是視窗卡頓的一個成因。 */
  .progress.on { opacity: 1; animation: shimmer 1.1s linear infinite; }
  @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }

  .field-row { display: flex; gap: 14px; align-items: flex-end; margin-bottom: 14px; flex-wrap: wrap; }
  .field-row > div { flex: 1; min-width: 180px; }
  label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 6px;
          font-weight: 600; letter-spacing: 0.03em; text-transform: uppercase; }

  select, textarea {
    width: 100%; font-family: inherit; font-size: 14px; color: var(--text);
    background: var(--card-2); border: 1px solid var(--border); border-radius: 9px;
    padding: 10px 12px; transition: border-color .15s, box-shadow .15s; outline: none;
  }
  select:focus, textarea:focus {
    border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
  }
  textarea { min-height: 148px; resize: vertical; line-height: 1.75; }

  .opts { display: flex; gap: 18px; font-size: 12.5px; color: var(--muted); margin: 12px 0 18px; }
  .opts label { display: flex; align-items: center; gap: 7px; font-weight: 400; margin: 0;
                text-transform: none; letter-spacing: normal; cursor: pointer; }
  .opts input { accent-color: var(--accent); }

  .actions { display: flex; gap: 10px; align-items: center; }
  button {
    font-family: inherit; font-size: 13.5px; font-weight: 600; cursor: pointer;
    background: var(--accent); color: white; border: none; border-radius: 9px;
    padding: 10px 20px; white-space: nowrap; transition: transform .12s, filter .12s, opacity .12s;
  }
  button:hover:not(:disabled) { filter: brightness(1.06); }
  button:active:not(:disabled) { transform: scale(0.97); }
  button:disabled { opacity: 0.55; cursor: default; }
  button.secondary {
    background: transparent; color: var(--text); border: 1px solid var(--border);
  }
  button.secondary:hover:not(:disabled) { background: var(--card-2); }

  .result-card {
    border-style: dashed; transition: border-color .3s;
  }
  .result-card.filled { border-style: solid; }
  .result-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .result-head h2 { font-size: 12px; margin: 0; color: var(--muted); font-weight: 600;
                    letter-spacing: 0.03em; text-transform: uppercase; }
  .result-head h2 .hint { font-weight: 400; letter-spacing: normal; text-transform: none;
                           color: var(--muted-2); margin-left: 4px; }
  .result-controls { display: flex; align-items: center; gap: 14px; }
  .legend { display: flex; gap: 16px; font-size: 12px; color: var(--muted); }
  .legend span { display: inline-flex; align-items: center; gap: 5px; }
  .legend .lgdot { width: 9px; height: 9px; border-radius: 3px; }
  .mask-config { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--muted); }
  .mask-config label { display: flex; align-items: center; gap: 4px; white-space: nowrap; }
  #head-reveal, #tail-reveal, #mask-symbol {
    width: auto; font-size: 11.5px; color: var(--text); padding: 3px 6px;
    border-radius: 6px; background: var(--card-2); border: 1px solid var(--border);
    text-align: center;
  }
  #head-reveal, #tail-reveal { width: 36px; }
  #mask-symbol { width: 36px; }

  .result-body { opacity: 0; transform: translateY(6px); transition: opacity .28s ease, transform .28s ease; }
  .result-body.show { opacity: 1; transform: translateY(0); }

  .result-text {
    line-height: 2.2; font-size: 14.5px; white-space: pre-wrap; word-break: break-word;
    margin-top: 12px;
  }
  .name-mark { padding: 1px 2px; border-radius: 4px; position: relative; }
  .sur { background: color-mix(in srgb, var(--sur) 22%, transparent); border-bottom: 2px solid var(--sur); }
  .giv { background: color-mix(in srgb, var(--giv) 22%, transparent); border-bottom: 2px solid var(--giv); }
  .for { background: color-mix(in srgb, var(--for) 22%, transparent); border-bottom: 2px solid var(--for); }
  .jpn { background: color-mix(in srgb, var(--jpn) 22%, transparent); border-bottom: 2px solid var(--jpn); }
  .name-occurrence { cursor: pointer; border-radius: 4px; transition: background .12s; }
  .name-occurrence:hover { background: color-mix(in srgb, var(--accent) 14%, transparent); }

  .name-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
  .name-chip {
    font-size: 13px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--border);
    background: var(--card-2); opacity: 0; transform: translateY(4px) scale(0.96);
    animation: chip-in .28s ease forwards; cursor: pointer; transition: border-color .12s, background .12s;
  }
  .name-chip:hover { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--card-2)); }
  @keyframes chip-in { to { opacity: 1; transform: translateY(0) scale(1); } }
  .name-chip b { color: var(--sur); }
  .name-chip i { color: var(--giv); font-style: normal; }
  .name-chip .count {
    margin-left: 7px; font-size: 11px; font-weight: 700; color: var(--muted);
    background: var(--border); border-radius: 999px; padding: 1px 7px;
  }
  .empty-hint { color: var(--muted-2); font-size: 13px; padding: 6px 0 2px; }

  .banner {
    display: flex; align-items: center; gap: 10px; font-size: 13px;
    background: var(--danger-bg); color: var(--danger); border-radius: 10px;
    padding: 11px 14px; margin-bottom: 16px; opacity: 0; max-height: 0; overflow: hidden;
    transition: opacity .2s ease, max-height .25s ease, margin .25s ease, padding .25s ease;
  }
  .banner.show { opacity: 1; max-height: 80px; margin-bottom: 16px; }
  .footer-hint { text-align: center; font-size: 11.5px; color: var(--muted-2); margin-top: 6px; }

  /* 授權碼鎖：蓋住整個頁面，沒有輸入有效授權碼之前完全看不到/用不到下面
     的標記人名功能——蓋住的是畫面，真正擋下功能的是 /tag 那支 API 本身
     （見 server.py），這裡只是讓使用者清楚知道現在為什麼不能用。 */
  .license-gate {
    position: fixed; inset: 0; z-index: 999; background: var(--bg);
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }
  .license-gate[hidden] { display: none; }
  .license-card {
    width: 100%; max-width: 360px; background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; box-shadow: var(--shadow-lg); padding: 26px 24px 24px; text-align: center;
  }
  .license-card img { width: 40px; height: 40px; border-radius: 10px; margin-bottom: 12px; }
  .license-card h2 { font-size: 15px; margin: 0 0 4px; }
  .license-card p { font-size: 12.5px; color: var(--muted); margin: 0 0 18px; line-height: 1.6; }
  .license-card input {
    width: 100%; font-family: inherit; font-size: 13px; color: var(--text);
    background: var(--card-2); border: 1px solid var(--border); border-radius: 9px;
    padding: 10px 12px; text-align: center; letter-spacing: 0.02em; outline: none;
    transition: border-color .15s, box-shadow .15s;
  }
  .license-card input:focus {
    border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .license-card button {
    width: 100%; margin-top: 12px; font-family: inherit; font-size: 13.5px; font-weight: 600;
    cursor: pointer; background: var(--accent); color: white; border: none; border-radius: 9px;
    padding: 10px 20px; transition: transform .12s, filter .12s, opacity .12s;
  }
  .license-card button:hover:not(:disabled) { filter: brightness(1.06); }
  .license-card button:active:not(:disabled) { transform: scale(0.97); }
  .license-card button:disabled { opacity: 0.55; cursor: default; }
  .license-error {
    font-size: 12px; color: var(--danger); margin-top: 10px; min-height: 14px;
  }
</style>
</head>
<body>
<div class="license-gate" id="license-gate">
  <div class="license-card">
    <img src="data:image/png;base64,__APP_ICON_B64__" alt="">
    <h2>需要授權碼</h2>
    <p>這是付費軟體，請輸入購買時收到的授權碼才能使用標記人名功能。</p>
    <input type="text" id="license-input" placeholder="CNT1-XXXXX-XXXXX-…" autocomplete="off" spellcheck="false">
    <button id="license-activate-btn">啟用</button>
    <div class="license-error" id="license-error"></div>
  </div>
</div>
<div class="topbar">
  <span class="dot" id="status-dot"></span>
  <img class="app-icon" src="data:image/png;base64,__APP_ICON_B64__" alt="">
  <h1>中文人名標示</h1>
  <span class="status-text" id="status-text">連線中…</span>
  <button class="icon-btn" id="settings-btn" title="設定" aria-label="設定">⚙</button>
</div>

<div class="settings-panel" id="settings-panel">
  <div class="inner">
    <div class="settings-row">
      <div>
        <div class="settings-label">預設模型</div>
        <div class="settings-hint">快捷鍵標記剪貼簿內容時使用</div>
      </div>
      <select id="settings-model"></select>
    </div>
    <div class="download-progress-row" id="download-progress-row" hidden>
      <div class="download-progress-label" id="download-progress-label"></div>
      <div class="download-progress-track"><div class="download-progress-fill" id="download-progress-fill"></div></div>
    </div>
    <div class="settings-row" id="downloaded-models-row" hidden style="align-items:flex-start;">
      <div>
        <div class="settings-label">已下載的模型</div>
        <div class="settings-hint">釋放磁碟空間用，之後需要可以再重新下載（使用中的模型不能刪）</div>
      </div>
      <div class="downloaded-models-list" id="downloaded-models-list"></div>
    </div>
    <div class="settings-row">
      <div class="settings-label">快捷鍵</div>
      <select id="settings-hotkey"></select>
    </div>
    <div class="settings-row">
      <div class="settings-label">開機自動啟動</div>
      <button class="settings-toggle" id="settings-autostart" role="switch" aria-checked="false"></button>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="banner" id="banner"></div>

  <div class="card" id="input-card">
    <div class="progress" id="progress"></div>
    <div class="field-row">
      <div>
        <label for="model">模型</label>
        <select id="model"></select>
      </div>
    </div>
    <label for="text">要分析的文字</label>
    <textarea id="text" placeholder="貼上一段中文文字…"></textarea>
    <div class="opts">
      <label><input type="checkbox" id="diffusion" checked> 篇章級擴散後處理（用同篇文章裡已確認的人名，召回/修補漏抓的部分）</label>
    </div>
    <div class="actions">
      <button id="run">標示人名</button>
      <button id="clear" class="secondary">清空</button>
    </div>
  </div>

  <div class="card result-card" id="result-card">
    <div class="result-head">
      <h2>結果<span class="hint">（點一下人名可以打碼）</span></h2>
      <div class="result-controls">
        <div class="legend">
          <span><span class="lgdot" style="background:var(--sur)"></span>姓</span>
          <span><span class="lgdot" style="background:var(--giv)"></span>名</span>
          <span><span class="lgdot" style="background:var(--for)"></span>外語音譯</span>
          <span><span class="lgdot" style="background:var(--jpn)"></span>日文人名</span>
        </div>
        <div class="mask-config">
          <label title="開頭保留幾個字不打碼">頭留
            <input type="number" id="head-reveal" min="0" max="6" step="1">
          字</label>
          <label title="結尾保留幾個字不打碼，中間會被打碼——想遮中間的字，開頭跟結尾都設保留就好">尾留
            <input type="number" id="tail-reveal" min="0" max="6" step="1">
          字</label>
          <label title="打碼要換成什麼符號">符號
            <input type="text" id="mask-symbol" maxlength="3">
          </label>
        </div>
      </div>
    </div>
    <div class="result-body" id="result-body">
      <div class="empty-hint" id="result-empty">還沒有結果——貼上文字後按「標示人名」，或用選單列的快捷鍵標記剪貼簿內容。</div>
      <div class="result-text" id="result-text"></div>
      <div class="name-list" id="name-list"></div>
    </div>
  </div>

  <div class="footer-hint">選單列圖示裡的「設定」可以切換模型版本、快捷鍵、開機自動啟動</div>
</div>

<script>
const modelSelect = document.getElementById('model');
const textArea = document.getElementById('text');
const runBtn = document.getElementById('run');
const clearBtn = document.getElementById('clear');
const progress = document.getElementById('progress');
const banner = document.getElementById('banner');
const resultCard = document.getElementById('result-card');
const resultBody = document.getElementById('result-body');
const resultEmpty = document.getElementById('result-empty');
const resultText = document.getElementById('result-text');
const nameList = document.getElementById('name-list');
const diffusionCheck = document.getElementById('diffusion');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const headRevealInput = document.getElementById('head-reveal');
const tailRevealInput = document.getElementById('tail-reveal');
const maskSymbolInput = document.getElementById('mask-symbol');
const settingsBtn = document.getElementById('settings-btn');
const settingsPanel = document.getElementById('settings-panel');
const settingsModelSelect = document.getElementById('settings-model');
const downloadProgressRow = document.getElementById('download-progress-row');
const downloadProgressLabel = document.getElementById('download-progress-label');
const downloadProgressFill = document.getElementById('download-progress-fill');
const downloadedModelsRow = document.getElementById('downloaded-models-row');
const downloadedModelsList = document.getElementById('downloaded-models-list');
const settingsHotkeySelect = document.getElementById('settings-hotkey');
const settingsAutostartToggle = document.getElementById('settings-autostart');
const licenseGate = document.getElementById('license-gate');
const licenseInput = document.getElementById('license-input');
const licenseActivateBtn = document.getElementById('license-activate-btn');
const licenseError = document.getElementById('license-error');

async function checkLicense() {
  try {
    const res = await fetch('/license');
    const data = await res.json();
    licenseGate.hidden = !!data.licensed;
  } catch (e) {
    // 連線失敗（server 可能還在啟動中）先假設鎖住，等 loadStatus() 那邊
    // 的重試機制連上之後，使用者重新整理或再點一次圖示就會重新檢查。
    licenseGate.hidden = false;
  }
}

licenseActivateBtn.addEventListener('click', async () => {
  const key = licenseInput.value.trim();
  if (!key) { licenseError.textContent = '請輸入授權碼。'; return; }
  licenseActivateBtn.disabled = true;
  licenseError.textContent = '';
  try {
    const res = await fetch('/license/activate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
    });
    const data = await res.json();
    if (data.ok) {
      licenseGate.hidden = true;
      loadStatus();
    } else {
      licenseError.textContent = data.error || '授權碼無效。';
    }
  } catch (e) {
    licenseError.textContent = '連線失敗：' + e;
  } finally {
    licenseActivateBtn.disabled = false;
  }
});
licenseInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') licenseActivateBtn.click();
});

let bannerTimer = null;
function showBanner(message) {
  banner.textContent = message;
  banner.classList.add('show');
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => banner.classList.remove('show'), 6000);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// 點一下標示出來的人名（不管是內文裡的醒目文字，還是下面的人名標籤），
// 那個人名就會打碼，再點一次復原。打碼規則是「開頭留 headReveal 個字、
// 結尾留 tailReveal 個字，中間全部換成 maskSymbol」——這樣「只打碼開頭」
// 「只打碼結尾」「打碼中間（頭尾都留）」「全部打碼」都是同一套規則的
// 特例，不用個別做開關。三個設定都可以在結果區塊右上角調整，調整當下
// 已經打碼的人名會直接套用新規則重畫，並存進 localStorage，重開視窗/
// 重開 App 都記得上次的選擇。
// maskedNames 存的是「姓+名」這個 key（哪些人名目前打了碼），
// lastSentences 存最後一次算出來的結果，重新畫（切換打碼/調整規則）
// 不用再打一次 /tag，直接拿舊資料重繪就好。
const maskedNames = new Set();
let lastSentences = [];
let headReveal = 1;
let tailReveal = 0;
let maskSymbol = '○';

const MASK_SETTINGS_KEY = 'ctMaskSettings';

function loadMaskSettings() {
  try {
    const raw = localStorage.getItem(MASK_SETTINGS_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (Number.isFinite(saved.headReveal) && saved.headReveal >= 0) {
      headReveal = saved.headReveal;
    } else if (Number.isFinite(saved.revealCount) && saved.revealCount >= 0) {
      headReveal = saved.revealCount; // 相容舊版（只有「開頭留幾字」）存的設定
    }
    if (Number.isFinite(saved.tailReveal) && saved.tailReveal >= 0) {
      tailReveal = saved.tailReveal;
    }
    if (typeof saved.maskSymbol === 'string' && saved.maskSymbol) {
      maskSymbol = saved.maskSymbol;
    }
  } catch (e) {
    // localStorage 在部分情境下可能不可用（例如私密瀏覽），失敗就用預設值。
  }
}

function saveMaskSettings() {
  try {
    localStorage.setItem(MASK_SETTINGS_KEY, JSON.stringify({ headReveal, tailReveal, maskSymbol }));
  } catch (e) {
    // 存不進去就算了，不影響當下的打碼功能照常運作。
  }
}

// 給定一個人名的總字數，算出「開頭留幾個字」跟「從第幾個字開始算結尾
// 保留範圍」，中間那段（head <= i < tailStart）才要打碼。headReveal/
// tailReveal 兩個範圍重疊或加起來超過總字數時，等於整個名字都不打碼。
function maskRange(len) {
  const head = Math.max(0, Math.min(headReveal, len));
  const tailStart = Math.max(head, len - Math.max(0, tailReveal));
  return { head, tailStart };
}

// 把「姓+名」這個完整字串套用 maskRange 算出的規則，再切回姓／名各自
// 要顯示的片段（照姓的字數切，跟打碼範圍落在姓還是名裡面無關）。
function applyMask(sur, giv) {
  sur = sur || '';
  giv = giv || '';
  const full = sur + giv;
  const symbol = maskSymbol || '○';
  const { head, tailStart } = maskRange(full.length);
  let masked = '';
  for (let i = 0; i < full.length; i++) {
    masked += (i >= head && i < tailStart) ? symbol : full[i];
  }
  return { surShown: masked.slice(0, sur.length), givShown: masked.slice(sur.length) };
}

// 把 predict_bert 逐字元輸出的 tagged 陣列，重新分組成「一般文字」跟
// 「完整一個實體」兩種區塊——標色/打碼都要以「一個完整實體」為單位
// 處理，不能逐字元各自獨立判斷。中文人名（entType 'CN'）姓/名分開存、
// 各自標不同顏色；外語音譯（'FOR'）/日文人名（'JPN'）整段是一個實體，
// 不切邊界，sur 固定是空字串、giv 存整段文字（沿用同一個 sur+giv 組合
// 的打碼機制，applyMask('', text) 一樣能正確運作，不用另外重寫打碼邏輯）。
function groupNameRuns(tagged) {
  const runs = [];
  let i = 0;
  while (i < tagged.length) {
    const tag = tagged[i][1];
    if (tag === 'B-SUR' || tag === 'I-SUR') {
      const chars = [];
      let sur = '', giv = '';
      while (i < tagged.length && (tagged[i][1] === 'B-SUR' || tagged[i][1] === 'I-SUR')) {
        chars.push({ ch: tagged[i][0], cls: 'sur' });
        sur += tagged[i][0];
        i++;
      }
      while (i < tagged.length && (tagged[i][1] === 'B-GIV' || tagged[i][1] === 'I-GIV')) {
        chars.push({ ch: tagged[i][0], cls: 'giv' });
        giv += tagged[i][0];
        i++;
      }
      runs.push({ type: 'name', entType: 'CN', chars, sur, giv, text: sur + giv });
    } else if (tag === 'B-FOR' || tag === 'B-JPN') {
      const entType = tag.slice(2); // 'FOR' 或 'JPN'
      const cls = entType.toLowerCase();
      const chars = [];
      let text = '';
      while (i < tagged.length && (tagged[i][1] === `B-${entType}` || tagged[i][1] === `I-${entType}`)) {
        chars.push({ ch: tagged[i][0], cls });
        text += tagged[i][0];
        i++;
      }
      runs.push({ type: 'name', entType, chars, sur: '', giv: text, text });
    } else {
      runs.push({ type: 'char', ch: tagged[i][0] });
      i++;
    }
  }
  return runs;
}

// CN 用「姓+名」全文當 key，FOR/JPN 加類型前綴避免跟同名的 CN 撞 key
// （例如巧合下有中文名跟音譯人名文字剛好一樣的極端情況）。
function entKey(entType, text) {
  return entType === 'CN' ? text : `${entType}:${text}`;
}

function toggleMask(key) {
  if (!key) return;
  if (maskedNames.has(key)) {
    maskedNames.delete(key);
  } else {
    maskedNames.add(key);
  }
  renderResult(lastSentences);
}

async function loadStatus() {
  try {
    const res = await fetch('/status');
    const data = await res.json();
    modelSelect.innerHTML = '';
    (data.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = m.downloaded ? m.label : `${m.label}（未下載）`;
      if (m.name === data.default) opt.selected = true;
      modelSelect.appendChild(opt);
    });
    statusDot.classList.add('on');
    statusText.textContent = '已連線';
  } catch (e) {
    statusDot.classList.remove('on');
    statusText.textContent = '連線失敗';
  }
}

async function loadSettings() {
  try {
    const res = await fetch('/settings');
    const data = await res.json();

    settingsModelSelect.innerHTML = '';
    (data.models || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = m.downloaded ? m.label : `${m.label}（未下載）`;
      if (m.name === data.model) opt.selected = true;
      settingsModelSelect.appendChild(opt);
    });
    renderDownloadedModelsList(data.models || [], data.model);

    settingsHotkeySelect.innerHTML = '';
    (data.hotkeyOptions || []).forEach(([label, combo]) => {
      const opt = document.createElement('option');
      opt.value = combo;
      opt.textContent = label;
      if (combo === data.hotkey) opt.selected = true;
      settingsHotkeySelect.appendChild(opt);
    });

    settingsAutostartToggle.classList.toggle('on', !!data.autostart);
    settingsAutostartToggle.setAttribute('aria-checked', data.autostart ? 'true' : 'false');
  } catch (e) {
    showBanner('設定讀取失敗：' + e);
  }
}

// 只列出「已下載、而且不是使用中」的模型可以刪——使用中的那個刪了會讓
// /tag 立刻沒有可用模型，跟原生選單「刪除已下載模型」子選單的限制
// 一致（見 menubar_app.py::_refresh_delete_menu()）。一個都沒有的話
// 整列隱藏起來，不要空著一個沒東西的區塊。
function renderDownloadedModelsList(models, currentModel) {
  const deletable = models.filter(m => m.downloaded && m.name !== currentModel);
  downloadedModelsList.innerHTML = '';
  downloadedModelsRow.hidden = deletable.length === 0;
  deletable.forEach(m => {
    const chip = document.createElement('div');
    chip.className = 'downloaded-model-chip';
    const label = document.createElement('span');
    label.textContent = m.label;
    const delBtn = document.createElement('button');
    delBtn.textContent = '刪除';
    delBtn.title = `刪除 ${m.label}（可以重新下載）`;
    delBtn.addEventListener('click', () => deleteModel(m.name, m.label));
    chip.appendChild(label);
    chip.appendChild(delBtn);
    downloadedModelsList.appendChild(chip);
  });
}

async function deleteModel(name, label) {
  try {
    const res = await fetch('/delete_model', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: name }),
    });
    const data = await res.json();
    if (data.error) {
      showBanner('刪除失敗：' + data.error);
    } else {
      showBanner(`已刪除模型「${label}」，之後需要可以再重新下載。`);
    }
  } catch (e) {
    showBanner('刪除失敗：' + e);
  } finally {
    loadSettings();
  }
}

settingsBtn.addEventListener('click', () => {
  const show = !settingsPanel.classList.contains('show');
  settingsPanel.classList.toggle('show', show);
  settingsBtn.classList.toggle('active', show);
  if (show) loadSettings();
});

// 輪詢 /download_progress 直到下載完成（或失敗），中途即時更新進度條。
// 下載本身是 /settings/model {confirmed:true} 觸發的背景執行緒（見
// menubar_app.py::select_default_model），這裡只負責顯示進度、不負責
// 觸發下載，也不負責下載完成後的「切換成這個模型」——那件事由
// on_download_complete() 在背景執行緒那邊做完了，這裡輪詢到 done:true
// 之後只需要重新整理設定面板（loadSettings），把「未下載」標籤真正
// 移除掉。
async function pollDownloadProgress(name, label) {
  downloadProgressRow.hidden = false;
  downloadProgressFill.style.width = '0%';
  downloadProgressLabel.textContent = `正在下載 ${label}…`;
  try {
    while (true) {
      await new Promise(r => setTimeout(r, 400));
      const res = await fetch(`/download_progress?model=${encodeURIComponent(name)}`);
      const data = await res.json();
      if (data.total) {
        const pct = Math.min(100, Math.round((data.downloaded / data.total) * 100));
        downloadProgressFill.style.width = `${pct}%`;
        downloadProgressLabel.textContent = `正在下載 ${label}… ${pct}%`;
      }
      if (data.done) {
        if (data.error) {
          showBanner(`模型下載失敗：${data.error}`);
        } else {
          downloadProgressFill.style.width = '100%';
          downloadProgressLabel.textContent = `${label} 下載完成`;
        }
        break;
      }
    }
  } finally {
    // 完成/失敗都停留一下讓使用者看到「100%」或錯誤訊息，再收起進度條，
    // 不要一結束就立刻消失，使用者會來不及看清楚結果。
    setTimeout(() => { downloadProgressRow.hidden = true; }, 1200);
  }
}

settingsModelSelect.addEventListener('change', async () => {
  const name = settingsModelSelect.value;
  try {
    let res = await fetch('/settings/model', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: name }),
    });
    let data = await res.json();
    if (data.needs_confirm) {
      // 網頁面板這條路線原本設計就是選了直接下載、不另外跳確認對話框
      // （原生選單才有 confirm_dialog，那是走 macOS 原生對話框；WKWebView
      // 不保證有實作 JS confirm() 的 delegate，這裡不引入沒驗證過的
      // window.confirm() 呼叫）。label 要在這裡先存下來，因為
      // /settings/model 第二次（confirmed）的回應不會再帶 label。
      const label = data.label || name;
      res = await fetch('/settings/model', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name, confirmed: true }),
      });
      data = await res.json();
      if (data.downloading) {
        await pollDownloadProgress(name, label);
      }
    }
    if (data.error) { showBanner('模型切換失敗：' + data.error); }
  } catch (e) {
    showBanner('模型切換失敗：' + e);
  } finally {
    loadSettings();
  }
});

settingsHotkeySelect.addEventListener('change', async () => {
  try {
    const res = await fetch('/settings/hotkey', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hotkey: settingsHotkeySelect.value }),
    });
    const data = await res.json();
    if (data.error) showBanner('快捷鍵設定失敗：' + data.error);
  } catch (e) {
    showBanner('快捷鍵設定失敗：' + e);
  }
});

settingsAutostartToggle.addEventListener('click', async () => {
  const enabled = !settingsAutostartToggle.classList.contains('on');
  try {
    const res = await fetch('/settings/autostart', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json();
    if (data.error) { showBanner('開機自動啟動設定失敗：' + data.error); return; }
    settingsAutostartToggle.classList.toggle('on', !!data.autostart);
    settingsAutostartToggle.setAttribute('aria-checked', data.autostart ? 'true' : 'false');
  } catch (e) {
    showBanner('開機自動啟動設定失敗：' + e);
  }
});

function renderResult(sentences) {
  sentences = sentences || [];
  lastSentences = sentences;

  let html = '';
  const allEntities = [];
  for (const sent of sentences) {
    for (const run of groupNameRuns(sent.tagged)) {
      if (run.type === 'char') {
        html += escapeHtml(run.ch);
        continue;
      }
      const key = entKey(run.entType, run.text);
      const masked = maskedNames.has(key);
      const { head, tailStart } = maskRange(run.chars.length);
      html += `<span class="name-occurrence" data-key="${escapeHtml(key)}" title="點一下打碼/取消打碼">`;
      run.chars.forEach((c, idx) => {
        const shouldMask = masked && idx >= head && idx < tailStart;
        const displayCh = shouldMask ? (maskSymbol || '○') : c.ch;
        html += `<span class="name-mark ${c.cls}">${escapeHtml(displayCh)}</span>`;
      });
      html += `</span>`;
    }
    (sent.names || []).forEach(ent => allEntities.push(ent));
  }
  resultText.innerHTML = html;
  resultEmpty.style.display = html ? 'none' : 'block';

  nameList.innerHTML = '';
  // 統計每個實體出現幾次（CN 用「姓+名」、FOR/JPN 用「類型+全名」當 key），
  // 依出現次數由多到少排序，次數相同的維持原本第一次出現的先後順序。
  const counts = new Map();
  allEntities.forEach(ent => {
    if (ent.type === 'CN' && !(ent.sur && ent.giv)) return; // 沒配對到名的殘缺姓/名不顯示，跟原本行為一致
    const key = entKey(ent.type, ent.text);
    const entry = counts.get(key);
    if (entry) {
      entry.count += 1;
    } else {
      counts.set(key, { ...ent, count: 1 });
    }
  });
  const ranked = Array.from(counts.values()).sort((a, b) => b.count - a.count);
  ranked.forEach((item, i) => {
    const key = entKey(item.type, item.text);
    const masked = maskedNames.has(key);
    const chip = document.createElement('span');
    chip.className = 'name-chip';
    chip.dataset.key = key;
    chip.title = '點一下打碼/取消打碼';
    chip.style.animationDelay = `${Math.min(i, 12) * 35}ms`;
    const countBadge = item.count > 1 ? `<span class="count">×${item.count}</span>` : '';
    if (item.type === 'CN') {
      let surShown = item.sur || '？';
      let givShown = item.giv || '？';
      if (masked) {
        const applied = applyMask(item.sur, item.giv);
        surShown = applied.surShown || '？';
        givShown = applied.givShown || '？';
      }
      chip.innerHTML = `<b>${escapeHtml(surShown)}</b><i>${escapeHtml(givShown)}</i>${countBadge}`;
    } else {
      let textShown = item.text || '？';
      if (masked) {
        const applied = applyMask('', item.text);
        textShown = applied.givShown || '？';
      }
      const typeColor = item.type === 'FOR' ? 'var(--for)' : 'var(--jpn)';
      chip.innerHTML = `<span style="color:${typeColor};font-size:10px;font-weight:700;margin-right:4px;">${item.type}</span><b>${escapeHtml(textShown)}</b>${countBadge}`;
    }
    nameList.appendChild(chip);
  });

  resultCard.classList.toggle('filled', !!html);
  resultBody.classList.remove('show');
  requestAnimationFrame(() => requestAnimationFrame(() => resultBody.classList.add('show')));
}

resultText.addEventListener('click', (e) => {
  const el = e.target.closest('.name-occurrence');
  if (el) toggleMask(el.dataset.key);
});
nameList.addEventListener('click', (e) => {
  const chip = e.target.closest('.name-chip');
  if (chip) toggleMask(chip.dataset.key);
});
headRevealInput.addEventListener('change', () => {
  const n = parseInt(headRevealInput.value, 10);
  headReveal = Number.isFinite(n) && n >= 0 ? n : 0;
  headRevealInput.value = headReveal;
  saveMaskSettings();
  renderResult(lastSentences);
});
tailRevealInput.addEventListener('change', () => {
  const n = parseInt(tailRevealInput.value, 10);
  tailReveal = Number.isFinite(n) && n >= 0 ? n : 0;
  tailRevealInput.value = tailReveal;
  saveMaskSettings();
  renderResult(lastSentences);
});
maskSymbolInput.addEventListener('change', () => {
  maskSymbol = maskSymbolInput.value || '○';
  maskSymbolInput.value = maskSymbol;
  saveMaskSettings();
  renderResult(lastSentences);
});

function setBusy(busy) {
  runBtn.disabled = busy;
  runBtn.textContent = busy ? '分析中…' : '標示人名';
  progress.classList.toggle('on', busy);
}

async function runTag(text, model, diffusion) {
  setBusy(true);
  try {
    const res = await fetch('/tag', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, model, diffusion }),
    });
    const data = await res.json();
    if (data.model_not_downloaded) {
      showBanner(`模型「${data.model_not_downloaded}」尚未下載，請從選單列圖示的「設定 > 模型版本」下載後再試一次。`);
      return;
    }
    if (data.error) {
      showBanner('錯誤：' + data.error);
      return;
    }
    renderResult(data.sentences);
  } catch (e) {
    showBanner('連線失敗：' + e);
  } finally {
    setBusy(false);
  }
}

runBtn.addEventListener('click', () => {
  const text = textArea.value.trim();
  if (!text) { showBanner('請先貼上要分析的文字。'); return; }
  runTag(text, modelSelect.value, diffusionCheck.checked);
});

clearBtn.addEventListener('click', () => {
  textArea.value = '';
  maskedNames.clear();
  renderResult([]);
});

// 給 mac/menubar_app.py 用 evaluateJavaScript 呼叫：把剪貼簿快捷鍵已經
// 算好的結果（text + /tag 的回傳）直接塞進頁面，不用使用者手動再按一次。
window.__ctApplyResult = function(payload) {
  if (!payload) return;
  textArea.value = payload.text || '';
  const data = payload.data || {};
  if (data.model_not_downloaded) {
    showBanner(`模型「${data.model_not_downloaded}」尚未下載，請從選單列圖示的「設定 > 模型版本」下載後再試一次。`);
    return;
  }
  if (data.error) {
    showBanner('錯誤：' + data.error);
    return;
  }
  renderResult(data.sentences);
};

loadMaskSettings();
headRevealInput.value = headReveal;
tailRevealInput.value = tailReveal;
maskSymbolInput.value = maskSymbol;
checkLicense();
loadStatus();
</script>
</body>
</html>
"""

INDEX_HTML = INDEX_HTML.replace("__APP_ICON_B64__", _APP_ICON_B64)
