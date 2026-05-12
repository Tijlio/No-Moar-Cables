import asyncio
import os
import shutil
import socket
import subprocess
import threading
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urlparse

from PIL import Image


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def png_to_jpeg(png_bytes, quality=80):
    image = Image.open(BytesIO(png_bytes)).convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality)
    return output.getvalue()


def find_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        scoop_ffmpeg = os.path.join(user_profile, "scoop", "shims", "ffmpeg.exe")
        if os.path.exists(scoop_ffmpeg):
            return scoop_ffmpeg

    return None


class WebsiteStreamer:
    def __init__(
        self,
        url,
        host="0.0.0.0",
        port=8080,
        width=1280,
        height=720,
        fps=5,
        jpeg_quality=80,
        on_log=None,
        on_status=None,
        on_request=None,
        auto_accept_prompts=True,
    ):
        self.url = url
        self.host = host
        self.port = int(port)
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))
        self.jpeg_quality = int(jpeg_quality)
        self.on_log = on_log
        self.on_status = on_status
        self.on_request = on_request
        self.auto_accept_prompts = auto_accept_prompts

        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.frame_ready = threading.Event()

        self.httpd = None
        self.server_thread = None
        self.render_thread = None
        self.render_error = None

        self.local_url = f"http://127.0.0.1:{self.port}/stream.mjpg"
        self.network_url = f"http://{get_local_ip()}:{self.port}/stream.mjpg"
        self.local_video_url = f"http://127.0.0.1:{self.port}/stream.ts"
        self.network_video_url = f"http://{get_local_ip()}:{self.port}/stream.ts"
        self.local_viewer_url = f"http://127.0.0.1:{self.port}/viewer"
        self.network_viewer_url = f"http://{get_local_ip()}:{self.port}/viewer"
        self.local_snapshot_viewer_url = f"http://127.0.0.1:{self.port}/snapshot-viewer"
        self.network_snapshot_viewer_url = f"http://{get_local_ip()}:{self.port}/snapshot-viewer"
        self.stream_url = self.network_video_url

    def start(self):
        self.stop_event.clear()
        self._start_http_server()
        self.render_thread = threading.Thread(target=self._run_renderer, daemon=True)
        self.render_thread.start()

    def stop(self):
        self.stop_event.set()

        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

        if self.render_thread and self.render_thread.is_alive():
            self.render_thread.join(timeout=10)

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5)

    def get_latest_frame(self):
        with self.frame_lock:
            return self.latest_frame

    def wait_for_frame(self, timeout=15):
        return self.frame_ready.wait(timeout)

    def _log(self, message):
        if self.on_log:
            self.on_log(message)

    def _status(self, message, color="blue"):
        if self.on_status:
            self.on_status(message, color)

    def _request(self, client_ip, path):
        if self.on_request:
            self.on_request(client_ip, path)

    def _start_http_server(self):
        streamer = self

        class StreamHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                request_path = urlparse(self.path).path
                streamer._request(self.client_address[0], request_path)

                if request_path in ("", "/"):
                    self._send_index()
                elif request_path == "/health":
                    self._send_text("OK\n")
                elif request_path == "/viewer":
                    self._send_viewer()
                elif request_path == "/snapshot-viewer":
                    self._send_snapshot_viewer()
                elif request_path == "/snapshot.jpg":
                    self._send_snapshot()
                elif request_path == "/stream.mjpg":
                    self._send_stream()
                elif request_path == "/stream.ts":
                    self._send_video_stream()
                else:
                    self.send_error(404)

            def log_message(self, format, *args):
                return

            def _send_text(self, text):
                body = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_index(self):
                host = self.headers.get("Host", f"127.0.0.1:{streamer.port}")
                links = [
                    ("Snapshot viewer", f"http://{host}/snapshot-viewer"),
                    ("Snapshot image", f"http://{host}/snapshot.jpg"),
                    ("MJPEG viewer", f"http://{host}/viewer"),
                    ("MJPEG stream", f"http://{host}/stream.mjpg"),
                    ("MPEG-TS video stream", f"http://{host}/stream.ts"),
                    ("Health check", f"http://{host}/health"),
                ]
                link_items = "\n".join(
                    f'<li><a href="{escape(url)}">{escape(label)}</a><code>{escape(url)}</code></li>'
                    for label, url in links
                )
                body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Website Stream</title>
  <style>
    body {{
      margin: 0;
      padding: 32px;
      background: #111;
      color: #f5f5f5;
      font-family: Arial, sans-serif;
      font-size: 24px;
      line-height: 1.35;
    }}
    h1 {{
      margin: 0 0 24px;
      font-size: 36px;
    }}
    ul {{
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    li {{
      margin: 0 0 18px;
      padding: 18px;
      background: #222;
      border: 1px solid #444;
    }}
    a {{
      display: block;
      margin-bottom: 8px;
      color: #8cc8ff;
      font-weight: bold;
      text-decoration: none;
    }}
    code {{
      display: block;
      color: #ddd;
      font-size: 16px;
      overflow-wrap: anywhere;
    }}
  </style>
</head>
<body>
  <h1>Website Stream</h1>
  <ul>
    {link_items}
  </ul>
</body>
</html>
""".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_viewer(self):
                body = b"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Website Stream</title>
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: #000;
    }
    img {
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      display: block;
      background: #000;
    }
  </style>
</head>
<body>
  <img src="/stream.mjpg" alt="">
</body>
</html>
"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_snapshot_viewer(self):
                interval_ms = max(200, int(1000 / streamer.fps))
                body = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Website Stream</title>
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
      background: #000;
    }}
    img {{
      width: 100vw;
      height: 100vh;
      object-fit: contain;
      display: block;
      background: #000;
    }}
  </style>
</head>
<body>
  <img id="frame" src="/snapshot.jpg" alt="">
  <script>
    var frame = document.getElementById("frame");
    function refreshFrame() {{
      frame.src = "/snapshot.jpg?t=" + Date.now();
    }}
    setInterval(refreshFrame, {interval_ms});
  </script>
</body>
</html>
""".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _send_snapshot(self):
                frame = streamer.get_latest_frame()
                if not frame:
                    self.send_error(503, "No frame available yet")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(frame)

            def _send_stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

                delay = 1 / streamer.fps
                while not streamer.stop_event.is_set():
                    frame = streamer.get_latest_frame()
                    if not frame:
                        time.sleep(0.1)
                        continue

                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(frame)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break

                    time.sleep(delay)

            def _send_video_stream(self):
                ffmpeg = find_ffmpeg()
                if not ffmpeg:
                    self.send_error(503, "ffmpeg is not installed or not on PATH")
                    return

                if not streamer.frame_ready.wait(timeout=15):
                    self.send_error(503, "No frame available yet")
                    return

                cmd = [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "mjpeg",
                    "-framerate",
                    str(streamer.fps),
                    "-i",
                    "pipe:0",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-tune",
                    "zerolatency",
                    "-profile:v",
                    "baseline",
                    "-level",
                    "3.1",
                    "-pix_fmt",
                    "yuv420p",
                    "-f",
                    "mpegts",
                    "pipe:1",
                ]

                try:
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except OSError as e:
                    self.send_error(503, f"Could not start ffmpeg: {e}")
                    return

                writer_stop = threading.Event()

                def feed_frames():
                    delay = 1 / streamer.fps
                    try:
                        while not streamer.stop_event.is_set() and not writer_stop.is_set():
                            frame = streamer.get_latest_frame()
                            if not frame:
                                time.sleep(0.1)
                                continue

                            try:
                                process.stdin.write(frame)
                                process.stdin.flush()
                            except (BrokenPipeError, OSError, AttributeError):
                                break

                            time.sleep(delay)
                    finally:
                        if process.stdin:
                            try:
                                process.stdin.close()
                            except OSError:
                                pass

                feeder = threading.Thread(target=feed_frames, daemon=True)
                feeder.start()

                self.send_response(200)
                self.send_header("Content-Type", "video/MP2T")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

                try:
                    while not streamer.stop_event.is_set():
                        if not process.stdout:
                            break

                        chunk = process.stdout.read(64 * 1024)
                        if not chunk:
                            break

                        self.wfile.write(chunk)
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    writer_stop.set()
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), StreamHandler)
        except OSError as e:
            raise RuntimeError(f"Port {self.port} is already in use or unavailable.") from e

        self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.server_thread.start()

    def _run_renderer(self):
        try:
            asyncio.run(self._render_loop())
        except Exception as e:
            self.render_error = e
            self._status(f"Error: {e}", "red")
            self._log(f"Website stream renderer stopped with error: {e}")
            self.stop_event.set()

    async def _render_loop(self):
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError("Playwright is not installed. Run: pip install playwright") from e

        self._status("Status: Rendering website locally", "blue")
        self._log(f"Rendering URL: {self.url}")

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
            except PlaywrightError as e:
                raise RuntimeError("Chromium is not installed. Run: python -m playwright install chromium") from e

            try:
                page = await browser.new_page(viewport={"width": self.width, "height": self.height})
                try:
                    await page.goto(self.url, wait_until="networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    self._log("Website load timed out; streaming the current rendered state.")
                except PlaywrightError as e:
                    raise RuntimeError(f"Could not load website: {e}") from e

                if self.auto_accept_prompts:
                    await self._auto_accept_prompts(page)

                delay = 1 / self.fps
                while not self.stop_event.is_set():
                    png_bytes = await page.screenshot(type="png")
                    jpeg_bytes = png_to_jpeg(png_bytes, quality=self.jpeg_quality)

                    with self.frame_lock:
                        self.latest_frame = jpeg_bytes

                    self.frame_ready.set()
                    await asyncio.sleep(delay)

            finally:
                await browser.close()

    async def _auto_accept_prompts(self, page):
        selectors = [
            "button:has-text('Accepteren')",
            "button:has-text('Accept')",
            "button:has-text('Allow')",
            "button:has-text('Toestaan')",
            "[role='button']:has-text('Accepteren')",
            "[role='button']:has-text('Accept')",
            "[role='button']:has-text('Allow')",
            "[role='button']:has-text('Toestaan')",
            "text=Accepteren",
            "text=Accept",
            "text=Allow",
            "text=Toestaan",
        ]

        for selector in selectors:
            if self.stop_event.is_set():
                return

            try:
                target = page.locator(selector).first
                if await target.count() == 0:
                    continue

                await target.click(timeout=1500)
                self._log(f"Clicked startup prompt: {selector}")
                await page.wait_for_timeout(500)
                return
            except Exception:
                continue
