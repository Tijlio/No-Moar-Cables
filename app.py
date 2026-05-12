import customtkinter as ctk
import json
import os
import subprocess
import threading
import time
import platform
import re
import sys
import contextlib
from io import StringIO
from PIL import Image
from catt.cli import cli as catt_cli
from catt.cli import get_config_as_dict

# --- Configuration Settings ---
CONFIG_FILE = "config.json"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    return {"tv_ip": "", "url": ""}
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {"tv_ip": "", "url": ""}
    return {"tv_ip": "", "url": ""}

def save_config(tv_ip, url):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"tv_ip": tv_ip, "url": url}, f)

# --- Background Automation Logic ---
is_running = False

def run_catt_internal(args):
    """Invokes catt internally without needing a separate process."""
    mystdout = StringIO()
    with contextlib.redirect_stdout(mystdout):
        try:
            # catt_cli is a click Group. main() is the entry point.
            catt_cli.main(args=args, obj=get_config_as_dict(), standalone_mode=False)
        except SystemExit:
            pass
        except Exception as e:
            print(f"Internal Catt Error: {e}")
    return mystdout.getvalue()

def ping_tv(ip):
    # Returns True if host (str) responds to a ping request
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', ip]
    return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0

def casting_loop(tv_ip, url, status_label):
    global is_running
    while is_running:
        if ping_tv(tv_ip):
            status_label.configure(text="Status: TV is Online. Checking cast...", text_color="orange")
            
            # Check if catt is already playing something
            try:
                status_output = run_catt_internal(['-d', tv_ip, 'status'])
                if "PLAYING" not in status_output:
                    status_label.configure(text="Status: Casting site...", text_color="blue")
                    run_catt_internal(['-d', tv_ip, 'cast_site', url])
                else:
                    status_label.configure(text="Status: Actively Casting", text_color="green")
            except Exception:
                # If status fails, assume it's not casting and try to cast
                status_label.configure(text="Status: Initiating cast...", text_color="blue")
                run_catt_internal(['-d', tv_ip, 'cast_site', url])
        else:
            status_label.configure(text="Status: TV is Offline. Waiting...", text_color="red")
        
        # Wait 60 seconds before checking again. 
        # Breaks early if user clicks "Stop"
        for _ in range(60):
            if not is_running:
                break
            time.sleep(1)

def discover_devices(ip_entry, status_label, scan_btn, device_menu):
    def run_scan():
        scan_btn.configure(state="disabled", text="Scanning...")
        status_label.configure(text="Status: Scanning for devices...", text_color="blue")
        
        try:
            # Using catt scan internally
            output = run_catt_internal(['scan'])
            
            matches = re.findall(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s+-\s+(.+)$', output, re.MULTILINE)
            
            if matches:
                # Create a map for selection
                options = [f"{m[1]} ({m[0]})" for m in matches]
                ip_map = {f"{m[1]} ({m[0]})": m[0] for m in matches}
                
                def on_select(selected_name):
                    selected_ip = ip_map.get(selected_name)
                    if selected_ip:
                        ip_entry.delete(0, "end")
                        ip_entry.insert(0, selected_ip)
                        status_label.configure(text=f"Status: Selected {selected_name}", text_color="green")

                # Update the dropdown menu
                device_menu.configure(values=options, command=on_select)
                device_menu.pack(pady=(0, 10)) # Show the menu
                
                # Default selection (prefer Sony)
                default_choice = options[0]
                for opt in options:
                    if "Sony" in opt or "BRAVIA" in opt:
                        default_choice = opt
                        break
                
                device_menu.set(default_choice)
                on_select(default_choice)
                status_label.configure(text=f"Status: Found {len(matches)} devices", text_color="green")
            else:
                status_label.configure(text="Status: No devices found. Enter IP manually.", text_color="orange")
                device_menu.pack_forget() # Hide if nothing found
        except Exception as e:
            status_label.configure(text=f"Status: Scan failed ({str(e)})", text_color="red")
        finally:
            scan_btn.configure(state="normal", text="Scan for TV")

    threading.Thread(target=run_scan, daemon=True).start()

# --- GUI Setup ---
def start_app():
    global is_running
    if is_running:
        return
        
    tv_ip = ip_entry.get().strip()
    url = url_entry.get().strip()
    
    if not tv_ip or not url:
        status_label.configure(text="Error: IP and URL required!", text_color="red")
        return
        
    save_config(tv_ip, url)
    is_running = True
    
    # Disable inputs while running
    ip_entry.configure(state="disabled")
    url_entry.configure(state="disabled")
    start_btn.configure(state="disabled")
    stop_btn.configure(state="normal")
    
    # Start background thread
    threading.Thread(target=casting_loop, args=(tv_ip, url, status_label), daemon=True).start()

def stop_app():
    global is_running
    is_running = False
    
    # Re-enable inputs
    ip_entry.configure(state="normal")
    url_entry.configure(state="normal")
    start_btn.configure(state="normal")
    stop_btn.configure(state="disabled")
    status_label.configure(text="Status: Stopped", text_color="gray")

# --- Initialize GUI Window ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("HDMI CABLES ARE SO 2022 (Chromecast)")
app.geometry("450x700") # Increased height for the meme!

# Load saved settings
config = load_config()

# UI Elements
title_label = ctk.CTkLabel(app, text="NO MORE CABLES!!", font=("Arial", 20, "bold"))
title_label.pack(pady=(20, 10))

# The Meme (for the lulz)
try:
    meme_img = ctk.CTkImage(light_image=Image.open(resource_path("no-moar-cables.png")),
                            dark_image=Image.open(resource_path("no-moar-cables.png")),
                            size=(350, 350))
    meme_label = ctk.CTkLabel(app, image=meme_img, text="")
    meme_label.pack(pady=10)
except Exception:
    pass # Skip if meme missing

ip_label = ctk.CTkLabel(app, text="Sony TV IP Address:")
ip_label.pack(anchor="w", padx=40)

# Container for IP entry and dropdown
ip_container = ctk.CTkFrame(app, fg_color="transparent")
ip_container.pack(fill="x", padx=40)

ip_frame = ctk.CTkFrame(ip_container, fg_color="transparent")
ip_frame.pack(fill="x", pady=5)

ip_entry = ctk.CTkEntry(ip_frame, width=260, placeholder_text="e.g. 192.168.1.50")
ip_entry.insert(0, config.get("tv_ip", ""))
ip_entry.pack(side="left", padx=(0, 10))

# Dropdown for found devices (hidden until scan finds something)
device_menu = ctk.CTkOptionMenu(ip_container, width=370)
device_menu.pack_forget() 

scan_btn = ctk.CTkButton(ip_frame, text="Scan for TV", width=120, height=35, font=("Arial", 13, "bold"), command=lambda: discover_devices(ip_entry, status_label, scan_btn, device_menu))
scan_btn.pack(side="left")

url_label = ctk.CTkLabel(app, text="Dashboard URL to Cast:")
url_label.pack(anchor="w", padx=40)
url_entry = ctk.CTkEntry(app, width=370, placeholder_text="https://...")
url_entry.insert(0, config.get("url", ""))
url_entry.pack(pady=5)

status_label = ctk.CTkLabel(app, text="Status: Stopped", text_color="gray", font=("Arial", 14))
status_label.pack(pady=20)

button_frame = ctk.CTkFrame(app, fg_color="transparent")
button_frame.pack(pady=10)

start_btn = ctk.CTkButton(button_frame, text="Start Automation", command=start_app, fg_color="green", hover_color="darkgreen", width=180, height=45, font=("Arial", 15, "bold"))
start_btn.pack(side="left", padx=10)

stop_btn = ctk.CTkButton(button_frame, text="Stop Automation", command=stop_app, fg_color="red", hover_color="darkred", state="disabled", width=180, height=45, font=("Arial", 15, "bold"))
stop_btn.pack(side="right", padx=10)

app.mainloop()