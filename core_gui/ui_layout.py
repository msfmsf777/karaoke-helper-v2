import FreeSimpleGUI as sg
import platform
import os
import sys
import tkinter as tk

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
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    font_path = resource_path(os.path.join("assets", CUSTOM_FONT_FILE))
    if platform.system() == "Windows" and os.path.exists(font_path):
        import ctypes
        gdi32 = ctypes.WinDLL('gdi32')
        if gdi32.AddFontResourceW(font_path) > 0:
            sg.set_options(font=(CUSTOM_FONT_NAME, 11))
    else:
        raise FileNotFoundError
except Exception:
    sg.set_options(font=("Helvetica", 10))

# --- Custom Tooltip Manager (using native tkinter.Toplevel) ---
class TooltipManager:
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
        if not self._tk_root: return
        
        # Destroy any existing tooltip
        self._hide()

        x = widget.winfo_rootx() + 25
        y = widget.winfo_rooty() + 20
        
        self._tooltip = tk.Toplevel(self._tk_root)
        self._tooltip.wm_overrideredirect(True) # Make it borderless
        self._tooltip.wm_geometry(f"+{x}+{y}")
        
        bg_color = sg.theme_background_color()
        text_color = sg.theme_text_color()
        
        label = tk.Label(self._tooltip, text=text, justify=tk.LEFT,
                         background=bg_color, relief=tk.SOLID, borderwidth=0,
                         foreground=text_color,
                         wraplength=300, # Prevents overly wide tooltips
                         font=(CUSTOM_FONT_NAME, 9)) # Use custom font
        label.pack(ipadx=5, ipady=3)

    def close(self):
        self._hide()

# --- UI Layout Definition (Traditional Chinese) ---

file_explorer_panel = [
    # Added small info icon 'ⓘ' with key '-EXPLORER_INFO-' for tooltip binding in main.py
    [sg.Text("檔案總管", font=(CUSTOM_FONT_NAME, 14)), sg.Text("ⓘ", key='-EXPLORER_INFO-', tooltip="檔案總管說明")],
    [
        sg.Button("◀", key="-BACK-", size=(2,1)),
        sg.Input("(尚未選擇資料夾)", key="-FOLDER_PATH-", readonly=True, expand_x=True, enable_events=True),
        sg.FolderBrowse("更改", key="-CHANGE_FOLDER-")
    ],
    [sg.Listbox(
        values=[],
        key="-FILE_LIST-",
        expand_y=True,
        expand_x=True,
        enable_events=True,
    )],
    [
        sg.Text("左鍵: 選擇伴奏", background_color='#a8d8ea', text_color='black', font=(CUSTOM_FONT_NAME, 9), pad=((0,5),(0,0))),
        sg.Text("右鍵: 選擇人聲", background_color='#f3c9d8', text_color='black', font=(CUSTOM_FONT_NAME, 9)),
        sg.Push(),
        sg.Button("打開資料夾", key="-OPEN_FOLDER-"),
        sg.Button("重新整理", key="-REFRESH-")
    ]
]

vocal_separator_panel = [
    # Title row: UVR included in title and GPU status immediately to its right
    [
        sg.Text("UVR人聲分離工具", font=(CUSTOM_FONT_NAME, 14)),
        sg.Text("GPU加速檢測中", key='-SEP_GPU_STATUS-', background_color='#e0e0e0', text_color='black', pad=((8,0),(0,0)))
    ],
    [sg.Text("歌曲檔案:"), sg.Input(key="-SONG_FILE-", expand_x=True, readonly=True), sg.FileBrowse("選擇檔案", file_types=(("音訊檔案", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma"),), key="-SONG_FILE_BROWSE-")],
    [
        sg.Button("開始分離", key="-START_SEPARATION-", size=(12,1)),
        sg.Button("設定", key="-OPEN_SEPARATOR_SETTINGS-", size=(8,1)),
        sg.Text("", key='-SET_MSG-', size=(20,1), text_color="lightgreen"),
    ],
    [
        sg.Text("狀態:", size=(4,1)),
        sg.Text("就緒", key="-SEPARATOR_STATUS-", expand_x=True),
        sg.Text("總進度:", pad=((8,0),(0,0))),
        sg.ProgressBar(100, orientation='h', size=(25, 12), key='-SEP_TOTAL_PROGRESS-', visible=False),
        sg.Text("", key='-SEP_TOTAL_PERCENT-')
    ],
]

audio_player_panel = [
    # Added small info icon 'ⓘ' with key '-PLAYER_INFO-' for tooltip binding in main.py
    [sg.Text("音訊加載器", font=(CUSTOM_FONT_NAME, 14)), sg.Text("ⓘ", key='-PLAYER_INFO-', tooltip="音訊加載器說明")],
    [sg.Text("伴奏:", size=(12,1)), sg.Text("(尚未選擇)", key="-INSTRUMENTAL_DISPLAY-", size=(30,1))],
    [sg.Text("人聲:", size=(12,1)), sg.Text("(尚未選擇)", key="-VOCAL_DISPLAY-", size=(30,1))],
    [
        sg.Text("耳機 (您會聽到):"), sg.Text('ⓘ', key='-INFO1-'),
        sg.Combo([], default_value="", key="-HEADPHONE-", size=(40,1), enable_events=True)
    ],
    [
        sg.Text("直播 (觀眾聽到):"), sg.Text('ⓘ', key='-INFO2-'),
        sg.Combo([], default_value="", key="-VIRTUAL-", size=(40,1), enable_events=True)
    ],
    [
        sg.Text("目標採樣率:"),
        sg.Combo([44100, 48000], key="-SAMPLE_RATE-", default_value=44100, enable_events=True),
        sg.Text("Hz"),
        sg.Push(),
        sg.Text("", key="-DEVICE_SCAN_STATUS-", size=(8,1)),
        sg.Button("刷新設備", key="-REFRESH_DEVICES-")
    ],
    [
        sg.Checkbox("", key="-NORMALIZE-", default=False, enable_events=True),
        sg.Text("將音量統一至"),
        sg.Combo(['-14.0 (YouTube)', '-15.0 (Twitch)', '-16.0 (Apple Music/TikTok)', '-23.0 (EBU R128)'], 
                 key="-NORMALIZE_TARGET-", default_value='-14.0 (YouTube)', size=(22,1), enable_events=True, disabled=True),
        sg.Text("LUFS"), sg.Text('ⓘ', key='-LUFS_INFO-')
    ],
    [
        sg.Text("音調 (Key):"),
        sg.Button("-", key="-PITCH_DOWN-", size=(2,1)),
        sg.Slider(range=(-12, 12), default_value=0, orientation='h', key="-PITCH_SLIDER-", enable_events=True, resolution=1, disabled=False, expand_x=True, disable_number_display=False),
        sg.Button("+", key="-PITCH_UP-", size=(2,1))
    ],
    [sg.Button("加載音訊", key="-LOAD-", disabled=True), sg.ProgressBar(max_value=100, orientation='h', size=(20, 20), key='-LOAD_PROGRESS-'), sg.Text("", key="-LOAD_STATUS-")],
    [sg.HSep()],
    [sg.Text("播放器", font=(CUSTOM_FONT_NAME, 14))],
    [
        sg.Slider(range=(0, 0), orientation='h', size=(40, 15), key="-PROGRESS-", enable_events=True, resolution=0.1, disabled=True, disable_number_display=True, expand_x=True),
        sg.Text("00:00:00 / 00:00:00", key="-TIME_DISPLAY-")
    ],
    [
        sg.Button("<<5秒", key="-REWIND-", disabled=True),
        sg.Button("播放", key="-PLAY_PAUSE-", disabled=True),
        sg.Button("5秒>>", key="-FORWARD-", disabled=True),
        sg.Button("停止", key="-STOP-", disabled=True)
    ],
    [
        sg.Text("伴奏音量 (%)"),
        sg.Slider(range=(0, 150), default_value=70, orientation='h', size=(20, 15), key="-INST_VOLUME-", enable_events=True, expand_x=True)
    ],
    [
        sg.Text("人聲音量 (%)"),
        sg.Slider(range=(0, 150), default_value=100, orientation='h', size=(20, 15), key="-VOCAL_VOLUME-", enable_events=True, expand_x=True)
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
