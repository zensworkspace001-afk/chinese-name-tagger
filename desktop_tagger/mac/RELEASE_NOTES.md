## 安裝方式
1. 下載並解壓縮 `ChineseNameTaggerMac.zip`
2. 打開 Terminal，`cd` 到解壓縮出來的資料夾
3. 執行 `./install_mac.sh`

## 這個 App 沒有 Apple 開發者簽章，第一次開啟會被 Gatekeeper 擋下來
`install_mac.sh` 裝好之後如果選單列圖示一直顯示「尚未啟動」，在 Terminal 執行：
```
xattr -dr com.apple.quarantine /Applications/ChineseNameTagger.app
```
再重新開啟一次就可以了。

## 用法
選一段中文文字、Cmd+C 複製，按 ⌘⌥N（或點選單列圖示裡的「標記剪貼簿內容」），
會跳出視窗顯示標出的人名。第一次使用快捷鍵，系統會跳出「輸入監控」授權
提示，照著允許即可（App 裡也有選單「設定 > 輸入監控權限…」可以再叫出來）。
