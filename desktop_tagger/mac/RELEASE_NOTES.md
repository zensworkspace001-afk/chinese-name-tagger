## 安裝方式（推薦：用 Terminal）
1. 下載並解壓縮 `ChineseNameTaggerMac.zip`
2. 打開 Terminal，`cd` 到解壓縮出來的資料夾，執行：
   ```
   ./install_mac.sh
   ```
   會跳出原生視窗確認安裝內容、裝完也會跳出完成提示。

用 Terminal 執行是因為**不會**經過 Finder 的下載檔案檢查，不會卡在
Gatekeeper 警告，是目前測起來最順的方式。

### 也可以雙擊安裝（`install_mac.command`）
資料夾裡也有 `install_mac.command`，雙擊會自動開 Terminal 執行、效果跟上面
完全一樣。但因為是透過 Finder 開啟下載下來的檔案，**第一次雙擊可能會被
Gatekeeper 擋下來**，跳出「Apple 無法驗證此 App 是否包含惡意軟體」。
如果遇到，回到 Terminal（`cd` 到同一個資料夾）執行：
```
xattr -dr com.apple.quarantine .
```
再雙擊一次，或改用上面的 `./install_mac.sh` 方式。

## 這個 App 沒有 Apple 開發者簽章
這是免費的個人小工具，沒有加入付費的 Apple Developer Program，所以沒有
官方簽章/公證。`install_mac.sh` 裝好 App 時會自動解除隔離屬性，一般情況下
選單列圖示會直接正常啟動。如果圖示一直卡在「啟動中」沒變成「已就緒」，
在 Terminal 執行：
```
xattr -dr com.apple.quarantine /Applications/ChineseNameTagger.app
```
再重新開啟一次就可以了。

## 用法
選一段中文文字、Cmd+C 複製，按 ⌘⌥N（或點選單列圖示裡的「標記剪貼簿內容」），
會跳出視窗顯示標出的人名。第一次使用快捷鍵，系統會跳出「輸入監控」授權
提示，照著允許即可（App 裡也有選單「設定 > 輸入監控權限…」可以再叫出來）。
