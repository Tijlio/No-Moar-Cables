# NO MORE CABLES!! 🚀 (Auto-Caster v2)

A premium, automated casting utility for Sony TVs and Chromecasts. Designed to keep a specific URL (like a dashboard or kiosk site) alive on your TV without the hassle of HDMI cables or manual intervention.

## ✨ Features

- **Device Discovery**: Instantly scan your network for available Chromecasts and Sony BRAVIA TVs
- **Persistent Casting**: Automatically checks if the TV is online and ensures the site is casting. If the connection drops or the TV restarts, it pulls the site back up.
- **Smart Sony Integration**: Specifically optimized to recognize and prioritize Sony BRAVIA TVs.
- **Modern UI**: Built with `CustomTkinter` for a sleek, dark-mode-ready interface.
- **Persistent Config**: Remembers your last used IP and URL so you can get started with one click.

## 🛠️ Prerequisites

- **Python 3.10+**
- **catt (Cast All The Things)**: The engine behind the casting.
- **Windows / Linux / macOS** (Tested primarily on Windows).

## 🚀 Getting Started

1. **Download the Executable**: If you just want to run the app, go to the `dist` folder and run `NoMoreCables.exe`. No Python installation is required!
2. **Clone the repository** (for developers):

   ```bash
   git clone https://github.com/Waaslandia/waaslandia-cast-v2.git
   cd waaslandia-cast-v2
   ```

   ```bash
   git clone https://github.com/Waaslandia/waaslandia-cast-v2.git
   cd waaslandia-cast-v2
   ```

3. **Setup Virtual Environment**:

   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

4. **Install Dependencies**:

   ```bash
   pip install customtkinter catt pychromecast
   ```

5. **Run the App**:
   ```bash
   python app.py
   ```

## 📖 How to Use

1. **Scan**: Click the **"Scan for TV"** button. The app will search your network for available devices.
2. **Select**: If multiple devices are found, use the dropdown to select your target TV.
3. **URL**: Enter the URL you want to cast (e.g., your business dashboard).
4. **Go!**: Click **"Start Automation"**. The app will now ping the TV every 60 seconds and ensure your site stays visible.

## 🔧 Under the Hood

- **`app.py`**: The main application logic and GUI.
- **`config.json`**: Stores your settings locally.
- **`catt`**: Used for the heavy lifting of interacting with the Cast protocol.

## 📦 Creating the Executable

If you want to build the EXE yourself:

1. Run the build script:
   ```bash
   python build_exe.py
   ```
2. The standalone file will be generated in the `dist/` folder.

---

_HDMI CABLES ARE SO 2022. Welcome to the future._
