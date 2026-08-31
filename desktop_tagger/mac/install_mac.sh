#!/bin/bash
# 安裝「中文人名標示」到這台 Mac：
#   1. 把打包好的 ChineseNameTagger.app（含 Python/torch/模型）複製到
#      /Applications/（放這裡而不是 ~/Library 是因為系統設定裡「輸入監控」
#      清單的「+」新增檔案選擇視窗，跟 Finder 一樣預設不顯示 ~/Library，
#      放 /Applications 使用者才找得到、點得到）
#   2. 安裝 LaunchAgent，讓它在登入時自動啟動並常駐（選單列圖示）
#
# 用法：cd desktop_tagger/mac && ./install_mac.sh
#
# 使用方式（跟 Clipy 一樣：選單列圖示 + 全域快捷鍵，不是右鍵選單——
# 實測手刻的 Automator Services bundle 沒辦法通過 macOS 的 Spotlight 掃描
# 而無法註冊進右鍵選單，Clipy 本身其實也是走這條路，並不是右鍵選單）：
#   在任何 App 選取一段中文文字，按 ⌘⌥N，跳出視窗顯示標出的人名。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/Applications"
LOG_DIR="$HOME/Library/Logs/ChineseNameTagger"
LAUNCH_AGENT_DIR="$HOME/Library/LaunchAgents"
LABEL="com.zens.chinesetagger"

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
  echo "找不到 ChineseNameTagger.app。" >&2
  echo "如果你是要在本機重新打包，請先執行：" >&2
  echo "  ./build_venv/bin/pyinstaller ChineseNameTagger.spec --noconfirm" >&2
  echo "如果你是從 GitHub Release 下載的 zip，請確認解壓縮後" >&2
  echo "ChineseNameTagger.app 有跟 install_mac.sh 放在同一層資料夾。" >&2
  exit 1
fi

echo "==> 停止舊的服務（如果有在跑）"
launchctl unload "$LAUNCH_AGENT_DIR/$LABEL.plist" 2>/dev/null || true
pkill -f "ChineseNameTagger.app/Contents/MacOS/ChineseNameTagger" 2>/dev/null || true

echo "==> 安裝 App 到 $INSTALL_DIR"
rm -rf "$INSTALL_DIR/ChineseNameTagger.app"
cp -R "$APP_SRC" "$INSTALL_DIR/"
# 注意：不要在這裡動 ~/Library/Application Support/ChineseNameTagger ——
# 單一執行個體鎖檔（.instance.lock）放在那裡，如果舊 process 還在跑、
# 這裡把那個目錄砍掉重建，會讓舊 process 手上的 flock 變成鎖在一個已經
# 被刪除的 inode 上，新 process 反而能拿到「新的」鎖檔而重複啟動。

echo "==> 準備 log 目錄 $LOG_DIR"
mkdir -p "$LOG_DIR"

echo "==> 安裝 LaunchAgent（登入時自動啟動、常駐）"
mkdir -p "$LAUNCH_AGENT_DIR"
sed \
  -e "s#__INSTALL_DIR__#$INSTALL_DIR#g" \
  -e "s#__LOG_DIR__#$LOG_DIR#g" \
  "$HERE/com.zens.chinesetagger.plist" > "$LAUNCH_AGENT_DIR/$LABEL.plist"
launchctl load "$LAUNCH_AGENT_DIR/$LABEL.plist"

echo ""
echo "安裝完成。"
echo ""
echo "注意：這個執行檔沒有 Apple 開發者簽章，第一次啟動 macOS 可能會擋下來。"
echo "如果服務一直顯示「尚未啟動」，請執行以下指令解除隔離後再試一次："
echo "  xattr -dr com.apple.quarantine \"$INSTALL_DIR/ChineseNameTagger.app\""
echo ""
echo "螢幕右上角選單列會出現一個圖示（三個小點＝啟動中，星芒圖示＝已就緒）。"
echo "使用方式：在任何 App 選取一段中文文字，自己按 Cmd+C 複製，"
echo "再按 ⌘⌥N（Command+Option+N，或點選單列圖示裡的「標記剪貼簿內容」），"
echo "會跳出視窗顯示標出的人名；標到的話會自動複製到剪貼簿方便貼到別的地方。"
echo "（這個工具不會幫你模擬按 Cmd+C，複製動作永遠由你自己做，避免誤刪選取的文字。）"
echo "第一次使用快捷鍵功能時，macOS 可能會跳出「輸入監控」的授權提示（跟 Clipy 一樣），"
echo "請到「系統設定 > 隱私權與安全性 > 輸入監控」允許 ChineseNameTagger。"
echo "第一次執行如果剛登入、服務還在啟動，最多可能要等 30-40 秒（背景載入模型）。"
