#!/bin/bash
# 安裝「中文人名標示」到這台 Mac：
#   1. 把打包好的 ChineseNameTagger.app（含 Python/torch/模型）複製到
#      /Applications/（放這裡而不是 ~/Library 是因為系統設定裡「輸入監控」
#      清單的「+」新增檔案選擇視窗，跟 Finder 一樣預設不顯示 ~/Library，
#      放 /Applications 使用者才找得到、點得到）
#   2. 自動解除下載/解壓縮時被系統標上的「隔離」屬性（quarantine），
#      這樣大部分情況下第一次啟動就不會被 Gatekeeper 擋下來——不用等
#      使用者自己看到「無法驗證開發者」的警告才回頭查怎麼解
#   3. 安裝 LaunchAgent，讓它在登入時自動啟動並常駐（選單列圖示）
#
# 用法：
#   雙擊 install_mac.command（從 GitHub Release 下載解壓縮後，Finder
#   會自動用 Terminal 打開來跑，不用自己打指令、也看得到彈出的視窗）
#   或在 Terminal 裡 cd 到這個資料夾執行 ./install_mac.sh
#
# 使用方式（跟 Clipy 一樣：選單列圖示 + 全域快捷鍵，不是右鍵選單——
# 實測手刻的 Automator Services bundle 沒辦法通過 macOS 的 Spotlight 掃描
# 而無法註冊進右鍵選單，Clipy 本身其實也是走這條路，並不是右鍵選單）：
#   在任何 App 選取一段中文文字，按 ⌘⌥N，跳出視窗顯示標出的人名。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/Applications"
LOG_DIR="$HOME/Library/Logs/ChineseNameTagger"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LABEL="com.zens.chinesetagger"

# 本機開發反覆重新打包測試時會傳這個旗標，跳過會卡住等使用者點擊的
# 對話框（display dialog 是同步、會擋住整個 script，自動化測試沒有人
# 可以去點，不加這個旗標的話會直接卡死）。一般使用者（雙擊
# install_mac.command）不會帶這個參數，會走完整的對話框流程。
SKIP_DIALOGS=0
for arg in "$@"; do
  if [ "$arg" = "--skip-confirm" ]; then
    SKIP_DIALOGS=1
  fi
done

# 用原生的 macOS 對話框給提示/確認/結果，而不是只印在 Terminal 裡——
# 用 osascript display dialog 本身不會觸發 Gatekeeper 的「無法驗證開發
# 者」警告，那個警告是針對「執行未簽章的編譯後執行檔（Mach-O binary）」，
# shell script 用直譯器（bash）跑，不算，所以在這裡疊加對話框互動不會
# 讓使用者要多繞過一層 Gatekeeper。
dialog_info() {
  [ "$SKIP_DIALOGS" = "1" ] && return 0
  local message="$1"
  # 只跳脫雙引號，不動反斜線——訊息裡的 \n 要讓 AppleScript 自己解讀成
  # 換行，反斜線加倍反而會讓 \n 變成字面上的兩個字元「\n」而不是換行。
  local escaped="${message//\"/\\\"}"
  osascript -e "display dialog \"$escaped\" buttons {\"好\"} default button 1 with title \"中文人名標示 安裝程式\" with icon note" >/dev/null 2>&1
}

dialog_error() {
  [ "$SKIP_DIALOGS" = "1" ] && return 0
  local message="$1"
  # 只跳脫雙引號，不動反斜線——訊息裡的 \n 要讓 AppleScript 自己解讀成
  # 換行，反斜線加倍反而會讓 \n 變成字面上的兩個字元「\n」而不是換行。
  local escaped="${message//\"/\\\"}"
  osascript -e "display dialog \"$escaped\" buttons {\"好\"} default button 1 with title \"中文人名標示 安裝程式\" with icon stop" >/dev/null 2>&1
}

# 回傳 0 = 使用者選「繼續安裝」，1 = 選「取消」
dialog_confirm() {
  [ "$SKIP_DIALOGS" = "1" ] && return 0
  local message="$1"
  # 只跳脫雙引號，不動反斜線——訊息裡的 \n 要讓 AppleScript 自己解讀成
  # 換行，反斜線加倍反而會讓 \n 變成字面上的兩個字元「\n」而不是換行。
  local escaped="${message//\"/\\\"}"
  local result
  result="$(osascript -e "display dialog \"$escaped\" buttons {\"取消\", \"繼續安裝\"} default button \"繼續安裝\" with title \"中文人名標示 安裝程式\" with icon note" 2>&1)"
  [[ "$result" == *"繼續安裝"* ]]
}

# 任何一步失敗都跳原生錯誤對話框說明，而不是讓使用者只看到一片
# Terminal 錯誤訊息、完全不知道裝到哪一步、成功了沒有。
fail() {
  local message="$1"
  echo "錯誤：$message" >&2
  dialog_error "安裝失敗：\n\n$message"
  exit 1
}

if ! dialog_confirm "即將安裝「中文人名標示」（ChineseNameTagger）。\n\n這個安裝程式會：\n• 把 App 複製到 /Applications\n• 設定登入時自動啟動（常駐在選單列，不會出現在 Dock）\n\n之後第一次使用全域快捷鍵功能時，系統會另外詢問「輸入監控」權限——這是用來偵測你按下的快捷鍵組合，這個 App 不會記錄或上傳你輸入的其他任何文字。\n\n這個 App 沒有 Apple 開發者簽章（非商業小工具，沒有付費加入開發者計畫），這個安裝程式裝好後會自動處理，通常不會再跳出「無法驗證開發者」的警告。\n\n按「繼續安裝」開始。"; then
  echo "使用者取消安裝。"
  exit 0
fi

# 這支 script 有兩種用法，App 可能在兩個不同的地方：
#   1. 本機開發：cd desktop_tagger/mac && ./install_mac.sh，這時候
#      App 是本機剛用 pyinstaller 建出來的 dist/ChineseNameTagger.app。
#   2. 從 GitHub Release 下載的 zip 解壓縮後直接執行：CI 打包時是把
#      dist/ChineseNameTagger.app 跟 install_mac.sh 攤平放在同一層
#      （沒有 dist/ 這層目錄），這時候 App 就在 script 自己旁邊。
if [ -d "$HERE/dist/ChineseNameTagger.app" ]; then
  APP_SRC="$HERE/dist/ChineseNameTagger.app"
elif [ -d "$HERE/ChineseNameTagger.app" ]; then
  APP_SRC="$HERE/ChineseNameTagger.app"
else
  fail "找不到 ChineseNameTagger.app。\n\n如果你是要在本機重新打包，請先執行：\n./build_venv/bin/pyinstaller ChineseNameTagger.spec --noconfirm\n\n如果你是從 GitHub Release 下載的 zip，請確認解壓縮後 ChineseNameTagger.app 有跟這支安裝程式放在同一層資料夾。"
fi

echo "==> 停止舊的服務（如果有在跑）"
launchctl unload "$LAUNCH_AGENT_DIR/$LABEL.plist" 2>/dev/null || true
pkill -f "ChineseNameTagger.app/Contents/MacOS/ChineseNameTagger" 2>/dev/null || true

echo "==> 安裝 App 到 $INSTALL_DIR"
rm -rf "$INSTALL_DIR/ChineseNameTagger.app"
if ! cp -R "$APP_SRC" "$INSTALL_DIR/"; then
  fail "複製 App 到 $INSTALL_DIR 失敗，請確認這個資料夾有寫入權限。"
fi
# 注意：不要在這裡動 ~/Library/Application Support/ChineseNameTagger ——
# 單一執行個體鎖檔（.instance.lock）放在那裡，如果舊 process 還在跑、
# 這裡把那個目錄砍掉重建，會讓舊 process 手上的 flock 變成鎖在一個已經
# 被刪除的 inode 上，新 process 反而能拿到「新的」鎖檔而重複啟動。

echo "==> 解除隔離屬性（避免 Gatekeeper 擋下來）"
xattr -dr com.apple.quarantine "$INSTALL_DIR/ChineseNameTagger.app" 2>/dev/null || true

echo "==> 準備 log 目錄 $LOG_DIR"
mkdir -p "$LOG_DIR"

echo "==> 安裝 LaunchAgent（登入時自動啟動、常駐）"
mkdir -p "$LAUNCH_AGENT_DIR"
sed \
  -e "s#__INSTALL_DIR__#$INSTALL_DIR#g" \
  -e "s#__LOG_DIR__#$LOG_DIR#g" \
  "$HERE/com.zens.chinesetagger.plist" > "$LAUNCH_AGENT_DIR/$LABEL.plist"
if ! launchctl load "$LAUNCH_AGENT_DIR/$LABEL.plist"; then
  fail "設定自動啟動失敗（launchctl load 出錯）。App 已經裝在 /Applications，可以先手動雙擊開啟，之後再重新執行這支安裝程式試試看自動啟動設定。"
fi

echo ""
echo "安裝完成。"
echo ""
echo "螢幕右上角選單列會出現一個圖示（三個小點＝啟動中，星芒圖示＝已就緒）。"
echo "使用方式：在任何 App 選取一段中文文字，自己按 Cmd+C 複製，"
echo "再按 ⌘⌥N（Command+Option+N，或點選單列圖示裡的「標記剪貼簿內容」），"
echo "會跳出視窗顯示標出的人名；標到的話會自動複製到剪貼簿方便貼到別的地方。"
echo "（這個工具不會幫你模擬按 Cmd+C，複製動作永遠由你自己做，避免誤刪選取的文字。）"
echo "第一次使用快捷鍵功能時，macOS 可能會跳出「輸入監控」的授權提示（跟 Clipy 一樣），"
echo "請到「系統設定 > 隱私權與安全性 > 輸入監控」允許 ChineseNameTagger。"
echo "第一次執行如果剛登入、服務還在啟動，最多可能要等 30-40 秒（背景載入模型）。"
echo ""
echo "如果選單列圖示一直卡在「啟動中」沒變成「已就緒」，執行："
echo "  xattr -dr com.apple.quarantine \"$INSTALL_DIR/ChineseNameTagger.app\""
echo "再重新開啟一次。"

dialog_info "安裝完成！\n\n螢幕右上角選單列會出現一個圖示（第一次啟動載入模型可能要 30-40 秒）。\n\n使用方式：選取一段中文文字、Cmd+C 複製，按 ⌘⌥N，或點選單列圖示裡的「標記剪貼簿內容」，會跳出視窗顯示標出的人名。\n\n第一次使用快捷鍵功能時，系統會跳出「輸入監控」授權提示，照著允許即可（選單列圖示裡也有「設定 > 輸入監控權限…」可以再叫出來）。"
