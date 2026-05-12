# Implementation Brief: Add Website-to-Video Streaming Mode

## Goal

Add a **third, complementary mode** to the existing Auto-Caster app:

1. **Website / dashboard mode**  
   Existing mode using `catt cast_site <url>`

2. **Media / video URL mode**  
   Existing mode using `catt cast <url>`

3. **Website-to-video stream mode**  
   New mode that renders a normal website locally and exposes it as a live video-like stream.

This third mode is meant as a fallback for TVs or built-in Chromecast receivers that cannot reliably render websites through `catt cast_site`.

The goal is **not** to replace the existing modes. It should be added alongside them.

---

## Why this mode exists

Testing showed:

- Media casting works.
- Website casting through `catt cast_site` can fail on older Sony BRAVIA built-in Chromecast receivers.
- The failure can happen before the website even loads, during receiver startup.
- Some TVs are better at playing media/video streams than rendering web pages.

So the workaround is:

```text
Website/dashboard
      ↓
Render locally with browser
      ↓
Capture frames in memory
      ↓
Expose as a live stream
      ↓
TV / decoder / media receiver plays the stream
```

This keeps the TV dumb, which is exactly where most TVs perform best.

---

## Important constraint

Do **not** save screenshots or frames to disk.

Frames should be:

- captured in memory
- streamed immediately
- discarded/replaced

The app must not create a growing folder of images.

No `frame_000001.png`, no debug image dumps, no storage goblin.

---

## Recommended first implementation: MJPEG HTTP stream

Start with MJPEG because it is simple and easy to test.

Expose a local endpoint like:

```text
http://<computer-ip>:8080/stream.mjpg
```

A browser, decoder box, or compatible media receiver can then pull that stream.

The stream should behave like a basic IP camera feed.

---

## Proposed UI changes

Add a third radio button / mode option:

```text
Website / dashboard
Media / video URL
Website-to-video stream
```

When **Website-to-video stream** is selected:

- The URL field still accepts a normal website URL.
- The app renders that URL locally.
- The app starts a local MJPEG stream server.
- The app displays the generated stream URL in the UI/log.
- Optional: allow the user to cast the MJPEG stream using Media mode if supported.
- Optional: allow the user to copy the stream URL for use in an external decoder device.

Suggested status messages:

```text
Status: Starting local website stream...
Status: Stream running at http://<ip>:8080/stream.mjpg
Status: Rendering website locally
Status: Stream stopped
```

Suggested log output:

```text
Website stream mode selected.
Rendering URL: https://example.com
MJPEG stream available at: http://10.0.10.x:8080/stream.mjpg
Frames are streamed in memory only. Nothing is written to disk.
```

---

## Suggested dependencies

Add these dependencies only for streaming mode:

```bash
pip install playwright pillow
python -m playwright install chromium
```

Optional later dependency if implementing RTSP/HLS through FFmpeg:

```bash
ffmpeg
```

For the first version, prefer MJPEG over FFmpeg to reduce complexity.

---

## Suggested architecture

Create a separate module:

```text
website_streamer.py
```

This module should contain the streaming logic so `app.py` does not become a cursed all-in-one soup.

Suggested responsibilities:

### `WebsiteStreamer`

A class that:

- accepts a website URL
- accepts host, port, width, height, and FPS settings
- launches a browser renderer
- captures screenshots repeatedly
- stores only the latest JPEG frame in memory
- starts a local HTTP server
- serves `/stream.mjpg`
- can be stopped cleanly

Example public API:

```python
streamer = WebsiteStreamer(
    url="https://example.com",
    host="0.0.0.0",
    port=8080,
    width=1280,
    height=720,
    fps=5,
)

streamer.start()
print(streamer.stream_url)

streamer.stop()
```

---

## Frame handling requirement

Use a single shared in-memory frame variable.

Example concept:

```python
latest_frame: bytes | None = None
```

Each new frame replaces the previous one.

Do **not** append frames to a list.

Do **not** store historical frames.

Do **not** write frames to disk.

Use a lock when reading/writing the latest frame:

```python
frame_lock = threading.Lock()
```

---

## MJPEG endpoint behavior

The HTTP endpoint should:

- respond at `/stream.mjpg`
- use content type:

```text
multipart/x-mixed-replace; boundary=frame
```

Each frame should be sent as:

```text
--frame
Content-Type: image/jpeg
Content-Length: <length>

<jpeg bytes>
```

Then repeat until the client disconnects or the streamer stops.

---

## Browser rendering

Use Playwright Chromium.

Recommended defaults:

```text
width: 1280
height: 720
fps: 5
```

5 FPS is enough for dashboards and keeps CPU usage reasonable.

Optional later setting:

```text
fps: 10
```

Avoid high frame rates unless needed. This is a dashboard stream, not a Marvel movie.

---

## Playwright capture flow

Pseudo-code:

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(
        viewport={"width": width, "height": height}
    )
    await page.goto(url, wait_until="networkidle")

    while not stop_event.is_set():
        png_bytes = await page.screenshot(type="png")
        jpeg_bytes = convert_png_to_jpeg(png_bytes)
        replace_latest_frame(jpeg_bytes)
        await asyncio.sleep(1 / fps)
```

Convert PNG to JPEG using Pillow:

```python
from PIL import Image
from io import BytesIO

def png_to_jpeg(png_bytes, quality=80):
    image = Image.open(BytesIO(png_bytes)).convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality)
    return output.getvalue()
```

---

## HTTP server

Use Python standard library first:

```python
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
```

Suggested endpoints:

```text
/              simple text status page
/stream.mjpg   MJPEG stream
/snapshot.jpg  latest frame as single JPEG
/health        returns OK
```

`/snapshot.jpg` is useful for quick browser testing.

---

## Finding the local IP

The app should display a LAN-accessible stream URL.

Use a helper like:

```python
def get_local_ip():
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()
```

Fallback to:

```text
127.0.0.1
```

The UI should show both:

```text
Local: http://127.0.0.1:8080/stream.mjpg
Network: http://10.0.10.x:8080/stream.mjpg
```

Use the network URL for TVs/decoder boxes.

---

## Integration with existing app

In `app.py`:

- Keep existing CATT Website mode.
- Keep existing CATT Media mode.
- Add streaming mode.
- Add `streamer = None` global or instance variable.
- On start:
  - if mode is `website_stream`:
    - validate URL
    - normalize URL
    - start streamer
    - do not call `catt cast_site`
    - optionally offer/call `catt cast <stream_url>` if a checkbox is enabled later
  - else:
    - use existing CATT automation logic

On stop:

- stop CATT automation if running
- stop website streamer if running
- re-enable inputs

---

## Optional “Cast generated stream” checkbox

Add later, not required for first implementation.

Checkbox:

```text
Also cast generated stream to selected TV
```

If enabled:

1. Start the MJPEG stream.
2. Wait until `/snapshot.jpg` returns a frame.
3. Call:

```bash
catt -d <tv_ip> cast http://<computer-ip>:8080/stream.mjpg
```

Important: not all Chromecast devices support MJPEG directly. If this does not work, the stream URL can still be used in an external decoder device such as an IP video decoder.

---

## Decoder device use case

If an IONODES / IP video decoder is available behind the TV, configure it to pull:

```text
http://<computer-ip>:8080/stream.mjpg
```

If the decoder does not accept MJPEG over HTTP, implement RTSP later.

---

## Future RTSP implementation

If MJPEG is not supported by the decoder, add RTSP as a second streaming backend.

Recommended architecture:

```text
Playwright screenshots
      ↓
FFmpeg
      ↓
MediaMTX
      ↓
rtsp://<computer-ip>:8554/dashboard
```

Do not implement RTSP first unless MJPEG fails.

RTSP is more correct for video decoders but adds more moving pieces.

---

## Error handling

The app should handle:

- invalid URL
- Playwright not installed
- Chromium browser not installed
- port already in use
- page load timeout
- render loop crashes
- no frame produced after startup
- client disconnects from MJPEG stream
- stop requested while stream is starting

Useful user-facing messages:

```text
Error: Playwright is not installed. Run: pip install playwright
Error: Chromium is not installed. Run: python -m playwright install chromium
Error: Port 8080 is already in use.
Error: Could not load website.
Error: Stream started, but no frame was produced yet.
```

---

## Performance guidelines

Default to:

```text
1280x720
5 FPS
JPEG quality 80
```

This should be enough for dashboards.

Avoid:

```text
1920x1080 at 30 FPS
```

unless explicitly needed. That will burn CPU for no good reason, which is very on-brand for computers but still rude.

---

## Config changes

Update `config.json` support to remember:

```json
{
  "tv_ip": "",
  "url": "",
  "cast_mode": "website",
  "stream_host": "0.0.0.0",
  "stream_port": 8080,
  "stream_width": 1280,
  "stream_height": 720,
  "stream_fps": 5
}
```

Make sure old config files still load safely by merging with defaults.

---

## README updates

Update README to explain the three modes:

### Website / dashboard mode

Uses:

```bash
catt cast_site <url>
```

Best for devices that support website rendering.

### Media / video URL mode

Uses:

```bash
catt cast <url>
```

Best for direct video files and supported media URLs.

### Website-to-video stream mode

Renders the website locally and exposes it as:

```text
http://<computer-ip>:8080/stream.mjpg
```

Best for old TVs, external decoders, or devices that cannot render websites directly.

Add a warning:

```text
Streaming mode uses more CPU because the computer is rendering the website and generating a live stream.
Frames are kept in memory only and are not saved to disk.
```

---

## Acceptance criteria

Implementation is done when:

- Existing Website mode still works as before.
- Existing Media mode still works as before.
- A new Website-to-video stream mode exists.
- The app can start an MJPEG stream from a website URL.
- Visiting `/snapshot.jpg` in a browser shows the latest rendered frame.
- Visiting `/stream.mjpg` in a browser shows a live MJPEG stream.
- Stopping the app stops the renderer and HTTP server.
- No image files are written to disk.
- The README explains all three modes.
- Existing config files do not break.

---

## Suggested implementation order

1. Create `website_streamer.py`.
2. Implement local HTTP server with `/health`, `/snapshot.jpg`, and `/stream.mjpg`.
3. Implement Playwright screenshot loop.
4. Store only the latest JPEG frame in memory.
5. Test stream in a normal browser.
6. Integrate start/stop controls into `app.py`.
7. Add the third UI mode.
8. Update config handling.
9. Update README.
10. Only then consider optional casting of the generated stream.

---

## Manual test plan

### Test 1: Simple website stream

Input:

```text
https://example.com
```

Expected:

- stream starts
- `/snapshot.jpg` shows the page
- `/stream.mjpg` shows the live stream

### Test 2: Live-ish website

Input:

```text
https://time.is
```

Expected:

- stream starts
- time display updates every few frames

### Test 3: Stop behavior

Steps:

1. Start website stream.
2. Open `/stream.mjpg` in browser.
3. Stop app.

Expected:

- browser stream ends
- app status says stopped
- no background Chromium process remains

### Test 4: No disk growth

Steps:

1. Run stream for 10 minutes.
2. Check project folder.

Expected:

- no generated frame images
- no growing screenshots folder
- only normal logs/config files

### Test 5: Existing modes

Verify:

- Website mode still calls `catt cast_site`
- Media mode still calls `catt cast`

---

## Notes for the implementing agent

Do not rewrite the whole app.

Do not remove the existing CATT modes.

Do not introduce a giant framework.

Do not save frames to disk.

Keep the streaming code isolated in `website_streamer.py`.

Prefer clear boring code over clever code. This is a utility, not a thesis defense.

The end result should make the app more robust while keeping the original spirit:

```text
NO MORE CABLES.
NO MORE BLACK SCREENS.
NO MORE TV BROWSER NONSENSE.
```
