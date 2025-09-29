# v2.0.0 - 白芙妮的伴唱小幫手 v2 (KHelperV2)
專為 **實況主、歌手、VTuber** 打造的多功能音訊工具。  
[![release](https://img.shields.io/github/v/release/msfmsf777/karaoke-helper-v2?label=Release)](https://github.com/msfmsf777/karaoke-helper-v2/releases)  
[![downloads](https://img.shields.io/github/downloads/msfmsf777/karaoke-helper-v2/total?label=Downloads)](https://github.com/msfmsf777/karaoke-helper-v2/releases)  
![platform](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)  
![gpu](https://img.shields.io/badge/GPU-CUDA%2012.4%20%2F%20cuDNN%209-00a86b)  
![license](https://img.shields.io/badge/License-MIT-lightgrey)
----
![Splash](https://i.imgur.com/0RWhoxL.png)  
![UI](https://i.imgur.com/rJrG6nC.png)
>感謝[菲比](https://x.com/fibimeow222)繪製的Logo圖
----------
## ✨ 功能特色

-   **AI 人聲分離（UVR 模型）**：一鍵輸出高品質 **伴奏** 與 **導唱人聲**。
-   **雙聲道播放器**：同一首歌，同步輸出兩種混音到兩個裝置：
    -   耳機 → 聽原曲（伴奏+人聲）
    -   直播 → 只給觀眾伴奏（KTV 背景）
-   **音訊調整**：
    -   **移調（不變速）**：升/降 Key 貼合音域
    -   **獨立音量**：人聲 / 伴奏可分別調整
    -   **LUFS 音量一致化**：不同歌維持接近的聽感音量
-   **常用格式**（WAV/FLAC/MP3…）【推薦wav】
----------
## 🖥️ 系統需求
-   **作業系統**：Windows 10/11（x64）【暫不支援Mac/Linux】
-   **CPU 版**：無需 GPU
-   **GPU 版（選用）**：
    -   NVIDIA GPU（建議 ≥ 6GB VRAM；GTX 1060 6GB 或以上）
    -   顯示卡驅動版本 **≥ 551.61**
    -   **CUDA 12.4** 與 **cuDNN 9**
-   **FFmpeg**：安裝程式可自動配置（或自行加入 PATH）
-   **Microsoft VC++ 2015–2022 x64**：安裝程式會自動檢查/安裝
----------
## ⬇️ 下載與安裝
到 GitHub Releases （或者下面）下載 **安裝程式** 並執行即可。
**【非常重要 · 注意】**
1.  請在下載前檢查自己是否安裝符合最低GPU加速要求的Nvidia顯示卡以及驅動（見上方系統需求），若符合可以選擇 **GPU** 版本（更快分離速度）；否則請選擇 **CPU** 版本（安裝體積小，分離速度較慢）

【[CPU版本下載連結](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.0.0/CPU.KHelperV2_Setup.exe)】【[GPU版本下載連結](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.0.0/GPU.KHelperV2_Setup.exe)】
    
2.  安裝器會自動：
    -   安裝核心 GUI
    -   解壓對應人聲分離必備檔案（CPU/GPU）
    -   檢查/安裝 微軟VC++（若系統未安裝）
    -   配置 FFmpeg（若系統未安裝）
3. 首次運行需初始化，可能加載時間較長，後面運行速度跟電腦效能有關。
        
> 若遇到 Windows SmartScreen（未簽章），點「更多資訊 → 仍要執行」。

4. 進入APP後能看到 GPU 加速的狀態，若顯示未啓用，可以去設定打開。

----------
## ⚡快速開始
1.  **【推薦】建立/選擇一個固定資料夾**  
    點擊界面左上方「更改」來選擇一個資料夾，便於後面隨時選擇音檔。  
    【注：確保同首歌曲的伴奏/人聲在同一個資料夾內】
2.  **嘗試人聲分離**  
    首次使用請先在右上方「UVR 人聲分離工具」面板按 **設定**，若不願微調可以直接按「**儲存**」來初始化 **UVR 人聲分離設定**（不確定可先用推薦模型）。  
    點擊「**選擇檔案**」載入歌曲音檔 → 按 **分離**，等待完成（速度取決於 CPU/顯卡）。
3.  **載入音檔**  
    分離完成後，若輸出位置是檔案總管的資料夾，音檔會自動被選擇。若想改變選擇，使用：
    -   左鍵：選擇伴奏檔
    -   右鍵：選擇人聲檔  
        調整輸出位置與其他設定後按 **加載音訊** 即可。
> 直播軟體（OBS 等）請把「直播輸出裝置」設定為音訊來源。

### 更詳細教學請見【[使用教程](https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B)】

---
## ❓ 常見問題（精選）

-   **分離後仍殘留少量人聲/伴奏？**  
    正常，可更換模型；MDX Inst 系列的人聲檔可能帶些伴奏，但伴奏檔會盡量乾淨。
-   **直播側沒有聲音？**  
    檢查「直播輸出裝置」與 OBS 設定是否一致；確認沒有靜音。
-   **音量忽大忽小？**  
    啟用 **LUFS 音量統一** 並設定合適目標值。
----------
## 🧰 疑難排解（安裝 / 啟動）

-   **啟動畫面卡住或逾時**
    -   確認已安裝正確的 **版本（CPU 或 GPU）**
    -   GPU 版請確認驅動 ≥ 551.61、已安裝 **CUDA 12.4 / cuDNN 9**
    -   檢查防毒/安全性工具是否攔截；嘗試「以系統管理員執行」
    -   安裝路徑避免過長或含特殊字元
-   **FFmpeg 找不到**
    -   重新安裝（安裝器會自動配置），或將 `<安裝路徑>\ffmpeg\bin` 加入 PATH
-   **VC++ 相關錯誤**
    -   確認已安裝 **Microsoft VC++ 2015–2022 x64**（安裝器應該會自動處理，但如果安裝器出現錯誤，請點擊下載安裝【[快速傳送](https://aka.ms/vs/17/release/vc_redist.x64.exe)】）

----------

## 🙏 致謝

-   **[Ultimate Vocal Remover (UVR)](https://github.com/Anjok07/ultimatevocalremovergui)** 開源人聲分離模型與研究
-   **ONNX Runtime**（CPU/GPU 執行）
-   **FFmpeg**（轉檔/解碼）
-   **Python** 與相關生態
-   **NVIDIA CUDA/cuDNN**（若使用 GPU）
> 感謝以上專案與社群的貢獻，讓本工具得以實現。

----------
## 🤝 支持小芙妮

拜托來追隨窩的推特 才不會錯過最新的酷酷内容喔 雖然平常都廢文就是了~ 【[@msfmsf777](https://x.com/msfmsf777)】
也可以來看看我的頻道~ 平常是ponpon愛唱歌的芙妮w

【[YouTube](https://www.youtube.com/channel/UCNJO-LslaeE_VHfSKeNMRTQ)】【[Twitch](https://www.twitch.tv/msfmsf777)】【[B站](https://space.bilibili.com/2052734754)】

----------

## 📄 [授權 License](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/LICENSE)

此專案以 **MIT** 授權釋出（使用到的模型/元件均爲允許重新利用的開源項目，第三方元件依其各自授權【詳見[THIRD-PARTY-NOTICES](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/THIRD-PARTY-NOTICES.md "THIRD-PARTY-NOTICES.md")】。
>請注意：對於所有希望使用本APP繼續開發的第三方開發者，請遵循MIT License，並對本APP，UVR及其開發者給予適當的聲明。

----------

## 📬 支援

遇到問題/功能請求 可以APP内點左上方【回報問題】！回報Bug時建議附上安裝方式、日誌與重現步驟！

💖工商 · 合作 · 疑問請聯係信箱：msfmsfyt@gmail.com
