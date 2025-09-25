"""
Transport-only sidecar client for KHelperV2.
- Speaks NDJSON to the sidecar (no torch / onnxruntime / audio-separator imports here).
- Backward-compatible exports and method names so existing GUI code keeps working:
    * SidecarClient.start_separation(..., **kwargs)   (shim → start_job)
    * SeparatorWorker.separate_audio(...)             (shim → sidecar)
    * list_models() returns [{'filename','name'}]
- Traditional Chinese stage names are mapped to legacy GUI keys and overall %.

This version includes improved GPU detection handling. The client now accepts
`gpu_info` events either with an "info" payload or flat fields. If the
availability flag is absent, it derives it from provider names and device
strings. This ensures the GUI reflects correct GPU status even when the
sidecar uses different message structures.
"""

from __future__ import annotations
import os
import sys
import json
import time
import threading
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

APP_NAME = "KHelperV2"

def _appdata_path() -> str:
    if os.name == "nt":
        return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".config", APP_NAME)

APP_DATA_DIR = _appdata_path()
MODELS_DIR = os.path.join(APP_DATA_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "model_filename": "UVR-MDX-NET-Inst_HQ_5.onnx",
    "output_format": "wav",
    "use_gpu": False,
    "mdx_params": {
        "hop_length": 1024,
        "segment_size": 256,
        "overlap": 0.25,
        "batch_size": 1,
        "enable_denoise": False,
    },
}

def get_recommended_model() -> str:
    return "UVR-MDX-NET-Inst_HQ_5.onnx"

# stage weight *percent* chunks for overall progress (sum ~95, we clamp to 100)
_STAGE_WEIGHTS = {
    "DownloadingModel": 10,
    "LoadingModel": 15,
    "Separation": 65,
    "Finalize": 5,
}

def _dbg(msg: str) -> None:
    try:
        sys.stderr.write(f"[SEP DEBUG] CLIENT: {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass

def _resolve_app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(os.path.dirname(sys.executable))
    return os.path.abspath(os.path.dirname(__file__))

def _sidecar_paths() -> Tuple[str, str, str]:
    root = _resolve_app_root()
    if os.name == "nt":
        interp = os.path.join(root, "sidecar_venv_cpu", "Scripts", "python.exe")
    else:
        interp = os.path.join(root, "sidecar_venv_cpu", "bin", "python")
    service = os.path.join(root, "sidecar", "service.py")
    sidecar_cwd = os.path.dirname(service)
    return interp, service, sidecar_cwd

def _map_stage_to_key(zh: str) -> str:
    m = {
        "下載模型": "DownloadingModel",
        "載入模型": "LoadingModel",
        "分離中": "Separation",
        "儲存結果": "Finalize",
        "就緒": "Finalize",
    }
    return m.get(zh, zh or "")

def _calc_overall(stage_key: str, stage_pct: int) -> int:
    weights = _STAGE_WEIGHTS
    order = ["DownloadingModel", "LoadingModel", "Separation", "Finalize"]
    total = 0
    for name in order:
        w = weights.get(name, 0)
        if name == stage_key:
            total += int(round(w * (max(0, min(100, stage_pct)) / 100.0)))
            break
        else:
            total += w
    return max(0, min(100, total))

def _to_mapping(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, (list, tuple)) and len(obj) == 2 and isinstance(obj[0], str):
        return {"type": obj[0], "value": obj[1]}
    return {"value": obj}

def _to_model_pairs(models: Any) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if models is None:
        return out
    if isinstance(models, (dict, tuple, list, str)):
        seq: List[Any]
        if isinstance(models, (dict, str)) or (isinstance(models, tuple) and len(models) == 2 and isinstance(models[0], str)):
            seq = [models]
        else:
            seq = list(models)  # type: ignore[arg-type]
        for item in seq:
            if isinstance(item, dict):
                fn = item.get("filename") or item.get("file") or item.get("name")
                nm = item.get("name") or item.get("friendly_name") or fn
                if isinstance(fn, str) and fn:
                    out.append((fn, str(nm or fn)))
            elif isinstance(item, (list, tuple)) and len(item) >= 1:
                fn = item[0]
                nm = item[1] if len(item) > 1 else item[0]
                if isinstance(fn, str):
                    out.append((fn, str(nm)))
            elif isinstance(item, str):
                out.append((item, item))
    seen = set()
    uniq: List[Tuple[str, str]] = []
    for fn, nm in out:
        if fn not in seen:
            seen.add(fn)
            uniq.append((fn, nm))
    return uniq

class SidecarClient:
    def __init__(
        self,
        interpreter_path: Optional[str] = None,
        service_path: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> None:
        if interpreter_path and service_path:
            py = interpreter_path
            svc = service_path
            sidecar_cwd = cwd or os.path.dirname(service_path)
        else:
            py, svc, sidecar_cwd = _sidecar_paths()

        if not os.path.isfile(py):
            raise FileNotFoundError(f"找不到 sidecar 解譯器: {py}")
        if not os.path.isfile(svc):
            raise FileNotFoundError(f"找不到 sidecar 服務: {svc}")

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]

        args = [py, "-u", "-X", "utf8", svc]
        _dbg(f"Spawning sidecar: {args} cwd={sidecar_cwd}")
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=sidecar_cwd,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",
            env=env,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError("無法啟動 sidecar 服務")

        self._alive = True
        self._rd = threading.Thread(target=self._read_loop, daemon=True)
        self._rd.start()
        self._rd_err = threading.Thread(target=self._read_stderr, daemon=True)
        self._rd_err.start()

        # NOTE: _cb_progress receives a DICT payload from the reader thread (we bridge shape below)
        self._cb_progress: Optional[Callable[[Dict[str, Any]], None]] = None
        self._cb_done: Optional[Callable[[Dict[str, Any]], None]] = None
        self._cb_error: Optional[Callable[[Dict[str, Any]], None]] = None
        self._job_active = False

        self._models_waiter: Optional["_Waiter"] = None

        # NEW: GPU capability callback + buffer last seen info
        self.on_gpu_info: Optional[Callable[[Dict[str, Any]], None]] = None
        self.last_gpu_info: Optional[Dict[str, Any]] = None

        self._send({"cmd": "hello"})

    def _read_stderr(self) -> None:
        if not self.proc.stderr:
            return
        for line in self.proc.stderr:
            if not self._alive:
                break
            try:
                sys.stderr.write(line)
                sys.stderr.flush()
            except Exception:
                pass

    def _send(self, obj: Dict[str, Any]) -> None:
        if self.proc.poll() is not None:
            raise RuntimeError(f"sidecar 已退出 (exit {self.proc.returncode})")
        try:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            _dbg(f"CLIENT -> sidecar: {obj.get('cmd')}")
        except Exception as e:
            raise RuntimeError(f"傳送指令失敗: {e}")

    def _read_loop(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            if not self._alive:
                break
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception as e:
                _dbg(f"Bad NDJSON from sidecar: {e}: {line[:200]}")
                continue

            # Handle early GPU capability report from sidecar (job-independent)
            if isinstance(ev, dict) and ev.get("type") == "gpu_info":
                # Accept both new and old formats: prefer nested 'info'; else derive from flat fields
                info = ev.get("info")
                if not info or not isinstance(info, dict):
                    # Flatten event minus type
                    info = {k: v for k, v in ev.items() if k != "type"}
                # Derive availability if missing
                if "available" not in info:
                    try:
                        info['available'] = bool(
                            info.get('cuda') or info.get('torch_cuda') or
                            ('CUDAExecutionProvider' in (info.get('ort_providers') or [])) or
                            (str(info.get('ort_device', '')).lower() != 'cpu' and info.get('ort_device'))
                        )
                    except Exception:
                        info['available'] = False
                # buffer last seen so GUI can fetch it after binding
                self.last_gpu_info = info
                # deliver to dedicated callback if bound
                if self.on_gpu_info:
                    try:
                        self.on_gpu_info(info)
                    except Exception:
                        pass
                # also mirror to per-job progress for existing GUI wiring
                if self._cb_progress:
                    try:
                        self._cb_progress({"type": "gpu_info", "info": info})
                    except Exception:
                        pass
                continue  # handled

            self._dispatch(ev)

    def _dispatch(self, ev: Dict[str, Any]) -> None:
        et = ev.get("type")

        if et == "models":
            if self._models_waiter:
                self._models_waiter.set_result(ev.get("models") or [])
            return

        if et == "status":
            stage_zh = str(ev.get("stage") or "")
            key = ev.get("stage_key") or _map_stage_to_key(stage_zh)
            if self._cb_progress and key:
                payload = {"type": "progress", "stage": key, "stage_pct": 0, "overall": _calc_overall(key, 0)}
                try:
                    self._cb_progress(payload)
                except Exception:
                    pass
            return

        if et == "progress":
            stage_zh = str(ev.get("stage") or "")
            pct = int(ev.get("pct", 0))
            key = ev.get("stage_key") or _map_stage_to_key(stage_zh)
            payload = {"type": "progress", "stage": key, "stage_pct": pct, "overall": _calc_overall(key, pct)}
            _dbg(f"CLIENT <- progress: stage={key} pct={pct} overall={payload['overall']}")
            if self._cb_progress:
                try:
                    self._cb_progress(payload)
                except Exception:
                    pass
            return

        if et == "done":
            self._job_active = False
            files = list(ev.get("files") or [])
            duration = int(ev.get("duration_sec", 0))
            payload = {"type": "done", "files": files, "duration": duration}
            if self._cb_done:
                try:
                    self._cb_done(payload)
                except Exception:
                    pass
            return

        if et == "aborted":
            self._job_active = False
            if self._cb_error:
                try:
                    self._cb_error({"type": "aborted"})
                except Exception:
                    pass
            return

        if et == "error":
            self._job_active = False
            msg = str(ev.get("msg") or "未知錯誤")
            payload = {"type": "error", "message": msg}
            if self._cb_error:
                try:
                    self._cb_error(payload)
                except Exception:
                    pass
            return

    def list_models(self, timeout: float = 30.0) -> List[Dict[str, str]]:
        w = _Waiter()
        self._models_waiter = w
        self._send({"cmd": "list_models"})
        raw = w.wait(timeout=timeout)
        self._models_waiter = None
        pairs = _to_model_pairs(raw)
        out: List[Dict[str, str]] = [{"filename": fn, "name": nm} for fn, nm in pairs]
        _dbg(f"list_models() normalized {len(out)} items")
        return out

    def start_job(
        self,
        *,
        input_path: str,
        output_dir: str,
        model_dir: str,
        model_filename: str,
        use_gpu: bool,
        output_format: str,
        on_progress: Callable[[Dict[str, Any]], None],
        on_done: Callable[[Dict[str, Any]], None],
        on_error: Callable[[Dict[str, Any]], None],
    ) -> None:
        self._cb_progress = on_progress
        self._cb_done = on_done
        self._cb_error = on_error
        self._job_active = True
        self._send(
            {
                "cmd": "separate",
                "id": f"job-{int(time.time() * 1000)}",
                "input_path": input_path,
                "output_dir": output_dir,
                "model_file_dir": model_dir,
                "model_filename": model_filename,
                "use_gpu": bool(use_gpu),
                "output_format": (output_format or "wav").lower(),
            }
        )

    def start_separation(
        self,
        *,
        input_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        **kwargs: Any,
    ) -> None:
        """
        Minimal-compat shim:
        - Accepts your GUI's on_progress(stage, pct), on_status(stage, msg), on_done(files, duration), on_error(where, msg)
        - Still supports legacy dict-style progress_callback / callback.
        """
        if input_path is None:
            input_path = kwargs.get("input_path")
        if output_dir is None:
            output_dir = kwargs.get("output_dir")
        if settings is None:
            settings = {}

        merged: Dict[str, Any] = {}
        merged.update(settings or {})
        merged.update(kwargs or {})

        model_filename = (
            merged.get("model_filename")
            or merged.get("filename")
            or DEFAULT_SETTINGS["model_filename"]
        )
        model_dir = (
            merged.get("model_file_dir")
            or merged.get("model_dir")
            or MODELS_DIR
        )
        use_gpu = bool(merged.get("use_gpu", DEFAULT_SETTINGS["use_gpu"]))
        out_fmt = str(merged.get("output_format", DEFAULT_SETTINGS["output_format"])).lower()

        # Pick up all callback names the GUI may pass
        cb_prog_2 = merged.get("on_progress")          # expects (stage, pct)
        cb_stat_2 = merged.get("on_status")            # expects (stage, msg) [optional]
        cb_done_2 = merged.get("on_done")              # expects (files, duration_sec)
        cb_err_2  = merged.get("on_error")             # expects (where, msg)

        # Legacy single-callback dict style
        if progress_callback is None:
            progress_callback = merged.get("progress_callback") or merged.get("callback")

        _dbg(
            f"start_separation shim: input={input_path}, outdir={output_dir}, model={model_filename}, dir={model_dir}, fmt={out_fmt}, use_gpu={use_gpu}"
        )
        if not input_path or not output_dir:
            raise ValueError("缺少必要參數：input_path 或 output_dir")

        # Bridge from dict payloads coming from the reader thread to the GUI's expected signatures
        def _bridge_progress(p: Dict[str, Any]) -> None:
            mp = _to_mapping(p)
            stage = str(mp.get("stage") or "")
            pct = int(mp.get("stage_pct", mp.get("pct", 0)))
            try:
                # Prefer GUI two-arg progress callback
                if cb_prog_2:
                    cb_prog_2(stage, pct)
                # Fallback to legacy dict-style progress callback
                elif progress_callback:
                    progress_callback({"type": "progress", "stage": stage, "stage_pct": pct, "overall": _calc_overall(stage, pct)})
            except Exception:
                pass

        def _bridge_done(p: Dict[str, Any]) -> None:
            mp = _to_mapping(p)
            files = list(mp.get("files") or [])
            duration = int(mp.get("duration", mp.get("duration_sec", 0)))
            try:
                if cb_done_2:
                    cb_done_2(files, duration)
                elif progress_callback:
                    progress_callback({"type": "done", "files": files, "duration": duration})
            except Exception:
                pass

        def _bridge_error(p: Dict[str, Any]) -> None:
            mp = _to_mapping(p)
            typ = mp.get("type")
            if typ == "aborted":
                # Try to emit a non-error cancel path
                try:
                    if progress_callback:
                        progress_callback({"type": "aborted"})
                    elif cb_err_2:
                        cb_err_2("aborted", "已取消")
                except Exception:
                    pass
                return
            # General error
            msg = str(mp.get("message", "未知錯誤"))
            try:
                if cb_err_2:
                    cb_err_2("general", msg)
                elif progress_callback:
                    progress_callback({"type": "error", "message": msg})
            except Exception:
                pass

        # Also bridge status (stage change with 0%) if GUI supplied on_status
        def _bridge_status_like(p: Dict[str, Any]) -> None:
            if not cb_stat_2:
                return
            mp = _to_mapping(p)
            stage = str(mp.get("stage") or "")
            msg = str(mp.get("msg") or "")
            try:
                cb_stat_2(stage, msg)
            except Exception:
                pass

        # Wire the bridges into start_job
        # We wrap _bridge_progress to also call on_status if stage_pct==0 (status-like tick)
        def _on_progress_dispatch(mp: Dict[str, Any]) -> None:
            if int(mp.get("stage_pct", mp.get("pct", 0))) == 0:
                _bridge_status_like(mp)
            _bridge_progress(mp)

        self.start_job(
            input_path=input_path,
            output_dir=output_dir,
            model_dir=model_dir,
            model_filename=model_filename,
            use_gpu=use_gpu,
            output_format=out_fmt,
            on_progress=_on_progress_dispatch,
            on_done=_bridge_done,
            on_error=_bridge_error,
        )

    def abort(self) -> None:
        try:
            self._send({"cmd": "abort"})
        except Exception:
            pass

class _Waiter:
    def __init__(self) -> None:
        self.evt = threading.Event()
        self.res: Any = None
    def set_result(self, x: Any) -> None:
        self.res = x; self.evt.set()
    def wait(self, timeout: float) -> Any:
        if not self.evt.wait(timeout):
            raise TimeoutError("等待回應逾時")
        return self.res

_client_lock = threading.Lock()
_client_singleton: Optional[SidecarClient] = None

def _get_client() -> SidecarClient:
    global _client_singleton
    with _client_lock:
        if _client_singleton is None:
            _client_singleton = SidecarClient()
        return _client_singleton

def list_models() -> List[Dict[str, str]]:
    return _get_client().list_models()

class SeparatorWorker:
    """
    Back-compat helper for older code paths. For new code, use SidecarClient directly.
    """
    def __init__(self) -> None:
        self._cli = _get_client()

    def separate(
        self,
        input_path: str,
        output_dir: str,
        model_dir: str,
        model_filename: str,
        callback: Callable[[Dict[str, Any]], None],
        *,
        use_gpu: bool = False,
        output_format: str = "wav",
    ) -> None:
        def on_prog(p: Dict[str, Any]) -> None:
            try: callback(_to_mapping(p))
            except Exception: pass
        def on_done(p: Dict[str, Any]) -> None:
            try: callback(_to_mapping(p))
            except Exception: pass
        def on_err(p: Dict[str, Any]) -> None:
            mp = _to_mapping(p)
            typ = mp.get("type")
            if typ == "aborted":
                try: callback({"type": "aborted"})
                except Exception: pass
                return
            try: callback({"type": "error", "message": mp.get("message", "未知錯誤")})
            except Exception: pass

        self._cli.start_job(
            input_path=input_path,
            output_dir=output_dir,
            model_dir=model_dir,
            model_filename=model_filename,
            use_gpu=use_gpu,
            output_format=output_format,
            on_progress=on_prog,
            on_done=on_done,
            on_error=on_err,
        )

    def separate_audio(
        self,
        input_path: str,
        output_dir: str,
        settings: Dict[str, Any],
        progress_callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        self._cli.start_separation(
            input_path=input_path,
            output_dir=output_dir,
            settings=settings or {},
            progress_callback=progress_callback,
        )

    def abort(self) -> None:
        self._cli.abort()

__all__ = [
    "SidecarClient",
    "SeparatorWorker",
    "list_models",
    "MODELS_DIR",
    "APP_DATA_DIR",
    "get_recommended_model",
]