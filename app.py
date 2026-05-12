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
from PIL import Image, ImageEnhance

from bravia_launcher import launch_bravia_web_url
from catt.cli import cli as catt_cli
from catt.cli import get_config_as_dict
from website_streamer import WebsiteStreamer, find_ffmpeg


# --- Configuration Settings ---
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "tv_ip": "",
    "url": "",
    "cast_mode": "website",
    "stream_host": "0.0.0.0",
    "stream_port": 8080,
    "stream_width": 1920,
    "stream_height": 1080,
    "stream_fps": 5,
    "stream_cast_method": "video",
    "native_browser_url": "snapshot_viewer",
    "bravia_psk": "",
    "stream_auto_accept": False,
    "stream_theme": "auto",
    "stream_pixel_shift": False,
}

stop_event = threading.Event()
worker_thread = None
website_streamer = None
active_tv_ip = None


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


def save_config(tv_ip, url, cast_mode, width, height, fps, auto_accept, psk, cast_method, theme, pixel_shift):
    current = load_config()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "tv_ip": tv_ip,
                "url": url,
                "cast_mode": cast_mode,
                "stream_host": current.get("stream_host", DEFAULT_CONFIG["stream_host"]),
                "stream_port": current.get("stream_port", DEFAULT_CONFIG["stream_port"]),
                "stream_width": width,
                "stream_height": height,
                "stream_fps": fps,
                "stream_cast_method": cast_method,
                "native_browser_url": current.get("native_browser_url", DEFAULT_CONFIG["native_browser_url"]),
                "bravia_psk": psk,
                "stream_auto_accept": auto_accept,
                "stream_theme": theme,
                "stream_pixel_shift": pixel_shift,
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


def get_safe_int(entry, default_val):
    try:
        val = entry.get().strip()
        return int(val) if val else default_val
    except (ValueError, AttributeError):
        return default_val


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


def log_stream_request(client_ip, path):
    if path in ("/snapshot.jpg", "/snapshot-viewer", "/viewer", "/stream.mjpg", "/stream.ts"):
        log(f"Stream HTTP request from {client_ip}: {path}")


def configure_widget(widget, **kwargs):
    ui_call(lambda: widget.configure(**kwargs))


def set_inputs_enabled(enabled):
    state = "normal" if enabled else "disabled"
    configure_widget(ip_entry, state=state)
    configure_widget(bravia_psk_entry, state=state)
    configure_widget(stream_width_entry, state=state)
    configure_widget(stream_height_entry, state=state)
    configure_widget(stream_fps_entry, state=state)
    configure_widget(stream_theme_menu, state=state)
    configure_widget(stream_auto_accept_checkbox, state=state)
    configure_widget(stream_pixel_shift_checkbox, state=state)
    configure_widget(url_entry, state=state)
    configure_widget(scan_btn, state=state)
    configure_widget(mode_website, state=state)
    configure_widget(mode_media, state=state)
    configure_widget(mode_stream, state=state)
    configure_widget(mode_native_browser, state=state)
    configure_widget(stream_cast_video, state=state)
    configure_widget(stream_cast_viewer, state=state)
    configure_widget(stream_cast_snapshot_viewer, state=state)
    configure_widget(start_btn, state="normal" if enabled else "disabled")
    configure_widget(stop_btn, state="disabled" if enabled else "normal")
    configure_widget(recast_btn, state=state if enabled else "disabled")


def selected_cast_mode():
    return cast_mode_var.get()


def cast_command_for_mode(cast_mode):
    if cast_mode == "media":
        return "cast"
    return "cast_site"


def human_mode_name(cast_mode):
    if cast_mode == "media":
        return "Media"
    if cast_mode == "website_stream":
        return "Website-to-video stream"
    if cast_mode == "native_browser":
        return "TV native browser"
    return "Website"


def is_stream_mode(cast_mode):
    return cast_mode == "website_stream"


def is_local_stream_mode(cast_mode):
    return cast_mode in ("website_stream", "native_browser")


def selected_stream_cast_method():
    return stream_cast_method_var.get()


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
        time.sleep(5)  # Increased delay for older TVs

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
    ok, out = cast_url(tv_ip, url, cast_mode, force_stop_first=True)
    if not ok and "timed out" in out.lower():
        set_status("Status: Initial cast timed out. Waiting 10s...", "orange")
        log("Initial cast timed out. The TV is likely warming up.")
        time.sleep(10)

    while not stop_event.is_set():
        ok, status_output = get_catt_status(tv_ip)

        if not ok:
            set_status("Status: TV/cast status unavailable. Retrying...", "orange")
            log("Status check failed. Will try casting again.")
            cast_url(tv_ip, url, cast_mode, force_stop_first=False)

        elif should_recast_from_status(status_output):
            set_status("Status: Cast not active. Recasting...", "orange")
            ok, out = cast_url(tv_ip, url, cast_mode, force_stop_first=False)
            if not ok and "timed out" in out.lower():
                set_status("Status: TV is slow to respond. Waiting 10s...", "orange")
                log("Cast timed out. Giving the TV 10 seconds to catch up.")
                time.sleep(10)

        else:
            set_status(f"Status: Actively Casting ({human_mode_name(cast_mode)})", "green")

        # Wait up to 60 seconds, but stop quickly when requested.
        for _ in range(60):
            if stop_event.is_set():
                break
            time.sleep(1)

    set_status("Status: Stopped", "gray")
    log("Automation stopped.")


def website_stream_loop(tv_ip, url):
    global website_streamer

    stream_config = load_config()
    had_error = False
    set_status("Status: Starting local website stream...", "blue")
    log("Website stream mode selected.")

    try:
        website_streamer = WebsiteStreamer(
            url=url,
            host=stream_config.get("stream_host", DEFAULT_CONFIG["stream_host"]),
            port=stream_config.get("stream_port", DEFAULT_CONFIG["stream_port"]),
            width=stream_config.get("stream_width", DEFAULT_CONFIG["stream_width"]),
            height=stream_config.get("stream_height", DEFAULT_CONFIG["stream_height"]),
            fps=stream_config.get("stream_fps", DEFAULT_CONFIG["stream_fps"]),
            auto_accept_prompts=stream_config.get("stream_auto_accept", False),
            theme=stream_config.get("stream_theme", "auto"),
            pixel_shift=stream_config.get("stream_pixel_shift", False),
            on_log=log,
            on_status=set_status,
            on_request=log_stream_request,
        )
        website_streamer.start()

        log(f"MJPEG stream available at: {website_streamer.network_url}")
        log(f"Cast video stream available at: {website_streamer.network_video_url}")
        log(f"Browser fallback viewer available at: {website_streamer.network_viewer_url}")
        log(f"Snapshot-refresh viewer available at: {website_streamer.network_snapshot_viewer_url}")
        log(f"Local stream URL: {website_streamer.local_url}")
        log("Frames are streamed in memory only. Nothing is written to disk.")
        set_status(f"Status: Stream running at {website_streamer.network_video_url}", "green")

        if website_streamer.wait_for_frame(timeout=15):
            stream_cast_method = stream_config.get(
                "stream_cast_method",
                DEFAULT_CONFIG["stream_cast_method"],
            )

            if stream_cast_method == "viewer":
                set_status("Status: Opening stream viewer on TV...", "blue")
                log(f"Opening browser fallback viewer on selected TV: {tv_ip}")
                cast_url(tv_ip, website_streamer.network_viewer_url, "website", force_stop_first=True)
            elif stream_cast_method == "snapshot_viewer":
                set_status("Status: Opening snapshot viewer on TV...", "blue")
                log(f"Opening snapshot-refresh viewer on selected TV: {tv_ip}")
                cast_url(tv_ip, website_streamer.network_snapshot_viewer_url, "website", force_stop_first=True)
            else:
                if not find_ffmpeg():
                    raise RuntimeError("ffmpeg is not installed or not on PATH. Install ffmpeg before casting /stream.ts.")

                set_status("Status: Casting generated video stream to TV...", "blue")
                log(f"Casting generated video stream to selected TV: {tv_ip}")
                cast_url(tv_ip, website_streamer.network_video_url, "media", force_stop_first=True)
        elif not website_streamer.render_error:
            log("Stream started, but no frame was produced yet. Not casting to TV until a frame exists.")

        while not stop_event.is_set() and not website_streamer.stop_event.is_set():
            time.sleep(0.2)

        if website_streamer.render_error:
            had_error = True

    except RuntimeError as e:
        had_error = True
        set_status(f"Error: {e}", "red")
        log(str(e))

    finally:
        if website_streamer:
            website_streamer.stop()
            website_streamer = None

        if not had_error:
            set_status("Status: Stream stopped", "gray")
        log("Website stream stopped.")


def native_browser_loop(tv_ip, url, bravia_psk):
    global website_streamer

    stream_config = load_config()
    had_error = False
    set_status("Status: Starting local browser stream...", "blue")
    log("TV native browser mode selected.")

    try:
        website_streamer = WebsiteStreamer(
            url=url,
            host=stream_config.get("stream_host", DEFAULT_CONFIG["stream_host"]),
            port=stream_config.get("stream_port", DEFAULT_CONFIG["stream_port"]),
            width=stream_config.get("stream_width", DEFAULT_CONFIG["stream_width"]),
            height=stream_config.get("stream_height", DEFAULT_CONFIG["stream_height"]),
            fps=stream_config.get("stream_fps", DEFAULT_CONFIG["stream_fps"]),
            auto_accept_prompts=stream_config.get("stream_auto_accept", False),
            theme=stream_config.get("stream_theme", "auto"),
            pixel_shift=stream_config.get("stream_pixel_shift", False),
            on_log=log,
            on_status=set_status,
            on_request=log_stream_request,
        )
        website_streamer.start()

        if website_streamer.wait_for_frame(timeout=15):
            set_status(f"Status: Open on TV: {website_streamer.network_snapshot_viewer_url}", "green")
            log("Open this URL in the TV native browser:")
            log(website_streamer.network_snapshot_viewer_url)
            log(f"Snapshot viewer URL: {website_streamer.network_snapshot_viewer_url}")
            log(f"MJPEG viewer URL: {website_streamer.network_viewer_url}")
            log("This mode does not use CATT/Chromecast.")

            if tv_ip and bravia_psk:
                try:
                    set_status("Status: Launching BRAVIA browser...", "blue")
                    launch_bravia_web_url(tv_ip, website_streamer.network_snapshot_viewer_url, bravia_psk)
                    set_status("Status: BRAVIA browser launch command sent", "green")
                    log(f"BRAVIA browser launch command sent to {tv_ip}.")
                except Exception as e:
                    set_status("Status: Manual TV browser open required", "orange")
                    log(f"BRAVIA browser auto-launch failed: {e}")
                    log("Open the snapshot viewer URL manually on the TV.")
            else:
                log("BRAVIA auto-launch skipped. Enter TV IP and Sony PSK to enable it.")
        elif not website_streamer.render_error:
            log("Stream started, but no frame was produced yet.")

        while not stop_event.is_set() and not website_streamer.stop_event.is_set():
            time.sleep(0.2)

        if website_streamer.render_error:
            had_error = True

    except RuntimeError as e:
        had_error = True
        set_status(f"Error: {e}", "red")
        log(str(e))

    finally:
        if website_streamer:
            website_streamer.stop()
            website_streamer = None

        if not had_error:
            set_status("Status: Native browser stream stopped", "gray")
        log("TV native browser stream stopped.")


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
    global worker_thread, active_tv_ip

    if worker_thread and worker_thread.is_alive():
        return

    tv_ip = ip_entry.get().strip()
    bravia_psk = bravia_psk_entry.get().strip()
    url = normalize_url(url_entry.get().strip())
    cast_mode = selected_cast_mode()

    if not url:
        set_status("Error: URL required.", "red")
        return

    if not tv_ip and not is_local_stream_mode(cast_mode):
        set_status("Error: IP and URL required.", "red")
        return

    if tv_ip and not is_valid_ip(tv_ip):
        set_status("Error: Invalid TV IP address.", "red")
        return

    if not is_valid_url(url):
        set_status("Error: Enter a valid http/https URL.", "red")
        return

    # Put normalized URL back in the UI so the user sees what will be used.
    url_entry.delete(0, "end")
    url_entry.insert(0, url)

    # Gather settings
    width = get_safe_int(stream_width_entry, DEFAULT_CONFIG["stream_width"])
    height = get_safe_int(stream_height_entry, DEFAULT_CONFIG["stream_height"])
    fps = get_safe_int(stream_fps_entry, DEFAULT_CONFIG["stream_fps"])
    auto_accept = stream_auto_accept_var.get()
    cast_method = selected_stream_cast_method()
    theme = stream_theme_var.get()
    pixel_shift = stream_pixel_shift_var.get()

    save_config(tv_ip, url, cast_mode, width, height, fps, auto_accept, bravia_psk, cast_method, theme, pixel_shift)

    stop_event.clear()
    active_tv_ip = tv_ip
    set_inputs_enabled(False)

    if is_stream_mode(cast_mode):
        worker_thread = threading.Thread(
            target=website_stream_loop,
            args=(tv_ip, url),
            daemon=True,
        )
    elif cast_mode == "native_browser":
        worker_thread = threading.Thread(
            target=native_browser_loop,
            args=(tv_ip, url, bravia_psk),
            daemon=True,
        )
    else:
        worker_thread = threading.Thread(
            target=casting_loop,
            args=(tv_ip, url, cast_mode),
            daemon=True,
        )
    worker_thread.start()


def stop_app():
    global website_streamer, active_tv_ip

    stop_event.set()
    if website_streamer:
        website_streamer.stop_event.set()

    tv_ip = active_tv_ip or ip_entry.get().strip()
    if is_valid_ip(tv_ip):
        def run_stop_cast():
            log(f"Stopping receiver session on TV: {tv_ip}")
            stop_current_cast(tv_ip)

        threading.Thread(target=run_stop_cast, daemon=True).start()

    set_inputs_enabled(True)
    set_status("Status: Stopping...", "orange")
    log("Stop requested.")


def recast_once():
    tv_ip = ip_entry.get().strip()
    url = normalize_url(url_entry.get().strip())
    cast_mode = selected_cast_mode()

    if is_local_stream_mode(cast_mode):
        set_status("Status: Recast is only available for CATT modes.", "orange")
        return

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
app.geometry("950x660")
app.minsize(900, 600)

config = load_config()

# --- UI Elements ---
title_label = ctk.CTkLabel(app, text="NO MORE CABLES!!", font=("Arial", 22, "bold"))
title_label.pack(pady=(18, 8))

# --- Layout Container ---
try:
    img = Image.open(resource_path("no-moar-cables.png")).convert("RGBA")
    enhancer = ImageEnhance.Brightness(img)
    img_dark = enhancer.enhance(0.15)  # 15% brightness, very dark for readability
    
    bg_image = ctk.CTkImage(
        light_image=img_dark,
        dark_image=img_dark,
        size=(1920, 1080),
    )
    bg_label = ctk.CTkLabel(app, image=bg_image, text="")
    bg_label.place(x=0, y=0, relwidth=1, relheight=1)
    bg_label.lower()  # Send to back so it doesn't cover the title
except Exception:
    pass

main_content = ctk.CTkScrollableFrame(app, fg_color="transparent")
main_content.pack(fill="both", expand=True, padx=30, pady=(0, 20))

# Left Column (Controls)
left_column = ctk.CTkFrame(main_content, fg_color="transparent")
left_column.pack(side="left", fill="both", expand=True, padx=(0, 20))

# Right Column (Log)
right_column = ctk.CTkFrame(main_content, fg_color="transparent")
right_column.pack(side="left", fill="both", expand=True)

# --- Left Column Elements ---
form_frame = ctk.CTkFrame(left_column, fg_color="transparent")
form_frame.pack(fill="x")

ip_label = ctk.CTkLabel(form_frame, text="TV IP Address:")
ip_label.pack(anchor="w")

ip_container = ctk.CTkFrame(form_frame, fg_color="transparent")
ip_container.pack(fill="x")

ip_frame = ctk.CTkFrame(ip_container, fg_color="transparent")
ip_frame.pack(fill="x", pady=5)

ip_entry = ctk.CTkEntry(ip_frame, width=200, placeholder_text="e.g. 192.168.1.50")
ip_entry.insert(0, config.get("tv_ip", ""))
ip_entry.pack(side="left", padx=(0, 10), fill="x", expand=True)

scan_btn = ctk.CTkButton(
    ip_frame,
    text="Scan for TV",
    width=110,
    height=35,
    font=("Arial", 12, "bold"),
    command=discover_devices,
)
scan_btn.pack(side="left")

device_menu = ctk.CTkOptionMenu(ip_container, width=400)
device_menu.pack_forget()

bravia_psk_label = ctk.CTkLabel(form_frame, text="Sony BRAVIA PSK (optional):")
bravia_psk_label.pack(anchor="w", pady=(10, 0))

bravia_psk_entry = ctk.CTkEntry(form_frame, placeholder_text="Pre-shared key for IP Control")
bravia_psk_entry.insert(0, config.get("bravia_psk", ""))
bravia_psk_entry.pack(pady=5, fill="x")

url_label = ctk.CTkLabel(form_frame, text="URL to Cast:")
url_label.pack(anchor="w", pady=(10, 0))

url_entry = ctk.CTkEntry(form_frame, placeholder_text="https://example.com or YouTube/media URL")
url_entry.insert(0, config.get("url", ""))
url_entry.pack(pady=5, fill="x")

mode_label = ctk.CTkLabel(form_frame, text="Cast Mode:")
mode_label.pack(anchor="w", pady=(10, 0))

cast_mode_var = ctk.StringVar(value=config.get("cast_mode", "website"))
stream_cast_method_var = ctk.StringVar(value=config.get("stream_cast_method", "video"))

mode_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
mode_frame.pack(fill="x", pady=(2, 8))

mode_website = ctk.CTkRadioButton(
    mode_frame,
    text="Website",
    variable=cast_mode_var,
    value="website",
)
mode_website.pack(side="left", padx=(0, 15))

mode_media = ctk.CTkRadioButton(
    mode_frame,
    text="Media / Video",
    variable=cast_mode_var,
    value="media",
)
mode_media.pack(side="left", padx=(0, 15))

mode_stream = ctk.CTkRadioButton(
    mode_frame,
    text="Website-to-video stream",
    variable=cast_mode_var,
    value="website_stream",
)
mode_stream.pack(side="left", padx=(0, 15))

mode_native_browser = ctk.CTkRadioButton(
    mode_frame,
    text="TV native browser",
    variable=cast_mode_var,
    value="native_browser",
)
mode_native_browser.pack(side="left")

stream_cast_label = ctk.CTkLabel(form_frame, text="Website stream cast target:")
stream_cast_label.pack(anchor="w", pady=(4, 0))

stream_cast_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
stream_cast_frame.pack(fill="x", pady=(2, 8))

stream_cast_video = ctk.CTkRadioButton(
    stream_cast_frame,
    text="Video stream",
    variable=stream_cast_method_var,
    value="video",
)
stream_cast_video.pack(side="left", padx=(0, 15))

stream_cast_viewer = ctk.CTkRadioButton(
    stream_cast_frame,
    text="TV browser viewer",
    variable=stream_cast_method_var,
    value="viewer",
)
stream_cast_viewer.pack(side="left", padx=(0, 15))

stream_cast_snapshot_viewer = ctk.CTkRadioButton(
    stream_cast_frame,
    text="Snapshot viewer",
    variable=stream_cast_method_var,
    value="snapshot_viewer",
)
stream_cast_snapshot_viewer.pack(side="left")

# --- Stream Settings Group ---
stream_settings_label = ctk.CTkLabel(form_frame, text="Stream Settings:", font=("Arial", 12, "bold"))
stream_settings_label.pack(anchor="w", pady=(15, 0))

stream_settings_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
stream_settings_frame.pack(fill="x", pady=5)

# Row 1: Width, Height, FPS
stream_dims_frame = ctk.CTkFrame(stream_settings_frame, fg_color="transparent")
stream_dims_frame.pack(fill="x")

ctk.CTkLabel(stream_dims_frame, text="Width:").pack(side="left")
stream_width_entry = ctk.CTkEntry(stream_dims_frame, width=60)
stream_width_entry.insert(0, str(config.get("stream_width", 1920)))
stream_width_entry.pack(side="left", padx=(5, 15))

ctk.CTkLabel(stream_dims_frame, text="Height:").pack(side="left")
stream_height_entry = ctk.CTkEntry(stream_dims_frame, width=60)
stream_height_entry.insert(0, str(config.get("stream_height", 1080)))
stream_height_entry.pack(side="left", padx=(5, 15))

ctk.CTkLabel(stream_dims_frame, text="FPS:").pack(side="left")
stream_fps_entry = ctk.CTkEntry(stream_dims_frame, width=40)
stream_fps_entry.insert(0, str(config.get("stream_fps", 5)))
stream_fps_entry.pack(side="left", padx=(5, 15))

# Row 2: Theme
stream_theme_frame = ctk.CTkFrame(stream_settings_frame, fg_color="transparent")
stream_theme_frame.pack(fill="x", pady=(5, 0))

ctk.CTkLabel(stream_theme_frame, text="Theme:").pack(side="left")
stream_theme_var = ctk.StringVar(value=config.get("stream_theme", "auto"))
stream_theme_menu = ctk.CTkOptionMenu(
    stream_theme_frame,
    variable=stream_theme_var,
    values=["auto", "dark", "light"],
    width=80
)
stream_theme_menu.pack(side="left", padx=(5, 0))

# Row 3: Checkboxes
stream_checkboxes_frame = ctk.CTkFrame(stream_settings_frame, fg_color="transparent")
stream_checkboxes_frame.pack(fill="x", pady=(10, 0))

stream_auto_accept_var = ctk.BooleanVar(value=config.get("stream_auto_accept", False))
stream_auto_accept_checkbox = ctk.CTkCheckBox(
    stream_checkboxes_frame,
    text="Auto-accept prompts (cookies)",
    variable=stream_auto_accept_var,
    font=("Arial", 12)
)
stream_auto_accept_checkbox.pack(anchor="w")

stream_pixel_shift_var = ctk.BooleanVar(value=config.get("stream_pixel_shift", False))
stream_pixel_shift_checkbox = ctk.CTkCheckBox(
    stream_checkboxes_frame,
    text="Pixel shift (burn-in protection)",
    variable=stream_pixel_shift_var,
    font=("Arial", 12)
)
stream_pixel_shift_checkbox.pack(anchor="w", pady=(5, 0))

status_label = ctk.CTkLabel(left_column, text="Status: Stopped", text_color="gray", font=("Arial", 14, "bold"))
status_label.pack(pady=(15, 10))

button_frame = ctk.CTkFrame(left_column, fg_color="transparent")
button_frame.pack(pady=(5, 0))

start_btn = ctk.CTkButton(
    button_frame,
    text="Start",
    command=start_app,
    fg_color="green",
    hover_color="darkgreen",
    width=110,
    height=40,
    font=("Arial", 13, "bold"),
)
start_btn.pack(side="left", padx=5)

recast_btn = ctk.CTkButton(
    button_frame,
    text="Recast",
    command=recast_once,
    width=110,
    height=40,
    font=("Arial", 13, "bold"),
)
recast_btn.pack(side="left", padx=5)

stop_btn = ctk.CTkButton(
    button_frame,
    text="Stop",
    command=stop_app,
    fg_color="red",
    hover_color="darkred",
    state="disabled",
    width=110,
    height=40,
    font=("Arial", 13, "bold"),
)
stop_btn.pack(side="left", padx=5)

# --- Right Column Elements ---
log_label = ctk.CTkLabel(right_column, text="Activity Log:", font=("Arial", 12, "bold"))
log_label.pack(anchor="w", pady=(0, 5))

log_box = ctk.CTkTextbox(right_column, font=("Consolas", 11))
log_box.pack(fill="both", expand=True)
log_box.insert("end", "Ready. The cables are nervous.\n")
log_box.configure(state="disabled")

app.mainloop()
