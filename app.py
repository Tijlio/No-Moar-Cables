import contextlib
import ipaddress
import json
import os
import re
import sys
import threading
import time
from io import StringIO
from urllib.parse import urlparse

import customtkinter as ctk
from PIL import Image

from catt.cli import cli as catt_cli
from catt.cli import get_config_as_dict


# --- Configuration Settings ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "tv_ip": "",
    "url": "",
    "cast_mode": "website",
}

stop_event = threading.Event()
worker_thread = None


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return DEFAULT_CONFIG.copy()

            loaded = json.loads(content)
            config = DEFAULT_CONFIG.copy()
            config.update({k: v for k, v in loaded.items() if k in config})
            return config
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(tv_ip, url, cast_mode):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "tv_ip": tv_ip,
                "url": url,
                "cast_mode": cast_mode,
            },
            f,
            indent=2,
        )


def normalize_url(url):
    """Add https:// when the user enters something like example.com."""
    url = url.strip()
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def is_valid_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_valid_url(value):
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def run_catt_internal(args):
    """
    Run CATT inside this process.

    Returns:
        tuple[bool, str]: success flag and captured stdout/stderr.
    """
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            catt_cli.main(
                args=args,
                obj=get_config_as_dict(),
                standalone_mode=False,
            )

        output = stdout_buffer.getvalue() + stderr_buffer.getvalue()
        return True, output.strip()

    except SystemExit as e:
        output = stdout_buffer.getvalue() + stderr_buffer.getvalue()
        code = e.code if isinstance(e.code, int) else 0
        return code == 0, output.strip()

    except Exception as e:
        output = stdout_buffer.getvalue() + stderr_buffer.getvalue()
        if output:
            output += "\n"
        output += f"Internal CATT Error: {e}"
        return False, output.strip()


# --- GUI helpers. Tkinter must only be touched from the main thread. ---
def ui_call(callback):
    app.after(0, callback)


def set_status(text, color="gray"):
    ui_call(lambda: status_label.configure(text=text, text_color=color))


def log(message):
    timestamp = time.strftime("%H:%M:%S")

    def _append():
        log_box.configure(state="normal")
        log_box.insert("end", f"[{timestamp}] {message}\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    ui_call(_append)


def configure_widget(widget, **kwargs):
    ui_call(lambda: widget.configure(**kwargs))


def set_inputs_enabled(enabled):
    state = "normal" if enabled else "disabled"
    configure_widget(ip_entry, state=state)
    configure_widget(url_entry, state=state)
    configure_widget(scan_btn, state=state)
    configure_widget(mode_website, state=state)
    configure_widget(mode_media, state=state)
    configure_widget(start_btn, state="normal" if enabled else "disabled")
    configure_widget(stop_btn, state="disabled" if enabled else "normal")


def selected_cast_mode():
    return cast_mode_var.get()


def cast_command_for_mode(cast_mode):
    if cast_mode == "media":
        return "cast"
    return "cast_site"


def human_mode_name(cast_mode):
    if cast_mode == "media":
        return "Media"
    return "Website"


def stop_current_cast(tv_ip):
    # CATT stop may stop playback but may not always close the receiver app.
    # It still helps reset sticky sessions before a new cast attempt.
    ok, output = run_catt_internal(["-d", tv_ip, "stop"])
    if output:
        log(f"CATT stop: {output}")
    return ok


def get_catt_status(tv_ip):
    ok, output = run_catt_internal(["-d", tv_ip, "status"])
    if output:
        log(f"CATT status: {output}")
    return ok, output


def cast_url(tv_ip, url, cast_mode, force_stop_first=True):
    command = cast_command_for_mode(cast_mode)

    if force_stop_first:
        set_status("Status: Resetting current cast session...", "orange")
        stop_current_cast(tv_ip)
        time.sleep(2)

    set_status(f"Status: Casting {human_mode_name(cast_mode).lower()}...", "blue")
    log(f"Running: catt -d {tv_ip} {command} {url}")

    ok, output = run_catt_internal(["-d", tv_ip, command, url])
    if output:
        log(f"CATT {command}: {output}")

    return ok, output


def should_recast_from_status(status_output):
    """
    Basic status check.

    CATT output can vary by version/device, so keep this intentionally broad.
    If it does not clearly look active, recast.
    """
    if not status_output:
        return True

    normalized = status_output.upper()
    active_keywords = ("PLAYING", "BUFFERING", "LOADING")
    return not any(keyword in normalized for keyword in active_keywords)


def casting_loop(tv_ip, url, cast_mode):
    set_status("Status: Starting automation...", "blue")
    log(f"Automation started in {human_mode_name(cast_mode)} mode.")
    log(f"Target TV: {tv_ip}")
    log(f"Target URL: {url}")

    # Always try a fresh cast at startup. It prevents sticky old receiver sessions,
    # which are apparently a lifestyle choice for Chromecast.
    cast_url(tv_ip, url, cast_mode, force_stop_first=True)

    while not stop_event.is_set():
        ok, status_output = get_catt_status(tv_ip)

        if not ok:
            set_status("Status: TV/cast status unavailable. Retrying...", "orange")
            log("Status check failed. Will try casting again.")
            cast_url(tv_ip, url, cast_mode, force_stop_first=False)

        elif should_recast_from_status(status_output):
            set_status("Status: Cast not active. Recasting...", "orange")
            cast_url(tv_ip, url, cast_mode, force_stop_first=False)

        else:
            set_status(f"Status: Actively Casting ({human_mode_name(cast_mode)})", "green")

        # Wait up to 60 seconds, but stop quickly when requested.
        for _ in range(60):
            if stop_event.is_set():
                break
            time.sleep(1)

    set_status("Status: Stopped", "gray")
    log("Automation stopped.")


def discover_devices():
    def run_scan():
        configure_widget(scan_btn, state="disabled", text="Scanning...")
        set_status("Status: Scanning for devices...", "blue")
        log("Scanning for Cast devices...")

        try:
            ok, output = run_catt_internal(["scan"])

            if output:
                log(f"CATT scan: {output}")

            if not ok:
                set_status("Status: Scan failed. Enter IP manually.", "red")
                return

            matches = re.findall(
                r"^(\d{1,3}(?:\.\d{1,3}){3})\s+-\s+(.+)$",
                output,
                re.MULTILINE,
            )

            valid_matches = []
            for ip, name in matches:
                if is_valid_ip(ip):
                    valid_matches.append((ip, name.strip()))

            if not valid_matches:
                set_status("Status: No devices found. Enter IP manually.", "orange")
                ui_call(device_menu.pack_forget)
                return

            options = [f"{name} ({ip})" for ip, name in valid_matches]
            ip_map = {f"{name} ({ip})": ip for ip, name in valid_matches}

            def on_select(selected_name):
                selected_ip = ip_map.get(selected_name)
                if not selected_ip:
                    return

                ip_entry.delete(0, "end")
                ip_entry.insert(0, selected_ip)
                set_status(f"Status: Selected {selected_name}", "green")
                log(f"Selected device: {selected_name}")

            default_choice = options[0]
            for option in options:
                if "sony" in option.lower() or "bravia" in option.lower():
                    default_choice = option
                    break

            def update_menu():
                device_menu.configure(values=options, command=on_select)
                device_menu.pack(pady=(0, 10))
                device_menu.set(default_choice)
                on_select(default_choice)

            ui_call(update_menu)
            set_status(f"Status: Found {len(valid_matches)} device(s)", "green")

        except Exception as e:
            set_status(f"Status: Scan failed ({e})", "red")
            log(f"Scan failed: {e}")

        finally:
            configure_widget(scan_btn, state="normal", text="Scan for TV")

    threading.Thread(target=run_scan, daemon=True).start()


def start_app():
    global worker_thread

    if worker_thread and worker_thread.is_alive():
        return

    tv_ip = ip_entry.get().strip()
    url = normalize_url(url_entry.get().strip())
    cast_mode = selected_cast_mode()

    if not tv_ip or not url:
        set_status("Error: IP and URL required.", "red")
        return

    if not is_valid_ip(tv_ip):
        set_status("Error: Invalid TV IP address.", "red")
        return

    if not is_valid_url(url):
        set_status("Error: Enter a valid http/https URL.", "red")
        return

    # Put normalized URL back in the UI so the user sees what will be used.
    url_entry.delete(0, "end")
    url_entry.insert(0, url)

    save_config(tv_ip, url, cast_mode)
    stop_event.clear()
    set_inputs_enabled(False)

    worker_thread = threading.Thread(
        target=casting_loop,
        args=(tv_ip, url, cast_mode),
        daemon=True,
    )
    worker_thread.start()


def stop_app():
    stop_event.set()
    set_inputs_enabled(True)
    set_status("Status: Stopping...", "orange")
    log("Stop requested.")


def recast_once():
    tv_ip = ip_entry.get().strip()
    url = normalize_url(url_entry.get().strip())
    cast_mode = selected_cast_mode()

    if not is_valid_ip(tv_ip):
        set_status("Error: Invalid TV IP address.", "red")
        return

    if not is_valid_url(url):
        set_status("Error: Enter a valid http/https URL.", "red")
        return

    def run_recast():
        cast_url(tv_ip, url, cast_mode, force_stop_first=True)

    threading.Thread(target=run_recast, daemon=True).start()


# --- Initialize GUI Window ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("No More Cables")
app.geometry("500x820")
app.minsize(500, 780)

config = load_config()

# --- UI Elements ---
title_label = ctk.CTkLabel(app, text="NO MORE CABLES!!", font=("Arial", 22, "bold"))
title_label.pack(pady=(18, 8))

try:
    meme_img = ctk.CTkImage(
        light_image=Image.open(resource_path("no-moar-cables.png")),
        dark_image=Image.open(resource_path("no-moar-cables.png")),
        size=(340, 340),
    )
    meme_label = ctk.CTkLabel(app, image=meme_img, text="")
    meme_label.pack(pady=(0, 12))
except Exception:
    pass

form_frame = ctk.CTkFrame(app, fg_color="transparent")
form_frame.pack(fill="x", padx=40)

ip_label = ctk.CTkLabel(form_frame, text="TV IP Address:")
ip_label.pack(anchor="w")

ip_container = ctk.CTkFrame(form_frame, fg_color="transparent")
ip_container.pack(fill="x")

ip_frame = ctk.CTkFrame(ip_container, fg_color="transparent")
ip_frame.pack(fill="x", pady=5)

ip_entry = ctk.CTkEntry(ip_frame, width=275, placeholder_text="e.g. 192.168.1.50")
ip_entry.insert(0, config.get("tv_ip", ""))
ip_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

scan_btn = ctk.CTkButton(
    ip_frame,
    text="Scan for TV",
    width=125,
    height=35,
    font=("Arial", 13, "bold"),
    command=discover_devices,
)
scan_btn.pack(side="left")

device_menu = ctk.CTkOptionMenu(ip_container, width=420)
device_menu.pack_forget()

url_label = ctk.CTkLabel(form_frame, text="URL to Cast:")
url_label.pack(anchor="w", pady=(10, 0))

url_entry = ctk.CTkEntry(form_frame, width=420, placeholder_text="https://example.com or YouTube/media URL")
url_entry.insert(0, config.get("url", ""))
url_entry.pack(pady=5, fill="x")

mode_label = ctk.CTkLabel(form_frame, text="Cast Mode:")
mode_label.pack(anchor="w", pady=(10, 0))

cast_mode_var = ctk.StringVar(value=config.get("cast_mode", "website"))

mode_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
mode_frame.pack(fill="x", pady=(2, 8))

mode_website = ctk.CTkRadioButton(
    mode_frame,
    text="Website / dashboard",
    variable=cast_mode_var,
    value="website",
)
mode_website.pack(side="left", padx=(0, 18))

mode_media = ctk.CTkRadioButton(
    mode_frame,
    text="Media / video URL",
    variable=cast_mode_var,
    value="media",
)
mode_media.pack(side="left")

hint_label = ctk.CTkLabel(
    form_frame,
    text="Website mode uses catt cast_site. Media mode uses catt cast.",
    text_color="gray",
    font=("Arial", 12),
)
hint_label.pack(anchor="w", pady=(0, 10))

status_label = ctk.CTkLabel(app, text="Status: Stopped", text_color="gray", font=("Arial", 14))
status_label.pack(pady=(8, 8))

button_frame = ctk.CTkFrame(app, fg_color="transparent")
button_frame.pack(pady=(4, 10))

start_btn = ctk.CTkButton(
    button_frame,
    text="Start Automation",
    command=start_app,
    fg_color="green",
    hover_color="darkgreen",
    width=165,
    height=42,
    font=("Arial", 14, "bold"),
)
start_btn.pack(side="left", padx=7)

recast_btn = ctk.CTkButton(
    button_frame,
    text="Recast Once",
    command=recast_once,
    width=125,
    height=42,
    font=("Arial", 14, "bold"),
)
recast_btn.pack(side="left", padx=7)

stop_btn = ctk.CTkButton(
    button_frame,
    text="Stop",
    command=stop_app,
    fg_color="red",
    hover_color="darkred",
    state="disabled",
    width=100,
    height=42,
    font=("Arial", 14, "bold"),
)
stop_btn.pack(side="left", padx=7)

log_label = ctk.CTkLabel(app, text="Log:")
log_label.pack(anchor="w", padx=40)

log_box = ctk.CTkTextbox(app, width=420, height=115, font=("Consolas", 11))
log_box.pack(padx=40, pady=(0, 16), fill="both", expand=False)
log_box.insert("end", "Ready. The cables are nervous.\n")
log_box.configure(state="disabled")

app.mainloop()
