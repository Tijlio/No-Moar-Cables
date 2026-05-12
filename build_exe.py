import os
import subprocess
import sys

# Get the venv paths
venv_bin = os.path.join(os.getcwd(), "venv", "Scripts")
venv_lib = os.path.join(os.getcwd(), "venv", "Lib", "site-packages")
ctk_path = os.path.join(venv_lib, "customtkinter")
pyinstaller_exe = os.path.join(venv_bin, "pyinstaller.exe")

if not os.path.exists(pyinstaller_exe):
    print(f"Error: Could not find pyinstaller at {pyinstaller_exe}")
    sys.exit(1)

if not os.path.exists(ctk_path):
    print(f"Error: Could not find customtkinter at {ctk_path}")
    sys.exit(1)

# Construct the PyInstaller command
cmd = [
    pyinstaller_exe,
    "--noconsole",
    "--onefile",
    "--name", "NoMoreCables",
    "--add-data", f"{ctk_path};customtkinter/",
]

# Include meme if it exists
if os.path.exists("no-moar-cables.png"):
    cmd.extend(["--add-data", "no-moar-cables.png;."])

cmd.extend([
    "--collect-all", "catt",
    "--collect-all", "pychromecast",
    "--collect-all", "zeroconf",
    "app.py"
])

print(f"Running: {' '.join(cmd)}")
subprocess.run(cmd, check=True)

print("\nBuild complete! Check the 'dist' folder for NoMoreCables.exe")
