# THIRD-PARTY-NOTICES.md

本專案（“白芙妮的伴唱小幫手 v2”）包含或分發第三方軟體。這些元件的授權文本和歸屬如下提供（或鏈接）。某些工件（模型/二進位檔）可能在執行時下載或通過安裝程式運送；其授權仍然適用。
This project (“白芙妮的伴唱小幫手 v2”) includes or distributes third-party software. The license texts and attribution for those components are provided below (or linked). Some artifacts (models/binaries) may be downloaded at runtime or shipped via the installer; their licenses still apply.

> 注意：以下清單為常見相依元件與授權簡述。實際隨發行版（CPU/GPU sidecar venv，以及安裝器所打包/下載的檔案）所包含之套件，請以該發行版為準並據以補齊/修正。

>Note: The following list provides a summary of common dependencies and their licenses. The actual packages included with the release (CPU/GPU sidecar venv, and files packaged/downloaded by the installer) should be referred to for completeness and correction.
---

## 摘要 Summary (quick reference)

| 元件 Component | 用途 Purpose | 授權 License (short) |
|---|---|---|
| Python (CPython) | Runtime | PSF-2.0 |
| ONNX Runtime | Inference backend (CPU/GPU) | MIT |
| FFmpeg | Decode/encode | LGPL-2.1+ or GPL (build-dependent) |
| Ultimate Vocal Remover (UVR) & Models | Vocal separation tooling & models | Varies by model; see upstream |
| tqdm | Progress bars | MIT |
| GUI toolkit (e.g., FreeSimpleGUI / PySimpleGUI-equivalent) | UI | See upstream |
| numpy | Array math | BSD-3-Clause |
| soundfile | Audio I/O | BSD-style |
| librosa | Audio analysis | ISC |
| numba / llvmlite | JIT / toolchain | BSD-2/3-Clause |
| torch / torchaudio (if included in some builds) | DL runtime / audio ops | BSD-style (+ third-party notices) |

> ⚠️ Some rows above are placeholders because exact packages can vary across CPU/GPU “sidecar” environments. Verify against the precise wheels/binaries you ship.

---

## 授權信息/連結 License Details & Links

### Python (CPython)
- **License**: Python Software Foundation License 2.0 (PSF-2.0)  
- **Notes**: You may redistribute Python under PSF terms.  
- **Link**: https://www.python.org/download/releases/3.13.1/license/

### ONNX Runtime
- **License**: MIT  
- **Notes**: Applies to both CPU and GPU packages (e.g., `onnxruntime`, `onnxruntime-gpu`).  
- **Link**: https://github.com/microsoft/onnxruntime/blob/main/LICENSE

### FFmpeg
- **License**: **LGPL-2.1+** or **GPL** depending on how the binary is built.  
- **Notes**:
  - If you redistribute a **GPL** build, you must comply with GPL terms (include the GPL license text and corresponding source/offer for FFmpeg).  
  - If you need more permissive terms, use an **LGPL** build (no GPL-only components enabled).  
- **Links**:
  - Licensing overview: https://ffmpeg.org/legal.html  
  - License texts: https://ffmpeg.org/legal.html#license

### Ultimate Vocal Remover (UVR) & Models
- **License**: See the **UVR repository** and **each model’s license/readme**. Different models (e.g., MDX/MDX-Net/UVR-MDX-NET) may have different terms.  
- **Notes**:
  - Attribute UVR when you provide the UVR integration.  
  - Respect individual model licenses。  
- **Link**: https://github.com/Anjok07/ultimatevocalremovergui

### tqdm
- **License**: MIT  
- **Link**: https://github.com/tqdm/tqdm/blob/master/LICENCE

### GUI Toolkit (FreeSimpleGUI / PySimpleGUI-equivalent)
- **License**: GNU Lesser General Public License v3 or later (LGPLv3+)
- **Link**: https://github.com/spyoungtech/FreeSimpleGUI/blob/main/license.txt

### numpy
- **License**: BSD-3-Clause  
- **Link**: https://github.com/numpy/numpy/blob/main/LICENSE.txt

### soundfile
- **License**: BSD-style  
- **Link**: https://github.com/bastibe/python-soundfile/blob/master/LICENSE

### librosa
- **License**: ISC  
- **Link**: https://github.com/librosa/librosa/blob/main/LICENSE.md

### numba / llvmlite
- **License**: BSD-2/3-Clause  
- **Links**:
  - numba: https://github.com/numba/numba/blob/main/LICENSE
  - llvmlite: https://github.com/numba/llvmlite/blob/main/LICENSE

### torch / torchaudio
- **License**: BSD-style
- **Links**:
  - torch: https://github.com/pytorch/pytorch/blob/main/LICENSE  
  - torchaudio: https://github.com/pytorch/audio/blob/main/LICENSE



## 聯絡 Contact
若你發現缺漏或授權資訊不正確，請建立錯誤回報告知，我會儘速修正。

If you notice any omissions or incorrect licensing information, please create an issue to let us know, and we will correct it as soon as possible.
