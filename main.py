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

from ui_layout import create_layout, TooltipManager, CUSTOM_FONT_NAME
from audio_player import AudioPlayer
from file_explorer import FileExplorer
from vocal_separator import SidecarClient, get_recommended_model
import config_manager
from i18n_helper import I18nManager


"""
Main application file with internationalization support.

This module builds the GUI, wires up events and manages the overall
application lifecycle. All user-facing text is obtained via the
I18nManager so that language can be switched at runtime. The language
menu populates from the available locales and stores the user's
selection in the configuration.
"""

# ------------------------------------------------------------------------------
# Utility functions and sidecar helpers copied from the original implementation
# The functions below are used unchanged to preserve existing behaviour.

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


def truncate_text(text: str, max_len: int) -> str:
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text


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
    return "Finalize"


def _normalize_stage(stage_in: str) -> str:
    if stage_in in ("DownloadingModel", "LoadingModel", "Separation", "Finalize", "Preparing"):
        return stage_in
    return _map_ch_stage_to_token(stage_in)


_STAGE_ORDER = ["DownloadingModel", "LoadingModel", "Separation", "Finalize"]
_STAGE_WEIGHTS = {
    "DownloadingModel": 0.15,
    "LoadingModel": 0.20,
    "Separation": 0.60,
    "Finalize": 0.05,
}


def _overall_from_stage(token: str, stage_pct: float) -> int:
    stage_pct = max(0.0, min(100.0, float(stage_pct)))
    total_before = 0.0
    for t in _STAGE_ORDER:
        if t == token:
            break
        total_before += _STAGE_WEIGHTS.get(t, 0.0)
    w = _STAGE_WEIGHTS.get(token, 0.0)
    overall = (total_before + (w * (stage_pct / 100.0))) * 100.0
    return int(max(0.0, min(100.0, overall)))


def preload_resources_blocking(t=lambda k: k):
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
    splash_content.append([sg.Text(t('splash_loading'), key='-SPLASH_TEXT-')])
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
            preload_err = {"msg": None}
            def _preload_on_error(where, msg):
                if str(where) in ("startup", "list_models", "general"):
                    preload_err["msg"] = f"{where}: {msg}"
            client.on_error = _preload_on_error
            try:
                models = client.list_models(timeout=60.0)
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass
                client = SidecarClient(interpreter_path=interp, service_path=svc)
                client.on_error = _preload_on_error
                models = client.list_models(timeout=60.0)
            if preload_err["msg"]:
                raise RuntimeError(f"模型清單載入失敗：{preload_err['msg']}")
            pairs = []
            for m in models or []:
                fname = m.get("filename") or ""
                friendly = (m.get("name") or m.get("Name") or fname or "").strip()
                pairs.append((fname, friendly))
            result["models"] = pairs
            try:
                from sounddevice import query_devices
                devices = query_devices()
                output_devices = {i: d for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0}
                result["device_info"] = output_devices
            except Exception:
                result["device_info"] = {}
            result["client"] = client
            # --- Discover locales during splash ---
            try:
                from i18n_helper import list_available_languages
                locales_dir = resource_path(os.path.join("locales"))
                result["languages"] = list_available_languages(locales_dir)
            except Exception:
                result["languages"] = []
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
            splash['-SPLASH_TEXT-'].update(t('splash_loading') + "." * dots)
        except Exception:
            pass
    splash.close()
    if result["error"]:
        sg.popup_error(f"啟動失敗：{result['error']}", title="錯誤")
        sys.exit(1)
    return result["models"], result["device_info"], result["client"], result["gpu_info"], result.get("languages", [])


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
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def main():
    # Hardcoded application version
    APP_VERSION = "2.1.0"

    # Where to check for version info (per your instruction). The checker will attempt to
    # load the raw content if a GitHub blob url is provided.
    VERSION_CHECK_URL = "https://github.com/msfmsf777/karaoke-helper-v2/blob/main/version.json"

    # Set up i18n manager
    locales_dir = resource_path('locales')
    i18n = I18nManager(locales_dir=locales_dir, default_lang='zh_TW')

    # Load application config and language preference
    app_config = config_manager.load_config()
    # ---- i18n: language menu helpers ----
    def _current_lang_from_config(app_cfg, available):
        # Preferred from config, else zh_TW if present, else en_US, else first available
        pref = (app_cfg or {}).get("language", "")
        codes = [c for c, _ in available]
        if pref in codes:
            return pref
        if "zh_TW" in codes:
            return "zh_TW"
        if "en_US" in codes:
            return "en_US"
        return codes[0] if codes else "zh_TW"

    def _build_menu_def(i18n, current_lang_code, available_langs):
        # Prefix ✓ on the active language. Use ::LANG::<code> for stable events.
        lang_title = i18n.t("menu_language")
        help_title = i18n.t("menu_help")
        items = []
        for code, name in available_langs:
            label = f"✓ {name}" if code == current_lang_code else name
            items.append(f"{label}::LANG::{code}")
        # Help items (stable event keys)
        help_items = [
            i18n.t("menu_check_updates") + '::CHECK_UPDATE',
            i18n.t("menu_tutorial")     + '::TUTORIAL',
            i18n.t("menu_feedback")     + '::FEEDBACK',
            '---',
            i18n.t("menu_about")        + '::ABOUT',
        ]
        # Language menu must come BEFORE help, per your requirement
        return [[lang_title, items], [help_title, help_items]]
    

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


    # NOTE: models/devices/sidecar_client/gpu_info_pre acquired above by splash

    # 1) Load config first to get a provisional language for the splash
    app_config = config_manager.load_config()
    provisional_lang = app_config.get('language', 'zh_TW')  # or 'en_US' if you prefer

    # 2) Initialize i18n with the provisional language so the splash can translate
    i18n = I18nManager(locales_dir=resource_path(os.path.join("locales")), default_lang=provisional_lang)

    # 3) Run splash (can use i18n.t for "Loading...")
    model_list_cache_startup, device_info_pre, sidecar_client, gpu_info_pre, langs_from_splash = preload_resources_blocking(i18n.t)

    # 4) Decide the final language now that we know what's available, then apply if different
    current_lang_code = _current_lang_from_config(app_config, langs_from_splash)
    if current_lang_code != i18n.lang:
        i18n.set_language(current_lang_code)

    # Build UI layout with translations
    from ui_layout import create_layout
    layout = create_layout(i18n.t)

    # Build menu (language first, then help), and give Menu a key so we can update it later
    menu_def = _build_menu_def(i18n, current_lang_code, langs_from_splash)
    layout_with_menu = [[sg.Menu(menu_def, key='-MENUBAR-')]] + layout


    app_icon_path = resource_path(os.path.join("assets", "icon.ico"))
    window_icon = app_icon_path if os.path.exists(app_icon_path) else None

    # create the window resizable and with saved size
    (win_w, win_h), was_max = config_manager.get_window_prefs(app_config)
    window = sg.Window(
        i18n.t('window_title'),
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
        window['-INSTRUMENTAL_DISPLAY-'].update(i18n.t('instrumental_display_placeholder'))
        window['-VOCAL_DISPLAY-'].update(i18n.t('vocal_display_placeholder'))
        handle_input_change()
        app_config['last_folder'] = new_folder
        config_manager.save_config(app_config)

    def populate_listbox():
        nonlocal listbox_items
        listbox_items.clear()
        subdirs, files = explorer.scan_folder(explorer.current_folder)
        for d in subdirs:
            listbox_items.append(f"📁 {d}")
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
                if item_text.startswith("📁"):
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
            if item_text.startswith("📁"): return 'folder'
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

    # Tooltips
    main_tooltip_manager = TooltipManager(window)
    # Bind info tooltips with translated text
    main_tooltip_manager.bind(window['-INFO1-'].Widget, i18n.t('headphone_info_tooltip'))
    main_tooltip_manager.bind(window['-INFO2-'].Widget, i18n.t('virtual_info_tooltip'))
    main_tooltip_manager.bind(window['-LUFS_INFO-'].Widget, i18n.t('lufs_info_tooltip'))
    try:
        main_tooltip_manager.bind(window['-EXPLORER_INFO-'].Widget, i18n.t('explorer_info_tooltip'))
    except Exception:
        pass
    try:
        main_tooltip_manager.bind(window['-PLAYER_INFO-'].Widget, i18n.t('player_info_tooltip'))
    except Exception:
        pass
    try:
        if '-SEP_GPU_STATUS-' in window.AllKeysDict:
            main_tooltip_manager.bind(window['-SEP_GPU_STATUS-'].Widget, i18n.t('gpu_info_tooltip'))
    except Exception:
        pass

    window['-BACK-'].update(disabled=True)
    if app_config.get('last_folder') and os.path.isdir(app_config['last_folder']):
        change_directory(app_config['last_folder'])
    else:
        window['-FOLDER_PATH-'].update(i18n.t('folder_path_placeholder'))

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
            window['-HEADPHONE-'].update(values=[i18n.t('device_not_found')], value=i18n.t('device_not_found'))
            window['-VIRTUAL-'].update(values=[i18n.t('device_not_found')], value=i18n.t('device_not_found'))

    update_device_list(device_info_pre)

    def scan_for_audio_devices_async():
        window['-REFRESH_DEVICES-'].update(disabled=True)
        window['-DEVICE_SCAN_STATUS-'].update(i18n.t('scan_in_progress'), text_color=sg.theme_text_color())

        def _worker():
            try:
                from sounddevice import query_devices
                devices = query_devices()
                output_devices = {i: d for i, d in enumerate(devices) if d.get('max_output_channels', 0) > 0}
                window.write_event_value('-DEVICE_SCAN_COMPLETE-', output_devices)
            except Exception as e:
                window.write_event_value('-DEVICE_SCAN_COMPLETE-', {'error': str(e)})
        threading.Thread(target=_worker, daemon=True).start()

    # Settings modal uses translator; pass i18n.t into function
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
            is_rec = (filename == get_recommended_model())
            label = f"{fr} ★" if is_rec else fr
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
            ('hop_length', i18n.t('hop_length_label'), hop_options, 1024),
            ('segment_size', i18n.t('segment_size_label'), seg_options, 256),
            ('overlap', i18n.t('overlap_label'), overlap_options, 0.25),
            ('batch_size', i18n.t('batch_size_label'), batch_options, 1)
        ]

        for key, label, options, default in mdx_param_defs:
            current_val = str(mdx.get(key, default))
            if current_val not in options:
                options.insert(0, current_val)
            mdx_params_layout.append([
                sg.Text(label), sg.Text('ⓘ', key=f'-S_{key.upper()}_INFO-'),
                sg.Combo(options, key=f'-S_{key.upper()}_CMB-', default_value=current_val, size=(10, 1)),
                sg.Text(i18n.t('default_value_label').format(default=default))
            ])

        output_dir_val = settings.get("output_dir", "")
        is_default_dir = (output_dir_val == os.path.expanduser("~"))
        display_dir = i18n.t('choose_folder_button') if is_default_dir else output_dir_val

        layout_settings = [
            [sg.Push(), sg.Text(i18n.t('separator_settings_title'), font=("Helvetica", 16)), sg.Push()],
            [sg.Text(i18n.t('model_label')),
             sg.Combo(model_choices, key="-S_MODEL-", size=(48,1), default_value=default_model_selection),
             sg.Button(i18n.t('open_model_folder_button'), key="-OPEN_MODEL_FOLDER-", size=(14,1))],
            [sg.Text(i18n.t('output_format_label')), sg.Combo(["wav","flac","mp3","m4a"], key="-S_FMT-", default_value=settings.get("output_format","wav"))],
            [sg.Checkbox(i18n.t('enable_gpu_checkbox_label'), key="-S_GPU-", default=settings.get("use_gpu", False))],
            [sg.Frame(i18n.t('mdx_params_frame_title'), mdx_params_layout, expand_x=True)],
            [sg.Checkbox(i18n.t('save_to_explorer_checkbox_label'), key="-S_SAVE_TO_EXPLORER-", default=settings.get("save_to_explorer", True), enable_events=True)],
            [sg.Text(i18n.t('output_dir_label')), sg.Input(display_dir, key="-S_OUTDIR-", expand_x=True, text_color='grey' if is_default_dir else sg.theme_input_text_color()), sg.FolderBrowse(i18n.t('choose_folder_button'), key="-S_BROWSE-")],
            [sg.Button(i18n.t('save_settings_button'), key="-S_SAVE-"), sg.Button(i18n.t('close_button'), key="-S_CANCEL-")]
        ]

        win = sg.Window(i18n.t('separator_settings_title'), layout_settings, modal=True, finalize=True, icon=window_icon)
        modal_tooltip_manager = TooltipManager(win)

        win['-S_OUTDIR-'].bind('<FocusIn>', '+FOCUS_IN')

        # Bind tooltips for MDX parameters
        modal_tooltip_manager.bind(win['-S_HOP_LENGTH_INFO-'].Widget, i18n.t('hop_length_tooltip'))
        modal_tooltip_manager.bind(win['-S_SEGMENT_SIZE_INFO-'].Widget, i18n.t('segment_size_tooltip'))
        modal_tooltip_manager.bind(win['-S_OVERLAP_INFO-'].Widget, i18n.t('overlap_tooltip'))
        modal_tooltip_manager.bind(win['-S_BATCH_SIZE_INFO-'].Widget, i18n.t('batch_size_tooltip'))
        try:
            modal_tooltip_manager.bind(win['-S_GPU-'].Widget, i18n.t('gpu_info_tooltip'))
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

                if ev == '-S_OUTDIR-+FOCUS_IN' and vals['-S_OUTDIR-'] == i18n.t('choose_folder_button'):
                    win['-S_OUTDIR-'].update("", text_color=sg.theme_input_text_color())

                if ev == "-OPEN_MODEL_FOLDER-":
                    try:
                        os.makedirs(MODELS_DIR, exist_ok=True)
                        open_folder_in_explorer(MODELS_DIR)
                    except Exception as e:
                        show_error_dialog(i18n.t('error_message'), str(e), "")

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
                    if not outdir or outdir == i18n.t('choose_folder_button'):
                        outdir = default_folder or app_config.get("last_folder") or os.path.expanduser("~")
                    settings["output_dir"] = outdir

                    settings["mdx_params"] = {
                        "hop_length": int(vals["-S_HOP_LENGTH_CMB-"]), "segment_size": int(vals["-S_SEGMENT_SIZE_CMB-"]),
                        "overlap": float(vals["-S_OVERLAP_CMB-"]), "batch_size": int(vals["-S_BATCH_SIZE_CMB-"])
                    }

                    app_config['separator_settings'] = settings
                    config_manager.save_config(app_config)
                    show_setting_message(i18n.t('settings_saved_message'), 2.0, color="lightgreen")
                    # [GPU] Show “checking…” until sidecar reports, then forward sidecar gpu_info → GUI event
                    update_gpu_status_display(i18n.t('gpu_status_checking'), 'checking')
                    try:
                        if sidecar_client:
                            # --- Refresh GPU label after settings saved ---
                            # Rebind the callback (in case client was recreated or window changed)
                            sidecar_client.on_gpu_info = lambda info: window.write_event_value('-SEP_GPU_INFO-', info)

                            # Flush any known capability to update the label right away
                            cached_gpu = getattr(sidecar_client, 'last_gpu_info', None)
                            if cached_gpu is not None:
                                window.write_event_value('-SEP_GPU_INFO-', cached_gpu)
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
        except Exception:
            pass

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
    update_gpu_status_display(i18n.t('gpu_status_checking'), 'checking')
    try:
        # --- GPU status binding (main window scope) ---
        # 1) When sidecar reports GPU capability later, forward it into the GUI event loop
        sidecar_client.on_gpu_info = lambda info: window.write_event_value('-SEP_GPU_INFO-', info)

        # 2) If we already learned GPU capability during splash, deliver it now
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

    def show_error_dialog(chinese_error_name: str, error_text: str, terminal_output: str):
        try:
            full_brief = chinese_error_name or i18n.t('error_message')
            err_line = (error_text or "").strip()
            term = (terminal_output or "").strip()
            err_line_clean = err_line.replace(i18n.t('recent_output_label'), "").strip()
            if term:
                err_line_display = err_line_clean
                term_content = term
            else:
                err_line_display = ""
                term_content = err_line_clean or "(no more output)"
            header_text = f"{full_brief}:"
            copy_blob = f"{header_text}\n{err_line_clean}\n\n{ i18n.t('recent_output_label') }\n{term_content}"
            header_font = (CUSTOM_FONT_NAME, 12, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 12, "bold")
            body_font = (CUSTOM_FONT_NAME, 10) if CUSTOM_FONT_NAME else ("Helvetica", 10)
            recent_label_font = (CUSTOM_FONT_NAME, 11, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 11, "bold")
            mono_font = ("Courier", 10)
            layout_err = [
                [sg.Text(header_text, font=header_font)],
                ([sg.Text(err_line_display, font=body_font)] if err_line_display else [sg.Text("", visible=False)]),
                [sg.Text(i18n.t('recent_output_label'), font=recent_label_font)],
                [sg.Multiline(term_content, size=(95, 14), key='-ERR_TERMINAL-', disabled=True,
                              autoscroll=True, no_scrollbar=False,
                              background_color='black', text_color='white', font=mono_font)],
                [sg.Button(i18n.t('copy_button'), key='-ERR_COPY-'), sg.Button(i18n.t('report_error_button'), key='-ERR_REPORT-', button_color=('white','firebrick')), sg.Push()]
            ]
            err_win = sg.Window(i18n.t('error_dialog_title'), layout_err, modal=True, finalize=True, icon=window_icon, resizable=False)
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
                            sg.popup(i18n.t('copy_to_clipboard_failed'), title=i18n.t('tip_title'))
                        except Exception:
                            pass
                    try:
                        err_win['-ERR_COPY-'].update(i18n.t('copied_button'), disabled=True)
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
                        err_win['-ERR_COPY-'].update(i18n.t('copy_button'), disabled=False)
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
                sg.popup_error(f"{i18n.t('error_message')}:\n{error_text}\n\n{i18n.t('recent_output_label')}\n{terminal_output}", title=i18n.t('error_dialog_title'))
            except Exception:
                pass

    def open_folder_in_explorer(path):
        if not path or not os.path.isdir(path):
            sg.popup_error(i18n.t('select_valid_folder_msg'), title=i18n.t('error_message'))
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":  # macOS
                subprocess.call(["open", path])
            else:  # Linux
                subprocess.call(["xdg-open", path])
        except Exception as e:
            sg.popup_error(f"{i18n.t('cannot_open_folder_msg')}: {e}", title=i18n.t('error_message'))

    # --- Update checker -------------------------------------------------
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
                        raise Exception(f"{i18n.t('update_failed_msg')}{e1}; {e2}")
                else:
                    raise Exception(f"{i18n.t('update_failed_msg')}{e1}")
            try:
                data = json.loads(raw)
            except Exception as ex:
                raise Exception(f"Failed to parse version JSON: {ex}")
            remote_version = data.get("version")
            if not remote_version:
                raise Exception("Version info missing 'version' field")
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
            remote_ver = remote_data.get('version', '???')
            download_url = remote_data.get('download_url', '')
            notes = remote_data.get('notes', []) or []
            notes_text = "\n".join(notes) if isinstance(notes, (list, tuple)) else str(notes)
            header_font = (CUSTOM_FONT_NAME, 12, "bold") if CUSTOM_FONT_NAME else ("Helvetica", 12, "bold")
            body_font = (CUSTOM_FONT_NAME, 10) if CUSTOM_FONT_NAME else ("Helvetica", 10)
            layout_upd = [
                [sg.Text(i18n.t('update_title'), font=header_font)],
                [sg.Text(f"{i18n.t('your_version_label')}{APP_VERSION}", font=body_font)],
                [sg.Text(f"{i18n.t('available_version_label')}{remote_ver}", font=body_font)],
                [sg.Text(i18n.t('update_notes_label'), font=body_font)],
                [sg.Multiline(notes_text, size=(80, 12), disabled=True, autoscroll=True)],
                [sg.Push(), sg.Button(i18n.t('go_to_download_button'), key='-GO_DOWNLOAD-'), sg.Button(i18n.t('remind_later_button'), key='-REMIND_LATER-')]
            ]
            win = sg.Window(i18n.t('update_title'), layout_upd, modal=True, finalize=True, icon=window_icon, resizable=False)
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
            sg.popup_error(f"{i18n.t('update_failed_title')}: {ex}")

    try:
        start_update_check_async(manual=False)
    except Exception:
        pass

    # --------------------------- main event loop --------------------------
    current_stage_token = "Preparing"  # track stage for progress mapping

    # Map UI keys to translation keys for dynamic updates
    ui_translation_map = {
        'file_explorer_title': 'file_explorer_title',
        '-FOLDER_PATH-': 'folder_path_placeholder',
        '-BACK-': 'back_button',
        '-CHANGE_FOLDER-': 'change_folder_button',
        '-OPEN_FOLDER-': 'open_folder_button',
        '-REFRESH-': 'refresh_button',
        'vocal_separator_title': 'vocal_separator_title',
        '-SEP_GPU_STATUS-': 'gpu_status_checking',
        'song_file_label': 'song_file_label',
        '-SONG_FILE_BROWSE-': 'browse_file_button',
        '-START_SEPARATION-': 'start_separation_button',
        '-OPEN_SEPARATOR_SETTINGS-': 'separator_settings_button',
        '-SEPARATOR_STATUS-': 'separator_status_ready',
        'audio_loader_title': 'audio_loader_title',
        'instrumental_label': 'instrumental_label',
        'vocal_label': 'vocal_label',
        'headphone_label': 'headphone_label',
        'virtual_label': 'virtual_label',
        'sample_rate_label': 'sample_rate_label',
        'hz_label': 'hz_label',
        '-REFRESH_DEVICES-': 'refresh_devices_button',
        'normalize_label': 'normalize_label',
        'lufs_label': 'lufs_label',
        'pitch_label': 'pitch_label',
        '-LOAD-': 'load_audio_button',
        'player_title': 'player_title',
        '-REWIND-': 'rewind_button',
        '-PLAY_PAUSE-': 'play_button',
        '-FORWARD-': 'forward_button',
        '-STOP-': 'stop_button',
        'instrumental_volume_label': 'instrumental_volume_label',
        'vocal_volume_label': 'vocal_volume_label'
    }

    def apply_translations():
        """Update UI text values to reflect the current language."""
        # Update window title
        window.TKroot.title(i18n.t('window_title'))
        # Update menu
        try:
            window['-MENUBAR-'].update(
                menu_definition=_build_menu_def(i18n, i18n.lang, langs_from_splash)
            )
        except Exception:
            pass
        # Update static widgets
        for widget_key, trans_key in ui_translation_map.items():
            try:
                if widget_key in window.AllKeysDict:
                    # Special handling for buttons with dynamic text such as PLAY/PAUSE
                    if widget_key == '-START_SEPARATION-':
                        # Determine correct label based on separation state
                        text_key = 'stop_separation_button' if separating else 'start_separation_button'
                        window[widget_key].update(i18n.t(text_key))
                    elif widget_key == '-PLAY_PAUSE-':
                        # Determine Play/Pause text based on playing state
                        text_key = 'pause_button' if player.playing else 'play_button'
                        window[widget_key].update(i18n.t(text_key))
                    else:
                        window[widget_key].update(i18n.t(trans_key))
            except Exception:
                pass
        # Update tooltips
        main_tooltip_manager.bind(window['-INFO1-'].Widget, i18n.t('headphone_info_tooltip'))
        main_tooltip_manager.bind(window['-INFO2-'].Widget, i18n.t('virtual_info_tooltip'))
        main_tooltip_manager.bind(window['-LUFS_INFO-'].Widget, i18n.t('lufs_info_tooltip'))
        try:
            main_tooltip_manager.bind(window['-EXPLORER_INFO-'].Widget, i18n.t('explorer_info_tooltip'))
        except Exception:
            pass
        try:
            main_tooltip_manager.bind(window['-PLAYER_INFO-'].Widget, i18n.t('player_info_tooltip'))
        except Exception:
            pass
        try:
            if '-SEP_GPU_STATUS-' in window.AllKeysDict:
                main_tooltip_manager.bind(window['-SEP_GPU_STATUS-'].Widget, i18n.t('gpu_info_tooltip'))
        except Exception:
            pass
        # Update GPU status text if appropriate
        update_gpu_status_display(i18n.t('gpu_status_checking'), 'checking')


    # Accept both "KEY" and "...::KEY" forms (FreeSimpleGUI vs PySimpleGUI behavior)
    def _menu_event_is(ev: object, key: str) -> bool:
        return isinstance(ev, str) and (ev == key or ev.endswith(f"::{key}"))


    def _extract_lang_code(ev: str) -> str | None:
        # Supports "LANG::<code>" and "<label>::LANG::<code>"
        if not isinstance(ev, str):
            return None
        if ev.startswith("LANG::"):
            return ev.split("::", 1)[1]
        if "::LANG::" in ev:
            return ev.split("::LANG::", 1)[1]
        return None

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
        
        # --- language click handler ---
        code = _extract_lang_code(event)
        if code and code != i18n.lang:
            # Build a small modal so we can control button sizes
            btn_yes = i18n.t('restart_now')
            btn_no  = i18n.t('restart_later')
            layout_popup = [
                [sg.Text(i18n.t('restart_prompt'), size=(30, 3))],
                [sg.Push(),
                sg.Button(btn_yes, key='-YES-', size=(10, 1)),
                sg.Button(btn_no,  key='-NO-',  size=(10, 1)),
                sg.Push()]
            ]
            pop = sg.Window(
                i18n.t('restart_title'),
                layout_popup,
                modal=True,
                keep_on_top=True,
                finalize=True
            )
            evp, _ = pop.read()
            pop.close()

            if evp == '-YES-':
                # Persist and restart with the new language
                app_config["language"] = code
                try:
                    config_manager.save_config(app_config)
                except Exception as ex:
                    print(f"[i18n DEBUG] save_config failed: {ex}")
                try:
                    subprocess.Popen([sys.executable, *sys.argv])
                except Exception:
                    pass
                window.close()
                sys.exit(0)
            # If '-NO-' or the window was closed: do nothing at all
            # (No language apply, no menu change, no config save)

        # Handle menu events by event keys (defined via :: suffix)
        if _menu_event_is(event, 'CHECK_UPDATE'):
            start_update_check_async(manual=True)

        if event == '-UPDATE_AVAILABLE-':
            payload = values[event]
            remote = payload.get('remote', {}) if isinstance(payload, dict) else {}
            show_update_popup(remote)

        if event == '-UPDATE_NOUPDATE-':
            payload = values[event] if isinstance(values[event], dict) else {}
            if payload.get('manual'):
                try:
                    sg.popup(i18n.t('latest_version_msg'), title=i18n.t('update_title'))
                except Exception:
                    pass

        if event == '-UPDATE_ERROR-':
            payload = values[event] if isinstance(values[event], dict) else {}
            if payload.get('manual'):
                try:
                    sg.popup_error(f"{i18n.t('update_failed_msg')}{payload.get('error', '未知錯誤')}", title=i18n.t('update_failed_title'))
                except Exception:
                    pass
            else:
                player._dbg(f"Background update check error: {payload.get('error')}")

        # Help menu handlers
        if _menu_event_is(event, 'TUTORIAL'):
            try:
                webbrowser.open_new_tab(TUTORIAL_URL)
            except Exception as e:
                player._dbg(f"Failed to open tutorial URL: {e}")

        if _menu_event_is(event, 'FEEDBACK'):
            try:
                webbrowser.open_new_tab(FEEDBACK_URL)
            except Exception as e:
                player._dbg(f"Failed to open feedback URL: {e}")
        if _menu_event_is(event, 'ABOUT'):
            about_img = resource_path(os.path.join("assets", "splash_icon.png"))
            img_elem = None
            if os.path.exists(about_img):
                img_elem = sg.Image(about_img)
            about_col = []
            if img_elem:
                about_col.append([img_elem])
            about_col.append([sg.Text(i18n.t('about_text'), size=(80, 3), justification='center')])
            about_col.append([sg.HorizontalSeparator()])
            about_col.append([
                sg.Text(i18n.t('about_subtext'), key='-ABOUT_TX-'),
                sg.Text("  "),
                sg.Text("[" + i18n.t('twitter_portal') + "]", key='-ABOUT_TW-', enable_events=True, tooltip=i18n.t('twitter_portal'), text_color="#054393", justification='left')
            ])
            about_layout = [
                [sg.VPush()],
                [sg.Column(about_col, element_justification='center', vertical_alignment='center', pad=(20,10))],
                [sg.VPush()]
            ]
            about_win = sg.Window(i18n.t('about_title'), about_layout, modal=True, finalize=True, icon=window_icon, no_titlebar=False)
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

        if event == '-PLAYER_DEBUG-':
            print("[PLAYER_DEBUG]", values[event])

        if event == '-PITCH_SHIFT_ERROR-':
            show_error_dialog(i18n.t('error_message'), str(values[event]), "")

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
                window['-DEVICE_SCAN_STATUS-'].update(i18n.t('refresh_failed'), text_color='red')
            else:
                window['-DEVICE_SCAN_STATUS-'].update(i18n.t('refresh_success'), text_color='lightgreen')
                update_device_list(new_device_info)

        if event in ("-LEFT_CLICK-", "-FILE_LIST-"):
            if player.playing or separating:
                continue
            idx = values.get(event)
            if isinstance(idx, list): idx = idx[0]
            if isinstance(idx, int) and 0 <= idx < len(listbox_items):
                selected = listbox_items[idx]
                if selected.startswith("📁"):
                    change_directory(os.path.join(explorer.current_folder, selected.replace("📁 ", "")))
                else:
                    explorer.set_instrumental(selected)
                    window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or i18n.t('instrumental_display_placeholder'))
                    window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or i18n.t('vocal_display_placeholder'))
                    listbox_widget.selection_clear(0, 'end')
                    colorize_listbox()
                    handle_input_change()

        if event == "-RIGHT_CLICK-":
            if player.playing or separating:
                continue
            idx = values.get(event)
            if isinstance(idx, int) and 0 <= idx < len(listbox_items):
                selected = listbox_items[idx]
                if not selected.startswith("📁"):
                    explorer.set_vocal(selected)
                    window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or i18n.t('instrumental_display_placeholder'))
                    window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or i18n.t('vocal_display_placeholder'))
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
                    show_error_dialog(i18n.t('error_message'), i18n.t('file_not_found_msg'), "")
                    continue

                sep_out_dir = explorer.current_folder if chosen.get("save_to_explorer", False) else (chosen.get("output_dir") or os.path.dirname(input_file))
                try:
                    os.makedirs(sep_out_dir, exist_ok=True)
                except Exception as e:
                    if sep_out_dir is None:
                        show_error_dialog(i18n.t('error_message'), i18n.t('select_valid_folder_msg'), f"\n{e}")
                    else:
                        show_error_dialog(i18n.t('error_message'), i18n.t('cannot_open_folder_msg'), f"{sep_out_dir}\n\n{e}")
                    continue

                # GUI state
                separating = True
                window['-START_SEPARATION-'].update(i18n.t('stop_separation_button'))
                # ---- A) SHOW the total progress UI at job start ----
                window['-SEP_TOTAL_PROGRESS-'].update(0, visible=True)
                window['-SEP_TOTAL_PERCENT-'].update("0%", visible=True)
                window['-SEPARATOR_STATUS-'].update(i18n.t('gpu_status_checking'))
                last_overall_display = 0  # [MONO] reset high-water mark on job start

                sep_worker = sidecar_client  # minimal change: keep variable name

                # Define callbacks that convert sidecar events to our UI event
                def _on_status(stage_in, msg):
                    nonlocal current_stage_token
                    token = _normalize_stage(stage_in)   # accept zh or token safely
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
                    token = _normalize_stage(stage_in)
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
                        "terminal": ""
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
                    window['-START_SEPARATION-'].update(i18n.t('start_separation_button'))
                    window['-SEPARATOR_STATUS-'].update(i18n.t('error_message'))
                    # ensure UI returns to hidden state on failure
                    window['-SEP_TOTAL_PROGRESS-'].update(0, visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                    show_setting_message(i18n.t('error_message'), 3.0, color="red")
                    show_error_dialog(i18n.t('error_message'), str(ex), "")
            else:
                # Abort
                if sep_worker:
                    try:
                        sep_worker.abort()
                    except Exception:
                        pass
                separating = False
                window['-START_SEPARATION-'].update(i18n.t('start_separation_button'))
                show_setting_message(i18n.t('canceled_message'), 3.0, color="red")
                window['-SEPARATOR_STATUS-'].update(i18n.t('separator_status_ready'))
                last_overall_display = 0  # reset
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

                overall_disp = max(overall_in, last_overall_display)
                last_overall_display = overall_disp

                if separating:
                    try:
                        window['-SEP_TOTAL_PROGRESS-'].update(overall_disp)
                        window['-SEP_TOTAL_PERCENT-'].update(f"{overall_disp}%")
                    except Exception:
                        pass
                    try:
                        # Map normalized tokens to i18n keys, then translate
                        _stage_keymap = {
                            "Preparing": "stage_preparing",
                            "DownloadingModel": "stage_downloading_model",
                            "LoadingModel": "stage_loading_model",
                            "Separation": "stage_separating",
                            "Finalize": "stage_finalize",
                        }
                        label = i18n.t(_stage_keymap.get(stage, stage))
                        window['-SEPARATOR_STATUS-'].update(f"{label} — {stage_pct}%")
                    except Exception:
                        pass

            elif ptype == "done":
                files = payload.get("files", [])
                separating = False
                window['-START_SEPARATION-'].update(i18n.t('start_separation_button'))
                last_overall_display = 100
                try:
                    window['-SEP_TOTAL_PROGRESS-'].update(100)
                    window['-SEP_TOTAL_PERCENT-'].update("100%")
                    window['-SEP_TOTAL_PROGRESS-'].update(visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                except Exception:
                    pass
                window['-SEPARATOR_STATUS-'].update(i18n.t('separator_status_ready'))
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

                window['-INSTRUMENTAL_DISPLAY-'].update(explorer.instrumental_selection_name or i18n.t('instrumental_display_placeholder'))
                window['-VOCAL_DISPLAY-'].update(explorer.vocal_selection_name or i18n.t('vocal_display_placeholder'))
                colorize_listbox()
                show_setting_message(i18n.t('separation_completed_message'), 3.0, color="lightgreen")

            elif ptype in ("aborted", "error"):
                separating = False
                window['-START_SEPARATION-'].update(i18n.t('start_separation_button'))
                window['-SEPARATOR_STATUS-'].update(i18n.t('separator_status_ready') if ptype == "aborted" else i18n.t('error_message'))
                last_overall_display = 0
                try:
                    window['-SEP_TOTAL_PROGRESS-'].update(0)
                    window['-SEP_TOTAL_PERCENT-'].update("0%")
                    window['-SEP_TOTAL_PROGRESS-'].update(visible=False)
                    window['-SEP_TOTAL_PERCENT-'].update("", visible=False)
                except Exception:
                    pass
                show_setting_message(i18n.t('canceled_message') if ptype == "aborted" else i18n.t('error_message'), 3.0, color="red")
                if ptype == "error":
                    err_msg = payload.get('message', '')
                    terminal = payload.get('terminal', '') or ''
                    show_error_dialog(i18n.t('error_message'), err_msg, terminal)
                populate_listbox()

        # [GPU] Handle sidecar GPU capability report
        if event == '-SEP_GPU_INFO-':
            info = values.get('-SEP_GPU_INFO-') or {}
            if not isinstance(info, dict):
                info = {}
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
            separator_settings = app_config.get('separator_settings') or {}
            user_wants_gpu = bool(separator_settings.get('use_gpu', False))
            if available and user_wants_gpu:
                update_gpu_status_display(i18n.t('gpu_status_enabled'), 'enabled')
            elif available:
                update_gpu_status_display(i18n.t('gpu_status_disabled'), 'disabled')
            else:
                update_gpu_status_display(i18n.t('gpu_status_unavailable'), 'unavail')

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
            prog, raw_text = payload if isinstance(payload, (tuple, list)) else (payload, "load_status_loading")
            # Translate if it's a key; if it's already plain text, i18n.t will just return it unchanged.
            status_text = i18n.t(raw_text)
            window['-LOAD_STATUS-'].update(status_text, text_color='white')
            window['-LOAD_PROGRESS-'].update(int(prog))


        if event == "-LOAD_DONE-":
            done_val = values[event]
            if isinstance(done_val, str) and done_val.startswith("ERROR"):
                show_error_dialog(i18n.t('error_message'), done_val, "")
                window['-LOAD_PROGRESS-'].update(0)
                window['-LOAD_STATUS-'].update("", text_color='white')
                window['-LOAD-'].update(disabled=False)
                player.audio_loaded = False
            else:
                window['-LOAD_PROGRESS-'].update(100)
                window['-LOAD_STATUS-'].update(i18n.t('separator_status_ready'), text_color='lightgreen')
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
            show_error_dialog(i18n.t('error_message'), str(values[event]), "")

        is_busy = player.playing or separating
        window["-PLAY_PAUSE-"].update(i18n.t('pause_button') if player.playing else i18n.t('play_button'), disabled=not player.audio_loaded)
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
            key_name = 'last_headphone' if event == "-HEADPHONE-" else 'last_virtual'
            app_config[key_name] = values[event]
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
            window["-PLAY_PAUSE-"].update(i18n.t('play_button'))

        if event == "-PLAYBACK_ENDED-":
            player.stop_immediate()
            player.seek(0.0)
            window['-PROGRESS-'].update(value=0)
            window['-PLAY_PAUSE-'].update(i18n.t('play_button'))
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
            window['-PLAY_PAUSE-'].update(i18n.t('play_button'))
            window['-TIME_DISPLAY-'].update(f"00:00:00 / {player.format_time(player.duration)}")

    # Clean shutdown
    if sep_worker:
        try:
            sep_worker.abort()
        except Exception:
            pass
    player.stop_immediate()
    main_tooltip_manager.close()
    try:
        is_zoomed = (last_state == 'zoomed')
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