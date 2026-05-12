import os
import subprocess
import sys


APP_NAME = "NoMoreCables"
ENTRYPOINT = "app.py"
MEME_FILE = "no-moar-cables.png"


def fail(message):
    print(f"Error: {message}")
    sys.exit(1)


def path_exists_or_fail(path, description):
    if not os.path.exists(path):
        fail(f"Could not find {description} at: {path}")


def add_data_arg(source, destination):
    """
    PyInstaller uses ; on Windows and : on Linux/macOS for --add-data.
    Because apparently one separator would have been too merciful.
    """
    separator = ";" if os.name == "nt" else ":"
    return f"{source}{separator}{destination}"


def main():
    project_dir = os.getcwd()

    if not os.path.exists(ENTRYPOINT):
        fail(f"Could not find {ENTRYPOINT} in {project_dir}")

    venv_dir = os.path.join(project_dir, "venv")

    if os.name == "nt":
        venv_bin = os.path.join(venv_dir, "Scripts")
        pyinstaller_exe = os.path.join(venv_bin, "pyinstaller.exe")
    else:
        venv_bin = os.path.join(venv_dir, "bin")
        pyinstaller_exe = os.path.join(venv_bin, "pyinstaller")

    path_exists_or_fail(pyinstaller_exe, "PyInstaller executable")

    cmd = [
        pyinstaller_exe,
        "--noconsole",
        "--onefile",
        "--clean",
        "--name",
        APP_NAME,
        "--collect-all",
        "customtkinter",
        "--collect-all",
        "catt",
        "--collect-all",
        "pychromecast",
        "--collect-all",
        "zeroconf",
        "--collect-all",
        "PIL",
        "--collect-all",
        "playwright",
        "--hidden-import",
        "PIL._tkinter_finder",
    ]

    if os.path.exists(MEME_FILE):
        cmd.extend(["--add-data", add_data_arg(MEME_FILE, ".")])
    else:
        print(f"Warning: {MEME_FILE} not found. The app will build without the meme.")

    cmd.append(ENTRYPOINT)

    print("Running:")
    print(" ".join(f'"{part}"' if " " in part else part for part in cmd))

    subprocess.run(cmd, check=True)

    exe_name = f"{APP_NAME}.exe" if os.name == "nt" else APP_NAME
    print(f"\nBuild complete! Check the dist folder for {exe_name}")


if __name__ == "__main__":
    main()
