from __future__ import annotations
import sys, os, json, time, threading, traceback, urllib.request, subprocess, shlex, re
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# ----- Force UTF-8 stdio (avoid Windows cp1252 issues) -----
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

APP_NAME = "KHelperV2"
def _appdata_path() -> str:
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", APP_NAME)

def _app_root() -> Path:
    # Works both in dev (source .py) and frozen exe
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

def _find_sidecar_python(want_gpu: bool) -> str:
    base = _app_root()
    # Put the most likely names first. You said CPU build puts the venv as "sidecar_venv"
    candidates = []
    if want_gpu:
        candidates += [base / "sidecar_venv_gpu" / "Scripts" / "python.exe"]
    candidates += [
        base / "sidecar_venv"      / "Scripts" / "python.exe",
        base / "sidecar_venv_cpu"  / "Scripts" / "python.exe",
        base / "sidecar_venv_gpu"  / "Scripts" / "python.exe",  # fallback order
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # absolute fallback: whatever launched us (dev case)
    return sys.executable

APP_DATA_DIR = _appdata_path()
MODELS_DIR = os.path.join(APP_DATA_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# zh-TW stages
STAGE_DL    = "下載模型"
STAGE_LOAD  = "載入模型"
STAGE_SEP   = "分離中"
STAGE_SAVE  = "儲存結果"
STAGE_READY = "就緒"   # default idle

CANDIDATE_MANIFEST_URLS = [
    "https://huggingface.co/seanghay/uvr_models/resolve/main/download_checks.json",
    "https://huggingface.co/ekopat/uvr_models/resolve/main/download_checks.json",
    "https://raw.githubusercontent.com/seanghay/uvr_models/main/download_checks.json",
    "https://raw.githubusercontent.com/msfmsf777/uvr_model_manifest/main/download_checks.json",
]

_out_lock = threading.Lock()
def send_event(obj: Dict[str, Any]) -> None:
    """Emit NDJSON to GUI (ASCII-escaped to be safe across consoles)."""
    try:
        line = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    except Exception as e:
        try: sys.stderr.write(f"[SEP DEBUG] JSON encode failure: {e}\n"); sys.stderr.flush()
        except Exception: pass
        return
    with _out_lock:
        try:
            sys.stdout.write(line + "\n"); sys.stdout.flush()
        except Exception as e:
            try: sys.stderr.write(f"[SEP DEBUG] stdout write failure: {e}\n"); sys.stderr.flush()
            except Exception: pass

def dbg(msg: str) -> None:
    try: sys.stderr.write(f"[SEP DEBUG] {msg}\n"); sys.stderr.flush()
    except Exception: pass

# Map zh stage -> GUI stage key (used by client to compute overall %)
def _stage_key_from_zh(zh: str) -> str:
    mapping = {
        STAGE_DL:   "DownloadingModel",
        STAGE_LOAD: "LoadingModel",
        STAGE_SEP:  "Separation",
        STAGE_SAVE: "Finalize",
        STAGE_READY:"Finalize",  # when bouncing back to ready after work/cancel
    }
    return mapping.get(zh, zh or "")

# ---------------------- Model listing (unchanged logic) ----------------------

def fetch_remote_manifest() -> Dict[str, Dict[str, Any]]:
    last_err = None
    for url in CANDIDATE_MANIFEST_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KHelperV2/1.0"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status != 200:
                    last_err = f"HTTP {resp.status}"; continue
                raw = resp.read()
                try: data = json.loads(raw)
                except Exception: data = json.loads(raw.decode("utf-8", errors="ignore"))
                if not isinstance(data, (dict, list)): continue
                normalized: Dict[str, Dict[str, Any]] = {}
                items = data.items() if isinstance(data, dict) else []
                if isinstance(data, list):
                    for it in data:
                        if isinstance(it, dict):
                            fn = it.get("filename") or it.get("file") or it.get("name")
                            if fn: items.append((fn, it))
                for k, v in items:
                    if not isinstance(v, dict): continue
                    fname = str(k).strip()
                    if not fname: continue
                    normalized[fname] = {
                        "url": v.get("url") or v.get("download_url") or v.get("hf_url"),
                        "sha256": v.get("sha256") or v.get("sha256sum"),
                        "size": v.get("size"),
                        "family": v.get("family"),
                        "friendly_name": v.get("friendly_name") or v.get("label") or fname,
                    }
                if normalized:
                    dbg(f"Remote manifest loaded from {url} with {len(normalized)} entries")
                    return normalized
        except Exception as e:
            last_err = str(e); continue
    dbg(f"Remote manifest not available ({last_err}).")
    return {}

def read_packaged_models() -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []; seen=set()
    try:
        import importlib.resources as ir
        import audio_separator
        for fname in ("model-data.json", "models-scores.json"):
            try:
                data=None
                if hasattr(ir, "files"):
                    p = ir.files(audio_separator) / fname
                    if p.is_file():
                        with p.open("r", encoding="utf-8") as f: data=json.load(f)
                else:
                    with ir.open_text("audio_separator", fname, encoding="utf-8") as f: data=json.load(f)
                if not data: continue
                if isinstance(data, dict):
                    if "models" in data and isinstance(data["models"], list):
                        for m in data["models"]:
                            fn=(m.get("filename") or "").strip()
                            fr=(m.get("friendly_name") or m.get("name") or fn).strip()
                            if fn and fn.lower().endswith(".onnx") and fn.lower() not in seen:
                                out.append((fn, fr or fn)); seen.add(fn.lower())
                    else:
                        for fn, m in data.items():
                            fr=(m.get("friendly_name") or m.get("name") or fn).strip() if isinstance(m, dict) else str(m)
                            sfn=str(fn)
                            if sfn and sfn.lower().endswith(".onnx") and sfn.lower() not in seen:
                                out.append((sfn, fr or sfn)); seen.add(sfn.lower())
                elif isinstance(data, list):
                    for m in data:
                        if isinstance(m, dict):
                            fn=(m.get("filename") or m.get("Model Filename") or "").strip()
                            fr=(m.get("friendly_name") or m.get("Friendly Name") or fn).strip()
                            if fn and fn.lower().endswith(".onnx") and fn.lower() not in seen:
                                out.append((fn, fr or fn)); seen.add(fn.lower())
                dbg(f"read_packaged_models: added from {fname}: {len(out)} total so far")
            except FileNotFoundError:
                dbg(f"read_packaged_models: {fname} not found in package")
            except Exception as e:
                dbg(f"read_packaged_models: failed to parse {fname}: {e}")
    except Exception as e:
        dbg(f"read_packaged_models: importlib.resources failed: {e}")
    return out

def list_models_combined() -> List[Dict[str, str]]:
    out: List[Tuple[str, str]] = []; seen=set()
    try:
        for fn in os.listdir(MODELS_DIR):
            if fn.lower().endswith(".onnx"):
                out.append((fn, fn)); seen.add(fn.lower())
        dbg(f"list_models: found {len(out)} local .onnx")
    except Exception as e:
        dbg(f"list_models: local scan failed: {e}")
    added_api=0
    try:
        from audio_separator.separator import Separator
        sep=Separator()
        if hasattr(sep, "list_models"):
            api_list=sep.list_models()
            for m in api_list or []:
                filename=(m.get("model_filename") or m.get("Model Filename") or m.get("filename"))
                friendly=m.get("Friendly Name") or m.get("friendly_name") or filename
                if filename and filename.lower() not in seen:
                    out.append((filename, friendly or filename)); seen.add(filename.lower()); added_api+=1
        dbg(f"list_models: API added {added_api}, total {len(out)}")
    except Exception as e:
        dbg(f"list_models: API list failed: {e}")
    try:
        pkg_models=read_packaged_models(); added=0
        for fn, fr in pkg_models:
            if fn.lower() not in seen:
                out.append((fn, fr or fn)); seen.add(fn.lower()); added+=1
        dbg(f"list_models: packaged metadata added {added}, total {len(out)}")
    except Exception as e:
        dbg(f"list_models: packaged metadata failed: {e}")
    try:
        manifest=fetch_remote_manifest(); added=0
        for fname, meta in manifest.items():
            if fname and fname.lower().endswith(".onnx") and fname.lower() not in seen:
                out.append((fname, meta.get("friendly_name") or fname)); seen.add(fname.lower()); added+=1
        dbg(f"list_models: manifest added {added}, total {len(out)}")
    except Exception as e:
        dbg(f"list_models: manifest failed: {e}")
    if not out:
        out=[("UVR-MDX-NET-Inst_HQ_5.onnx","UVR MDX-NET Inst HQ 5 (recommended)"),
             ("UVR-MDX-NET-Inst_HQ_4.onnx","UVR MDX-NET Inst HQ 4"),
             ("UVR_MDXNET_KARA_2.onnx","UVR MDXNET KARA 2")]
    rec="UVR-MDX-NET-Inst_HQ_5.onnx"; enhanced=[]
    for fn, fr in out:
        name=fr or fn
        if fn==rec and "(recommended)" not in (name or "").lower():
            name=f"{name} (recommended)"
        enhanced.append({"filename":fn,"name":name})
    return enhanced

# ---------------------- Ensure / Download ----------------------

class AbortError(Exception): pass

def download_with_progress(url: str, dest_path: str, abort_evt: threading.Event) -> None:
    tmp_path = dest_path + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KHelperV2/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = resp.getheader("Content-Length")
            total_len = int(total) if total and total.isdigit() else None
            bytes_read = 0; last_emit = 0.0
            with open(tmp_path, "wb") as out:
                while True:
                    if abort_evt.is_set(): raise AbortError("download aborted")
                    chunk = resp.read(65536)
                    if not chunk: break
                    out.write(chunk); bytes_read += len(chunk)
                    now=time.time()
                    if total_len and (now - last_emit) >= 0.15:
                        pct = int(round((bytes_read/total_len)*100))
                        send_event({"type":"progress","stage":STAGE_DL,"pct":max(0,min(100,pct)),"stage_key":_stage_key_from_zh(STAGE_DL)})
                        last_emit = now
        os.replace(tmp_path, dest_path)
        send_event({"type":"progress","stage":STAGE_DL,"pct":100,"stage_key":_stage_key_from_zh(STAGE_DL)})
    except AbortError:
        try:
            if os.path.exists(tmp_path): os.remove(tmp_path)
        except Exception: pass
        raise
    except Exception:
        try:
            if os.path.exists(tmp_path): os.remove(tmp_path)
        except Exception: pass
        raise

def ensure_model_available(model_filename: str, model_file_dir: str, abort_evt: threading.Event) -> None:
    """
    Lenient behavior (mirrors the older working version):
    - If local file exists -> return (OK).
    - If manifest does not contain an entry for the file -> DO NOT raise.
      Emit a status hint and return, letting audio-separator attempt its own download.
    - If manifest has URL -> download with progress (supports abort & .part cleanup).
    """
    if not model_filename:
        raise RuntimeError("未指定模型檔名")

    md_dir = model_file_dir or MODELS_DIR
    os.makedirs(md_dir, exist_ok=True)
    local_path = os.path.join(md_dir, model_filename)

    if os.path.exists(local_path):
        dbg(f"ensure_model_available: using local model {local_path}")
        return

    manifest = fetch_remote_manifest()
    entry = manifest.get(model_filename)

    # ---- LENIENT CHANGE: if no manifest entry, do NOT raise; allow child to try API download ----
    if not entry or not entry.get("url"):
        dbg(f"ensure_model_available: manifest missing for {model_filename}; letting API try auto-download")
        send_event({
            "type": "status",
            "stage": STAGE_DL,
            "msg": f"未在清單中；交由 API 嘗試下載 {model_filename}",
            "stage_key": _stage_key_from_zh(STAGE_DL),
        })
        return  # <--- lenient exit; do not block the pipeline

    # If we do have a URL, download as usual
    send_event({"type":"status","stage":STAGE_DL,"msg":f"下載 {model_filename}","stage_key":_stage_key_from_zh(STAGE_DL)})
    download_with_progress(entry["url"], local_path, abort_evt)

# ---------------------- Separation via child script ----------------------

class SidecarWorker:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._abort_evt = threading.Event()
        self._child: Optional[subprocess.Popen] = None
        self._child_reader: Optional[threading.Thread] = None
        self._child_err_reader: Optional[threading.Thread] = None  # drain child stderr
        # ---- NEW: track current stage + last parsed tqdm pct from stderr (for DL/LOAD only)
        self._current_stage: str = STAGE_READY
        self._stderr_pct_last: Dict[str, int] = {STAGE_DL: -1, STAGE_LOAD: -1}
        self._stderr_last_emit: float = 0.0

    def busy(self) -> bool:
        alive_thread = self._thread is not None and self._thread.is_alive()
        alive_child  = self._child is not None and self._child.poll() is None
        return alive_thread or alive_child

    def abort(self) -> None:
        self._abort_evt.set()
        dbg("Abort requested")
        if self._child and self._child.poll() is None:
            try: self._child.terminate()
            except Exception as e: dbg(f"Abort terminate failed: {e}")
        send_event({"type":"status","stage":STAGE_READY,"msg":"已取消","stage_key":_stage_key_from_zh(STAGE_READY)})

    def ensure_model(self, model_file_dir: str, model_filename: str) -> None:
        if self.busy():
            send_event({"type":"error","where":"download","msg":"忙碌中，請稍候"}); return
        def _run():
            try:
                self._abort_evt.clear()
                dbg(f"ensure_model: start for {model_filename} in {model_file_dir}")
                ensure_model_available(model_filename, model_file_dir, self._abort_evt)
                send_event({"type":"status","stage":STAGE_READY,"msg":"模型就緒","stage_key":_stage_key_from_zh(STAGE_READY)})
            except AbortError:
                send_event({"type":"status","stage":STAGE_READY,"msg":"已取消","stage_key":_stage_key_from_zh(STAGE_READY)})
            except Exception as e:
                send_event({"type":"error","where":"download","msg":str(e)})
        self._thread = threading.Thread(target=_run, daemon=True); self._thread.start()

    def _read_child_stdout(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line: continue
            try:
                ev = json.loads(line)
            except Exception as e:
                dbg(f"child bad json: {e}: {line[:200]}"); continue
            # normalize stage to attach stage_key
            zh = str(ev.get("stage") or "")
            if ev.get("type") == "status" and ev.get("stage") in ("待命","READY","Idle"):
                zh = STAGE_READY
                ev["stage"] = STAGE_READY
            if zh:
                ev["stage_key"] = _stage_key_from_zh(zh)
                # ---- NEW: remember current stage so stderr parser knows what we're doing
                self._current_stage = zh
            dbg(f"child says: {ev.get('type')} {zh}")
            send_event(ev)

    # drain child stderr to avoid pipe blocking / freezes
    # ---- ENHANCED: also parse tqdm bars and emit progress for DL/LOAD
    def _read_child_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        pct_re = re.compile(r'(\d{1,3})%\|')  # matches " 42%|████..."
        for raw in proc.stderr:
            # Always mirror child's stderr for debugging:
            try:
                sys.stderr.write(raw)
                sys.stderr.flush()
            except Exception:
                pass
            # Parse tqdm only during Download/Load
            try:
                stage = self._current_stage
                if stage not in (STAGE_DL, STAGE_LOAD):
                    continue
                m = pct_re.search(raw)
                if not m:
                    continue
                pct = max(0, min(100, int(m.group(1))))
                last = self._stderr_pct_last.get(stage, -1)
                now = time.time()
                # throttle ~150ms and ignore regressions
                if pct > last and (now - self._stderr_last_emit) >= 0.15:
                    self._stderr_pct_last[stage] = pct
                    self._stderr_last_emit = now
                    send_event({
                        "type":"progress",
                        "stage": stage,
                        "pct": pct,
                        "stage_key": _stage_key_from_zh(stage),
                    })
            except Exception:
                # Never let parsing failures affect the child
                pass

    def separate(self, payload: Dict[str, Any]) -> None:
        if self.busy():
            send_event({"type":"error","where":"separate","msg":"忙碌中，請稍候"}); return

        def _parent_job():
            try:
                self._abort_evt.clear()
                input_path  = payload["input_path"]
                output_dir  = payload["output_dir"]
                model_dir   = payload["model_file_dir"] or MODELS_DIR
                model_fname = payload["model_filename"]
                dbg(f"separate: Preparing with model={model_fname}, model_dir={model_dir}")

                send_event({"type":"status","stage":STAGE_DL,"msg":f"準備模型 {model_fname}","stage_key":_stage_key_from_zh(STAGE_DL)})
                ensure_model_available(model_fname, model_dir, self._abort_evt)
                if self._abort_evt.is_set():
                    send_event({"type":"status","stage":STAGE_READY,"msg":"已取消","stage_key":_stage_key_from_zh(STAGE_READY)})
                    send_event({"type":"aborted"})
                    return

                # Let the child drive the full download/load progress; avoid synthetic % here
                send_event({"type":"status","stage":STAGE_LOAD,"msg":"載入模型","stage_key":_stage_key_from_zh(STAGE_LOAD)})
                # Reset stderr-derived progress baselines when entering LOAD
                self._current_stage = STAGE_LOAD
                self._stderr_pct_last[STAGE_DL] = -1
                self._stderr_pct_last[STAGE_LOAD] = -1
                self._stderr_last_emit = 0.0

                child_path = os.path.join(os.path.dirname(__file__), "child_worker.py")
                if not os.path.isfile(child_path):
                    send_event({"type":"error","where":"separate","msg":"找不到子程序 child_worker.py"})
                    send_event({"type":"status","stage":STAGE_READY,"msg":"錯誤","stage_key":_stage_key_from_zh(STAGE_READY)})
                    return

                payload2 = dict(payload)
                payload2["use_gpu"] = bool(payload.get("use_gpu", False))

                # --- minimal fix: use the sidecar venv python, not sys.executable ---
                exe = _find_sidecar_python(want_gpu=bool(payload.get("use_gpu", False)))
                args = [exe, "-u", "-X", "utf8", child_path]
                dbg(f"separate: starting child with: {shlex.join(args)}")

                env = os.environ.copy()
                env.setdefault("PYTHONIOENCODING", "utf-8")
                env.setdefault("PYTHONUTF8", "1")

                self._child = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=os.path.dirname(child_path),
                    bufsize=1, universal_newlines=True, encoding="utf-8", env=env,
                )

                # Feed payload then close child's stdin
                assert self._child.stdin is not None
                self._child.stdin.write(json.dumps(payload2, ensure_ascii=False) + "\n")
                self._child.stdin.flush()
                if self._child.stdin: self._child.stdin.close()

                # Start BOTH stdout and stderr reader threads (stderr drain + tqdm parsing)
                self._child_reader = threading.Thread(target=self._read_child_stdout, args=(self._child,), daemon=True)
                self._child_reader.start()
                self._child_err_reader = threading.Thread(target=self._read_child_stderr, args=(self._child,), daemon=True)
                self._child_err_reader.start()

                # Wait for child to exit
                while True:
                    code = self._child.poll()
                    if code is not None:
                        dbg(f"separate: child exited with code {code}")
                        break
                    if self._abort_evt.is_set():
                        time.sleep(0.1); continue
                    time.sleep(0.1)

                # If not canceled and child didn't explicitly emit done/error, return to READY
                if not self._abort_evt.is_set():
                    send_event({"type":"status","stage":STAGE_READY,"msg":"就緒","stage_key":_stage_key_from_zh(STAGE_READY)})
                return

            except Exception as e:
                tb = traceback.format_exc(); dbg(f"separate error: {e}\n{tb}")
                send_event({"type":"error","where":"separate","msg":str(e)})
                send_event({"type":"status","stage":STAGE_READY,"msg":"錯誤","stage_key":_stage_key_from_zh(STAGE_READY)})
            finally:
                self._child = None
                self._child_reader = None
                self._child_err_reader = None

        self._thread = threading.Thread(target=_parent_job, daemon=True); self._thread.start()

# -------------------- Command loop --------------------

class SidecarService:
    def __init__(self) -> None:
        self.worker = SidecarWorker()

    def hello(self) -> None:
        api = "0.1.0"
        try:
            import audio_separator as asep; sep_ver = getattr(asep, "__version__", "unknown")
        except Exception:
            sep_ver = "unavailable"
        try:
            import torch; torch_ver = getattr(torch, "__version__", "unavailable")
        except Exception:
            torch_ver = "unavailable"
        try:
            import onnxruntime as ort; ort_ver = getattr(ort, "__version__", "unavailable")
        except Exception:
            ort_ver = "unavailable"
        send_event({"type":"hello","api":api,"sep_version":sep_ver,"torch":torch_ver,"ort":ort_ver})
        # Emit a one-shot GPU capability snapshot for the GUI label
        cuda = False
        torch_cuda = False
        gpu_name = ""
        ort_providers = []
        ort_device = "CPU"
        try:
            import onnxruntime as ort
            if hasattr(ort, "get_available_providers"):
                ort_providers = list(ort.get_available_providers())
                cuda = "CUDAExecutionProvider" in ort_providers
            if hasattr(ort, "get_device"):
                ort_device = ort.get_device()
        except Exception:
            pass
        try:
            import torch
            torch_cuda = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
            if torch_cuda:
                gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            pass
        # Determine availability
        available = bool(
            cuda or torch_cuda or ('CUDAExecutionProvider' in ort_providers) or (ort_device and ort_device.lower() != 'cpu')
        )
        # Package into info dict
        gpu_info_payload = {
            "available": available,
            "cuda": cuda,
            "torch_cuda": torch_cuda,
            "gpu_name": gpu_name,
            "ort_providers": ort_providers,
            "ort_device": ort_device,
        }
        # Emit with nested info and top-level for backwards compat
        send_event({
            "type": "gpu_info",
            "info": gpu_info_payload,
            "available": available,
            "cuda": cuda,
            "torch_cuda": torch_cuda,
            "gpu_name": gpu_name,
            "ort_providers": ort_providers,
            "ort_device": ort_device,
        })
        send_event({"type":"status","stage":STAGE_READY,"msg":"就緒","stage_key":_stage_key_from_zh(STAGE_READY)})

    def handle(self, obj: Dict[str, Any]) -> None:
        cmd = obj.get("cmd")
        if not cmd: return
        if cmd == "hello": self.hello(); return
        if cmd == "list_models":
            try:
                models = list_models_combined()
                send_event({"type":"models","models":models})
            except Exception as e:
                dbg(f"list_models error: {e}")
                send_event({"type":"error","where":"list_models","msg":str(e)})
            return
        if cmd == "ensure_model":
            model = obj.get("model") or obj.get("model_filename")
            model_dir = obj.get("model_file_dir") or MODELS_DIR
            if not model:
                send_event({"type":"error","where":"download","msg":"缺少 model / model_filename"}); return
            self.worker.ensure_model(model_dir, model); return
        if cmd == "separate":
            required = ["input_path","output_dir","model_file_dir","model_filename"]
            missing = [k for k in required if not obj.get(k)]
            if missing:
                send_event({"type":"error","where":"general","msg":f"缺少必要欄位：{', '.join(missing)}"}); return
            self.worker.separate(obj); return
        if cmd == "abort":
            self.worker.abort(); return
        send_event({"type":"error","where":"general","msg":f"未知指令: {cmd}"})

def main() -> None:
    service = SidecarService(); service.hello()
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
        except Exception as e:
            dbg(f"Bad JSON from client: {e} :: {line[:200]}"); continue
        try:
            service.handle(obj)
        except Exception as e:
            tb = traceback.format_exc(); dbg(f"Dispatch error: {e}\n{tb}")
            send_event({"type":"error","where":"general","msg":str(e)})
    dbg("stdin closed; exiting.")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: pass
