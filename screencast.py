# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated
# all copyright and related and neighboring rights to this software to the public
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software.
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import ctypes
import os
import subprocess
import threading
from ctypes import wintypes
from datetime import datetime

import sculptforge as sf

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
FRAMERATE = 30
# ---------------------------------------------------------------------------

_process = None
_lock = threading.Lock()
_output_dir = os.path.join(os.path.expanduser("~"), "Desktop")


def _ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


def _window_rect():
    """Return (left, top, width, height) of the SculptForge window, or None."""
    try:
        handle = sf.ui.main_window_handle()
    except Exception:
        return None
    if not handle:
        return None
    hwnd = int(handle)
    try:
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return rect.left, rect.top, w, h
    except Exception:
        return None


def _capture_region():
    """ffmpeg arguments that capture only the SculptForge window."""
    region = _window_rect()
    if region is None:
        # Fall back to the whole desktop.
        return ["-f", "gdigrab", "-framerate", str(FRAMERATE), "-i", "desktop"]
    left, top, w, h = region
    # yuv420p needs even dimensions.
    w -= w % 2
    h -= h % 2
    if w <= 0 or h <= 0:
        return ["-f", "gdigrab", "-framerate", str(FRAMERATE), "-i", "desktop"]
    return ["-f", "gdigrab", "-framerate", str(FRAMERATE),
            "-offset_x", str(left), "-offset_y", str(top),
            "-video_size", "%dx%d" % (w, h), "-i", "desktop"]


def _pick_folder():
    """Show a Windows folder picker and return the chosen path (or None)."""
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        try:
            class BROWSEINFO(ctypes.Structure):
                _fields_ = [
                    ("hwndOwner", wintypes.HWND),
                    ("pidlRoot", ctypes.c_void_p),
                    ("pszDisplayName", ctypes.c_wchar_p),
                    ("lpszTitle", ctypes.c_wchar_p),
                    ("ulFlags", ctypes.c_uint),
                    ("lpfn", ctypes.c_void_p),
                    ("lParam", ctypes.c_void_p),
                    ("iImage", ctypes.c_int),
                ]

            BIF_RETURNONLYFSDIRS = 0x00000001
            BIF_NEWDIALOGSTYLE = 0x00000040
            bi = BROWSEINFO()
            bi.lpszTitle = "Choose the folder where videos are saved"
            bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
            pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
            if not pidl:
                return None
            buf = ctypes.create_unicode_buffer(260)
            if shell32.SHGetPathFromIDListW(pidl, buf):
                path = buf.value
            else:
                path = None
            ole32.CoTaskMemFree(pidl)
            return path if path else None
        finally:
            ole32.CoUninitialize()
    except Exception as exc:
        print("Screen cast: folder picker failed (%s)." % exc)
        return None


def _set_output_dir(path):
    global _output_dir
    if path:
        _output_dir = path
        print("Screen cast: output folder set to %s" % _output_dir)


def _start_recording():
    global _process
    with _lock:
        if _process is not None and _process.poll() is None:
            print("Screen cast: already recording, press Stop first.")
            return
        if not _ffmpeg_available():
            print("Screen cast: ffmpeg was not found on PATH.")
            print("  Install it (https://ffmpeg.org) and make sure 'ffmpeg' runs")
            print("  from a terminal, then try again.")
            return
        os.makedirs(_output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_output_dir, "sculptforge_%s.mp4" % stamp)
        cmd = ["ffmpeg", "-y"] + _capture_region() + [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p", path,
        ]
        try:
            _process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except Exception as exc:
            _process = None
            print("Screen cast: could not start ffmpeg (%s)." % exc)
            return
        print("Screen cast: recording the SculptForge window to %s" % path)
        print("  Keep the window in place; press 'Stop recording' to save.")


def _stop_recording():
    global _process
    with _lock:
        proc = _process
        _process = None
    if proc is None or proc.poll() is not None:
        print("Screen cast: nothing is recording.")
        return
    try:
        proc.stdin.write(b"q")
        proc.stdin.flush()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    print("Screen cast: saved.")


def _open_folder():
    os.makedirs(_output_dir, exist_ok=True)
    try:
        os.startfile(_output_dir)
    except Exception:
        try:
            subprocess.Popen(["explorer", _output_dir])
        except Exception as exc:
            print("Screen cast: could not open the folder (%s)." % exc)


def _choose_folder():
    path = _pick_folder()
    if path:
        _set_output_dir(path)


def _declare_ui():
    sf.ui.action("screencast.record", "Record", _start_recording, icon="play",
                 help="Start recording the SculptForge window with ffmpeg")
    sf.ui.action("screencast.stop", "Stop", _stop_recording, icon="scissors",
                 help="Stop recording and save the video")
    sf.ui.action("screencast.folder", "Folder", _open_folder, icon="download",
                 help="Open the folder where videos are saved")
    sf.ui.action("screencast.choose", "Choose", _choose_folder, icon="box",
                 help="Choose the folder where videos are saved")

    panel = sf.ui.panel("screencast", "Screen cast")
    panel.label("Record the SculptForge window (ffmpeg)")
    panel.label("Output folder: %s" % _output_dir)
    panel.separator()
    panel.button("screencast.record", label="Record")
    panel.button("screencast.stop", label="Stop")
    panel.button("screencast.choose", label="Choose folder")
    panel.button("screencast.folder", label="Open folder")
    panel.separator()
    panel.label("Keep the window in place while recording.")

    sf.ui.place("screencast.record", "top")
    sf.ui.place("screencast", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Screen cast: 'Record', 'Stop', 'Choose folder' and 'Open folder' added.")
else:
    print("Screen cast: sf.ui missing; call _start_recording() / _stop_recording() "
          "from the console.")
