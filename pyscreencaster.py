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
import threading
import time
from ctypes import wintypes
from datetime import datetime

import sculptforge as sf

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
FRAMERATE = 30
# ---------------------------------------------------------------------------

try:
    import sys
    import types
    import ctypes
    from ctypes import wintypes

    if "pyautogui" not in sys.modules:
        _pa = types.ModuleType("pyautogui")

        def _pyautogui_position():
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return (pt.x, pt.y)

        _pa.position = _pyautogui_position
        sys.modules["pyautogui"] = _pa

    from pyscreenrecorder import pyScreenRecorder as _BaseRecorder
    _LIBS_ERROR = ""
except Exception as _exc:
    _BaseRecorder = None
    _LIBS_ERROR = str(_exc)

_process_thread = None
_stop_event = threading.Event()
_lock = threading.Lock()
_output_dir = os.path.join(os.path.expanduser("~"), "Desktop")


def _mouse_position():
    """Mouse position via the Win32 API (no pyautogui dependency)."""
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _window_rect():
    try:
        handle = sf.ui.main_window_handle()
    except Exception:
        return None
    if not handle:
        return None
    try:
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(int(handle), ctypes.byref(rect)):
            return None
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return rect.left, rect.top, w, h, int(handle)
    except Exception:
        return None


def _monitor_for_window():
    """Return the mss monitor index that contains the SculptForge window."""
    info = _window_rect()
    if info is None:
        return 1
    left, top, w, h, _ = info
    cx, cy = left + w // 2, top + h // 2
    try:
        import mss
        with mss.MSS() as sct:
            for idx in range(1, len(sct.monitors)):
                m = sct.monitors[idx]
                if (m["left"] <= cx < m["left"] + m["width"] and
                        m["top"] <= cy < m["top"] + m["height"]):
                    return idx
    except Exception:
        pass
    return 1


class _Recorder(_BaseRecorder if _BaseRecorder is not None else object):
    """pyScreenRecorder subclass that supports start/stop via an event."""

    def __init__(self, *args, **kwargs):
        if _BaseRecorder is None:
            raise RuntimeError("pyscreenrecorder is not installed")
        super().__init__(*args, **kwargs)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def screenRecorder(self):
        import cv2
        import mss
        import numpy as np

        valid_formats = ["avi", "mp4", "mkv"]
        file_extension = self.filename.split(".")[-1].lower()
        if file_extension not in valid_formats:
            raise ValueError(
                "Unsupported file format: %s. Supported: %s"
                % (file_extension, valid_formats))

        with mss.MSS() as sct:
            monitors = sct.monitors
            if self.monitor_number < 0 or self.monitor_number >= len(monitors):
                raise ValueError(
                    "Invalid monitor_number %d. Must be 0..%d."
                    % (self.monitor_number, len(monitors) - 1))
            monitor = monitors[self.monitor_number]
            screen_width, screen_height = monitor["width"], monitor["height"]

        if self.resolution:
            output_width, output_height = self.resolution
        else:
            output_width, output_height = screen_width, screen_height

        scale_x = output_width / screen_width
        scale_y = output_height / screen_height

        fourcc = (cv2.VideoWriter_fourcc(*"mp4v")
                  if file_extension == "mp4"
                  else cv2.VideoWriter_fourcc(*"XVID"))
        out = cv2.VideoWriter(
            self.filename, fourcc, self.fps, (output_width, output_height))

        start_time = time.time()
        frame_interval = 1.0 / self.fps
        next_time = start_time

        with mss.MSS() as sct:
            while not self._stop.is_set():
                now = time.time()
                if next_time > now:
                    time.sleep(next_time - now)
                next_time += frame_interval

                frame = np.array(sct.grab(monitor))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if self.resolution and (output_width, output_height) != (
                        screen_width, screen_height):
                    frame = cv2.resize(frame, (output_width, output_height))

                if self.mouse:
                    mx, my = _mouse_position()
                    scaled_x = int(mx * scale_x)
                    scaled_y = int(my * scale_y)
                    cv2.circle(frame, (scaled_x, scaled_y), self.mouse_size,
                               self.mouse_color, self.mouse_thickness)

                out.write(frame)

        out.release()


def _start_recording():
    global _process_thread
    with _lock:
        if _process_thread is not None and _process_thread.is_alive():
            print("Screen cast: already recording, press Stop first.")
            return
        if _BaseRecorder is None:
            print("Screen cast: pyscreenrecorder is not installed (%s)." % _LIBS_ERROR)
            print("  Install with:")
            print('  py -3.13 -m pip install --target "%s" pyscreenrecorder mss opencv-python'
                  % os.path.join(sf.scripts_folder(), "site-packages"))
            return

        os.makedirs(_output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_output_dir, "sculptforge_%s.mp4" % stamp)

        monitor_number = _monitor_for_window()

        recorder = _Recorder(
            filename=path,
            fps=FRAMERATE,
            monitor_number=monitor_number,
            mouse=True,
        )
        recorder._stop = threading.Event()

        def run():
            try:
                recorder.screenRecorder()
                print("Screen cast: saved %s" % path)
                if os.path.exists(path):
                    print("  size: %d bytes" % os.path.getsize(path))
            except Exception as exc:
                print("Screen cast: recording failed (%s)." % exc)

        thread = threading.Thread(target=run, daemon=True)
        _process_thread = thread
        # store recorder + stop handle on the thread for _stop_recording
        thread.recorder = recorder
        thread.out_path = path
        thread.start()
        print("Screen cast: recording monitor %d to %s" % (monitor_number, path))
        print("  Press 'Stop recording' to save.")


def _stop_recording():
    global _process_thread
    with _lock:
        thread = _process_thread
        _process_thread = None
    if thread is None or not thread.is_alive():
        print("Screen cast: nothing is recording.")
        return
    try:
        thread.recorder.stop()
    except Exception:
        pass
    thread.join(timeout=30)
    path = getattr(thread, "out_path", None)
    if path and os.path.exists(path):
        size = os.path.getsize(path)
        if size > 0:
            print("Screen cast: saved %s (%d bytes)." % (path, size))
        else:
            print("Screen cast: file is empty (%s)." % path)
    else:
        print("Screen cast: output file not found.")


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
    global _output_dir
    # Reuse the Win32 folder picker (ctypes) to avoid tkinter dependency.
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
                return
            buf = ctypes.create_unicode_buffer(260)
            if shell32.SHGetPathFromIDListW(pidl, buf):
                _output_dir = buf.value
                print("Screen cast: output folder set to %s" % _output_dir)
            ole32.CoTaskMemFree(pidl)
        finally:
            ole32.CoUninitialize()
    except Exception as exc:
        print("Screen cast: folder picker failed (%s)." % exc)


def _declare_ui():
    sf.ui.action("pyscreencaster.record", "Record", _start_recording, icon="play",
                 help="Start recording with pyscreenrecorder")
    sf.ui.action("pyscreencaster.stop", "Stop", _stop_recording, icon="scissors",
                 help="Stop recording and save the video")
    sf.ui.action("pyscreencaster.folder", "Go to save Folder", _open_folder, icon="download",
                 help="Open the folder where videos are saved")
    sf.ui.action("pyscreencaster.choose", "Choose save folder", _choose_folder, icon="box",
                 help="Choose the folder where videos are saved")

    panel = sf.ui.panel("pyscreencaster", "Py screen cast")
    panel.label("Record with pyscreenrecorder (mss)")
    panel.label("Output folder: %s" % _output_dir)
    panel.separator()
    panel.button("pyscreencaster.choose", label="Choose folder")
    panel.button("pyscreencaster.folder", label="Open folder")
    panel.separator()
    panel.button("pyscreencaster.record", label="Record")
    panel.button("pyscreencaster.stop", label="Stop")
    panel.separator()
    panel.label("Edit FRAMERATE at the top of the script.")

    sf.ui.place("pyscreencaster.record", "top")
    sf.ui.place("pyscreencaster", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Py screen cast: 'Record', 'Stop', 'Choose folder' and 'Open folder' added.")
else:
    print("Py screen cast: sf.ui missing; call _start_recording() / _stop_recording() "
          "from the console.")
