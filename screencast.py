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
import time
from ctypes import wintypes
from datetime import datetime

import sculptforge as sf

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
FRAMERATE = 20
# ---------------------------------------------------------------------------

_process = None
_capture_thread = None
_stop_flag = threading.Event()
_lock = threading.Lock()
_output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
_log_path = None


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


def _capture_loop(hwnd, width, height, proc, stop_event):
    """Capture the window's pixels and feed them to ffmpeg (rawvideo)."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    BI_RGB = 0

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER)]

    hdc = user32.GetWindowDC(hwnd)
    if not hdc:
        return
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 24
    bmi.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                 ctypes.byref(bits), None, 0)
    if not hbmp or not bits.value:
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)
        return
    gdi32.SelectObject(memdc, hbmp)
    stride = ((width * 3 + 3) // 4) * 4
    interval = 1.0 / FRAMERATE
    try:
        while not stop_event.is_set():
            t0 = time.time()
            gdi32.BitBlt(memdc, 0, 0, width, height, hdc, 0, 0, SRCCOPY)
            data = ctypes.string_at(bits.value, stride * height)
            if stride == width * 3:
                proc.stdin.write(data)
            else:
                tight = bytearray(width * 3 * height)
                for y in range(height):
                    tight[y * width * 3:(y + 1) * width * 3] = \
                        data[y * stride:(y * stride + width * 3)]
                proc.stdin.write(tight)
            proc.stdin.flush()
            dt = time.time() - t0
            if dt < interval:
                time.sleep(interval - dt)
    except (BrokenPipeError, OSError):
        pass
    finally:
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)


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
    global _process, _capture_thread, _log_path
    with _lock:
        if _process is not None and _process.poll() is None:
            print("Screen cast: already recording, press Stop first.")
            return
        if not _ffmpeg_available():
            print("Screen cast: ffmpeg was not found on PATH.")
            print("  Install it (https://ffmpeg.org) and make sure 'ffmpeg' runs")
            print("  from a terminal, then try again.")
            return
        rect = _window_rect()
        if rect is None:
            print("Screen cast: could not read the SculptForge window position.")
            return
        left, top, w, h = rect
        # yuv420p needs even dimensions.
        w -= w % 2
        h -= h % 2
        if w <= 0 or h <= 0:
            print("Screen cast: window is too small to record.")
            return
        try:
            handle = int(sf.ui.main_window_handle())
        except Exception as exc:
            print("Screen cast: no window handle (%s)." % exc)
            return
        os.makedirs(_output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_output_dir, "sculptforge_%s.mp4" % stamp)
        _log_path = os.path.join(_output_dir, "sculptforge_ffmpeg.log")
        log_file = open(_log_path, "w")
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", "%dx%d" % (w, h), "-r", str(FRAMERATE), "-i", "pipe:0",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-pix_fmt", "yuv420p", path,
        ]
        print("Screen cast: starting ffmpeg")
        print("  " + " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=log_file,
                stderr=subprocess.STDOUT)
        except Exception as exc:
            log_file.close()
            print("Screen cast: could not start ffmpeg (%s)." % exc)
            return
        proc._log_file = log_file
        _process = proc
        _stop_flag.clear()
        thread = threading.Thread(
            target=_capture_loop, args=(handle, w, h, proc, _stop_flag),
            daemon=True)
        _capture_thread = thread
        thread.start()
        print("Screen cast: recording the SculptForge window to %s" % path)
        print("  Keep the window visible; press 'Stop recording' to save.")


def _stop_recording():
    global _process, _capture_thread
    with _lock:
        proc = _process
        _process = None
    if proc is None or proc.poll() is not None:
        if proc is not None:
            print("Screen cast: ffmpeg already exited (code %s)." % proc.returncode)
            _print_log_tail()
        else:
            print("Screen cast: nothing is recording.")
        return
    _stop_flag.set()
    thread = _capture_thread
    if thread is not None:
        thread.join(timeout=10)
    try:
        proc.stdin.close()
    except Exception:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait()
    log_file = getattr(proc, "_log_file", None)
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass
    out_path = proc.args[-1] if isinstance(proc.args, list) else None
    if out_path and os.path.exists(out_path):
        size = os.path.getsize(out_path)
        if size > 0:
            print("Screen cast: saved %s (%d bytes)." % (out_path, size))
        else:
            print("Screen cast: file is empty (%s)." % out_path)
            _print_log_tail()
    else:
        print("Screen cast: output file not found.")
        _print_log_tail()


def _print_log_tail():
    global _log_path
    if not _log_path or not os.path.exists(_log_path):
        return
    try:
        with open(_log_path) as f:
            lines = f.readlines()
        tail = lines[-12:]
        if tail:
            print("  ffmpeg log (last lines):")
            for line in tail:
                print("    " + line.rstrip())
    except Exception:
        pass


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
                 help="Start recording the SculptForge window")
    sf.ui.action("screencast.stop", "Stop", _stop_recording, icon="scissors",
                 help="Stop recording and save the video")
    sf.ui.action("screencast.folder", "Folder", _open_folder, icon="download",
                 help="Open the folder where videos are saved")
    sf.ui.action("screencast.choose", "Choose", _choose_folder, icon="box",
                 help="Choose the folder where videos are saved")

    panel = sf.ui.panel("screencast", "Screen cast")
    panel.label("Record the SculptForge window")
    panel.label("Output folder: %s" % _output_dir)
    panel.separator()
    panel.button("screencast.record", label="Record")
    panel.button("screencast.stop", label="Stop")
    panel.button("screencast.choose", label="Choose folder")
    panel.button("screencast.folder", label="Open folder")
    panel.separator()
    panel.label("Keep the window visible while recording.")

    sf.ui.place("screencast.record", "top")
    sf.ui.place("screencast", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Screen cast: 'Record', 'Stop', 'Choose folder' and 'Open folder' added.")
else:
    print("Screen cast: sf.ui missing; call _start_recording() / _stop_recording() "
          "from the console.")
