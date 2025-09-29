import FreeSimpleGUI as sg
import platform
import os
import sys
import tkinter as tk

"""
UI layout definitions with support for internationalization.

This module exposes a single factory function, `create_layout`, which
accepts a translation function and returns the structured layout used by
the application. All user-facing text is obtained by invoking the
translation function `t(key)`, allowing the caller to supply strings
appropriate for the current language. Keys for interactive elements
remain unchanged so as not to disrupt event handling in the rest of the
program.

Example usage::

    from ui_layout import create_layout, TooltipManager
    from i18n_helper import I18nManager
    i18n = I18nManager(locales_dir='locales')
    layout = create_layout(i18n.t)

The factory does not maintain any global state. The caller is
responsible for passing a translation function when building the UI and
for updating text values when the language changes at runtime.
"""

# --- DPI Awareness Fix for Windows ---
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

# --- Font Loading & Options ---
CUSTOM_FONT_NAME = "GenSenRounded2 TW R"
CUSTOM_FONT_FILE = "GenSenRounded2TW-R.otf"


def resource_path(relative_path):
    """Return absolute path to resource, working for dev and PyInstaller."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


try:
    font_path = resource_path(os.path.join("assets", CUSTOM_FONT_FILE))
    if platform.system() == "Windows" and os.path.exists(font_path):
        import ctypes
        gdi32 = ctypes.WinDLL('gdi32')
        AddFontResourceEx = gdi32.AddFontResourceExW
        AddFontResourceEx.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        AddFontResourceEx.restype = ctypes.c_int
        FR_PRIVATE = 0x10  # only for this process; no system-wide install

        if AddFontResourceEx(font_path, FR_PRIVATE, None) > 0:
            sg.set_options(font=(CUSTOM_FONT_NAME, 11))

    else:
        raise FileNotFoundError
except Exception:
    sg.set_options(font=("Helvetica", 10))


class TooltipManager:
    """
    A helper for attaching tooltips to widgets using native Tk windows.

    This class is intentionally unchanged from the original implementation
    to preserve existing behaviour. It can be used to bind tooltip text
    to any widget. The caller should provide translated tooltip strings
    when binding in order to support multiple languages.
    """

    def __init__(self, window):
        self._tk_root = window.TKroot
        self._tooltip = None
        self._show_timer = None

    def bind(self, widget, text):
        widget.bind("<Enter>", lambda e, w=widget, t=text: self._schedule_show(w, t))
        widget.bind("<Leave>", lambda e: self._hide())

    def _schedule_show(self, widget, text):
        self._hide()
        if self._tk_root:
            self._show_timer = self._tk_root.after(500, lambda: self._show(widget, text))

    def _hide(self):
        if self._show_timer and self._tk_root:
            self._tk_root.after_cancel(self._show_timer)
            self._show_timer = None
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def _show(self, widget, text):
        if not self._tk_root:
            return
        # Destroy any existing tooltip
        self._hide()
        x = widget.winfo_rootx() + 25
        y = widget.winfo_rooty() + 20
        self._tooltip = tk.Toplevel(self._tk_root)
        self._tooltip.wm_overrideredirect(True)  # Make it borderless
        self._tooltip.wm_geometry(f"+{x}+{y}")
        bg_color = "#7894b4"  #sg.theme_background_color()
        text_color = sg.theme_text_color()
        label = tk.Label(
            self._tooltip,
            text=text,
            justify=tk.LEFT,
            background=bg_color,
            foreground=text_color,
            wraplength=300,
            font=(CUSTOM_FONT_NAME, 9),
            relief=tk.SOLID,
            borderwidth=0,
            # add a crisp white outline so it doesn't blend with the app bg
            highlightthickness=2,             
            highlightbackground="white",
            highlightcolor="white",
        )
        label.pack(ipadx=5, ipady=3)


    def close(self):
        self._hide()


def create_layout(t):
    """
    Build and return the application layout using a translation function.

    :param t: A callable that takes a translation key and returns the
              translated string for the current language.
    :return: The constructed layout definition for FreeSimpleGUI.
    """
    # File explorer panel
    file_explorer_panel = [
        [sg.Text(t("file_explorer_title"), key="file_explorer_title", font=(CUSTOM_FONT_NAME, 14)),
         sg.Text("ⓘ", key='-EXPLORER_INFO-', tooltip=t("explorer_info_tooltip"))],
        [
            sg.Button(t("back_button"), key="-BACK-", size=(2, 1)),
            sg.Input(t("folder_path_placeholder"), key="-FOLDER_PATH-", readonly=True, expand_x=True, enable_events=True),
            sg.FolderBrowse(t("change_folder_button"), key="-CHANGE_FOLDER-")
        ],
        [sg.Listbox(values=[], key="-FILE_LIST-", expand_y=True, expand_x=True, enable_events=True)],
        [
            sg.Text(t("left_click_choose_instrumental"), background_color='#a8d8ea', text_color='black', font=(CUSTOM_FONT_NAME, 9), pad=((0, 5), (0, 0))),
            sg.Text(t("right_click_choose_vocal"), background_color='#f3c9d8', text_color='black', font=(CUSTOM_FONT_NAME, 9)),
            sg.Push(),
            sg.Button(t("open_folder_button"), key="-OPEN_FOLDER-"),
            sg.Button(t("refresh_button"), key="-REFRESH-")
        ]
    ]

    # Vocal separator panel
    vocal_separator_panel = [
        [
            sg.Text(t("vocal_separator_title"), key="vocal_separator_title", font=(CUSTOM_FONT_NAME, 14)),
            sg.Text(t("gpu_status_checking"), key='-SEP_GPU_STATUS-', background_color='#e0e0e0', text_color='black', pad=((8, 0), (0, 0)))
        ],
        [sg.Text(t("song_file_label"), key="song_file_label"), sg.Input(key="-SONG_FILE-", expand_x=True, readonly=True), sg.FileBrowse(t("browse_file_button"), file_types=((t("audio_files"), "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma"),), key="-SONG_FILE_BROWSE-")],
        [
            sg.Button(t("start_separation_button"), key="-START_SEPARATION-", size=(12, 1)),
            sg.Button(t("separator_settings_button"), key="-OPEN_SEPARATOR_SETTINGS-", size=(8, 1)),
            sg.Text("", key='-SET_MSG-', size=(20, 1), text_color="lightgreen"),
        ],
        [
            sg.Text(t("separator_status_label"), size=(5, 1)),
            sg.Text(t("separator_status_ready"), key="-SEPARATOR_STATUS-", expand_x=True),
            sg.Text(t("total_progress_label"), pad=((8, 0), (0, 0))),
            sg.ProgressBar(100, orientation='h', size=(25, 12), key='-SEP_TOTAL_PROGRESS-', visible=False),
            sg.Text("", key='-SEP_TOTAL_PERCENT-')
        ],
    ]

    # Audio player panel
    audio_player_panel = [
        [sg.Text(t("audio_loader_title"), key="audio_loader_title", font=(CUSTOM_FONT_NAME, 14)), sg.Text("ⓘ", key='-PLAYER_INFO-', tooltip=t("player_info_tooltip"))],
        [sg.Text(t("instrumental_label"), key="instrumental_label", size=(12, 1)), sg.Text(t("instrumental_display_placeholder"), key="-INSTRUMENTAL_DISPLAY-", size=(30, 1))],
        [sg.Text(t("vocal_label"), key="vocal_label", size=(12, 1)), sg.Text(t("vocal_display_placeholder"), key="-VOCAL_DISPLAY-", size=(30, 1))],
        [
            sg.Text(t("headphone_label"), key="headphone_label"), sg.Text('ⓘ', key='-INFO1-'),
            sg.Combo([], default_value="", key="-HEADPHONE-", size=(40, 1), enable_events=True)
        ],
        [
            sg.Text(t("virtual_label"), key="virtual_label"), sg.Text('ⓘ', key='-INFO2-'),
            sg.Combo([], default_value="", key="-VIRTUAL-", size=(40, 1), enable_events=True)
        ],
        [
            sg.Text(t("sample_rate_label"), key="sample_rate_label"),
            sg.Combo([44100, 48000], key="-SAMPLE_RATE-", default_value=44100, enable_events=True),
            sg.Text(t("hz_label"), key="hz_label"),
            sg.Push(),
            sg.Text("", key="-DEVICE_SCAN_STATUS-", size=(8, 1)),
            sg.Button(t("refresh_devices_button"), key="-REFRESH_DEVICES-")
        ],
        [
            sg.Checkbox("", key="-NORMALIZE-", default=False, enable_events=True),
            sg.Text(t("normalize_label"), key="normalize_label"),
            sg.Combo(['-14.0 (YouTube)', '-15.0 (Twitch)', '-16.0 (Apple Music/TikTok)', '-23.0 (EBU R128)'], key="-NORMALIZE_TARGET-", default_value='-14.0 (YouTube)', size=(22, 1), enable_events=True, disabled=True),
            sg.Text(t("lufs_label"), key="lufs_label"), sg.Text('ⓘ', key='-LUFS_INFO-')
        ],
        [
            sg.Text(t("pitch_label"), key="pitch_label"),
            sg.Button("-", key="-PITCH_DOWN-", size=(2, 1)),
            sg.Slider(range=(-12, 12), default_value=0, orientation='h', size=(30, 15), key="-PITCH_SLIDER-", enable_events=True, resolution=1, disabled=False, expand_x=False, disable_number_display=False),
            sg.Button("+", key="-PITCH_UP-", size=(2, 1))
        ],
        [sg.Button(t("load_audio_button"), key="-LOAD-", disabled=True), sg.ProgressBar(max_value=100, orientation='h', size=(20, 20), key='-LOAD_PROGRESS-'), sg.Text("", key="-LOAD_STATUS-")],
        [sg.HSep()],
        [sg.Text(t("player_title"), key="player_title", font=(CUSTOM_FONT_NAME, 14))],
        [
            sg.Slider(range=(0, 0), orientation='h', size=(40, 15), key="-PROGRESS-", enable_events=True, resolution=0.1, disabled=True, disable_number_display=True, expand_x=True),
            sg.Text("00:00:00 / 00:00:00", key="-TIME_DISPLAY-")
        ],
        [
            sg.Button(t("rewind_button"), key="-REWIND-", disabled=True),
            sg.Button(t("play_button"), key="-PLAY_PAUSE-", disabled=True),
            sg.Button(t("forward_button"), key="-FORWARD-", disabled=True),
            sg.Button(t("stop_button"), key="-STOP-", disabled=True)
        ],
        [
            sg.Text(t("instrumental_volume_label"), size=(9, 1), pad=((0, 0), (15, 0))),
            sg.Slider(range=(0, 150), default_value=70, orientation='h', size=(30, 15), key="-INST_VOLUME-", enable_events=True, expand_x=False)
        ],
        [
            sg.Text(t("vocal_volume_label"), size=(9, 1), pad=((0, 0), (15, 0))),
            sg.Slider(range=(0, 150), default_value=100, orientation='h', size=(30, 15), key="-VOCAL_VOLUME-", enable_events=True, expand_x=False)
        ],
    ]

    layout = [
        [
            sg.Column(file_explorer_panel, expand_x=True, expand_y=True, key='-COL_EXPLORER-'),
            sg.VSep(),
            sg.Column([
                [sg.Column(vocal_separator_panel, expand_x=True, key='-COL_SEPARATOR-')],
                [sg.HSep()],
                [sg.Column(audio_player_panel, expand_x=True, key='-COL_PLAYER-')]
            ], expand_x=True, expand_y=True)
        ]
    ]
    return layout
