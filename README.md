# NO MORE CABLES!! 🚀

## Auto-Caster v2

A small utility that keeps a URL casting to a TV.

Useful for dashboards, kiosk pages, schedules, menus, or anything else that should stay visible without someone crawling behind a screen with an HDMI cable like it’s 2011.

It works with Chromecasts and Sony BRAVIA TVs.

---

## What it does

- Finds available Chromecast / Sony TV devices on the network
- Lets you pick the target TV
- Casts a URL to it
- Checks regularly whether the TV is still reachable
- Restarts the cast if the TV drops, restarts, or forgets what it was doing
- Remembers your last used TV IP and URL

Basically: set it once, let it babysit the screen.

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
pip install customtkinter catt pychromecast
```

Run the app:

```bash
python app.py
```

---

## How to use

1. Click **Scan for TV**
2. Pick the TV from the dropdown
3. Enter the URL you want to show
4. Click **Start Automation**

The app will keep checking the TV and try to restore the cast if it drops.

---

## Files

- `app.py`  
  Main application and UI

- `config.json`  
  Stores the last used TV IP and URL locally

- `build_exe.py`  
  Builds the standalone Windows executable

- `dist/`  
  Contains the ready-to-run `.exe`

---

## Build the executable

```bash
python build_exe.py
```

The executable will appear in:

```bash
dist/
```

---

## Notes

This tool depends on your local network behaving like a civilized invention, which is never guaranteed.

If discovery does not work, make sure:

- The TV and computer are on the same network
- The TV is powered on
- Casting is enabled
- Your firewall is not silently ruining your day

---

_HDMI cables had a good run. Then we automated their job._
