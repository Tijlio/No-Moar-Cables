# NO MORE CABLES!! 🚀

## Auto-Caster v2

A small utility that keeps a URL casting to a TV.

Useful for dashboards, kiosk pages, schedules, menus, video links, or anything else that should stay visible without someone crawling behind a screen with an HDMI cable like it’s 2011.

It works with Chromecasts and Sony BRAVIA TVs through [`catt`](https://github.com/skorokithakis/catt).

---

## What it does

- Finds available Chromecast / Sony TV devices on the network
- Lets you pick the target TV
- Casts either:
  - a normal website / dashboard URL
  - a media / video URL
  - a locally rendered website-to-video MJPEG stream
  - a local stream for manual use in the TV native browser
- Checks regularly whether the cast is still active
- Restarts the cast if the session drops or the TV forgets what it was doing
- Remembers your last used TV IP, URL, and cast mode
- Includes a one-click **Recast Once** button for when the TV needs a gentle slap from software

Basically: set it once, let it babysit the screen.

---

## Casting modes

The app has four modes.

### Website / dashboard mode

Uses:

```bash
catt cast_site <url>
```

Use this for:

- dashboards
- kiosk pages
- public web pages
- simple internal status pages
- anything that should render like a website

This mode asks the Chromecast receiver to render the page. It is not a full desktop Chrome browser, because apparently that would have been too convenient.

Some sites may show a black screen if they rely on unsupported browser features, login cookies, heavy scripts, redirects, blocked content, or other web nonsense.

### Media / video mode

Uses:

```bash
catt cast <url>
```

Use this for:

- YouTube links
- direct video files
- media URLs supported by `yt-dlp`
- streams that `catt` can resolve as media

If video sites stop working, update `yt-dlp`:

```bash
pip install -U yt-dlp
```

### Website-to-video stream mode

Renders the website locally with Chromium and exposes it as live streams:

```text
http://<computer-ip>:8080/stream.mjpg
http://<computer-ip>:8080/stream.ts
```

Use this for old TVs, external decoders, or Chromecast receivers that can play media but cannot reliably render websites with `catt cast_site`.

In this mode the app starts the local stream, waits until a first frame exists, then sends the generated MPEG-TS video URL to the selected TV with:

```bash
catt cast http://<computer-ip>:8080/stream.ts
```

The MJPEG endpoint is still useful for browser/debug testing. The MPEG-TS endpoint requires `ffmpeg` and is intended for Cast playback.

If the TV opens the Cast receiver but never starts video, choose **TV browser viewer** as the website stream cast target. That opens:

```text
http://<computer-ip>:8080/viewer
```

The viewer is a full-screen page containing the MJPEG stream. It is a lazy fallback for devices that can render a very simple page but cannot play the generated video stream.

If that still shows a black screen, choose **Snapshot viewer**. That opens:

```text
http://<computer-ip>:8080/snapshot-viewer
```

This page repeatedly reloads `/snapshot.jpg`, so the TV only needs to display normal JPEG images.

### TV native browser mode

Starts the same local renderer and logs a TV-safe URL:

```text
http://<computer-ip>:8080/snapshot-viewer
```

Open that URL manually in the TV's built-in browser. This avoids the unreliable Chromecast website receiver entirely and keeps the computer responsible for rendering the real dashboard.

On compatible Sony BRAVIA TVs, the app can try to open this URL automatically through Sony IP Control. Enable this on the TV:

```text
Settings > Network > Home network > IP control
Authentication: Normal and Pre-Shared Key
```

Then enter the same pre-shared key in **Sony BRAVIA PSK** before starting **TV native browser** mode.

The stream also exposes:

```text
http://<computer-ip>:8080/snapshot.jpg
http://<computer-ip>:8080/health
```

Streaming mode uses more CPU because the computer renders the website and generates a live stream. Frames are kept in memory only and are not saved to disk.

---

## For normal users

Go to the `dist` folder and run:

```bash
NoMoreCables.exe
```

No Python setup needed. No terminal ceremony. Humanity briefly wins.

---

## For developers

### Requirements

- Python 3.10+
- `catt`
- `customtkinter`
- `pychromecast`
- `Pillow`
- `playwright`
- `ffmpeg` on PATH for Cast-compatible website stream mode
- `pyinstaller` if you want to build the executable

Tested mostly on Windows, but it should also work on Linux and macOS if the network gods are in a good mood.

### Setup

Clone the repo:

```bash
git clone https://github.com/Waaslandia/waaslandia-cast-v2.git
cd waaslandia-cast-v2
```

Create and activate a virtual environment:

```bash
python -m venv venv
.\venv\Scripts\activate
```

Install dependencies:

```bash
pip install customtkinter catt pychromecast pillow playwright pyinstaller
python -m playwright install chromium
```

Run the app:

```bash
python app.py
```

---

## How to use

1. Click **Scan for TV**
2. Pick the TV from the dropdown, or enter the TV IP manually
3. Enter the URL you want to cast
4. Choose the cast mode:
   - **Website / dashboard** for normal pages
   - **Media / video URL** for video/media links
   - **Website-to-video stream** for a local MJPEG stream
   - **TV native browser** when the TV browser can open the viewer manually
5. Click **Start Automation**

The app will keep checking the cast and try to restore it if it drops.

You can also click **Recast Once** to manually stop the current cast session and start it again.

---

## Good test URLs

For Website mode, start with something simple:

```text
https://example.com
```

Then test your real dashboard.

Do not judge the whole app based on one cursed website. Some pages render fine in desktop Chrome and still throw a tantrum on Chromecast.

For Media mode, test with a known media URL or supported video link.

For Website-to-video stream mode, start with:

```text
https://example.com
```

Then open the generated `/snapshot.jpg` or `/stream.mjpg` URL shown in the log from another browser or decoder on the same network. The app can try to cast `/stream.ts` to the selected TV, or open `/viewer` through website casting.

---

## Files

- `app.py`  
  Main application and UI

- `website_streamer.py`  
  Local browser renderer and MJPEG HTTP stream server

- `config.json`  
  Stores the last used TV IP, URL, and cast mode locally

- `build_exe.py`  
  Builds the standalone executable

- `no-moar-cables.png`  
  Optional meme image shown in the app

- `dist/`  
  Contains the ready-to-run executable after building

---

## Build the executable

Make sure your virtual environment is active and dependencies are installed:

```bash
pip install customtkinter catt pychromecast pillow playwright pyinstaller
python -m playwright install chromium
```

Then run:

```bash
python build_exe.py
```

The executable will appear in:

```bash
dist/
```

On Windows, the file will be:

```text
dist/NoMoreCables.exe
```

---

## Troubleshooting

### The TV is found, but the screen is black

The cast probably launched, but the Chromecast receiver could not render the page.

Try:

```text
https://example.com
```

If that works, your app is fine and the website is the problem. Congratulations, the internet has betrayed you again.

Common causes:

- page requires login cookies
- page redirects through authentication
- page uses unsupported browser APIs
- page is too heavy for the Chromecast receiver
- page blocks or fails in embedded/cast receiver contexts
- HTTPS certificate issues
- assets are not reachable from the TV
- mixed HTTP/HTTPS content

### Scan does not find the TV

Try entering the TV IP manually.

Also check:

- the TV and computer are on the same network
- the TV is powered on
- casting is enabled
- your firewall is not blocking local discovery
- the network allows mDNS / local device discovery

### Media links stopped working

Update `yt-dlp`:

```bash
pip install -U yt-dlp
```

Video platforms change constantly because apparently stability was outlawed.

### Streaming mode says Playwright or Chromium is missing

Install Playwright and its Chromium browser:

```bash
pip install playwright
python -m playwright install chromium
```

### Streaming mode starts, but the TV cannot play it

Open the logged `/snapshot.jpg` URL in a browser first. If that works, the app is rendering correctly. The video stream target casts `/stream.ts`, which requires `ffmpeg`; if that stalls on the TV, switch the website stream cast target to **TV browser viewer**.

---

_HDMI cables had a good run. Then we automated their job._
