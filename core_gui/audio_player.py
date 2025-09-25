# audio_player.py
import threading
import time
import numpy as np
from pydub import AudioSegment
import sounddevice as sd
import FreeSimpleGUI as sg
import os
import traceback
import stftpitchshift
from concurrent.futures import ProcessPoolExecutor
import pyloudnorm as pyln

# Added stdlib imports used previously for ffmpeg fallback (kept if present)
import subprocess
import tempfile
import shutil


class AudioPlayer:
    """
    Thread-safe audio loader + preview player.
    Performs real-time mixing of separate vocal and instrumental tracks.

    Improvements:
    - Robust seek handling: debounced and accumulative while playing to avoid
      spawning many restart threads during rapid skip presses.
    """

    def __init__(self, window, debug=False):
        self.window = window
        self.debug = debug
        self.audio_loaded = False
        self.vocal_audio_data = None
        self.instrumental_audio_data = None
        self.sample_rate = 44100
        self.duration = 0.0
        self.position = 0.0
        self.headphone_device_id = None
        self.virtual_device_id = None
        self.headphone_stream = None
        self.virtual_stream = None
        self.playing = False
        self._hp_frame = [0]
        self._vp_frame = [0]
        self._stream_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self.instrumental_volume = 0.7
        self.vocal_volume = 1.0
        self.last_error = ""

        # Seeking/debounce helpers
        self._seek_lock = threading.Lock()
        # pending absolute target (None if not used)
        self._pending_seek_absolute = None
        # pending relative accumulation in seconds (sum of quick +5/-5 presses)
        self._pending_seek_delta = 0.0
        # debounce timer object (threading.Timer)
        self._seek_timer = None
        # debounce interval (seconds)
        self._seek_debounce = 0.15

    def _dbg(self, msg: str):
        if not self.debug:
            return
        try:
            print(f"[AudioPlayer DEBUG] {msg}")
            self.window.write_event_value("-PLAYER_DEBUG-", msg)
        except Exception:
            pass

    @staticmethod
    def _normalize_channel(data, rate, target_lufs):
        """
        Normalize a single-channel 1-D numpy array to target LUFS using pyloudnorm.
        Returns the normalized 1-D numpy array.
        """
        meter = pyln.Meter(rate)
        loudness = meter.integrated_loudness(data)
        normalized_audio = pyln.normalize.loudness(data, loudness, target_lufs)
        return normalized_audio

    @staticmethod
    def _pitch_shift_channel(channel_data, factor, sample_rate):
        shifter = stftpitchshift.StftPitchShift(framesize=2048, hopsize=512, samplerate=sample_rate)
        shifted_channel = shifter.shiftpitch(channel_data, factors=[factor])
        return shifted_channel

    def mark_needs_reload(self):
        try:
            self.stop_immediate_async()
        except Exception:
            pass
        self.audio_loaded = False
        try:
            self.window.write_event_value("-AUDIO_NEEDS_RELOAD-", True)
        except Exception:
            pass

    def load_audio(self, instrumental_path, vocal_path, pitch_semitones=0, sample_rate=44100, normalize=False, target_lufs=-14.0):
        threading.Thread(target=self._load_worker, args=(instrumental_path, vocal_path, pitch_semitones, sample_rate, normalize, target_lufs), daemon=True).start()

    def _ensure_stereo_float32(self, arr):
        """
        Ensure arr is a (n,2) float32 numpy array, convert/expand if necessary,
        and remove NaNs/Infs. This guards against unexpected shapes/dtypes returned
        from processing steps.
        """
        a = np.asarray(arr)
        if a.ndim == 1:
            a = np.repeat(a.reshape(-1, 1), 2, axis=1)
        elif a.ndim == 2:
            if a.shape[1] == 1:
                a = np.repeat(a, 2, axis=1)
            elif a.shape[1] >= 2:
                a = a[:, :2]
            else:
                # Unexpected shape, coerce to zeros
                a = np.zeros((a.shape[0], 2), dtype=np.float32)
        else:
            # Unexpected dim, coerce to empty
            a = np.zeros((0, 2), dtype=np.float32)

        # remove NaNs / Infs and ensure float32
        a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
        return a.astype(np.float32, copy=False)

    def _load_worker(self, instrumental_path, vocal_path, pitch_semitones, sample_rate, normalize, target_lufs):
        try:
            self.sample_rate = sample_rate
            self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (0, "讀取音訊檔案..."))
            if not instrumental_path or not os.path.exists(instrumental_path):
                raise RuntimeError("伴奏檔案不存在")
            if not vocal_path or not os.path.exists(vocal_path):
                raise RuntimeError("人聲檔案不存在")

            # helper: try loading via pydub; on failure, transcode with ffmpeg to PCM16 WAV then load
            def _load_with_ffmpeg(path, target_sr):
                try:
                    seg = AudioSegment.from_file(path).set_channels(2).set_frame_rate(target_sr)
                    return seg
                except Exception as e_load:
                    # pydub load failed — attempt an ffmpeg transcode to PCM16 wav as a robust fallback
                    try:
                        self._dbg(f"AudioSegment.from_file failed for {path}: {e_load}. Attempting ffmpeg->pcm_s16le fallback.")
                    except Exception:
                        pass
                    ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
                    tmpf = None
                    try:
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                        tmpf = tmp.name
                        tmp.close()
                        cmd = [
                            ffmpeg_exe, "-y", "-loglevel", "error",
                            "-i", path,
                            "-ac", "2",
                            "-ar", str(target_sr),
                            "-c:a", "pcm_s16le",
                            tmpf
                        ]
                        try:
                            proc = subprocess.run(cmd, capture_output=True, text=True)
                        except FileNotFoundError as fnf:
                            # ffmpeg not found in PATH
                            raise RuntimeError(f"ffmpeg not found for fallback transcode: {fnf}")
                        if proc.returncode != 0:
                            # include stderr for debug but raise so upstream handles it
                            raise RuntimeError(f"ffmpeg transcode failed: {proc.stderr.strip() or proc.stdout.strip()}")
                        seg = AudioSegment.from_file(tmpf).set_channels(2).set_frame_rate(target_sr)
                        return seg
                    finally:
                        if tmpf:
                            try:
                                os.unlink(tmpf)
                            except Exception:
                                pass

            # Load instrumental (with fallback)
            bg_audio = _load_with_ffmpeg(instrumental_path, self.sample_rate)
            self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (15, "讀取音訊檔案..."))

            # Load vocal (with fallback)
            vocal_audio = _load_with_ffmpeg(vocal_path, self.sample_rate)
            self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (30, "轉換音訊格式..."))

            vocal_samples = np.array(vocal_audio.get_array_of_samples(), dtype=np.int16).astype(np.float32) / 32768.0
            instrumental_samples = np.array(bg_audio.get_array_of_samples(), dtype=np.int16).astype(np.float32) / 32768.0

            vocal_data = vocal_samples.reshape((-1, 2)) if vocal_audio.channels == 2 else np.repeat(vocal_samples.reshape((-1, 1)), 2, axis=1)
            instrumental_data = instrumental_samples.reshape((-1, 2)) if bg_audio.channels == 2 else np.repeat(instrumental_samples.reshape((-1, 1)), 2, axis=1)

            # --- Start of Processing Pipeline ---
            processed_vocal = vocal_data.copy()
            processed_instrumental = instrumental_data.copy()

            if normalize:
                # Update progress in UI
                self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (45, "音量標準化..."))
                # Normalize per-channel to avoid potential multidimensional edge-cases in pyloudnorm
                try:
                    inst_l = processed_instrumental[:, 0].copy()
                    inst_r = processed_instrumental[:, 1].copy()
                    inst_l = AudioPlayer._normalize_channel(inst_l, self.sample_rate, target_lufs)
                    inst_r = AudioPlayer._normalize_channel(inst_r, self.sample_rate, target_lufs)
                    processed_instrumental = np.stack((inst_l, inst_r), axis=1)

                    voc_l = processed_vocal[:, 0].copy()
                    voc_r = processed_vocal[:, 1].copy()
                    voc_l = AudioPlayer._normalize_channel(voc_l, self.sample_rate, target_lufs)
                    voc_r = AudioPlayer._normalize_channel(voc_r, self.sample_rate, target_lufs)
                    processed_vocal = np.stack((voc_l, voc_r), axis=1)
                except Exception as e:
                    # Keep debug information but re-raise; we avoid swallowing errors silently.
                    self._dbg(f"Normalization failed: {e}")
                    raise

            if pitch_semitones != 0:
                self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (65, "音訊升降調..."))
                factor = 2**(pitch_semitones / 12.0)

                # We send copies to the parallel processes to be safe
                tasks = [processed_vocal[:, 0].copy(), processed_vocal[:, 1].copy(),
                         processed_instrumental[:, 0].copy(), processed_instrumental[:, 1].copy()]

                with ProcessPoolExecutor() as executor:
                    futures = [executor.submit(AudioPlayer._pitch_shift_channel, channel, factor, self.sample_rate) for channel in tasks]
                    results = [f.result() for f in futures]

                self.window.write_event_value("-LOAD_PROGRESS_EVENT-", (90, "混合音訊..."))
                shifted_vocal_l, shifted_vocal_r, shifted_inst_l, shifted_inst_r = results

                min_len_v = min(len(shifted_vocal_l), len(shifted_vocal_r))
                processed_vocal = np.stack((shifted_vocal_l[:min_len_v], shifted_vocal_r[:min_len_v]), axis=1)

                min_len_i = min(len(shifted_inst_l), len(shifted_inst_r))
                processed_instrumental = np.stack((shifted_inst_l[:min_len_i], shifted_inst_r[:min_len_i]), axis=1)

            # --- End of Processing Pipeline ---

            # Ensure both channels are proper (n,2) float32 arrays and have no NaN/Inf
            processed_instrumental = self._ensure_stereo_float32(processed_instrumental)
            processed_vocal = self._ensure_stereo_float32(processed_vocal)

            with self._stream_lock:
                self.instrumental_audio_data = processed_instrumental
                self.vocal_audio_data = processed_vocal
                self.duration = float(len(self.instrumental_audio_data)) / float(self.sample_rate)
                self.position = 0.0
                self._hp_frame[0] = 0
                self._vp_frame[0] = 0

            self.audio_loaded = True
            self.window.write_event_value("-LOAD_DONE-", True)
            self._dbg(f"Load complete: duration {self.duration:.1f}s")
        except Exception as e:
            tb = traceback.format_exc()
            errmsg = f"ERROR: 無法載入音訊: {e}\n{tb}"
            print(errmsg)
            try:
                self.window.write_event_value("-LOAD_DONE-", "ERROR: 無法載入音訊: " + str(e))
            except Exception:
                pass

    def _hp_callback(self, outdata, frames, time_info, status):
        try:
            start = int(self._hp_frame[0])

            inst_data = self.instrumental_audio_data
            voc_data = self.vocal_audio_data

            if inst_data is None or voc_data is None:
                outdata.fill(0)
                raise sd.CallbackStop

            inst_len = len(inst_data)
            inst_chunk = np.zeros((frames, 2), dtype=np.float32)
            if start < inst_len:
                available = min(frames, inst_len - start)
                inst_slice = inst_data[start: start + available]
                if inst_slice.ndim == 1:
                    inst_chunk[:available] = np.repeat(inst_slice.reshape(-1, 1), 2, axis=1)
                else:
                    inst_chunk[:available] = inst_slice

            voc_len = len(voc_data)
            voc_chunk = np.zeros((frames, 2), dtype=np.float32)
            if start < voc_len:
                available = min(frames, voc_len - start)
                voc_slice = voc_data[start: start + available]
                if voc_slice.ndim == 1:
                    voc_chunk[:available] = np.repeat(voc_slice.reshape(-1, 1), 2, axis=1)
                else:
                    voc_chunk[:available] = voc_slice

            mixed_chunk = (inst_chunk * self.instrumental_volume) + (voc_chunk * self.vocal_volume)
            np.clip(mixed_chunk, -1.0, 1.0, out=mixed_chunk)

            outdata[:] = mixed_chunk
            self._hp_frame[0] = start + frames

            if start >= inst_len and start >= voc_len:
                raise sd.CallbackStop

        except sd.CallbackStop:
            raise
        except Exception:
            outdata.fill(0)
            raise sd.CallbackStop

    def _vp_callback(self, outdata, frames, time_info, status):
        try:
            start = int(self._vp_frame[0])
            data = self.instrumental_audio_data
            if data is None:
                outdata.fill(0)
                raise sd.CallbackStop

            available = len(data)
            if start >= available:
                outdata.fill(0)
                raise sd.CallbackStop

            chunk = np.zeros((frames, 2), dtype=np.float32)
            num_frames_to_copy = min(frames, available - start)
            slice_data = data[start: start + num_frames_to_copy]
            if slice_data.ndim == 1:
                slice_data = np.repeat(slice_data.reshape(-1, 1), 2, axis=1)
            chunk[:num_frames_to_copy] = slice_data

            outdata[:] = chunk * self.instrumental_volume
            self._vp_frame[0] = start + frames

        except sd.CallbackStop:
            raise
        except Exception:
            outdata.fill(0)
            raise sd.CallbackStop

    def _close_streams(self):
        with self._stream_lock:
            if self.headphone_stream:
                try: self.headphone_stream.stop()
                except Exception: pass
                try: self.headphone_stream.close()
                except Exception: pass
                self.headphone_stream = None

            if self.virtual_stream:
                try: self.virtual_stream.stop()
                except Exception: pass
                try: self.virtual_stream.close()
                except Exception: pass
                self.virtual_stream = None

            self.playing = False
            self._dbg("Streams closed (background)")

    def _open_streams(self, start_frame_index=0):
        started_any = False
        self.last_error = ""
        with self._stream_lock:
            self._hp_frame[0] = int(start_frame_index)
            self._vp_frame[0] = int(start_frame_index)

        try:
            hp_stream = sd.OutputStream(
                samplerate=self.sample_rate, device=self.headphone_device_id,
                channels=2, dtype='float32', callback=self._hp_callback)
            hp_stream.start()
            with self._stream_lock:
                self.headphone_stream = hp_stream
            started_any = True
            self._dbg(f"Opened headphone stream (device id {self.headphone_device_id})")
        except Exception as e:
            self.last_error = f"耳機: {e}"
            self._dbg(f"Failed to open headphone stream: {e}")

        try:
            if self.virtual_device_id is not None and self.virtual_device_id != self.headphone_device_id:
                vp_stream = sd.OutputStream(
                    samplerate=self.sample_rate, device=self.virtual_device_id,
                    channels=2, dtype='float32', callback=self._vp_callback)
                vp_stream.start()
                with self._stream_lock:
                    self.virtual_stream = vp_stream
                started_any = True
                self._dbg(f"Opened virtual stream (device id {self.virtual_device_id})")
        except Exception as e:
            error_msg = f"虛擬: {e}"
            self.last_error += f"\n{error_msg}" if self.last_error else error_msg
            self._dbg(f"Failed to open virtual stream: {e}")

        if not started_any:
            self._dbg("Failed to start any audio streams.")
            return False

        self.playing = True
        return True

    def stop_immediate_async(self):
        threading.Thread(target=self._close_streams, daemon=True).start()

    def _restart_at_position_background(self, seconds: float):
        # Use restart lock to ensure only one restart happens at a time
        with self._restart_lock:
            self._dbg(f"Restarting at position {seconds:.3f}s (background) - begin")
            self._close_streams()
            frame_index = int(seconds * self.sample_rate)
            if self._open_streams(start_frame_index=frame_index):
                with self._stream_lock:
                    self.position = float(frame_index) / float(self.sample_rate)
                threading.Thread(target=self._playback_monitor, daemon=True).start()
                self._dbg("Restarted streams successfully")
            else:
                self.playing = False
                self.window.write_event_value('-PLAYBACK_ERROR-', self.last_error)
                self._dbg("Restart failed — could not open streams")
            self._dbg(f"Restarting at position {seconds:.3f}s (background) - end")

    def play_pause(self):
        if not self.audio_loaded: return
        if self.playing:
            self._dbg("play_pause -> stopping (async)")
            self.stop_immediate_async()
            return

        frame_index = int(self.position * self.sample_rate)
        self._dbg(f"play_pause -> starting (background) at {self.position:.3f}s (frame {frame_index})")

        def _start_bg():
            if not self._open_streams(start_frame_index=frame_index):
                self.playing = False
                self.window.write_event_value('-PLAYBACK_ERROR-', self.last_error)
                self._dbg(f"Failed to open output devices: {self.last_error}")
            else:
                threading.Thread(target=self._playback_monitor, daemon=True).start()

        threading.Thread(target=_start_bg, daemon=True).start()
        self.playing = True

    def stop_immediate(self):
        self._close_streams()
        self._dbg("stop_immediate completed (sync)")

    def _schedule_seek_action(self):
        """
        Internal: schedules/starts the debounce timer that will perform the pending seek.
        Must be called while holding _seek_lock or in a thread-safe context.
        Cancels existing timer if present.
        """
        # Cancel existing timer safely
        try:
            if self._seek_timer:
                try:
                    self._seek_timer.cancel()
                except Exception:
                    pass
                self._seek_timer = None
        except Exception:
            pass

        # Start a new timer
        def _on_timer():
            try:
                self._perform_pending_seek()
            except Exception as e:
                self._dbg(f"_on_timer exception: {e}")

        self._seek_timer = threading.Timer(self._seek_debounce, _on_timer)
        self._seek_timer.daemon = True
        self._seek_timer.start()
        self._dbg("Seek debounce timer started")

    def _perform_pending_seek(self):
        """
        Called from debounce timer thread to execute the pending seek.
        Computes final target from pending absolute or accumulated delta,
        then calls restart procedure (in background) and clears pending state.
        """
        with self._seek_lock:
            # capture pending values and reset immediately
            pending_abs = self._pending_seek_absolute
            pending_delta = self._pending_seek_delta
            self._pending_seek_absolute = None
            self._pending_seek_delta = 0.0
            # clear timer reference
            try:
                self._seek_timer = None
            except Exception:
                pass

        # Determine final target
        if pending_abs is not None:
            target = pending_abs
            self._dbg(f"Performing pending absolute seek to {target:.3f}s")
        else:
            # relative delta: compute from most recent known position
            # Use latest hp_frame if possible to estimate current playback position
            try:
                with self._stream_lock:
                    cur_frame = int(self._hp_frame[0])
                    cur_pos = float(cur_frame) / float(self.sample_rate)
            except Exception:
                cur_pos = float(self.position)
            target = cur_pos + pending_delta
            self._dbg(f"Performing pending relative seek delta {pending_delta:.3f}s from {cur_pos:.3f}s -> target {target:.3f}s")

        # clamp
        target = max(0.0, min(target, self.duration))

        # Perform restart in a dedicated background thread (keeps UI responsive)
        threading.Thread(target=self._restart_at_position_background, args=(target,), daemon=True).start()

    def seek(self, seconds: float):
        """
        Public seek API. If paused -> instant apply position update synchronously.
        If playing -> schedule debounced restart (accumulates rapid presses).
        """
        if not self.audio_loaded:
            return
        seconds = max(0.0, min(seconds, self.duration))

        if not self.playing:
            # immediate update while paused
            with self._stream_lock:
                self.position = seconds
                frame = int(seconds * self.sample_rate)
                self._hp_frame[0] = frame
                self._vp_frame[0] = frame
            self._dbg(f"seek (paused) -> position {seconds:.3f}s")
        else:
            # schedule a debounced absolute seek while playing
            with self._seek_lock:
                # set absolute target and clear accumulated delta to prefer the slider/directed seek
                self._pending_seek_absolute = seconds
                self._pending_seek_delta = 0.0
                self._schedule_seek_action()
            self._dbg(f"seek (playing) -> scheduled absolute seek to {seconds:.3f}s (debounced)")

    def _adjust_pending_seek_delta(self, delta_seconds: float):
        """
        Adjust the pending relative delta while playing. This accumulates multiple
        quick presses (e.g. +5 +5 +5 -> +15) and debounces the actual restart.
        """
        if not self.audio_loaded:
            return

        if not self.playing:
            # if paused, simply adjust position immediately
            new_pos = max(0.0, min(self.position + delta_seconds, self.duration))
            with self._stream_lock:
                self.position = new_pos
                frame = int(new_pos * self.sample_rate)
                self._hp_frame[0] = frame
                self._vp_frame[0] = frame
            self._dbg(f"adjust_pending_seek_delta (paused) -> new position {new_pos:.3f}s")
            return

        with self._seek_lock:
            # If an absolute pending seek exists, convert it to a relative base then accumulate
            if self._pending_seek_absolute is not None:
                base = self._pending_seek_absolute
                self._pending_seek_absolute = None
                self._pending_seek_delta = base - self.position

            # accumulate delta
            self._pending_seek_delta += delta_seconds
            self._dbg(f"Accumulated pending seek delta now {self._pending_seek_delta:.3f}s (added {delta_seconds:.3f}s)")

            # reschedule debounce timer
            self._schedule_seek_action()

    def rewind_5sec(self):
        # use delta adjust to aggregate quick presses
        self._adjust_pending_seek_delta(-5.0)

    def forward_5sec(self):
        # use delta adjust to aggregate quick presses
        self._adjust_pending_seek_delta(5.0)

    def _playback_monitor(self):
        while self.playing:
            try:
                cur_frame = int(self._hp_frame[0])
                self.position = float(cur_frame) / float(self.sample_rate)
            except Exception:
                pass
            time.sleep(1.0)

            with self._stream_lock:
                hp_active = self.headphone_stream and self.headphone_stream.active
                vp_active = self.virtual_stream and self.virtual_stream.active

            if not hp_active and not vp_active:
                break

        if self.playing:  # If loop broke but still marked as playing, it was end of stream
            self.playing = False
            self.window.write_event_value("-PLAYBACK_ENDED-", True)

        self._dbg("playback monitor ending — closing streams")
        self._close_streams()

    def format_time(self, seconds: float) -> str:
        try:
            s = int(round(seconds))
            h = s // 3600
            m = (s % 3600) // 60
            sec = s % 60
            return f"{h:02d}:{m:02d}:{sec:02d}"
        except Exception:
            return "00:00:00"
