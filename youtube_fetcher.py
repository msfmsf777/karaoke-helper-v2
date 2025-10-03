from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import json
from pathlib import Path
from typing import Callable, Optional
from urllib.request import Request, urlopen


class DependencyError(RuntimeError):
    """Raised when a required external dependency is missing."""

    def __init__(self, dependency: str, message: Optional[str] = None) -> None:
        self.dependency = dependency
        super().__init__(message or dependency)


class DownloadCanceled(RuntimeError):
    """Raised when a download is cancelled by the user."""

    pass


class YTDownloader:
    """Thin wrapper around yt-dlp for downloading audio as WAV."""

    _REMOTE_CHECK_INTERVAL = 6 * 3600  # seconds
    _GITHUB_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
    _USER_AGENT = "KHelperV2/1.0"

    def __init__(self, storage_root: Optional[str] = None) -> None:
        self._ffmpeg_path: Optional[str] = None
        self._ytdlp_path: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._is_downloading = False
        self._cancel_requested = False
        self._storage_root = Path(storage_root) if storage_root else None
        self._remote_version_cache: Optional[tuple[str, str]] = None
        self._remote_cache_time = 0.0

    def is_downloading(self) -> bool:
        with self._lock:
            proc = self._process
            active = self._is_downloading
        return active and proc is not None and proc.poll() is None

    def cancel(self) -> None:
        with self._lock:
            self._cancel_requested = True
            proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _app_dir(self) -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _storage_dir(self) -> Optional[Path]:
        if not self._storage_root:
            return None
        try:
            self._storage_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        return self._storage_root

    def _target_ytdlp_path(self) -> Optional[Path]:
        storage = self._storage_dir()
        if not storage:
            return None
        return storage / 'yt-dlp.exe'

    def _version_file_path(self) -> Optional[Path]:
        storage = self._storage_dir()
        if not storage:
            return None
        return storage / 'yt-dlp.version'

    def _read_version_file(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding='utf-8').strip() or None
        except Exception:
            return None

    def _write_version_file(self, path: Path, version: str) -> None:
        try:
            path.write_text(version.strip(), encoding='utf-8')
        except Exception:
            pass

    def _probe_local_version(self, exe_path: Path) -> Optional[str]:
        try:
            completed = subprocess.run(
                [str(exe_path), '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                check=False
            )
        except Exception:
            return None
        output = (completed.stdout or completed.stderr or '').strip().splitlines()
        if not output:
            return None
        line = output[0].strip()
        return line or None

    def _normalize_version(self, version: Optional[str]) -> Optional[str]:
        if not version:
            return None
        cleaned = version.strip()
        if not cleaned:
            return None
        parts = cleaned.split()
        for part in reversed(parts):
            if any(ch.isdigit() for ch in part):
                return part
        return cleaned

    def _get_local_version(self, exe_path: Path) -> Optional[str]:
        version_file = self._version_file_path()
        if version_file:
            cached = self._read_version_file(version_file)
            if cached:
                return cached
        version_line = self._probe_local_version(exe_path)
        norm = self._normalize_version(version_line)
        if norm and version_file:
            self._write_version_file(version_file, norm)
        return norm or version_line

    def _get_remote_release_info(self) -> Optional[tuple[str, str]]:
        now = time.time()
        if self._remote_version_cache and (now - self._remote_cache_time) < self._REMOTE_CHECK_INTERVAL:
            return self._remote_version_cache
        info = None
        try:
            info = self._fetch_latest_release_info()
        except Exception:
            pass
        if info:
            self._remote_version_cache = info
            self._remote_cache_time = now
        return info or self._remote_version_cache

    def _fetch_latest_release_info(self) -> Optional[tuple[str, str]]:
        req = Request(self._GITHUB_RELEASE_API, headers={'User-Agent': self._USER_AGENT, 'Accept': 'application/vnd.github+json'})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8', 'replace'))
        tag = data.get('tag_name') or data.get('name')
        download_url = None
        for asset in data.get('assets', []):
            if asset.get('name') == 'yt-dlp.exe':
                download_url = asset.get('browser_download_url')
                break
        if not (tag and download_url):
            return None
        return tag, download_url

    def _download_ytdlp(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = Request(url, headers={'User-Agent': self._USER_AGENT})
        tmp_path: Optional[Path] = None
        try:
            with urlopen(req, timeout=120) as resp:
                with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent), suffix='.tmp') as tmp:
                    shutil.copyfileobj(resp, tmp)
                    tmp_path = Path(tmp.name)
            os.replace(tmp_path, dest)
            tmp_path = None
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def _ensure_latest_ytdlp(self) -> Optional[str]:
        target = self._target_ytdlp_path()
        if target is None:
            return None
        version_file = self._version_file_path()
        local_exists = target.is_file()
        remote_info = self._get_remote_release_info()
        remote_version = None
        remote_url = None
        if remote_info:
            remote_version, remote_url = remote_info
        if not local_exists:
            if remote_url:
                try:
                    self._download_ytdlp(remote_url, target)
                    if remote_version and version_file:
                        norm_remote = self._normalize_version(remote_version) or remote_version
                        self._write_version_file(version_file, norm_remote)
                    return str(target)
                except Exception:
                    if target.exists():
                        return str(target)
                    return None
            return None
        local_version = self._get_local_version(target)
        remote_norm = self._normalize_version(remote_version)
        if remote_norm and remote_url and (not local_version or remote_norm != local_version):
            try:
                self._download_ytdlp(remote_url, target)
                if version_file:
                    self._write_version_file(version_file, remote_norm)
                local_version = remote_norm
            except Exception:
                pass
        elif local_version and version_file and not version_file.exists():
            self._write_version_file(version_file, local_version)
        return str(target)

    def _resolve_ffmpeg(self) -> Optional[str]:
        if self._ffmpeg_path and os.path.isfile(self._ffmpeg_path):
            return self._ffmpeg_path
        bundled = Path(self._app_dir()) / "ffmpeg" / "bin" / "ffmpeg.exe"
        if bundled.is_file():
            self._ffmpeg_path = str(bundled)
            return self._ffmpeg_path
        found = shutil.which("ffmpeg")
        if found:
            self._ffmpeg_path = found
            return self._ffmpeg_path
        return None

    def _resolve_ytdlp(self) -> Optional[str]:
        if self._ytdlp_path and os.path.isfile(self._ytdlp_path):
            return self._ytdlp_path
        ensured = None
        try:
            ensured = self._ensure_latest_ytdlp()
        except Exception:
            ensured = None
        if ensured and os.path.isfile(ensured):
            self._ytdlp_path = ensured
            return self._ytdlp_path
        bundled = Path(self._app_dir()) / "yt-dlp.exe"
        if bundled.is_file():
            self._ytdlp_path = str(bundled)
            return self._ytdlp_path
        found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if found:
            self._ytdlp_path = found
            return self._ytdlp_path
        return None

    def download_best_audio_to_wav(
        self,
        url: str,
        out_dir: str,
        target_sr: int,
        on_progress: Optional[Callable[[int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Download a YouTube URL as a stereo WAV file and return the path."""
        ytdlp_path = self._resolve_ytdlp()
        if not ytdlp_path:
            raise DependencyError("ytdlp", "yt-dlp executable not found")
        ffmpeg_path = self._resolve_ffmpeg()
        if not ffmpeg_path:
            raise DependencyError("ffmpeg", "ffmpeg executable not found")

        try:
            target_sr_int = int(target_sr)
        except Exception:
            target_sr_int = 44100
        if target_sr_int <= 0:
            target_sr_int = 44100

        os.makedirs(out_dir, exist_ok=True)
        output_template = str(Path(out_dir) / "%(title)s [%(id)s].%(ext)s")

        cmd = [
            ytdlp_path,
            "-f",
            "bestaudio/best",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "wav",
            "--postprocessor-args",
            f"-ar {target_sr_int} -ac 2",
            "--output",
            output_template,
            url,
        ]

        if ffmpeg_path:
            ffmpeg_arg = ffmpeg_path if ffmpeg_path.lower().endswith("ffmpeg.exe") else ffmpeg_path
            cmd.extend(["--ffmpeg-location", ffmpeg_arg])

        temp_patterns = ('*.part', '*.tmp')
        before_temp = {p.name for pattern in temp_patterns for p in Path(out_dir).glob(pattern)}

        progress_regex = re.compile(r"(\d+(?:\.\d+)?)%")
        final_path: Optional[str] = None
        log_lines: list[str] = []
        process: Optional[subprocess.Popen] = None
        success = False

        if on_progress:
            on_progress(0)

        try:
            with self._lock:
                if self._is_downloading:
                    raise RuntimeError("download already in progress")
                self._is_downloading = True
                self._cancel_requested = False

            popen_kwargs = dict(
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                try:
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                except Exception:
                    pass
                popen_kwargs["startupinfo"] = startupinfo
                create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if create_no_window:
                    popen_kwargs["creationflags"] = create_no_window
            process = subprocess.Popen(cmd, **popen_kwargs)

            with self._lock:
                self._process = process

            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.strip()
                log_lines.append(line)
                if on_log and line:
                    on_log(line)
                match = progress_regex.search(line)
                if match and on_progress:
                    try:
                        pct = float(match.group(1))
                        on_progress(max(0, min(100, int(pct))))
                    except Exception:
                        pass
                if "Destination:" in line:
                    possible = line.split("Destination:", 1)[1].strip().strip('"')
                    if possible:
                        final_path = possible

            return_code = process.wait()
            if process.stdout:
                process.stdout.close()

            if self._cancel_requested:
                raise DownloadCanceled("cancelled")

            if return_code != 0:
                tail = "\n".join(log_lines[-5:]) if log_lines else ""
                raise RuntimeError(f"yt-dlp failed: {tail}")

            if on_progress:
                on_progress(100)

            if not final_path or not os.path.isfile(final_path):
                final_path = self._find_latest_wav(out_dir)

            if not final_path or not os.path.isfile(final_path):
                raise RuntimeError("Downloaded WAV file not found")

            success = True
            return os.path.abspath(final_path)

        finally:
            if process and process.stdout and not process.stdout.closed:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            with self._lock:
                proc = self._process
                self._process = None
                self._is_downloading = False
                self._cancel_requested = False
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            if not success:
                for pattern in temp_patterns:
                    for temp_file in Path(out_dir).glob(pattern):
                        if temp_file.name not in before_temp:
                            try:
                                temp_file.unlink()
                            except Exception:
                                pass
                if final_path and os.path.isfile(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass

    def _find_latest_wav(self, folder: str) -> Optional[str]:
        try:
            wav_files = [
                Path(folder) / entry
                for entry in os.listdir(folder)
                if entry.lower().endswith('.wav')
            ]
        except Exception:
            return None
        if not wav_files:
            return None
        wav_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(wav_files[0])

