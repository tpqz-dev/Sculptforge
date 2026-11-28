# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
# 
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty. 
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import ctypes
import json
import os
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from ctypes import wintypes
from datetime import datetime

import sculptforge as sf

HOST = "127.0.0.1"
PORT = 8188
SERVER = "http://%s:%d" % (HOST, PORT)
PROMPT = "improve this render like a to 3d render from zbrush or blender"
NEGATIVE = ""
STEPS = 20
CFG = 7.0
DENOISE = 0.5
RANDOM_SEED = True
SEED = 0
SAMPLER = "euler"
SCHEDULER = "normal"
MAX_SIDE = 1024
TIMEOUT = 180

_lock = threading.Lock()
_busy = False
_last_image = ""
_output_dir = os.path.join(os.path.expanduser("~"), "Desktop")


def _clipboard_rgb():
    """Read the image on the Windows clipboard as top-down RGB bytes."""
    cf_dib, cf_dibv5 = 8, 17
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    if not user32.OpenClipboard(0):
        raise RuntimeError("could not open the clipboard")

    try:
        fmt = cf_dibv5
        handle = user32.GetClipboardData(fmt)
        if not handle:
            fmt = cf_dib
            handle = user32.GetClipboardData(fmt)
        if not handle:
            raise RuntimeError("the clipboard holds no image")

        size = kernel32.GlobalSize(handle)
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise RuntimeError("could not lock the clipboard image")

        try:
            header = ctypes.string_at(pointer, min(size, 128))
            header_size = struct.unpack_from("<I", header, 0)[0]
            width, height = struct.unpack_from("<ii", header, 4)
            bpp = struct.unpack_from("<H", header, 14)[0]
            compression = struct.unpack_from("<I", header, 16)[0]
            top_down = height < 0
            height = abs(height)
            if width <= 0 or height <= 0:
                raise RuntimeError("the clipboard image has an empty size")
            if bpp not in (24, 32):
                raise RuntimeError("unsupported clipboard image depth: %d bpp" % bpp)

            if fmt == cf_dib and compression == 3:
                header_size += 12
            rgb_order = False
            if compression == 3 and size >= 52:
                red = struct.unpack_from("<I", header, 40)[0]
                blue = struct.unpack_from("<I", header, 48)[0]
                rgb_order = red == 0x000000FF and blue == 0x00FF0000

            pixel_bytes = bpp // 8
            stride = ((width * bpp + 31) // 32) * 4
            offset = max(40, header_size)
            if size < offset + stride * height:
                stride = width * pixel_bytes
            raw = ctypes.string_at(pointer + offset, stride * height)
            rows = []
            for row_index in range(height):
                row = raw[row_index * stride:(row_index + 1) * stride]
                pixel = bytearray(width * 3)
                if bpp == 32:
                    if rgb_order:
                        pixel[0::3] = row[0:width * 4:4]
                        pixel[1::3] = row[1:width * 4:4]
                        pixel[2::3] = row[2:width * 4:4]
                    else:
                        pixel[0::3] = row[2:width * 4:4]
                        pixel[1::3] = row[1:width * 4:4]
                        pixel[2::3] = row[0:width * 4:4]
                else:
                    pixel[0::3] = row[2:width * 3:3]
                    pixel[1::3] = row[1:width * 3:3]
                    pixel[2::3] = row[0:width * 3:3]
                rows.append(bytes(pixel))
            if not top_down:
                rows.reverse()
            return b"".join(rows), width, height
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _fit_rgb(data, width, height):
    """Scale the image to a multiple of 8 pixels, at most MAX_SIDE per side."""
    scale = min(1.0, float(MAX_SIDE) / max(width, height))
    new_width = max(8, int(width * scale) // 8 * 8)
    new_height = max(8, int(height * scale) // 8 * 8)
    if (new_width, new_height) == (width, height):
        return data, width, height

    rows = [min(height - 1, int((y + 0.5) * height / new_height))
            for y in range(new_height)]
    columns = [min(width - 1, int((x + 0.5) * width / new_width))
               for x in range(new_width)]
    result = bytearray(new_width * new_height * 3)
    position = 0
    for source_y in rows:
        start = source_y * width * 3
        for source_x in columns:
            index = start + source_x * 3
            result[position:position + 3] = data[index:index + 3]
            position += 3
    return bytes(result), new_width, new_height


def _png_bytes(data, width, height):
    """Encode top-down RGB bytes as a PNG, with the standard library only."""
    import zlib

    stride = width * 3
    raw = b"".join(b"\x00" + data[y * stride:(y + 1) * stride]
                   for y in range(height))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _request(url, data=None, headers=None, timeout=60):
    request = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _json_get(url, timeout=30):
    return json.loads(_request(url, None, {"Accept": "application/json"}, timeout))


def _json_post(url, payload, timeout=60):
    body = json.dumps(payload).encode("utf-8")
    data = _request(url, body,
                    {"Content-Type": "application/json", "Accept": "application/json"},
                    timeout)
    return json.loads(data)


def _upload(url, name, image_bytes):
    boundary = "----sfclip" + uuid.uuid4().hex
    body = b"".join([
        ("--%s\r\n" % boundary).encode("ascii"),
        ('Content-Disposition: form-data; name="image"; filename="%s"\r\n' % name).encode("utf-8"),
        b"Content-Type: image/png\r\n\r\n",
        image_bytes,
        b"\r\n",
        ("--%s--\r\n" % boundary).encode("ascii"),
    ])
    reply = _request(url + "/upload/image", body,
                     {"Content-Type": "multipart/form-data; boundary=" + boundary},
                     120)
    info = json.loads(reply.decode("utf-8"))
    if "error" in info:
        raise RuntimeError(str(info["error"]))
    return info["name"]


def _first_checkpoint(url):
    info = _json_get(url + "/object_info/CheckpointLoaderSimple")
    entry = info.get("CheckpointLoaderSimple") or {}
    required = ((entry.get("input") or {}).get("required") or {})
    names = required.get("ckpt_name")
    if isinstance(names, list) and names:
        names = names[0]
    if not isinstance(names, list) or not names:
        raise RuntimeError("ComfyUI has no checkpoint installed")
    return names[0]


def _workflow(image_name, checkpoint, seed, steps=STEPS, cfg=CFG, denoise=DENOISE):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": PROMPT, "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": NEGATIVE, "clip": ["2", 1]}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["1", 0], "vae": ["2", 2]}},
        "6": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": SAMPLER, "scheduler": SCHEDULER,
                         "denoise": denoise, "model": ["2", 0],
                         "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["2", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": "SF_Improve"}},
    }


def _wait_for_image(url, prompt_id, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = _json_get(url + "/history/" + urllib.parse.quote(prompt_id))
        entry = history.get(prompt_id) or {}
        status = ((entry.get("status") or {}).get("status_str") or "").lower()
        if status == "error":
            raise RuntimeError("ComfyUI reported an error; see its console")
        for node in (entry.get("outputs") or {}).values():
            for image in node.get("images") or []:
                if image.get("filename"):
                    return image
        time.sleep(0.5)
    raise RuntimeError("ComfyUI did not finish within %d s" % timeout)


def _save_result(url, image_info, folder):
    query = urllib.parse.urlencode({
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    })
    data = _request(url + "/view?" + query, None, {}, 120)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = "sf_comfy_%s_%s" % (stamp, os.path.basename(image_info["filename"]))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as output:
        output.write(data)
    return path


def _open_viewer(path):
    if not path or not os.path.exists(path):
        print("Clip to Comfy: no image to open (%s)." % path)
        return
    try:
        os.startfile(path)
    except Exception as exc:
        print("Clip to Comfy: could not open the image viewer (%s)." % exc)


def _set_server(value):
    """Accept 'host:port', 'http://host:port' or a full URL."""
    global SERVER, HOST, PORT
    text = str(value).strip()
    if not text:
        return
    if "://" not in text:
        text = "http://" + text
    try:
        parsed = urllib.parse.urlsplit(text)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        host, port = "", None
    if not host or port is None or not (1 <= port <= 65535):
        print("Clip to Comfy: invalid server %r (expected host:port)." % value)
        return
    SERVER = "http://%s:%d" % (host, port)
    HOST, PORT = host, port
    print("Clip to Comfy: server set to %s" % SERVER)


def _ask_server():
    script = os.path.join(tempfile.gettempdir(), "sf_clip2comfy_server.vbs")
    with open(script, "w", encoding="ascii") as output:
        output.write('s = InputBox("ComfyUI server (host:port or http://host:port)", _\n')
        output.write('              "Clip to Comfy", "%s")\n' % SERVER)
        output.write("WScript.Echo s\n")
    try:
        result = subprocess.run(
            ["cscript", "//nologo", script], capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        print("Clip to Comfy: input box unavailable (%s); edit HOST and PORT "
              "at the top of the script." % exc)
        return
    finally:
        try:
            os.remove(script)
        except OSError:
            pass
    _set_server(result.stdout.strip())


def _panel_value(control, fallback):
    """Value of a panel control, or the default value."""
    try:
        value = sf.ui.value("clip2comfy." + control)
    except Exception:
        return fallback
    return fallback if value is None else value


def _run(url=None, open_viewer=True, steps=STEPS, cfg=CFG, denoise=DENOISE,
         seed=None, random_seed=RANDOM_SEED):
    global _last_image, _busy
    if url is None:
        url = SERVER
    with _lock:
        if _busy:
            print("Clip to Comfy: a conversion is already running.")
            return None
        _busy = True
    try:
        steps = max(1, min(200, int(steps)))
        cfg = max(0.1, min(100.0, float(cfg)))
        denoise = max(0.0, min(1.0, float(denoise)))

        print("Clip to Comfy: reading the clipboard...")
        image, width, height = _fit_rgb(*_clipboard_rgb())
        print("  image: %d x %d px" % (width, height))

        print("Clip to Comfy: sending to %s..." % url)
        name = _upload(url, "sf_clip.png", _png_bytes(image, width, height))
        checkpoint = _first_checkpoint(url)
        print("  checkpoint: %s" % checkpoint)

        if seed is None or random_seed:
            seed = int.from_bytes(os.urandom(4), "big") % (2 ** 31)
        seed = abs(int(seed)) % (2 ** 31)
        workflow = _workflow(name, checkpoint, seed, steps, cfg, denoise)
        print("  steps=%d  cfg=%.1f  denoise=%.2f  seed=%d"
              % (steps, cfg, denoise, seed))
        reply = _json_post(url + "/prompt",
                           {"prompt": workflow, "client_id": "sculptforge-" + uuid.uuid4().hex})
        prompt_id = reply.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt id: %r" % (reply,))
        print("  queued as %s, waiting..." % prompt_id)

        info = _wait_for_image(url, prompt_id)
        path = _save_result(url, info, _output_dir)
        _last_image = path
        print("Clip to Comfy: saved %s (%d bytes)." % (path, os.path.getsize(path)))
        if open_viewer:
            _open_viewer(path)
        return path
    except (urllib.error.URLError, OSError, RuntimeError, ValueError, KeyError) as exc:
        print("Clip to Comfy: failed (%s)." % exc)
        print("  Start ComfyUI at %s, or edit SERVER at the top of the script." % url)
        return None
    finally:
        with _lock:
            _busy = False


def _run_in_thread():
    settings = (
        int(_panel_value("steps", STEPS)),
        float(_panel_value("cfg", CFG)),
        float(_panel_value("denoise", DENOISE)),
        int(_panel_value("seed", SEED)),
        bool(_panel_value("random_seed", RANDOM_SEED)),
    )

    def work():
        _run(steps=settings[0], cfg=settings[1], denoise=settings[2],
             seed=settings[3], random_seed=settings[4])

    with _lock:
        if _busy:
            print("Clip to Comfy: a conversion is already running.")
            return
    threading.Thread(target=work, daemon=True).start()
    print("Clip to Comfy: started in the background.")


def _open_last():
    _open_viewer(_last_image)


def _check_server():
    try:
        reply = _json_get(SERVER + "/system_stats", 10)
        device = ""
        devices = reply.get("devices") or []
        if devices:
            device = " (%s)" % (devices[0].get("name") or devices[0].get("type") or "")
        print("Clip to Comfy: server OK%s." % device)
        print("  checkpoint: %s" % _first_checkpoint(SERVER))
    except Exception as exc:
        print("Clip to Comfy: server unreachable (%s)." % exc)


def _open_folder():
    os.makedirs(_output_dir, exist_ok=True)
    try:
        os.startfile(_output_dir)
    except Exception as exc:
        print("Clip to Comfy: could not open the folder (%s)." % exc)


def _choose_folder():
    global _output_dir
    try:
        ole32 = ctypes.windll.ole32
        shell32 = ctypes.windll.shell32
        ole32.CoInitialize(None)
        try:
            class BrowseInfo(ctypes.Structure):
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

            info = BrowseInfo()
            info.lpszTitle = "Choose the folder for ComfyUI images"
            info.ulFlags = 0x00000001 | 0x00000040
            pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
            if not pidl:
                return
            buffer = ctypes.create_unicode_buffer(260)
            if shell32.SHGetPathFromIDListW(pidl, buffer):
                _output_dir = buffer.value
                print("Clip to Comfy: output folder %s" % _output_dir)
            ole32.CoTaskMemFree(pidl)
        finally:
            ole32.CoUninitialize()
    except Exception as exc:
        print("Clip to Comfy: folder picker failed (%s)." % exc)


def _declare_ui():
    sf.ui.action(
        "clip2comfy.run", "Clipboard to ComfyUI", _run_in_thread, icon="upload",
        help="Send the clipboard image to ComfyUI for img2img, then open the result "
             "in the system's default image viewer")
    sf.ui.action(
        "clip2comfy.last", "Open last result", _open_last, icon="eye",
        help="Open the last image returned by ComfyUI")
    sf.ui.action(
        "clip2comfy.check", "Check server", _check_server, icon="settings",
        help="Check that the ComfyUI server answers and list its first checkpoint")
    sf.ui.action(
        "clip2comfy.server", "Set server", _ask_server, icon="file-code",
        help="Type the ComfyUI address (host:port or http://host:port). HOST and "
             "PORT can also be edited at the top of the script")
    sf.ui.action(
        "clip2comfy.choose", "Choose folder", _choose_folder, icon="box",
        help="Choose where the generated images are saved")
    sf.ui.action(
        "clip2comfy.folder", "Open folder", _open_folder, icon="download",
        help="Open the folder where the generated images are saved")

    panel = sf.ui.panel("clip2comfy", "Clip to Comfy")
    panel.label("Clipboard image -> ComfyUI img2img -> image viewer")
    panel.label("Prompt: " + PROMPT)
    panel.label("Server: " + SERVER + " (click Set server to change)")
    panel.separator()
    panel.label("Model settings")
    panel.slider("steps", "Steps", STEPS, 1, 60, integer=True)
    panel.slider("cfg", "CFG scale", CFG, 1.0, 20.0)
    panel.slider("denoise", "Denoise (noise added)", DENOISE, 0.0, 1.0)
    panel.checkbox("random_seed", "Random seed each run", RANDOM_SEED)
    panel.slider("seed", "Fixed seed", SEED, 0, 2147483647, integer=True)
    panel.label("Sampler: %s / Scheduler: %s (constants at the top)"
                % (SAMPLER, SCHEDULER))
    panel.separator()
    panel.button("clip2comfy.run", label="Run in ComfyUI")
    panel.button("clip2comfy.last", label="Open last image")
    panel.button("clip2comfy.check", label="Check server")
    panel.button("clip2comfy.server", label="Set server")
    panel.separator()
    panel.button("clip2comfy.choose", label="Choose folder")
    panel.button("clip2comfy.folder", label="Open folder")

    sf.ui.place("clip2comfy.run", "top")
    sf.ui.place("clip2comfy", "my_panel")


if hasattr(sf, "ui"):
    _declare_ui()
    print("Clip to Comfy: 'Run in ComfyUI' added (top shelf, My Panel, F3 palette).")
else:
    print("Clip to Comfy: sf.ui missing; call _run() from the Python console.")
