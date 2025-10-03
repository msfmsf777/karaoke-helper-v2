  

<a  id="en"></a>

[English](#en) | [日本語](#ja) | [简体中文](#zh-cn) | [繁體中文](#zh-tw)

  

# v2.2.0 - 白芙妮的伴唱小幫手 v2 (KHelperV2)

A multi‑purpose audio tool built for **streamers, singers, and VTubers**.

[![release](https://img.shields.io/github/v/release/msfmsf777/karaoke-helper-v2?label=Release)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

[![downloads](https://img.shields.io/github/downloads/msfmsf777/karaoke-helper-v2/total?label=Downloads)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

![platform](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)

![gpu](https://img.shields.io/badge/GPU-CUDA%2012.4%20%2F%20cuDNN%209-00a86b)

![license](https://img.shields.io/badge/License-MIT-lightgrey)

----

![Splash](https://i.imgur.com/VQ1jLQT.png)

![UI EN](https://i.imgur.com/eMXv4w8.gif)

>Thanks to [fibimeow222](https://x.com/fibimeow222) for the logo artwork.

----------

## ✨ Features

  

-  **AI Vocal Separation (UVR models)**: One click to export high‑quality **instrumental** and **guide vocals**.

-  **Dual‑output player**: Play one song while sending two different mixes to two devices at the same time:

- Headphones → Original mix (instrumental + vocal)

- Streaming → Instrumental only for the audience (KTV background)

-  **Audio adjustments**:

-  **Pitch shift (time‑stretch free)**: Raise/lower key to fit your range

-  **Independent volume**: Adjust vocals / instrumental separately

-  **LUFS loudness normalization**: Keep similar perceived loudness across songs

-  **Common formats** (WAV/FLAC/MP3…) **【Recommended: WAV】**

----------

## 🖥️ System Requirements

-  **OS**: Windows 10/11 (x64) 【Mac/Linux not supported for now】

-  **CPU build**: No GPU required

-  **GPU build (optional)**:

- NVIDIA GPU (≥ 6 GB VRAM recommended; GTX 1060 6GB or above)

- Graphics driver **≥ 551.61**

-  **CUDA 12.4** and **cuDNN 9**

-  **FFmpeg**: Configured automatically by the installer (or add to PATH yourself)

-  **Microsoft VC++ 2015–2022 x64**: Checked/installed by the installer

----------

## ⬇️ Download & Install

Grab the **installer** from GitHub Releases (or the links below) and run it.

**【VERY IMPORTANT】**

1. Before downloading, check whether your PC has an NVIDIA GPU and driver that meet the minimum GPU‑acceleration requirements (see System Requirements above). If yes, choose the **GPU** build (faster separation). Otherwise choose the **CPU** build (smaller install, slower separation).

  

Latest downloads:

【[CPU build](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_CPU.KHelperV2_Setup.exe)】【[GPU build](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_GPU.KHelperV2_Setup.exe)】

2. The installer will automatically:

- Install the core GUI

- Extract required vocal‑separation files (CPU/GPU)

- Check/install Microsoft VC++ (if missing)

- Configure FFmpeg (if missing)

3. On first run, initialization may take a while. Subsequent startup speed depends on your hardware.

> If Windows SmartScreen appears (unsigned), click “More info → Run anyway”.

  

4. Inside the app you can see the **GPU acceleration** status. If it shows **disabled**, you can enable it in Settings (if available).

  

----------

## ⚡ Quick Start

In first startup, the interface is displayed in **Chinese**. You can always go to the top left coner and change the language by **clicking the globe icon🌐**. An APP restart is needed to initialize a new language.

1.  **【Recommended】Create/choose a fixed folder**

Click “Change” at the top‑left to select a folder, so you can reliably pick audio files later.

【Note: Keep the instrumental and vocal of the same song in the same folder】

2.  **Try vocal separation**

On first use, open the top‑right **UVR Vocal Separation Tool** panel and click **Settings**. If you don’t want to tweak anything, simply click **Save** to initialize the **UVR separation settings** (you can start with the recommended model).

Click “**Browse**” or turn on **YouTube Mode** to load/download the song audio → press **Separate** and wait (speed depends on CPU/GPU).

3.  **Load audio**

After separation, if the output location is the File Explorer folder, the files will be auto‑selected. To change selection:

- Left‑click: choose instrumental

- Right‑click: choose vocal

Adjust output device and other settings, then click **Load Audio**.

> For streaming software (OBS etc.), set the **Streaming Output Device** as an audio source.

  

### For detailed guides, see 【[User Guide](https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B)】

  

---

## ❓ FAQ (Selected)

  

-  **Still hearing a bit of vocal/instrumental after separation?**

That can be normal—try another model. MDX Inst vocals may contain some bleed, but the instrumental is kept as clean as possible.

-  **No sound on the streaming side?**

Check that the **Streaming Output Device** matches your OBS settings; also confirm it isn’t muted.

-  **Inconsistent loudness between songs?**

Enable **LUFS Normalization** and set an appropriate target.

----------

## 🧰 Troubleshooting (Install / Launch)

  

-  **Stuck or timeout on splash screen**

- Ensure you installed the correct **build (CPU or GPU)**

- For GPU build, verify driver ≥ 551.61 and **CUDA 12.4 / cuDNN 9** installed

- Check antivirus/security tools; try “Run as administrator”

- Avoid overly long paths or special characters in the install path

-  **FFmpeg not found**

- Reinstall (the installer auto‑configures), or add `<InstallPath>\ffmpeg\bin` to PATH

-  **VC++ related errors**

- Ensure **Microsoft VC++ 2015–2022 x64** is installed (the installer should handle it; if it failed, download and install from 【[Direct link](https://aka.ms/vs/17/release/vc_redist.x64.exe)】)

  

----------

  

## 🙏 Acknowledgements

  

-  **[Ultimate Vocal Remover (UVR)](https://github.com/Anjok07/ultimatevocalremovergui)** — open‑source models & research

-  **ONNX Runtime** (CPU/GPU execution)

-  **FFmpeg** (transcoding/decoding)

-  **Python** and its ecosystem

-  **NVIDIA CUDA/cuDNN** (when using GPU)
- **yt-dlp** (YouTube video download)

> Huge thanks to the projects and communities that made this tool possible.

  

----------

## 🤝 Support Me

  

Please come follow me on X so you won’t miss the cool stuff—even if I mostly post silly things~ 【[@msfmsf777](https://x.com/msfmsf777)】

Also check out my channels if you wish — I loves to sing too♪

  

【[YouTube](https://www.youtube.com/channel/UCNJO-LslaeE_VHfSKeNMRTQ)】【[Twitch](https://www.twitch.tv/msfmsf777)】【[Bilibili](https://space.bilibili.com/2052734754)】

  

----------

  

## 📄 [License](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/LICENSE)

  

This project is released under the **MIT** License (all models/components used are open‑source and permitted for reuse; third‑party components follow their respective licenses — see [THIRD-PARTY-NOTICES](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/THIRD-PARTY-NOTICES.md)).

> For developers who wish to build upon this app, please comply with the MIT License and give proper attribution to this app, UVR, and their authors.

  

----------

  

## 📬 Support

  

Issues/feature requests: click **Report Issue** at the top‑left inside the app! When reporting bugs, please include your install method, logs, and repro steps.

  

💖 Business · Collaboration · Inquiries: msfmsfyt@gmail.com

  
  

---

  
  
  

<a  id="ja"></a>

[English](#en) | [日本語](#ja) | [简体中文](#zh-cn) | [繁體中文](#zh-tw)

  

# v2.2.0 - 白狐のカラオケヘルパー v2 (KHelperV2)

**配信者・歌手・VTuber** のための多機能オーディオツール。

[![release](https://img.shields.io/github/v/release/msfmsf777/karaoke-helper-v2?label=Release)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

[![downloads](https://img.shields.io/github/downloads/msfmsf777/karaoke-helper-v2/total?label=Downloads)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

![platform](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)

![gpu](https://img.shields.io/badge/GPU-CUDA%2012.4%20%2F%20cuDNN%209-00a86b)

![license](https://img.shields.io/badge/License-MIT-lightgrey)

----

![Splash](https://i.imgur.com/VQ1jLQT.png)

![UI JA](https://i.imgur.com/ctRlQy1.gif)

>ロゴ制作は [fibimeow222](https://x.com/fibimeow222) さん、ありがとうございます。

----------

## ✨ 特長

  

-  **AIボーカル分離（UVRモデル）**：ワンクリックで高品質な **インスト** と **ガイドボーカル** を出力。

-  **デュアル出力プレイヤー**：同じ曲を再生しつつ、異なるミックスを2つのデバイスへ同時出力：

- ヘッドホン → 原曲（インスト＋ボーカル）

- 配信 → 視聴者にはインストのみ（KTV風BGM）

-  **オーディオ調整**：

-  **ピッチ変更（タイムストレッチなし）**：キー上下で声域に合わせる

-  **個別ボリューム**：ボーカル / インストを個別調整

-  **LUFS 正規化**：曲間で近いラウドネスを維持

-  **一般的な形式**（WAV/FLAC/MP3…）【WAV推奨】

----------

## 🖥️ 動作環境

-  **OS**：Windows 10/11（x64）【現時点でMac/Linuxは非対応】

-  **CPU版**：GPU不要

-  **GPU版（任意）**：

- NVIDIA GPU（推奨 6GB VRAM以上；GTX 1060 6GB 以上）

- グラフィックドライバ **≥ 551.61**

-  **CUDA 12.4** と **cuDNN 9**

-  **FFmpeg**：インストーラが自動設定（または手動でPATHに追加）

-  **Microsoft VC++ 2015–2022 x64**：インストーラが自動確認/インストール

----------

## ⬇️ ダウンロードとインストール

GitHub Releases（または下記リンク）から **インストーラ** を取得して実行してください。

**【重要】**

1. ダウンロード前に、お使いのPCが最小要件を満たすNVIDIA GPUとドライバを備えているか確認してください（上記の動作環境参照）。満たしていれば **GPU版**（分離が高速）を、無い場合は **CPU版**（容量小、分離はやや遅い）を選択してください。

  

最新版ダウンロード：

【[CPU版](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.21.0/v2.2.0_CPU.KHelperV2_Setup.exe)】【[GPU版](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_GPU.KHelperV2_Setup.exe)】

2. インストーラは自動で以下を行います：

- コアGUIのインストール

- 対応するボーカル分離必須ファイル（CPU/GPU）の展開

- Microsoft VC++ の確認/インストール（未導入の場合）

- FFmpeg の設定（未導入の場合）

3. 初回起動時は初期化に時間がかかる場合があります。以降の速度はPC性能に依存します。

> Windows SmartScreen（未署名）が表示されたら「詳細情報 → 実行」を選択してください。

  

4. アプリ内で **GPU加速** の状態を確認できます。**未有効** と表示される場合は、（使用可能なら）設定から有効化してください。

  

----------

## ⚡ クイックスタート

初回起動時はインターフェースが**中国語**で表示されます。言語は画面左上の**地球儀アイコン🌐**をクリックして変更できます。新しい言語を反映するにはアプリの再起動が必要です。

1.  **【推奨】固定のフォルダを作成/選択**

左上の「変更」をクリックしてフォルダを選び、後で音声ファイルを選びやすくします。

【注：同じ曲のインスト/ボーカルは同一フォルダに置いてください】

2.  **ボーカル分離を試す**

初回は右上の **「UVR ボーカル分離ツール」** パネルで **設定** を開き、細かい調整をしない場合は **保存** を押して **UVR分離設定** を初期化します（迷ったら推奨モデルでOK）。

「**ファイルを選択**」をクリック、または **YouTube モード** を有効にして楽曲の音声を読み込み/ダウンロード → **分離** を押して完了を待ちます（速度は CPU/GPU に依存）。

3.  **音声を読み込む**

分離後、出力先がエクスプローラーのフォルダなら自動選択されます。選択を変えるには：

- 左クリック：インストを選択

- 右クリック：ボーカルを選択

出力先やその他の設定を調整し、**音声を読み込む** を押してください。

> 配信ソフト（OBS等）では「配信出力デバイス」を音声ソースとして設定してください。

  

### 詳細な手順は【[ユーザーガイド](https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B)】をご覧ください。

  

---

## ❓ よくある質問（抜粋）

  

-  **分離後も少しボーカル/インストが残る？**

正常な場合があります。モデルを変更してみてください。MDX Inst 系のボーカルは若干のインストが混入することがありますが、インスト側は可能な限りクリーンです。

-  **配信側で音が出ない？**

「配信出力デバイス」とOBSの設定が一致しているか確認し、ミュートされていないか確認してください。

-  **曲ごとに音量がバラつく？**

**LUFS正規化** を有効にし、適切な目標値を設定してください。

----------

## 🧰 トラブルシューティング（インストール / 起動）

  

-  **スプラッシュ画面で停止/タイムアウトする**

- 正しい **ビルド（CPU or GPU）** を導入しているか確認

- GPU版はドライバ ≥ 551.61、**CUDA 12.4 / cuDNN 9** の導入を確認

- セキュリティソフトの干渉を確認；「管理者として実行」を試す

- インストール先のパスが長すぎたり特殊文字を含まないか確認

-  **FFmpeg が見つからない**

- 再インストール（インストーラが自動設定）するか、`<InstallPath>\ffmpeg\bin` をPATHに追加

-  **VC++ 関連のエラー**

-  **Microsoft VC++ 2015–2022 x64** が導入済みか確認（通常はインストーラが対応。失敗した場合は【[こちら](https://aka.ms/vs/17/release/vc_redist.x64.exe)】から入手）

  

----------

  

## 🙏 謝辞

  

-  **[Ultimate Vocal Remover (UVR)](https://github.com/Anjok07/ultimatevocalremovergui)** のオープンソース研究/モデル

-  **ONNX Runtime**（CPU/GPU実行）

-  **FFmpeg**（トランスコード/デコード）

-  **Python** とそのエコシステム

-  **NVIDIA CUDA/cuDNN**（GPU使用時）
- **yt-dlp** (YouTubeビデオのダウンロード)

> 本ツールは多くのプロジェクト/コミュニティの貢献に支えられています。感謝！

  

----------

## 🤝 白狐の応援

  

X（旧Twitter）をフォローしてね！最新の楽しい情報を見逃さないように～（日常ポストも多いけど）【[@msfmsf777](https://x.com/msfmsf777)】

チャンネルもぜひ！ 歌うことが大好きです♪

  

【[YouTube](https://www.youtube.com/channel/UCNJO-LslaeE_VHfSKeNMRTQ)】【[Twitch](https://www.twitch.tv/msfmsf777)】【Bilibili](https://space.bilibili.com/2052734754)】

  

----------

  

## 📄 [ライセンス](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/LICENSE)

  

本プロジェクトは **MITライセンス** で提供されています（使用しているモデル/コンポーネントは再利用可能なオープンソース。サードパーティは各ライセンスに従います。詳細は [THIRD-PARTY-NOTICES](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/THIRD-PARTY-NOTICES.md) を参照）。

> 本アプリをベースに開発する場合は、MITライセンスを遵守し、本アプリ・UVR・各作者への適切なクレジット表示をお願いします。

  

----------

  

## 📬 サポート

  

不具合/要望はアプリ左上の **「問題を報告」** から！ バグ報告には、導入方法・ログ・再現手順の添付を推奨します。

  

💖 お仕事・コラボ・お問い合わせ：msfmsfyt@gmail.com

  
  

---

  
  
  

<a  id="zh-cn"></a>

[English](#en) | [日本語](#ja) | [简体中文](#zh-cn) | [繁體中文](#zh-tw)

  

# v2.2.0 - 白芙妮的伴唱小助手 v2 (KHelperV2)

为 **主播、歌手、VTuber** 打造的多功能音频工具。

[![release](https://img.shields.io/github/v/release/msfmsf777/karaoke-helper-v2?label=Release)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

[![downloads](https://img.shields.io/github/downloads/msfmsf777/karaoke-helper-v2/total?label=Downloads)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

![platform](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)

![gpu](https://img.shields.io/badge/GPU-CUDA%2012.4%20%2F%20cuDNN%209-00a86b)

![license](https://img.shields.io/badge/License-MIT-lightgrey)

----

![Splash](https://i.imgur.com/VQ1jLQT.png)

![UI zhCN](https://i.imgur.com/kJ7axrJ.gif)

>感谢 [fibimeow222](https://x.com/fibimeow222) 设计的 Logo。

----------

## ✨ 功能特色

  

-  **AI 人声分离（UVR 模型）**：一键导出高质量 **伴奏** 与 **导唱人声**。

-  **双通道播放器**：同一首歌，同时向两个设备输出两种混音：

- 耳机 → 听原曲（伴奏+人声）

- 直播 → 仅给观众伴奏（KTV 背景）

-  **音频调节**：

-  **变调（不变速）**：升/降 Key 贴合音域

-  **独立音量**：人声 / 伴奏可分别调节

-  **LUFS 响度统一**：不同歌曲保持接近的听感音量

-  **常见格式**（WAV/FLAC/MP3…）【推荐 WAV】

----------

## 🖥️ 系统需求

-  **操作系统**：Windows 10/11（x64）【暂不支持 Mac/Linux】

-  **CPU 版**：无需 GPU

-  **GPU 版（可选）**：

- NVIDIA 显卡（建议 ≥ 6GB 显存；GTX 1060 6GB 或以上）

- 显卡驱动版本 **≥ 551.61**

-  **CUDA 12.4** 与 **cuDNN 9**

-  **FFmpeg**：安装程序可自动配置（或自行加入 PATH）

-  **Microsoft VC++ 2015–2022 x64**：安装程序会自动检查/安装

----------

## ⬇️ 下载与安装

前往 GitHub Releases（或下方）下载 **安装程序** 并运行。

**【非常重要】**

1. 下载前请确认是否具备满足 GPU 加速最低要求的 NVIDIA 显卡与驱动（见上方系统需求）。若满足可选择 **GPU** 版（分离更快）；否则请选择 **CPU** 版（体积更小、分离较慢）。

  

最新版本下载：

【[CPU 版下载](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_CPU.KHelperV2_Setup.exe)】【[GPU 版下载](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_GPU.KHelperV2_Setup.exe)】

2. 安装器将自动：

- 安装核心 GUI

- 解压相应的人声分离必备文件（CPU/GPU）

- 检查/安装 Microsoft VC++（若系统未安装）

- 配置 FFmpeg（若系统未安装）

3. 首次运行需初始化，可能加载较久；后续速度取决于电脑性能。

> 若遇到 Windows SmartScreen（未签章），点击「更多信息 → 仍要运行」。

  

4. 进入 APP 后可看到 GPU 加速状态；若显示未启用，可在设置中开启（若可用）。

  

----------

## ⚡ 快速开始

1.  **【推荐】创建/选择一个固定文件夹**

点击界面左上方「更改」选择一个文件夹，方便后续随时选择音频文件。

【注：确保同一首歌的伴奏/人声在同一个文件夹内】

2.  **试试人声分离**

初次使用请先在右上方「UVR 人声分离工具」面板点击 **设置**；不想微调可直接点 **保存** 初始化 **UVR 分离设置**（不确定可先用推荐模型）。

点击「**选择文件**」或打开 **YouTube 模式** 载入/下载歌曲音频 → 按 **分离**，等待完成（速度取决于 CPU/显卡）。

3.  **载入音频**

分离完成后，若输出位置为资源管理器的文件夹，音频将自动被选中。若要更改选择：

- 左键：选择伴奏

- 右键：选择人声

调整输出位置与其他设置后，点击 **加载音频**。

> 直播软件（OBS 等）请将「直播输出设备」加入为音频来源。

  

### 更详细的教程请见【[使用教程](https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B)】

  

---

## ❓ 常见问题（精选）

  

-  **分离后仍残留少量人声/伴奏？**

正常，可更换模型；MDX Inst 系列的人声文件可能带有少量伴奏，但伴奏文件会尽量干净。

-  **直播端没有声音？**

检查「直播输出设备」与 OBS 设置是否一致；确认未被静音。

-  **音量忽大忽小？**

启用 **LUFS 响度统一** 并设置合适目标值。

----------

## 🧰 疑难排解（安装 / 启动）

  

-  **启动画面卡住或超时**

- 确认安装了正确的 **版本（CPU 或 GPU）**

- GPU 版请确认驱动 ≥ 551.61，且已安装 **CUDA 12.4 / cuDNN 9**

- 检查杀毒/安全软件拦截；尝试「以管理员身份运行」

- 安装路径避免过长或包含特殊字符

-  **找不到 FFmpeg**

- 重新安装（安装器会自动配置），或将 `<安装路径>\ffmpeg\bin` 加入 PATH

-  **VC++ 相关错误**

- 确认已安装 **Microsoft VC++ 2015–2022 x64**（安装器通常会自动处理；若失败请从【[快捷链接](https://aka.ms/vs/17/release/vc_redist.x64.exe)】下载安装）

  

----------

  

## 🙏 致谢

  

-  **[Ultimate Vocal Remover (UVR)](https://github.com/Anjok07/ultimatevocalremovergui)** 开源人声分离模型与研究

-  **ONNX Runtime**（CPU/GPU 执行）

-  **FFmpeg**（转码/解码）

-  **Python** 及其生态

-  **NVIDIA CUDA/cuDNN**（若使用 GPU）
- **yt-dlp** (YouTube视频下载)


> 感谢以上项目与社区的贡献，使本工具成为可能。

  

----------

## 🤝 支持小芙妮

  

欢迎关注我的 X（Twitter），别错过最新有趣内容～虽然日常碎碎念也很多啦~ 【[@msfmsf777](https://x.com/msfmsf777)】

也可以来看看我的频道～平时是个爱唱歌的芙妮~

  

【[YouTube](https://www.youtube.com/channel/UCNJO-LslaeE_VHfSKeNMRTQ)】【[Twitch](https://www.twitch.tv/msfmsf777)】【哔哩哔哩](https://space.bilibili.com/2052734754)】

  

----------

  

## 📄 [授权 License](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/LICENSE)

  

本项目以 **MIT** 许可发布（所使用的模型/组件均为允许再利用的开源项目；第三方组件依其各自许可，详见 [THIRD-PARTY-NOTICES](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/THIRD-PARTY-NOTICES.md)）。

> 希望基于本 APP 继续开发的第三方开发者请遵循 MIT 许可，并对本 APP、UVR 及其作者进行适当署名。

  

----------

  

## 📬 支援

  

遇到问题/功能请求可在 APP 左上角点击 **「回报问题」**！报告 Bug 建议附上安装方式、日志与复现步骤！

  

💖 商务 · 合作 · 咨询：msfmsfyt@gmail.com

  
  

---

  
  
  

<a  id="zh-tw"></a>

[English](#en) | [日本語](#ja) | [简体中文](#zh-cn) | [繁體中文](#zh-tw)

  

# v2.2.0 - 白芙妮的伴唱小幫手 v2 (KHelperV2)

專為 **實況主、歌手、VTuber** 打造的多功能音訊工具。

[![release](https://img.shields.io/github/v/release/msfmsf777/karaoke-helper-v2?label=Release)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

[![downloads](https://img.shields.io/github/downloads/msfmsf777/karaoke-helper-v2/total?label=Downloads)](https://github.com/msfmsf777/karaoke-helper-v2/releases)

![platform](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)

![gpu](https://img.shields.io/badge/GPU-CUDA%2012.4%20%2F%20cuDNN%209-00a86b)

![license](https://img.shields.io/badge/License-MIT-lightgrey)

----

![Splash](https://i.imgur.com/VQ1jLQT.png)

![UI zhTW](https://i.imgur.com/z5TpZGv.gif)

>感謝[菲比](https://x.com/fibimeow222)繪製的Logo圖

----------

## ✨ 功能特色

  

-  **AI 人聲分離（UVR 模型）**：一鍵輸出高品質 **伴奏** 與 **導唱人聲**。

-  **雙聲道播放器**：同一首歌，同步輸出兩種混音到兩個裝置：

- 耳機 → 聽原曲（伴奏+人聲）

- 直播 → 只給觀眾伴奏（KTV 背景）

-  **音訊調整**：

-  **移調（不變速）**：升/降 Key 貼合音域

-  **獨立音量**：人聲 / 伴奏可分別調整

-  **LUFS 音量一致化**：不同歌維持接近的聽感音量

-  **常用格式**（WAV/FLAC/MP3…）【推薦wav】

----------

## 🖥️ 系統需求

-  **作業系統**：Windows 10/11（x64）【暫不支援Mac/Linux】

-  **CPU 版**：無需 GPU

-  **GPU 版（選用）**：

- NVIDIA GPU（建議 ≥ 6GB VRAM；GTX 1060 6GB 或以上）

- 顯示卡驅動版本 **≥ 551.61**

-  **CUDA 12.4** 與 **cuDNN 9**

-  **FFmpeg**：安裝程式可自動配置（或自行加入 PATH）

-  **Microsoft VC++ 2015–2022 x64**：安裝程式會自動檢查/安裝

----------

## ⬇️ 下載與安裝

到 GitHub Releases （或者下面）下載 **安裝程式** 並執行即可。

**【非常重要 · 注意】**

1. 請在下載前檢查自己是否安裝符合最低GPU加速要求的Nvidia顯示卡以及驅動（見上方系統需求），若符合可以選擇 **GPU** 版本（更快分離速度）；否則請選擇 **CPU** 版本（安裝體積小，分離速度較慢）

  

最新版本下載連結：

【[CPU版本下載連結](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_CPU.KHelperV2_Setup.exe)】【[GPU版本下載連結](https://github.com/msfmsf777/karaoke-helper-v2/releases/download/v2.2.0/v2.2.0_GPU.KHelperV2_Setup.exe)】

2. 安裝器會自動：

- 安裝核心 GUI

- 解壓對應人聲分離必備檔案（CPU/GPU）

- 檢查/安裝 微軟VC++（若系統未安裝）

- 配置 FFmpeg（若系統未安裝）

3. 首次運行需初始化，可能加載時間較長，後面運行速度跟電腦效能有關。

> 若遇到 Windows SmartScreen（未簽章），點「更多資訊 → 仍要執行」。

  

4. 進入APP後能看到 GPU 加速的狀態，若顯示未啓用，可以去設定打開（若可用）。

  

----------

## ⚡快速開始

1.  **【推薦】建立/選擇一個固定資料夾**

點擊界面左上方「更改」來選擇一個資料夾，便於後面隨時選擇音檔。

【注：確保同首歌曲的伴奏/人聲在同一個資料夾內】

2.  **嘗試人聲分離**

首次使用請先在右上方「UVR 人聲分離工具」面板按 **設定**，若不願微調可以直接按「**儲存**」來初始化 **UVR 人聲分離設定**（不確定可先用推薦模型）。

點擊「**選擇檔案**」或打開 **YouTube 模式**載入/下載歌曲音檔 → 按 **分離**，等待完成（速度取決於 CPU/顯卡）。

3.  **載入音檔**

分離完成後，若輸出位置是檔案總管的資料夾，音檔會自動被選擇。若想改變選擇，使用：

- 左鍵：選擇伴奏檔

- 右鍵：選擇人聲檔

調整輸出位置與其他設定後按 **加載音訊** 即可。

> 直播軟體（OBS 等）請把「直播輸出裝置」設定為音訊來源。

  

### 更詳細教學請見【[使用教程](https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B)】

  

---

## ❓ 常見問題（精選）

  

-  **分離後仍殘留少量人聲/伴奏？**

正常，可更換模型；MDX Inst 系列的人聲檔可能帶些伴奏，但伴奏檔會盡量乾淨。

-  **直播側沒有聲音？**

檢查「直播輸出裝置」與 OBS 設定是否一致；確認沒有靜音。

-  **音量忽大忽小？**

啟用 **LUFS 音量統一** 並設定合適目標值。

----------

## 🧰 疑難排解（安裝 / 啟動）

  

-  **啟動畫面卡住或逾時**

- 確認已安裝正確的 **版本（CPU 或 GPU）**

- GPU 版請確認驅動 ≥ 551.61、已安裝 **CUDA 12.4 / cuDNN 9**

- 檢查防毒/安全性工具是否攔截；嘗試「以系統管理員執行」

- 安裝路徑避免過長或含特殊字元

-  **FFmpeg 找不到**

- 重新安裝（安裝器會自動配置），或將 `<安裝路徑>\ffmpeg\bin` 加入 PATH

-  **VC++ 相關錯誤**

- 確認已安裝 **Microsoft VC++ 2015–2022 x64**（安裝器應該會自動處理，但如果安裝器出現錯誤，請點擊下載安裝【[快速傳送](https://aka.ms/vs/17/release/vc_redist.x64.exe)】）

  

----------

  

## 🙏 致謝

  

-  **[Ultimate Vocal Remover (UVR)](https://github.com/Anjok07/ultimatevocalremovergui)** 開源人聲分離模型與研究

-  **ONNX Runtime**（CPU/GPU 執行）

-  **FFmpeg**（轉檔/解碼）

-  **Python** 與相關生態

-  **NVIDIA CUDA/cuDNN**（若使用 GPU）
- **yt-dlp** (YouTube影片下載)

> 感謝以上專案與社群的貢獻，讓本工具得以實現。

  

----------

## 🤝 支持小芙妮

  

拜托來追隨窩的推特 才不會錯過最新的酷酷内容喔 雖然平常都廢文就是了~ 【[@msfmsf777](https://x.com/msfmsf777)】

也可以來看看我的頻道~ 平常是ponpon愛唱歌的芙妮w

  

【[YouTube](https://www.youtube.com/channel/UCNJO-LslaeE_VHfSKeNMRTQ)】【[Twitch](https://www.twitch.tv/msfmsf777)】【[B站](https://space.bilibili.com/2052734754)】

  

----------

  

## 📄 [授權 License](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/LICENSE)

  

此專案以 **MIT** 授權釋出（使用到的模型/元件均爲允許重新利用的開源項目，第三方元件依其各自授權【詳見[THIRD-PARTY-NOTICES](https://github.com/msfmsf777/karaoke-helper-v2/blob/main/THIRD-PARTY-NOTICES.md  "THIRD-PARTY-NOTICES.md")】。

>請注意：對於所有希望使用本APP繼續開發的第三方開發者，請遵循MIT License，並對本APP，UVR及其開發者給予適當的聲明。

  

----------

  

## 📬 支援

  

遇到問題/功能請求 可以APP内點左上方【回報問題】！回報Bug時建議附上安裝方式、日誌與重現步驟！

  

💖工商 · 合作 · 疑問請聯係信箱：msfmsfyt@gmail.com
