## 安裝方式
1. 下載並解壓縮 `ChineseNameTaggerMac.zip`
2. 雙擊解壓縮出來的資料夾裡的 **`install_mac.command`**
   （Finder 會自動開一個 Terminal 視窗跑安裝程式，過程中會跳出原生視窗
   確認安裝內容、安裝完成後也會跳出提示）

如果比較習慣打指令，也可以用 Terminal `cd` 進資料夾後執行 `./install_mac.sh`，
效果完全一樣（只是不方便雙擊）。

## 這個 App 沒有 Apple 開發者簽章
這是免費的個人小工具，沒有加入付費的 Apple Developer Program，所以沒有
官方簽章/公證。安裝程式裝好時會自動處理這件事，一般情況下不會再看到
「無法驗證開發者」的警告。如果選單列圖示一直卡在「啟動中」沒變成
「已就緒」，在 Terminal 執行：
```
xattr -dr com.apple.quarantine /Applications/ChineseNameTagger.app
```
再重新開啟一次就可以了。

## 用法
選一段中文文字、Cmd+C 複製，按 ⌘⌥N（或點選單列圖示裡的「標記剪貼簿內容」），
會跳出視窗顯示標出的人名。第一次使用快捷鍵，系統會跳出「輸入監控」授權
提示，照著允許即可（App 裡也有選單「設定 > 輸入監控權限…」可以再叫出來）。
