from __future__ import annotations
import sys, os, json, time, traceback, importlib
from typing import Any, Dict, List

# Force UTF-8
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

STAGE_DL   = "下載模型"
STAGE_LOAD = "載入模型"
STAGE_SEP  = "分離中"
STAGE_SAVE = "儲存結果"
STAGE_READY= "就緒"

# current stage label used by the tqdm bridge
_CURRENT_TQDM_STAGE = STAGE_SEP

def _set_tqdm_stage(zh: str) -> None:
    global _CURRENT_TQDM_STAGE
    _CURRENT_TQDM_STAGE = zh or STAGE_SEP

def send(obj: Dict[str, Any]) -> None:
    try:
        line = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    except Exception as e:
        try: sys.stderr.write(f"[SEP DEBUG][child] JSON encode fail: {e}\n"); sys.stderr.flush()
        except Exception: pass
        return
    try:
        sys.stdout.write(line + "\n"); sys.stdout.flush()
    except Exception as e:
        try: sys.stderr.write(f"[SEP DEBUG][child] stdout fail: {e}\n"); sys.stderr.flush()
        except Exception: pass

def _install_tqdm_bridge() -> None:
    """
    Replace tqdm with a subclass that emits stage progress, and
    patch common import paths (tqdm, tqdm.auto, tqdm.std, notebook)
    plus HuggingFace's private tqdm wrapper when present.
    """
    try:
        import tqdm as _tqdm
        Real = _tqdm.tqdm

        class ProgressTQDM(Real):  # type: ignore
            _last_emit = 0.0
            _last_pct  = -1
            def _emit(self, force: bool=False):
                try:
                    total = getattr(self, "total", None)
                    n     = getattr(self, "n", None)
                    if not total or total <= 0 or n is None:
                        return
                    pct = int(min(100, max(0, round((n/total)*100))))
                    now = time.time()
                    if force or (pct != self._last_pct and (now - self._last_emit) >= 0.15):
                        # use current dynamic stage
                        send({"type":"progress","stage":_CURRENT_TQDM_STAGE,"pct":pct})
                        self._last_pct = pct
                        self._last_emit = now
                except Exception:
                    pass
            def update(self, n=1):
                r = super().update(n)
                self._emit(False)
                return r
            def close(self, *a, **k):  # ensure last tick
                try: self._emit(True)
                finally: return super().close(*a, **k)

        # Global swap for common entry points
        _tqdm.tqdm = ProgressTQDM

        # Also patch tqdm.auto / tqdm.std / tqdm.notebook
        try:
            import tqdm.auto as _tqdm_auto
            _tqdm_auto.tqdm = ProgressTQDM
        except Exception:
            pass
        try:
            import tqdm.std as _tqdm_std
            _tqdm_std.tqdm = ProgressTQDM
        except Exception:
            pass
        try:
            import tqdm.notebook as _tqdm_nb
            _tqdm_nb.tqdm = ProgressTQDM
        except Exception:
            pass

        # Patch specific modules that do "from tqdm import tqdm"
        for modname in (
            "audio_separator.separator.architectures.mdx_separator",
            "audio_separator.separator.common_separator",
            "audio_separator.common_separator",
        ):
            try:
                m = importlib.import_module(modname)
                try:
                    setattr(m, "tqdm", ProgressTQDM)
                except Exception:
                    pass
            except Exception:
                pass

        # If HuggingFace hub re-exports tqdm via a private path, patch that too
        try:
            hh = importlib.import_module("huggingface_hub.utils._tqdm.auto")
            try:
                setattr(hh, "tqdm", ProgressTQDM)
            except Exception:
                pass
        except Exception:
            pass

        sys.stderr.write("[SEP DEBUG][child] tqdm bridge installed\n"); sys.stderr.flush()
    except Exception as e:
        sys.stderr.write(f"[SEP DEBUG][child] tqdm bridge skipped: {e}\n"); sys.stderr.flush()

def main() -> int:
    line = sys.stdin.readline()
    if not line:
        send({"type":"error","where":"separate","msg":"no payload"}); return 2
    try:
        p = json.loads(line)
    except Exception as e:
        send({"type":"error","where":"separate","msg":f"bad payload: {e}"}); return 2

    try:
        if not bool(p.get("use_gpu", False)):
            os.environ.setdefault("CUDA_VISIBLE_DEVICES","-1")
            os.environ.setdefault("AUDIO_SEPARATOR_BACKEND","onnx")
            os.environ.setdefault("UVR_BACKEND","onnx")

        input_path  = p["input_path"]
        output_dir  = p["output_dir"]
        model_dir   = p["model_file_dir"]
        model_fname = p["model_filename"]
        out_fmt     = (p.get("output_format") or "wav").upper()

        if not os.path.isfile(input_path):
            send({"type":"error","where":"separate","msg":"找不到輸入檔案"}); return 3
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

        try:
            from audio_separator.separator import Separator
        except Exception as e:
            send({"type":"error","where":"separate","msg":f"無法載入 audio-separator: {e}"}); return 4

        try:
            sep = Separator(model_file_dir=model_dir, output_dir=output_dir, output_format=out_fmt)
        except TypeError:
            sep = Separator(); sep.model_file_dir=model_dir; sep.output_dir=output_dir; sep.output_format=out_fmt

        # Install tqdm bridge *before* load_model so download progress is captured
        _install_tqdm_bridge()

        # Decide whether load_model implies a real download or just load
        model_path = os.path.join(model_dir, model_fname)
        if not os.path.exists(model_path):
            send({"type":"status","stage":STAGE_DL,"msg":"下載模型"})
            _set_tqdm_stage(STAGE_DL)
        else:
            send({"type":"status","stage":STAGE_LOAD,"msg":"載入模型"})
            _set_tqdm_stage(STAGE_LOAD)

        sys.stderr.write(f"[SEP DEBUG][child] loading {model_fname} in {model_dir}\n"); sys.stderr.flush()
        sep.load_model(model_filename=model_fname)

        # Cap loading at 100% when done
        send({"type":"progress","stage":STAGE_LOAD,"pct":100})

        # Separation progress
        _set_tqdm_stage(STAGE_SEP)
        send({"type":"status","stage":STAGE_SEP,"msg":"分離中"})
        sys.stderr.write("[SEP DEBUG][child] calling sep.separate()\n"); sys.stderr.flush()
        result = sep.separate(input_path)
        sys.stderr.write("[SEP DEBUG][child] sep.separate() returned\n"); sys.stderr.flush()
        send({"type":"progress","stage":STAGE_SEP,"pct":100})

        # Save + enumerate outputs
        send({"type":"status","stage":STAGE_SAVE,"msg":"儲存結果"})
        files_out: List[str] = []
        if isinstance(result, (list, tuple)):
            for r in result:
                pth = r if os.path.isabs(r) else os.path.join(output_dir, r)
                if os.path.exists(pth): files_out.append(os.path.abspath(pth))
        if not files_out:
            base = os.path.splitext(os.path.basename(input_path))[0].lower()
            for fn in os.listdir(output_dir):
                fp = os.path.join(output_dir, fn); low = fn.lower()
                if os.path.isfile(fp) and (base in low or any(k in low for k in ("instrumental","_inst","vocals","_vocals","伴奏","人聲"))):
                    files_out.append(os.path.abspath(fp))
            if not files_out:
                for fn in os.listdir(output_dir):
                    fp = os.path.join(output_dir, fn)
                    if os.path.isfile(fp) and fn.lower().endswith((".wav",".flac",".mp3",".m4a")):
                        files_out.append(os.path.abspath(fp))

        if not files_out:
            send({"type":"error","where":"separate","msg":"未產生任何輸出檔案"}); return 5

        send({"type":"done","files":files_out})
        send({"type":"status","stage":STAGE_READY,"msg":"就緒"})
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        sys.stderr.write(f"[SEP DEBUG][child] crash: {e}\n{tb}\n"); sys.stderr.flush()
        send({"type":"error","where":"separate","msg":str(e)})
        return 10

if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: pass