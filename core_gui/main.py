import FreeSimpleGUI as sg
import threading
import time
import os
import json
import subprocess
import sys
import webbrowser
import urllib.request
import urllib.error
from ui_layout import layout, TooltipManager, CUSTOM_FONT_NAME
from audio_player import AudioPlayer
from file_explorer import FileExplorer
from vocal_separator import SidecarClient  # [Sidecar] new transport-only client
import config_manager


# --------- NEW: Sidecar path & model defaults (no extra deps) ----------------
APPDATA_DIR = os.environ.get("APPDATA") or os.path.expanduser("~")
MODELS_DIR = os.path.join(APPDATA_DIR, "KHelperV2", "models")  # default model folder used by sidecar

DEFAULT_SEPARATOR_SETTINGS = {
    "model_filename": "UVR-MDX-NET-Inst_HQ_5.onnx",
    "output_format": "wav",
    "use_gpu": False,
    "save_to_explorer": True,
    "output_dir": os.path.expanduser("~"),
    "sample_rate": 44100,
    "mdx_params": {
        "hop_length": 1024,
        "segment_size": 256,
        "overlap": 0.25,
        "batch_size": 1,
    },
}


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def format_stage_message(stage: str) -> str:
    # <-- CHANGED: Separation maps to 分離中 (not 分離)
    mapping = {
        "Preparing": "準備中",
        "DownloadingModel": "下載模型",
        "LoadingModel": "載入模型",
        "Separation": "分離中",
        "Finalize": "完成處理",
    }
    return mapping.get(stage, stage)


def translate_friendly_name(friendly: str) -> str:
    if not friendly:
        return friendly
    return friendly.replace("recommended", "推薦").replace("Recommended", "推薦")


def truncate_text(text: str, max_len: int) -> str:
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text


def open_folder_in_explorer(path):
    if not path or not os.path.isdir(path):
        sg.popup_error("請先選擇一個有效的資料夾。", title="錯誤")
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":  # macOS
            subprocess.call(["open", path])
        else:  # Linux
            subprocess.call(["xdg-open", path])
    except Exception as e:
        sg.popup_error(f"無法打開資料夾: {e}", title="錯誤")


# ---------- NEW: sidecar resolver & splash-time preload ----------------------
def _resolve_bundled_sidecar_python() -> str:
    """Prefer bundled venv next to EXE; else return empty string."""
    app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(app_dir, "sidecar_venv", "Scripts", "python.exe")
    return cand if os.path.isfile(cand) else ""


def _resolve_bundled_service_py() -> str:
    """Find sidecar/service.py next to EXE (copied via PyInstaller datas)."""
    app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, "sidecar", "service.py")


def _map_ch_stage_to_token(ch_stage: str) -> str:
    """Map sidecar's zh-TW stage label to our existing token used by format_stage_message()."""
    if ch_stage == "下載模型":
        return "DownloadingModel"
    if ch_stage == "載入模型":
        return "LoadingModel"
    if ch_stage == "分離中":
        return "Separation"
    if ch_stage == "儲存結果":
        return "Finalize"
    # treat idle/others as finalize/ready step
    return "Finalize"


def _normalize_stage(stage_in: str) -> str:
    """
    Accept either normalized tokens (DownloadingModel/LoadingModel/Separation/Finalize)
    or zh-TW labels from the sidecar; return the normalized token.
    """
    if stage_in in ("DownloadingModel", "LoadingModel", "Separation", "Finalize", "Preparing"):
        return stage_in
    return _map_ch_stage_to_token(stage_in)


# Stage weights used to compute a smooth overall progress bar
_STAGE_ORDER = ["DownloadingModel", "LoadingModel", "Separation", "Finalize"]
_STAGE_WEIGHTS = {
    "DownloadingModel": 0.15,
    "LoadingModel": 0.20,
    "Separation": 0.60,
    "Finalize": 0.05,
}


def _overall_from_stage(token: str, stage_pct: float) -> int:
    """Compute overall percent (0..100) from current stage token + stage percent."""
    stage_pct = max(0.0, min(100.0, float(stage_pct)))
    # sum of completed weights before this stage
    total_before = 0.0
    for t in _STAGE_ORDER:
        if t == token:
            break
        total_before += _STAGE_WEIGHTS.get(t, 0.0)
    # add partial
    w = _STAGE_WEIGHTS.get(token, 0.0)
    overall = (total_before + (w * (stage_pct / 100.0))) * 100.0
    return int(max(0.0, min(100.0, overall)))


def preload_resources_blocking():
    """
    Show a splash and block until:
      - sidecar starts
      - model list is fetched
      - audio output device list is fetched
    Returns: (models_list, device_info, sidecar_client)
      models_list is list[(filename, friendly_name)]
    """
    result = {"models": [], "device_info": {}, "client": None, "error": None, "gpu_info": None}
    finished = threading.Event()

    splash_icon_path = resource_path(os.path.join("assets", "splash_icon.png"))
    splash_content = []
    if os.path.exists(splash_icon_path):
        splash_content.append([sg.Image(splash_icon_path)])
    splash_content.append([sg.Text("加載中", key='-SPLASH_TEXT-')])
    splash_layout = [[sg.VPush()],
                     [sg.Column(splash_content, element_justification='center')],
                     [sg.VPush()]]
    splash = sg.Window("Loading", splash_layout, no_titlebar=True, finalize=True, keep_on_top=True)

    def _worker():
        try:
            # Start sidecar
            interp = _resolve_bundled_sidecar_python()
            svc = _resolve_bundled_service_py()
            if not interp or not os.path.isfile(interp):
                raise RuntimeError("找不到 sidecar Python (請確認已隨附 sidecar_venv/)")
            if not os.path.isfile(svc):
                raise RuntimeError("找不到 sidecar 服務腳本 (sidecar/service.py)")

            client = SidecarClient(interpreter_path=interp, service_path=svc)
            client.on_gpu_info = lambda info: result.__setitem__("gpu_info", info)
            # NEW: fail fast if sidecar reports a problem instead of models
            preload_err = {"msg": None}
            def _preload_on_error(where, msg):
                # catch startup/list_models/general errors
                if str(where) in ("startup", "list_models", "general"):
                    preload_err["msg"] = f"{where}: {msg}"
            client.on_error = _preload_on_error
            # Fetch models (synchronous)
            try:
                models = client.list_models(timeout=60.0)  # shorter, snappier
            except Exception:
                # quick one-time restart in case the first process died noisily
                try:
                    client.close()
                except Exception:
                    pass
                client = SidecarClient(interpreter_path=interp, service_path=svc)
                client.on_error = _preload_on_error
                models = client.list_models(timeout=60.0)

            if preload_err["msg"]:
                raise RuntimeError(f"模型清單載入失敗：{preload_err['msg']}")
            # Convert to list[(filename, friendly)]
            pairs = []
            for m in models or []:
                fname = m.get("filename") or ""
                # prefer 'name' then fallback to filename
                friendly = (m.get("name") or m.get("Name") or fname or "").strip()
                # small zh tweak
                friendly = translate_friendly_name(friendly)
                pairs.append((fname, friendly))
            result["models"] = pairs

            # Query audio devices
            try:
                from sounddevice import query_devices
                devices = query_devices()
                output_devices = {i: d for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0}
                result["device_info"] = output_devices
            except Exception:
                result["device_info"] = {}

            result["client"] = client
        except Exception as e:
            result["error"] = str(e)
        finally:
            finished.set()

    threading.Thread(target=_worker, daemon=True).start()

    dots = 0
    while True:
        ev, _ = splash.read(timeout=200)
        if finished.is_set():
            break
        dots = (dots + 1) % 4
        try:
            splash['-SPLASH_TEXT-'].update("加載中" + "." * dots)
        except Exception:
            pass

    splash.close()

    if result["error"]:
        sg.popup_error(f"啟動失敗：{result['error']}", title="錯誤")
        sys.exit(1)

    return result["models"], result["device_info"], result["client"], result["gpu_info"]
# ----------------------------------------------------------------------------


def main():
    # Hardcoded application version
    APP_VERSION = "2.0.0"

    # Where to check for version info (per your instruction). The checker will attempt to
    # load the raw content if a GitHub blob url is provided.
    VERSION_CHECK_URL = "https://github.com/msfmsf777/karaoke-helper-v2/blob/main/version.json"

    def _make_raw_if_github_blob(url: str) -> str:
        # If user passed a github.com blob url, convert to raw.githubusercontent.com
        try:
            if "github.com" in url and "/blob/" in url:
                parts = url.split("github.com/")[-1]
                before_blob, after_blob = parts.split("/blob/", 1)
                raw = f"https://raw.githubusercontent.com/{before_blob}/{after_blob}"
                return raw
        except Exception:
            pass
        return url

    # [Sidecar] Splash-load models + audio devices + start sidecar
    model_list_cache_startup, device_info_pre, sidecar_client, gpu_info_pre = preload_resources_blocking()

    app_icon_path = resource_path(os.path.join("assets", "icon.ico"))
    window_icon = app_icon_path if os.path.exists(app_icon_path) else None

    # Build a menu row and prepend it to the existing layout.
    # Added "檢查更新" at the top of the 幫助 menu as requested.
    menu_def = [['幫助', ['檢查更新', '使用教程', '回報問題/建議', '---', '關於']]]

    # create a new layout that places the menu on top
    layout_with_menu = [[sg.Menu(menu_def)]] + layout

    app_config = config_manager.load_config()

    # create the window resizable and with saved size
    (win_w, win_h), was_max = config_manager.get_window_prefs(app_config)
    window = sg.Window(
        "白芙妮的伴唱小幫手 v2",
        layout_with_menu,
        icon=window_icon,
        finalize=True,
        resizable=True,
        size=(win_w, win_h)
    )

    # if it was maximized last time, maximize now
    try:
        if was_max:
            try:
                window.maximize()                 # FreeSimpleGUI / PySimpleGUI method
            except Exception:
                window.TKroot.state('zoomed')     # Tk fallback
    except Exception:
        pass

    # ---- NEW: cache last non-maximized size + state safely ----
    last_normal_size = (win_w, win_h)
    last_state = 'normal'

    def _on_configure(event=None):
        nonlocal last_normal_size, last_state
        try:
            root = window.TKroot
            if not root or not root.winfo_exists():
                return
            st = root.state()
            last_state = st
            if st != 'zoomed':
                w = root.winfo_width()
                h = root.winfo_height()
                if w > 0 and h > 0:
                    last_normal_size = (w, h)
        except Exception:
            # Swallow transient errors from child toplevels being destroyed
            pass

    try:
        window.TKroot.bind('<Configure>', _on_configure)
    except Exception:
        pass


    # Ensure total progress is initialized (stable layout).
    try:
        window['-SEP_TOTAL_PROGRESS-'].update(0)
        window['-SEP_TOTAL_PERCENT-'].update("")
    except Exception:
        pass

    player = AudioPlayer(window, debug=True)
    explorer = FileExplorer()
    listbox_items = []

    # device id map
    device_map = {}

    # --- GPU status helpers -------------------------------------------------
    GPU_STATUS_KEYS = ['-SEP_GPU_STATUS-', '-GPU_STATUS-', '-SEP_GPU_LABEL-', '-SEP_GPU-']
    GPU_COLORS = {
        'checking': '#e0e0e0',
        'enabled':  '#b7f0c4',
        'disabled': '#ffd8a8',
        'unavail':  '#ffb3b3'
    }

    def update_gpu_status_display(text: str, style_key: str):
        color = GPU_COLORS.get(style_key, '#e0e0e0')
        for k in GPU_STATUS_KEYS:
            try:
                if k in window.AllKeysDict:
                    window[k].update(text, background_color=color, text_color='black')
            except Exception:
                pass

    # -----------------------------------------------------------------------

    def change_directory(new_folder):
        if not new_folder or not os.path.isdir(new_folder):
            return
        explorer.set_current_folder(new_folder)
        window['-FOLDER_PATH-'].update(truncate_text(new_folder, 45))
        window['-BACK-'].update(disabled=(os.path.dirname(new_folder) == new_folder))
        populate_listbox()
        window['-INSTRUMENTAL_DISPLAY-'].update("(尚未選擇)")
        window['-VOCAL_DISPLAY-'].update("(尚未選擇)")
        handle_input_change()
        app_config['last_folder'] = new_folder
        config_manager.save_config(app_config)

    def populate_listbox():
        nonlocal listbox_items
        listbox_items.clear()
        subdirs, files = explorer.scan_folder(explorer.current_folder)
        for d in subdirs:
            listbox_items.append(f"[資料夾] {d}")
        for f in files:
            listbox_items.append(f)
        try:
            window['-FILE_LIST-'].update(values=listbox_items)
        except Exception:
            pass
        colorize_listbox()

    def colorize_listbox():
        listbox_widget = window['-FILE_LIST-'].Widget
        for i, item_text in enumerate(listbox_items):
            try:
                listbox_widget.itemconfig(i, bg='white', fg='black')
                if item_text.startswith("[資料夾]"):
                    listbox_widget.itemconfig(i, fg='#b28330')
                elif item_text == explorer.instrumental_selection_name:
                    listbox_widget.itemconfig(i, bg='#a8d8ea')
                elif item_text == explorer.vocal_selection_name:
                    listbox_widget.itemconfig(i, bg='#f3c9d8')
            except Exception:
                pass

    def handle_input_change():
        if player.audio_loaded:
            player.mark_needs_reload()
            try:
                window['-LOAD-'].update(disabled=False)
            except Exception:
                pass

    listbox_widget = window['-FILE_LIST-'].Widget
    last_hover_index = None
    BASE_COLORS = {'instrumental': '#a8d8ea', 'vocal': '#f3c9d8', 'folder': 'white', 'default': 'white'}
    HOVER_COLORS = {'instrumental': '#cce8f4', 'vocal': '#fae3ea', 'folder': '#e0e0e0', 'default': '#e0e0e0'}

    def get_item_selection_type(index):
        if 0 <= index < len(listbox_items):
            item_text = listbox_items[index]
            if item_text.startswith("[資料夾]"): return 'folder'
            if item_text == explorer.instrumental_selection_name: return 'instrumental'
            if item_text == explorer.vocal_selection_name: return 'vocal'
        return 'default'

    listbox_widget.configure(selectborderwidth=0, activestyle='none', exportselection=0)

    def motion_handler(event):
        nonlocal last_hover_index
        try:
            if player.playing or separating:
                return "break"
            potential_index = listbox_widget.index(f"@{event.x},{event.y}")
            bbox = listbox_widget.bbox(potential_index)
            current_index = potential_index if bbox and (bbox[1] <= event.y < bbox[1] + bbox[3]) else None
        except Exception:
            current_index = None
        if current_index is None:
            if last_hover_index is not None: leave_handler(None)
            return
        if current_index != last_hover_index:
            if last_hover_index is not None:
                selection_type = get_item_selection_type(last_hover_index)
                base_color = BASE_COLORS[selection_type]
                try:
                    listbox_widget.itemconfig(last_hover_index, bg=base_color)
                except Exception:
                    pass
            selection_type = get_item_selection_type(current_index)
            hover_color = HOVER_COLORS[selection_type]
            try:
                listbox_widget.itemconfig(current_index, bg=hover_color)
            except Exception:
                pass
            last_hover_index = current_index

    def leave_handler(event):
        nonlocal last_hover_index
        if last_hover_index is not None:
            selection_type = get_item_selection_type(last_hover_index)
            base_color = BASE_COLORS[selection_type]
            try:
                listbox_widget.itemconfig(last_hover_index, bg=base_color)
            except Exception:
                pass
        last_hover_index = None

    def right_click_handler(event):
        try:
            if player.playing or separating:
                return "break"
            clicked_index = listbox_widget.index(f"@{event.x},{event.y}")
            bbox = listbox_widget.bbox(clicked_index)
            if bbox and (bbox[1] <= event.y < bbox[1] + bbox[3]) and 0 <= clicked_index < len(listbox_items):
                window.write_event_value('-RIGHT_CLICK-', clicked_index)
        except Exception:
            pass
        return "break"

    def left_click_handler(event):
        try:
            if player.playing or separating:
                return "break"
            clicked_index = listbox_widget.index(f"@{event.x},{event.y}")
            bbox = listbox_widget.bbox(clicked_index)
            if bbox and (bbox[1] <= event.y < bbox[1] + bbox[3]) and 0 <= clicked_index < len(listbox_items):
                window.write_event_value('-LEFT_CLICK-', clicked_index)
            else:
                listbox_widget.selection_clear(0, 'end')
                colorize_listbox()
        except Exception:
            pass
        return "break"

    listbox_widget.bind('<Motion>', motion_handler)
    listbox_widget.bind('<Leave>', leave_handler)
    listbox_widget.bind('<Button-3>', right_click_handler)
    listbox_widget.bind('<Button-1>', left_click_handler)

    main_tooltip_manager = TooltipManager(window)
    main_tooltip_manager.bind(window['-INFO1-'].Widget, '這是您自己會聽到的輸出，該軌道會輸出伴奏和人聲。請確認選擇的兩個輸出設備取樣率相同。')
    main_tooltip_manager.bind(window['-INFO2-'].Widget, '這是直播軟體(如OBS)應擷取的輸出，通常是一個虛擬音源線(例如VB-CABLE)。該軌道僅輸出伴奏。')
    main_tooltip_manager.bind(window['-LUFS_INFO-'].Widget, 'LUFS (Loudness Units Full Scale) 是一種測量音訊感知響度的國際標準。\n啟用此功能會自動將音訊的整體音量調整到所選的目標值，確保在不同歌曲之間有一致的聽感，特別適用於直播。')
    try:
        main_tooltip_manager.bind(window['-EXPLORER_INFO-'].Widget,
            '檔案總管只顯示常見音訊格式（例如 wav, mp3, flac, m4a, aac, ogg, opus, wma）。某些編碼或損壞的檔案可能無法顯示。')
    except Exception:
        pass
    try:
        main_tooltip_manager.bind(window['-PLAYER_INFO-'].Widget,
            '為獲得最佳品質，請確保伴奏與人聲檔案的采樣率/長度相符，且兩檔案已對齊（同步）。')
    except Exception:
        pass
    try:
        if '-SEP_GPU_STATUS-' in window.AllKeysDict:
            main_tooltip_manager.bind(window['-SEP_GPU_STATUS-'].Widget, 'GPU（圖形處理器）加速可加快人聲分離模型運算；若系統支援並在設定中啓用，將使用GPU。\n若GPU未啓用或無法使用，程式會改用CPU執行，但速度會較慢。')
    except Exception:
        pass

    window['-BACK-'].update(disabled=True)
    if app_config.get('last_folder') and os.path.isdir(app_config['last_folder']):
        change_directory(app_config['last_folder'])
    else:
        window['-FOLDER_PATH-'].update("(尚未選擇資料夾)")

    # Load last used audio settings
    window['-INST_VOLUME-'].update(value=app_config.get('last_volume', 70))
    player.instrumental_volume = app_config.get('last_volume', 70) / 100.0
    window['-VOCAL_VOLUME-'].update(value=app_config.get('last_vocal_volume', 100))
    player.vocal_volume = app_config.get('last_vocal_volume', 100) / 100.0
    window['-PITCH_SLIDER-'].update(value=app_config.get('last_pitch', 0))
    window['-SAMPLE_RATE-'].update(value=app_config.get('last_sample_rate', 44100))

    normalization_enabled = app_config.get('normalization_enabled', False)
    window['-NORMALIZE-'].update(value=normalization_enabled)
    window['-NORMALIZE_TARGET-'].update(disabled=not normalization_enabled)

    norm_target = app_config.get('normalization_target', -14.0)
    norm_target_display = f"{norm_target:.1f}"
    for item in window['-NORMALIZE_TARGET-'].Values:
        if item.startswith(norm_target_display):
            norm_target_display = item
            break
    window['-NORMALIZE_TARGET-'].update(value=norm_target_display)

    sep_worker = None  # kept for minimal changes; now refers to sidecar_client when used
    separating = False
    sep_out_dir = None
    last_overall_display = 0   # [MONO] total progress will never go backwards

    set_msg_expire_at = 0
    device_scan_msg_expire_at = 0
    model_list_cache = model_list_cache_startup  # from splash

    def update_device_list(device_info):
        nonlocal device_map
        device_map.clear()
        device_display_list = []
        if device_info:
            for dev_id, info in device_info.items():
                name = truncate_text(info['name'], 30)
                sr = int(info.get('default_samplerate', 44100))
                display_name = f"{name} ({sr} Hz)"
                device_display_list.append(display_name)
                device_map[display_name] = dev_id

        if device_display_list:
            last_hp_name = app_config.get('last_headphone')
            last_vp_name = app_config.get('last_virtual')

            sel_hp = last_hp_name if last_hp_name in device_display_list else device_display_list[0]
            sel_vp = last_vp_name if last_vp_name in device_display_list else (device_display_list[1] if len(device_display_list) > 1 else device_display_list[0])

            window['-HEADPHONE-'].update(values=device_display_list, value=sel_hp)
            window['-VIRTUAL-'].update(values=device_display_list, value=sel_vp)

            try:
                hp_id = device_map.get(sel_hp)
                vp_id = device_map.get(sel_vp)
                player.headphone_device_id = hp_id
                player.virtual_device_id = vp_id
                player._dbg(f"Device selection applied during list update: headphone={sel_hp} (id={hp_id}), virtual={sel_vp} (id={vp_id})")
            except Exception as e:
                player._dbg(f"Failed to apply device selection during update_device_list: {e}")
        else:
            window['-HEADPHONE-'].update(values=["找不到設備"], value="找不到設備")
            window['-VIRTUAL-'].update(values=["找不到設備"], value="找不到設備")

    update_device_list(device_info_pre)

    def scan_for_audio_devices_async():
        window['-REFRESH_DEVICES-'].update(disabled=True)
        window['-DEVICE_SCAN_STATUS-'].update("掃描中...", text_color=sg.theme_text_color())
        def _worker():
            try:
                from sounddevice import query_devices
                devices = query_devices()
                output_devices = {i: d for i, d in enumerate(devices) if d['max_output_channels'] > 0}
                window.write_event_value('-DEVICE_SCAN_COMPLETE-', output_devices)
            except Exception as e:
                window.write_event_value('-DEVICE_SCAN_COMPLETE-', {'error': str(e)})
        threading.Thread(target=_worker, daemon=True).start()

    # -------------- Settings modal (now config-based; no vocal_separator refs) -----------
    def open_separator_settings_modal(default_folder=None):
        settings = app_config.get("separator_settings") or {}
        # defaults
        for k, v in DEFAULT_SEPARATOR_SETTINGS.items():
            settings.setdefault(k, v if not isinstance(v, dict) else dict(v))
        mdx = settings.get("mdx_params", {})
        for k, v in DEFAULT_SEPARATOR_SETTINGS["mdx_params"].items():
            mdx.setdefault(k, v)
        settings["mdx_params"] = mdx
        settings.setdefault("save_to_explorer", True if app_config.get("last_folder") else False)
        settings.setdefault("output_dir", default_folder or app_config.get("last_folder") or os.path.expanduser("~"))

        # Build model dropdown values (from preloaded cache)
        available_model = model_list_cache or []
        model_choices = []
        label_to_filename = {}
        seen_filenames = set()

        for filename, friendly in available_model:
            if filename in seen_filenames:
                continue
            seen_filenames.add(filename)
            fr = friendly.replace(" (recommended)", "").replace("(recommended)", "").replace("（推薦）", "").strip()
            # add a badge heuristically if friendly already contained "推薦" / "recommended"
            is_rec = ("推薦" in friendly) or ("recommended" in friendly.lower())
            label = f"{fr} ★ 推薦" if is_rec else fr
            model_choices.append(label)
            label_to_filename[label] = filename

        saved_model_filename = settings.get("model_filename")
        default_model_selection = model_choices[0] if model_choices else ""
        if saved_model_filename and model_choices:
            for lbl, fname in label_to_filename.items():
                if fname == saved_model_filename:
                    default_model_selection = lbl
                    break

        hop_options = ["256", "512", "1024", "2048", "4096"]
        seg_options = ["64","128", "256", "512", "1024", "2048", "4096"]
        overlap_options = ["0.25", "0.5",  "0.75", "0.875", "0.99"]
        batch_options = ["1", "2", "4", "8", "16", "32"]

        mdx_params_layout = []
        mdx_param_defs = [
            ('hop_length', 'hop_length (分析窗移動)', hop_options, 1024),
            ('segment_size', 'segment_size (分段長度)', seg_options, 256),
            ('overlap', 'overlap (重疊比例)', overlap_options, 0.25),
            ('batch_size', 'batch_size (批次大小)', batch_options, 1)
        ]

        for key, label, options, default in mdx_param_defs:
            current_val = str(mdx.get(key, default))
            if current_val not in options:
                options.insert(0, current_val)
            mdx_params_layout.append([
                sg.Text(label), sg.Text('ⓘ', key=f'-S_{key.upper()}_INFO-'),
                sg.Combo(options, key=f'-S_{key.upper()}_CMB-', default_value=current_val, size=(10, 1)),
                sg.Text(f"(默認: {default})")
            ])

        output_dir_val = settings.get("output_dir", "")
        is_default_dir = (output_dir_val == os.path.expanduser("~"))
        display_dir = "(請選擇資料夾)" if is_default_dir else output_dir_val

        layout_settings = [
            [sg.Push(), sg.Text("人聲分離器設定", font=("Helvetica", 16)), sg.Push()],
            [sg.Text("模型:"),
             sg.Combo(model_choices, key="-S_MODEL-", size=(48,1), default_value=default_model_selection),
             sg.Button("打開模型資料夾", key="-OPEN_MODEL_FOLDER-", size=(12,1))],
            [sg.Text("輸出格式:"), sg.Combo(["wav","flac","mp3","m4a"], key="-S_FMT-", default_value=settings.get("output_format","wav"))],
            [sg.Checkbox("啓用GPU加速 (若可用)", key="-S_GPU-", default=settings.get("use_gpu", False))],
            [sg.Frame("MDX 模型參數（進階）", mdx_params_layout, expand_x=True)],
            [sg.Checkbox("將分離檔案儲存到檔案總管選取的資料夾", key="-S_SAVE_TO_EXPLORER-", default=settings.get("save_to_explorer", True), enable_events=True)],
            [sg.Text("輸出資料夾:"), sg.Input(display_dir, key="-S_OUTDIR-", expand_x=True, text_color='grey' if is_default_dir else sg.theme_input_text_color()), sg.FolderBrowse("選擇資料夾", key="-S_BROWSE-")],
            [sg.Button("儲存設定", key="-S_SAVE-"), sg.Button("關閉", key="-S_CANCEL-")]
        ]

        win = sg.Window("分離器設定", layout_settings, modal=True, finalize=True, icon=window_icon)
        modal_tooltip_manager = TooltipManager(win)

        win['-S_OUTDIR-'].bind('<FocusIn>', '+FOCUS_IN')

        modal_tooltip_manager.bind(win['-S_HOP_LENGTH_INFO-'].Widget, "hop_length：分析窗移動的樣本數。\n數值越大，計算量越少，但時間解析度會下降。")
        modal_tooltip_manager.bind(win['-S_SEGMENT_SIZE_INFO-'].Widget, "segment_size：模型一次處理的音訊片段長度。\n數值越大，處理更穩定，但記憶體需求更高。")
        modal_tooltip_manager.bind(win['-S_OVERLAP_INFO-'].Widget, "overlap：分段之間的重疊比例 (0.0–0.99)。\n數值越高可減少拼接痕跡，但處理速度會變慢。")
        modal_tooltip_manager.bind(win['-S_BATCH_SIZE_INFO-'].Widget, "batch_size：每次送進模型處理的片段數。\n數值越大可加快速度，但需要更多記憯體。")
        try:
            modal_tooltip_manager.bind(win['-S_GPU-'].Widget, "啓用GPU（圖形處理器）加速可提升人聲分離速度。若系統無GPU或不可用，則此選項無效。")
        except Exception:
            pass

        if settings.get("save_to_explorer"):
            win['-S_OUTDIR-'].update(disabled=True)
            win['-S_BROWSE-'].update(disabled=True)

        result = None
        try:
            while True:
                ev, vals = win.read()
                if ev in (sg.WIN_CLOSED, "-S_CANCEL-"):
                    break

                if ev == '-S_OUTDIR-+FOCUS_IN' and vals['-S_OUTDIR-'] == "(請選擇資料夾)":
                    win['-S_OUTDIR-'].update("", text_color=sg.theme_input_text_color())

                if ev == "-OPEN_MODEL_FOLDER-":
                    try:
                        os.makedirs(MODELS_DIR, exist_ok=True)
                        open_folder_in_explorer(MODELS_DIR)
                    except Exception as e:
                        show_error_dialog("無法打開模型資料夾", str(e), "")

                if ev == "-S_SAVE-":
                    model_sel = vals["-S_MODEL-"]
                    # map label back to filename
                    mf = model_sel
                    for lbl, fn in label_to_filename.items():
                        if lbl == model_sel:
                            mf = fn
                            break

                    settings["model_filename"] = mf
                    settings["output_format"] = vals["-S_FMT-"]
                    settings["use_gpu"] = vals["-S_GPU-"]
                    settings["save_to_explorer"] = vals["-S_SAVE_TO_EXPLORER-"]

                    outdir = vals["-S_OUTDIR-"]
                    if not outdir or outdir == "(請選擇資料夾)":
                        outdir = default_folder or app_config.get("last_folder") or os.path.expanduser("~")
                    settings["output_dir"] = outdir

                    settings["mdx_params"] = {
                        "hop_length": int(vals["-S_HOP_LENGTH_CMB-"]), "segment_size": int(vals["-S_SEGMENT_SIZE_CMB-"]),
                        "overlap": float(vals["-S_OVERLAP_CMB-"]), "batch_size": int(vals["-S_BATCH_SIZE_CMB-"])
                    }

                    app_config['separator_settings'] = settings
                    config_manager.save_config(app_config)
                    show_setting_message("設定已儲存", 2.0, color="lightgreen")
                    # [GPU] Show “checking…” until sidecar reports, then forward sidecar gpu_info → GUI event
                    update_gpu_status_display("GPU加速檢測中", 'checking')
                    try:
                        if sidecar_client:
                            # --- Refresh GPU label after settings saved ---
                            # Rebind the callback (in case client was recreated or window changed)
                            sidecar_client.on_gpu_info = lambda info: window.write_event_value('-SEP_GPU_INFO-', info)

                            # Flush any known capability to update the label right away
                            cached_gpu = getattr(sidecar_client, 'last_gpu_info', None)
                            if cached_gpu is not None:
                                window.write_event_value('-SEP_GPU_INFO-', cached_gpu)
                            # --- end refresh ---
                    except Exception:
                        pass

                    result = settings
                    break

                if ev == "-S_SAVE_TO_EXPLORER-":
                    win['-S_OUTDIR-'].update(disabled=vals[ev])
                    win['-S_BROWSE-'].update(disabled=vals[ev])
        finally:
            modal_tooltip_manager.close()
            win.close()

        return result

    def show_setting_message(text: str, seconds: float, color: str = "lightgreen"):
        nonlocal set_msg_expire_at
        try:
            window['-SET_MSG-'].update(text, text_color=color)
            set_msg_expire_at = time.time() + seconds
        except Exception: pass

    # (legacy shim kept for minimal change; now unused by sidecar path)
    def separator_progress_callback(payload: dict):
        try:
            window.write_event_value("-SEPARATION_PROGRESS-", payload)
        except Exception:
            pass

    pending_seek_active = False
    pending_seek_value = 0.0
    pending_seek_time = 0.0
    last_display_second = -1

    TUTORIAL_URL = "https://github.com/msfmsf777/karaoke-helper-v2/wiki/%E4%BD%BF%E7%94%A8%E6%95%99%E7%A8%8B"
    FEEDBACK_URL = "https://github.com/msfmsf777/karaoke-helper-v2/issues/new/choose"
    ABOUT_TWITTER_URL = "https://x.com/msfmsf777"

    # [GPU] Show “checking…” until sidecar reports; subscribe and ask immediately
    update_gpu_status_display("GPU加速檢測中", 'checking')
    try:
                # --- GPU status binding (main window scope) ---
        # 1) When sidecar reports GPU capability later, forward it into the GUI event loop
        sidecar_client.on_gpu_info = lambda info: window.write_event_value('-SEP_GPU_INFO-', info)

        # 2) If we already learned GPU capability during splash, deliver it now
        #    (preload_result is whatever you returned from preload_resources_blocking)
        early_gpu = None
        try:
            early_gpu = gpu_info_pre if isinstance(gpu_info_pre, dict) else None
            if early_gpu is not None:
                window.write_event_value('-SEP_GPU_INFO-', early_gpu)
        except Exception:
            pass

        # 3) Also try the client's internal cache in case the event arrived before we bound the callback
        cached_gpu = getattr(sidecar_client, 'last_gpu_info', None)

        # 4) Prefer splash value, fall back to cached value; emit once if available
        _gpu_now = early_gpu or cached_gpu
        if _gpu_now is not None:
            window.write_event_value('-SEP_GPU_INFO-', _gpu_now)
        # --- end GPU status binding ---

    except Exception:
        pass


    # ---- Consistent error dialog helper --------------------------------
    def show_error_dialog(chinese_error_name: str, error_text: str, terminal_output: str):
        try:
            full_brief = chinese_error_name or "錯誤"
            err_line = (error_text or "").strip()
            term = (terminal_output or "").strip()
            err_line_clean = err_line.replace("最近輸出", "").strip()
            if term:
                err_line_display = err_line_clean
                term_content = term
            else:
                err_line_display = ""
                term_content = err_line_clean or "(無更多輸出)"
            header_text = f"{full_brief}:"
            copy_blob = f"{header_text}\n{err_line_clean}\n\n最近輸出\n{term_content}"
            header_font = (CUSTOM_FONT_NAME, 12, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 12, "bold")
            body_font = (CUSTOM_FONT_NAME, 10) if CUSTOM_FONT_NAME else ("Helvetica", 10)
            recent_label_font = (CUSTOM_FONT_NAME, 11, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 11, "bold")
            mono_font = ("Courier", 10)
            layout_err = [
                [sg.Text(header_text, font=header_font)],
                ([sg.Text(err_line_display, font=body_font)] if err_line_display else [sg.Text("", visible=False)]),
                [sg.Text("最近輸出", font=recent_label_font)],
                [sg.Multiline(term_content, size=(95, 14), key='-ERR_TERMINAL-', disabled=True,
                              autoscroll=True, no_scrollbar=False,
                              background_color='black', text_color='white', font=mono_font)],
                [sg.Button("複製", key='-ERR_COPY-'), sg.Button("回報錯誤", key='-ERR_REPORT-', button_color=('white','firebrick')), sg.Push()]
            ]
            err_win = sg.Window("錯誤", layout_err, modal=True, finalize=True, icon=window_icon, resizable=False)
            while True:
                e, v = err_win.read(timeout=100)
                if e == sg.WIN_CLOSED:
                    break
                if e == '-ERR_COPY-':
                    try:
                        root = err_win.TKroot
                        root.clipboard_clear()
                        root.clipboard_append(copy_blob)
                        root.update()
                    except Exception:
                        try:
                            sg.popup("複製到剪貼簿可能失敗", title="提示")
                        except Exception:
                            pass
                    try:
                        err_win['-ERR_COPY-'].update("已複製", disabled=True)
                        def _reenable():
                            try:
                                err_win.write_event_value('-ERR_COPY_REENABLE-', True)
                            except Exception:
                                pass
                        threading.Timer(3.0, _reenable).start()
                    except Exception:
                        pass
                if e == '-ERR_COPY_REENABLE-':
                    try:
                        err_win['-ERR_COPY-'].update("複製", disabled=False)
                    except Exception:
                        pass
                if e == '-ERR_REPORT-':
                    try:
                        webbrowser.open_new_tab(FEEDBACK_URL)
                    except Exception as ex:
                        player._dbg(f"Failed to open feedback URL from error dialog: {ex}")
            try:
                err_win.close()
            except Exception:
                pass
        except Exception:
            try:
                sg.popup_error(f"{chinese_error_name}:\n{error_text}\n\n最近輸出\n{terminal_output}", title="錯誤")
            except Exception:
                pass
    # --------------------------------------------------------------------

    # ---- Update checker -------------------------------------------------
    def _compare_versions(v_local: str, v_remote: str) -> int:
        try:
            def parts(v):
                out = []
                for p in str(v).split('.'):
                    try:
                        out.append(int(p))
                    except Exception:
                        num = ''.join(ch for ch in p if p and ch.isdigit())
                        out.append(int(num) if num else 0)
                return out
            a = parts(v_local)
            b = parts(v_remote)
            ln = max(len(a), len(b))
            a += [0] * (ln - len(a))
            b += [0] * (ln - len(b))
            for ai, bi in zip(a, b):
                if ai < bi: return -1
                if ai > bi: return 1
            return 0
        except Exception:
            return 0

    def _check_update_worker(url: str, manual: bool):
        try:
            raw_url = _make_raw_if_github_blob(url)
            req_url = raw_url
            try:
                with urllib.request.urlopen(req_url, timeout=10) as r:
                    raw = r.read().decode('utf-8')
            except Exception as e1:
                if req_url != url:
                    try:
                        with urllib.request.urlopen(url, timeout=10) as r:
                            raw = r.read().decode('utf-8')
                    except Exception as e2:
                        raise Exception(f"無法下載版本資訊: {e1}; {e2}")
                else:
                    raise Exception(f"無法下載版本資訊: {e1}")
            try:
                data = json.loads(raw)
            except Exception as ex:
                raise Exception(f"無法解析版本資訊 JSON: {ex}")
            remote_version = data.get("version")
            if not remote_version:
                raise Exception("版本資訊格式錯誤 (缺少 version 欄位)")
            cmp = _compare_versions(APP_VERSION, remote_version)
            if cmp < 0:
                payload = {'remote': data}
                window.write_event_value('-UPDATE_AVAILABLE-', payload)
            else:
                window.write_event_value('-UPDATE_NOUPDATE-', {'manual': manual})
        except Exception as e:
            window.write_event_value('-UPDATE_ERROR-', {'error': str(e), 'manual': manual})

    def start_update_check_async(manual: bool = False):
        try:
            threading.Thread(target=_check_update_worker, args=(VERSION_CHECK_URL, manual), daemon=True).start()
        except Exception:
            pass

    def show_update_popup(remote_data: dict):
        try:
            remote_ver = remote_data.get('version', '未知')
            download_url = remote_data.get('download_url', '')
            notes = remote_data.get('notes', []) or []
            notes_text = "\n".join(notes) if isinstance(notes, (list, tuple)) else str(notes)
            header_font = (CUSTOM_FONT_NAME, 12, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 12, "bold")
            body_font = (CUSTOM_FONT_NAME, 10) if CUSTOM_FONT_NAME else ("Helvetica", 10)
            layout_upd = [
                [sg.Text("檢查更新", font=header_font)],
                [sg.Text(f"您目前版本：{APP_VERSION}", font=body_font)],
                [sg.Text(f"可用新版本：{remote_ver}", font=body_font)],
                [sg.Text("更新內容：", font=body_font)],
                [sg.Multiline(notes_text, size=(80, 12), disabled=True, autoscroll=True)],
                [sg.Push(), sg.Button("前往下載", key='-GO_DOWNLOAD-'), sg.Button("稍後提醒", key='-REMIND_LATER-')]
            ]
            win = sg.Window("更新可用", layout_upd, modal=True, finalize=True, icon=window_icon, resizable=False)
            while True:
                e, v = win.read()
                if e in (sg.WIN_CLOSED, '-REMIND_LATER-'):
                    break
                if e == '-GO_DOWNLOAD-':
                    try:
                        if download_url:
                            webbrowser.open_new_tab(download_url)
                    except Exception as ex:
                        player._dbg(f"Failed to open download URL: {ex}")
                    break
            try:
                win.close()
            except Exception:
                pass
        except Exception as ex:
            sg.popup_error(f"顯示更新視窗失敗: {ex}")

    try:
        start_update_check_async(manual=False)
    except Exception:
        pass
    # ---------------------------------------------------------------------

    # --------------------------- main event loop --------------------------
    current_stage_token = "Preparing"  # track stage for progress mapping

    while True:
        event, values = window.read(timeout=50)

        if event == sg.WIN_CLOSED:
            break

        now = time.time()

        try:
            if window['-SET_MSG-'].get() and set_msg_expire_at and now >= set_msg_expire_at:
                window['-SET_MSG-'].update("")
                if not separating:
                    try:
                        window['-SEP_TOTAL_PROGRESS-'].update(0)
                        window['-SEP_TOTAL_PERCENT-'].update("")
                    except Exception:
                        pass

            if now >= device_scan_msg_expire_at:
                window['-DEVICE_SCAN_STATUS-'].update("")
        except Exception:
            pass

        if event == '-DELAYED_POPULATE-':
            try:
                populate_listbox()
            except Exception:
                pass

        # Update-related events
        if event == '檢查更新':
            start_update_check_async(manual=True)

        if event == '-UPDATE_AVAILABLE-':
            payload = values[event]
            remote = payload.get('remote', {}) if isinstance(payload, dict) else {}
            show_update_popup(remote)

        if event == '-UPDATE_NOUPDATE-':
            payload = values[event] if isinstance(values[event], dict) else {}
            if payload.get('manual'):
                try:
                    sg.popup("您目前使用的是最新版本。", title="檢查更新")
                except Exception:
                    pass

        if event == '-UPDATE_ERROR-':
            payload = values[event] if isinstance(values[event], dict) else {}
            if payload.get('manual'):
                try:
                    sg.popup_error(f"檢查更新失敗：\n\n{payload.get('error', '未知錯誤')}", title="更新檢查失敗")
                except Exception:
                    pass
            else:
                player._dbg(f"Background update check error: {payload.get('error')}")

        # Menu handlers
        if event == '使用教程':
            try:
                webbrowser.open_new_tab(TUTORIAL_URL)
            except Exception as e:
                player._dbg(f"Failed to open tutorial URL: {e}")
        if event == '回報問題/建議':
            try:
                webbrowser.open_new_tab(FEEDBACK_URL)
            except Exception as e:
                player._dbg(f"Failed to open feedback URL: {e}")
        if event == '關於':
            about_img = resource_path(os.path.join("assets", "splash_icon.png"))
            img_elem = None
            if os.path.exists(about_img):
                img_elem = sg.Image(about_img)
            about_col = []
            if img_elem:
                about_col.append([img_elem])
            about_col.append([sg.Text("直播唱歌需要伴唱但又不想讓觀衆聽到原唱人聲？那這就是爲尼專門打造的小程式~\n本程式整合了高品質AI人聲分離、雙軌播放器、升降Key、音量標準化等多項強大功能!", size=(60, 3), justification='center')])
            about_col.append([sg.HorizontalSeparator()])
            about_col.append([
                sg.Text("窩的第一個程式可能有Bug，歡迎追隨我/回饋使用體驗~", key='-ABOUT_TX-'),
                sg.Text("  "),
                sg.Text("[推特傳送門]", key='-ABOUT_TW-', enable_events=True, tooltip='追隨窩~', text_color="#054393", justification='left')
            ])
            about_layout = [
                [sg.VPush()],
                [sg.Column(about_col, element_justification='center', vertical_alignment='center', pad=(20,10))],
                [sg.VPush()]
            ]
            about_win = sg.Window("關於", about_layout, modal=True, finalize=True, icon=window_icon, no_titlebar=False)
            try:
                while True:
                    aev, avals = about_win.read()
                    if aev == sg.WIN_CLOSED:
                        break
                    if aev == '-ABOUT_TW-':
                        try:
                            webbrowser.open_new_tab(ABOUT_TWITTER_URL)
                        except Exception as e:
                            player._dbg(f"Failed to open about twitter url: {e}")
                about_win.close()
            except Exception:
                try:
                    about_win.close()
                except Exception:
                    pass

        if event == "-PLAYER_DEBUG-":
            print("[PLAYER_DEBUG]", values[event])

        if event == "-PITCH_SHIFT_ERROR-":
            show_error_dialog("音調轉換錯誤", str(values[event]), "")

        if event in ("-FOLDER_PATH-", "-CHANGE_FOLDER-"):
            change_directory(values.get("-FOLDER_PATH-") or values.get("-CHANGE_FOLDER-"))

        if event == "-REFRESH-":
            populate_listbox()

        if event == "-BACK-":
            if explorer.current_folder:
                change_directory(os.path.dirname(explorer.current_folder))

        if event == "-OPEN_FOLDER-":
            open_folder_in_explorer(explorer.current_folder)

        if event == "-REFRESH_DEVICES-":
            scan_for_audio_devices_async()

        if event == "-DEVICE_SCAN_COMPLETE-":
            device_scan_msg_expire_at = time.time() + 2.0
            window['-REFRESH_DEVICES-'].update(disabled=False)
            new_device_info = values[event]
            if 'error' in new_device_info:
                window['-DEVICE_SCAN_STATUS-'].update("刷新失敗", text_color='red')
            else:
                window['-DEVICE_SCAN_STATUS-'].update("刷新成功", text_color='lightgreen')
                update_device_list(new_device_info)

        if event in ("-LEFT_CLICK-", "-FILE_LIST-"):
            if player.playing or separating:
                continue
            idx = values.get(event)
            if isinstance(idx, list): idx = idx[0]
            if isinstance(idx, int) and 0 <= idx < len(listbox_items):
                selected = listbox_items[idx]
                if selected.startswith("[資料夾]"):
                    change_directory(os.path.join(explorer.current_folder, selected.replace("[資料夾] ", "")))
                else:
                    explorer.set_instrumental(selected)
                    window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or "(尚未選擇)")
                    window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or "(尚未選擇)")
                    listbox_widget.selection_clear(0, 'end')
                    colorize_listbox()
                    handle_input_change()

        if event == "-RIGHT_CLICK-":
            if player.playing or separating:
                continue
            idx = values.get(event)
            if isinstance(idx, int) and 0 <= idx < len(listbox_items):
                selected = listbox_items[idx]
                if not selected.startswith("[資料夾]"):
                    explorer.set_vocal(selected)
                    window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or "(尚未選擇)")
                    window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or "(尚未選擇)")
                    listbox_widget.selection_clear(0, 'end')
                    colorize_listbox()
                    handle_input_change()

        if event == "-OPEN_SEPARATOR_SETTINGS-":
            open_separator_settings_modal(default_folder=explorer.current_folder)

        # ------------------- Start/Abort separation using sidecar -------------------
        if event == "-START_SEPARATION-":
            if not separating and not player.playing:
                chosen = app_config.get("separator_settings") or {}
                for k, v in DEFAULT_SEPARATOR_SETTINGS.items():
                    chosen.setdefault(k, v if not isinstance(v, dict) else dict(v))
                if not chosen:
                    chosen = open_separator_settings_modal(default_folder=explorer.current_folder)
                if not chosen:
                    continue

                input_file = values["-SONG_FILE-"]
                if not input_file or not os.path.exists(input_file):
                    show_error_dialog("請選擇檔案", "請先選擇要分離的歌曲檔案。", "")
                    continue

                sep_out_dir = explorer.current_folder if chosen.get("save_to_explorer", False) else (chosen.get("output_dir") or os.path.dirname(input_file))
                try:
                    os.makedirs(sep_out_dir, exist_ok=True)
                except Exception as e:
                    if sep_out_dir == None:
                        show_error_dialog("錯誤", "請選擇輸出資料夾", f"\n{e}")
                    else:
                        show_error_dialog("錯誤", "無法存取當前資料夾，請重試。", f"{sep_out_dir}\n\n{e}")
                    continue

                # GUI state
                separating = True
                window['-START_SEPARATION-'].update("終止")
                # ---- A) SHOW the total progress UI at job start ----
                window['-SEP_TOTAL_PROGRESS-'].update(0, visible=True)
                window['-SEP_TOTAL_PERCENT-'].update("0%", visible=True)
                window['-SEPARATOR_STATUS-'].update("分離中…")
                last_overall_display = 0  # [MONO] reset high-water mark on job start

                sep_worker = sidecar_client  # minimal change: keep variable name

                # Define callbacks that convert sidecar events to our UI event
                def _on_status(stage_in, msg):
                    nonlocal current_stage_token
                    token = _normalize_stage(stage_in)   # <-- CHANGED: accept zh or token safely
                    current_stage_token = token
                    overall = _overall_from_stage(token, 0)
                    window.write_event_value("-SEPARATION_PROGRESS-", {
                        "type": "progress",
                        "stage": token,
                        "stage_pct": 0,
                        "overall": overall
                    })

                def _on_progress(stage_in, pct):
                    nonlocal current_stage_token
                    token = _normalize_stage(stage_in)   # <-- CHANGED: accept zh or token safely
                    current_stage_token = token
                    overall = _overall_from_stage(token, pct)
                    window.write_event_value("-SEPARATION_PROGRESS-", {
                        "type": "progress",
                        "stage": token,
                        "stage_pct": int(pct),
                        "overall": overall
                    })

                def _on_done(files, duration_sec):
                    window.write_event_value("-SEPARATION_PROGRESS-", {
                        "type": "done",
                        "files": files,
                        "duration": duration_sec
                    })

                def _on_error(where, msg):
                    window.write_event_value("-SEPARATION_PROGRESS-", {
                        "type": "error",
                        "where": where,
                        "message": msg,
                        "terminal": ""  # no separate terminal log here
                    })

                # Start the job
                try:
                    os.makedirs(MODELS_DIR, exist_ok=True)
                    # [GPU] Forward sidecar gpu_info to GUI during this run as well
                    try:
                        sep_worker.on_gpu_info = lambda info: window.write_event_value('-SEP_GPU_INFO-', info)
                    except Exception:
                        pass
                    sep_worker.start_separation(
                        input_path=input_file,
                        output_dir=sep_out_dir,
                        model_file_dir=MODELS_DIR,
                        model_filename=chosen.get("model_filename", DEFAULT_SEPARATOR_SETTINGS["model_filename"]),
                        use_gpu=bool(chosen.get("use_gpu", False)),
                        output_format=chosen.get("output_format", "wav"),
                        on_progress=_on_progress,
                        on_status=_on_status,
                        on_done=_on_done,
                        on_error=_on_error
                    )
                except Exception as ex:
                    separating = False
                    window['-START_SEPARATION-'].update("開始分離")
                    window['-SEPARATOR_STATUS-'].update("錯誤")
                    # ensure UI returns to hidden state on failure
                    window['-SEP_TOTAL_PROGRESS-'].update(0, visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                    show_setting_message("錯誤", 3.0, color="red")
                    show_error_dialog("分離錯誤", str(ex), "")
            else:
                # Abort
                if sep_worker:
                    try:
                        sep_worker.abort()
                    except Exception:
                        pass
                separating = False
                window['-START_SEPARATION-'].update("開始分離")
                show_setting_message("已取消", 3.0, color="red")
                window['-SEPARATOR_STATUS-'].update("就緒")
                last_overall_display = 0  # [MONO] reset on user-cancel
                # ensure UI returns to hidden/cleared state on cancel from button
                window['-SEP_TOTAL_PROGRESS-'].update(0, visible=False)
                window['-SEP_TOTAL_PERCENT-'].update("", visible=False)

        # ------------------- Handle sidecar-progress UI updates ---------------------
        if event == "-SEPARATION_PROGRESS-":
            payload = values[event]
            ptype = payload.get("type")
            if ptype == "progress":
                overall_in = int(payload.get("overall", 0))
                stage = payload.get("stage", "")
                stage_pct = int(payload.get("stage_pct", payload.get("pct", 0)))

                # [MONO] clamp total progress so it never goes backwards
                overall_disp = max(overall_in, last_overall_display)
                last_overall_display = overall_disp

                # ---- Update ONLY while a job is running; ignore late/stray progress ----
                if separating:
                    try:
                        # don't flip visibility here; it's controlled at start/done/cancel
                        window['-SEP_TOTAL_PROGRESS-'].update(overall_disp)
                        window['-SEP_TOTAL_PERCENT-'].update(f"{overall_disp}%")
                    except Exception:
                        pass
                    try:
                        window['-SEPARATOR_STATUS-'].update(f"{format_stage_message(stage)} — {stage_pct}%")
                    except Exception:
                        pass


            elif ptype == "done":
                files = payload.get("files", [])
                separating = False
                window['-START_SEPARATION-'].update("開始分離")
                # ---- C) Finalize: success -> 100% then hide/clear ----
                last_overall_display = 100  # [MONO] lock high-water at completion
                try:
                    window['-SEP_TOTAL_PROGRESS-'].update(100)
                    window['-SEP_TOTAL_PERCENT-'].update("100%")
                    window['-SEP_TOTAL_PROGRESS-'].update(visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                except Exception:
                    pass
                window['-SEPARATOR_STATUS-'].update("就緒")
                populate_listbox()
                try:
                    threading.Timer(0.6, lambda: window.write_event_value('-DELAYED_POPULATE-', True)).start()
                except Exception:
                    pass

                new_inst, new_voc = None, None
                for p in files:
                    nm = os.path.basename(p)
                    low = nm.lower()
                    if "伴奏" in nm or "inst" in low or "instrumental" in low:
                        new_inst = nm
                    if "人聲" in nm or "voc" in low or "vocal" in low:
                        new_voc = nm
                if new_inst and new_inst in listbox_items:
                    explorer.set_instrumental(new_inst)
                if new_voc and new_voc in listbox_items:
                    explorer.set_vocal(new_voc)

                window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or "(尚未選擇)")
                window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or "(尚未選擇)")
                colorize_listbox()
                show_setting_message("分離完成", 3.0, color="lightgreen")

            elif ptype in ("aborted", "error"):
                separating = False
                window['-START_SEPARATION-'].update("開始分離")
                window['-SEPARATOR_STATUS-'].update("就緒" if ptype == "aborted" else "錯誤")
                # ---- C) Finalize: cancel/error -> 0% then hide/clear ----
                last_overall_display = 0  # [MONO] reset high-water on cancel/error
                try:
                    window['-SEP_TOTAL_PROGRESS-'].update(0)
                    window['-SEP_TOTAL_PERCENT-'].update("0%")
                    window['-SEP_TOTAL_PROGRESS-'].update(visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                except Exception:
                    pass
                show_setting_message("已取消" if ptype == "aborted" else "錯誤", 3.0, color="red")
                if ptype == "error":
                    err_msg = payload.get('message', '未知錯誤')
                    terminal = payload.get('terminal', '') or ''
                    show_error_dialog("分離錯誤", err_msg, terminal)
                populate_listbox()

        # [GPU] Handle sidecar GPU capability report
        if event == '-SEP_GPU_INFO-':
            info = values.get('-SEP_GPU_INFO-') or {}
            # Be defensive about types
            if not isinstance(info, dict):
                info = {}
            # Derive availability; tolerate legacy keys
            available = info.get('available')
            if available is None:
                try:
                    available = bool(
                        info.get('cuda') or info.get('torch_cuda') or
                        ('CUDAExecutionProvider' in (info.get('ort_providers') or [])) or
                        (str(info.get('ort_device', '')).lower() != 'cpu' and info.get('ort_device'))
                    )
                except Exception:
                    available = False

            # What the user wants (your current setting)
            separator_settings = app_config.get("separator_settings") or {}
            user_wants_gpu = bool(separator_settings.get("use_gpu", False))

            # Decide label text & style
            if available and user_wants_gpu:
                update_gpu_status_display("GPU加速已啓用", 'enabled')
            elif available:
                update_gpu_status_display("GPU加速已停用", 'disabled')
            else:
                update_gpu_status_display("GPU加速不可用", 'unavail')

        if event == "-LOAD-":
            normalize = values['-NORMALIZE-']
            target_lufs_str = values['-NORMALIZE_TARGET-'].split(' ')[0]
            target_lufs = float(target_lufs_str)
            player.load_audio(explorer.instrumental_path, explorer.vocal_path,
                              pitch_semitones=int(values["-PITCH_SLIDER-"]),
                              sample_rate=int(values["-SAMPLE_RATE-"]),
                              normalize=normalize,
                              target_lufs=target_lufs)

        if event == "-LOAD_PROGRESS_EVENT-":
            payload = values[event]
            prog, status_text = payload if isinstance(payload, (tuple, list)) else (payload, "加載中...")
            window['-LOAD_STATUS-'].update(status_text, text_color='white')
            window['-LOAD_PROGRESS-'].update(int(prog))

        if event == "-LOAD_DONE-":
            done_val = values[event]
            if isinstance(done_val, str) and done_val.startswith("ERROR"):
                show_error_dialog("載入錯誤", done_val, "")
                window['-LOAD_PROGRESS-'].update(0)
                window['-LOAD_STATUS-'].update("", text_color='white')
                window['-LOAD-'].update(disabled=False)
                player.audio_loaded = False
            else:
                window['-LOAD_PROGRESS-'].update(100)
                window['-LOAD_STATUS-'].update("就緒", text_color='lightgreen')
                duration = max(1.0, float(player.duration))
                window['-PROGRESS-'].update(range=(0, duration), value=0)
                window['-TIME_DISPLAY-'].update(f"00:00:00 / {player.format_time(player.duration)}")
                last_display_second = -1
                try:
                    window['-LOAD-'].update(disabled=True)
                except Exception:
                    pass

        if event == "-AUDIO_NEEDS_RELOAD-":
            player.audio_loaded = False
            window['-LOAD-'].update(disabled=False)
            window['-LOAD_PROGRESS-'].update(0)
            window['-LOAD_STATUS-'].update("", text_color='white')
            window['-PROGRESS-'].update(value=0, disabled=True)
            window['-TIME_DISPLAY-'].update("00:00:00 / 00:00:00")
            last_display_second = -1

        if event == '-PLAYBACK_ERROR-':
            show_error_dialog("播放錯誤", str(values[event]), "")

        is_busy = player.playing or separating
        window["-PLAY_PAUSE-"].update("暫停" if player.playing else "播放", disabled=not player.audio_loaded)
        for key in ['-PROGRESS-', '-REWIND-', '-FORWARD-', '-STOP-']:
            window[key].update(disabled=not player.audio_loaded)

        busy_keys = [
            '-FOLDER_PATH-','-BACK-', '-CHANGE_FOLDER-', '-REFRESH-', '-FILE_LIST-',
            '-OPEN_FOLDER-', '-SONG_FILE-', '-SONG_FILE_BROWSE-', '-HEADPHONE-', '-VIRTUAL-',
            '-PITCH_DOWN-', '-PITCH_UP-', '-PITCH_SLIDER-', '-OPEN_SEPARATOR_SETTINGS-', '-SAMPLE_RATE-',
            '-REFRESH_DEVICES-', '-NORMALIZE-', '-NORMALIZE_TARGET-'
        ]
        for key in busy_keys:
            try:
                window[key].update(disabled=is_busy)
            except Exception:
                pass

        try:
            window['-START_SEPARATION-'].update(disabled=player.playing)
        except Exception:
            pass

        if values['-NORMALIZE-']:
            window['-NORMALIZE_TARGET-'].update(disabled=is_busy)

        can_load = bool(explorer.instrumental_path and explorer.vocal_path and not is_busy and not player.audio_loaded)
        window['-LOAD-'].update(disabled=not can_load)

        if event in ("-HEADPHONE-", "-VIRTUAL-"):
            key = 'last_headphone' if event == "-HEADPHONE-" else 'last_virtual'
            app_config[key] = values[event]
            config_manager.save_config(app_config)
            handle_input_change()
            try:
                sel_name = values[event]
                if sel_name in device_map:
                    if event == "-HEADPHONE-":
                        player.headphone_device_id = device_map.get(sel_name)
                    else:
                        player.virtual_device_id = device_map.get(sel_name)
                    player._dbg(f"Device set via UI event: {event} -> {sel_name} (id={device_map.get(sel_name)})")
                else:
                    player._dbg(f"Selected device name not found in device_map: {sel_name}")
            except Exception as e:
                player._dbg(f"Error applying device selection from UI event: {e}")

        if event == "-SAMPLE_RATE-":
            app_config['last_sample_rate'] = values[event]
            config_manager.save_config(app_config)
            handle_input_change()

        if event == "-NORMALIZE-":
            window['-NORMALIZE_TARGET-'].update(disabled=not values['-NORMALIZE-'])
            app_config['normalization_enabled'] = values['-NORMALIZE-']
            config_manager.save_config(app_config)
            handle_input_change()

        if event == "-NORMALIZE_TARGET-":
            app_config['normalization_target'] = float(values['-NORMALIZE_TARGET-'].split(' ')[0])
            config_manager.save_config(app_config)
            handle_input_change()

        if event == "-INST_VOLUME-":
            vol = int(values["-INST_VOLUME-"])
            player.instrumental_volume = vol / 100.0
            app_config['last_volume'] = vol
            config_manager.save_config(app_config)

        if event == "-VOCAL_VOLUME-":
            vol = int(values["-VOCAL_VOLUME-"])
            player.vocal_volume = vol / 100.0
            app_config['last_vocal_volume'] = vol
            config_manager.save_config(app_config)

        if event in ("-PITCH_DOWN-", "-PITCH_UP-", "-PITCH_SLIDER-"):
            current_pitch = int(values["-PITCH_SLIDER-"])
            if event == "-PITCH_DOWN-": current_pitch = max(-12, current_pitch - 1)
            elif event == "-PITCH_UP-": current_pitch = min(12, current_pitch + 1)
            window["-PITCH_SLIDER-"].update(value=current_pitch)
            app_config['last_pitch'] = current_pitch
            config_manager.save_config(app_config)
            handle_input_change()

        if player.playing:
            current_second = int(player.position)
            if current_second != last_display_second:
                last_display_second = current_second
                if not pending_seek_active:
                    window["-PROGRESS-"].update(value=player.position)
                window["-TIME_DISPLAY-"].update(f"{player.format_time(player.position)} / {player.format_time(player.duration)}")

        if pending_seek_active and (now - pending_seek_time) > 0.15:
            player.seek(pending_seek_value)
            pending_seek_active = False

        if event == "-PLAY_PAUSE-":
            player.play_pause()
        if event == "-STOP-":
            player.stop_immediate()
            player.seek(0.0)
            window["-PROGRESS-"].update(value=0.0)
            window["-TIME_DISPLAY-"].update(f"00:00:00 / {player.format_time(player.duration)}")
            window["-PLAY_PAUSE-"].update("播放")

        if event == "-PLAYBACK_ENDED-":
            # Mirror the exact Stop behavior so UI resets when the track finishes naturally
            player.stop_immediate()
            player.seek(0.0)
            window['-PROGRESS-'].update(value=0)
            window['-PLAY_PAUSE-'].update("播放")
            window['-TIME_DISPLAY-'].update(f"00:00:00 / {player.format_time(player.duration)}")

        if event == "-PROGRESS-":
            val = values["-PROGRESS-"]
            window["-TIME_DISPLAY-"].update(f"{player.format_time(val)} / {player.format_time(player.duration)}")
            pending_seek_active = True
            pending_seek_value = val
            pending_seek_time = now

        if event == "-REWIND-":
            player.rewind_5sec()
            window["-PROGRESS-"].update(value=player.position)
        if event == "-FORWARD-":
            player.forward_5sec()
            window["-PROGRESS-"].update(value=player.position)

        if player.playing and player.position >= player.duration:
            player.stop_immediate()
            player.seek(0.0)
            window['-PROGRESS-'].update(value=0)
            window['-PLAY_PAUSE-'].update("播放")
            window['-TIME_DISPLAY-'].update(f"00:00:00 / {player.format_time(player.duration)}")

    # Clean shutdown
    if sep_worker:
        try:
            sep_worker.abort()
        except Exception:
            pass
    player.stop_immediate()
    main_tooltip_manager.close()
    # Save window size & maximized state WITHOUT touching Tk now
    try:
        is_zoomed = (last_state == 'zoomed')
        # If maximized, we still save the last normal size
        save_size = last_normal_size
        config_manager.set_window_prefs(app_config, save_size, is_zoomed)
        config_manager.save_config(app_config)
    except Exception as e:
        print(f"[winprefs] save failed (cached): {e}")

    window.close()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()