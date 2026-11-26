# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: CC0-1.0

# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated
# all copyright and related and neighboring rights to this software to the public
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software.
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import os
import subprocess
import threading
import time
from datetime import datetime

import sculptforge as sf

# ---------------------------------------------------------------------------
# Settings (edit these two lines if you want a different folder or frame rate)
# ---------------------------------------------------------------------------
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")
FRAMERATE = 30
# ---------------------------------------------------------------------------

_process = None
_lock = threading.Lock()


def _ffmpeg_available():
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False


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
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUTPUT_DIR, "sculptforge_%s.mp4" % stamp)
        cmd = [
            "ffmpeg", "-y",
            "-f", "gdigrab",
            "-framerate", str(FRAMERATE),
            "-i", "desktop",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            path,
        ]
        try:
            _process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except Exception as exc:
            _process = None
            print("Screen cast: could not start ffmpeg (%s)." % exc)
            return
        print("Screen cast: recording to %s" % path)
        print("  Press 'Stop recording' to finish and save the file.")


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
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        os.startfile(OUTPUT_DIR)
    except Exception:
        try:
            subprocess.Popen(["explorer", OUTPUT_DIR])
        except Exception as exc:
            print("Screen cast: could not open the folder (%s)." % exc)


def _declare_ui():
    sf.ui.action("screencast.record", "Record", _start_recording, icon="play",
                 help="Start recording the screen with ffmpeg")
    sf.ui.action("screencast.stop", "Stop", _stop_recording, icon="scissors",
                 help="Stop recording and save the video")
    sf.ui.action("screencast.folder", "Folder", _open_folder, icon="download",
                 help="Open the folder where videos are saved")

    panel = sf.ui.panel("screencast", "Screen cast")
    panel.label("Record the screen while you sculpt (ffmpeg)")
    panel.label("Output folder: %s" % OUTPUT_DIR)
    panel.separator()
    panel.button("screencast.record", label="Record")
    panel.button("screencast.stop", label="Stop")
    panel.button("screencast.folder", label="Open folder")
    panel.separator()
    panel.label("Edit OUTPUT_DIR at the top of the script to change the folder.")

    sf.ui.place("screencast.record", "top")
    sf.ui.place("screencast", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Screen cast: 'Record', 'Stop' and 'Folder' added (top shelf, My Panel).")
else:
    print("Screen cast: sf.ui missing; call _start_recording() / _stop_recording() "
          "from the console.")
