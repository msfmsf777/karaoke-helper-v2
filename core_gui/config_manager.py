# config_manager.py
import os
import json

APP_NAME = "KHelperV2"

def get_app_data_path():
    if os.name == 'nt':  # Windows
        return os.path.join(os.getenv('APPDATA'), APP_NAME)
    else:                # macOS/Linux
        return os.path.join(os.path.expanduser('~'), '.config', APP_NAME)

APP_DATA_DIR = get_app_data_path()
os.makedirs(APP_DATA_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "last_folder": None,
    "last_volume": 70,
    "last_vocal_volume": 100,
    "last_headphone": None,
    "last_virtual": None,
    "last_pitch": 0,
    "last_sample_rate": 44100,
    "normalization_enabled": False,
    "normalization_target": -14.0,
    "separator_settings": None,
    "window_size": [1280, 700],        # [width, height]
    "window_maximized": False          # True if last session ended maximized
}

def ensure_config_dir_exists():
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        return True
    except Exception:
        return False

def load_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                if isinstance(c, dict):
                    cfg.update(c)
                return cfg
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)
    except Exception as e:
        print(f"[config_manager] 無法儲存設定: {e}")

# --- small helpers for window prefs ---

def get_window_prefs(cfg: dict):
    """Return ((w, h), maximized_bool) with sane fallbacks."""
    try:
        sz = cfg.get("window_size") or [1280, 700]
        w = int(sz[0]); h = int(sz[1])
        w = max(800, min(3840, w))
        h = max(600, min(2160, h))
    except Exception:
        w, h = 1280, 700
    return (w, h), bool(cfg.get("window_maximized", False))


def set_window_prefs(cfg: dict, size_tuple, is_maximized: bool):
    """Mutate cfg in-place with the new size/maximized state."""
    try:
        w, h = int(size_tuple[0]), int(size_tuple[1])
    except Exception:
        return
    cfg["window_size"] = [w, h]
    cfg["window_maximized"] = bool(is_maximized)

