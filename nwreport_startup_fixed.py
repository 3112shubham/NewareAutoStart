"""
NWReport_DBWB startup automation (corrected).

1. Edit APP_EXE below to the full path to NWReport_DBWB.exe.
2. Install dependencies:
       py -m pip install pyautogui pygetwindow pillow
3. Test while logged into Windows:
       py nwreport_startup.py

This version checks for the actual executable process, not just a matching
window title. It does not retry blindly because the visible log error may
be a persistent configuration problem.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import time
from pathlib import Path

import pyautogui
import pygetwindow as gw

# The folder shown in your screenshot is on D: under VoltekAI\Applications.
# Confirm/edit this full path if your folder is elsewhere.
APP_EXE = (
    r"D:\VoltekAI\Applications\NWReport_DBWB_V1.0.0_20250303_64"
    r"\NWReport_DBWB_V1.0.0_20250303_64\NWReport_DBWB.exe"
)

APP_PROCESS_NAME = "NWReport_DBWB.exe"
WINDOW_TITLE_PART = "NWReport_DBWB"
INITIAL_WAIT_SECONDS = 30
WINDOW_WAIT_SECONDS = 30
RETRY_WAIT_SECONDS = 10
MAX_START_ATTEMPTS = 3
TARGET_DESKTOP_NUMBER = 2
DESKTOP_SWITCH_WAIT_SECONDS = 10

LOG_FILE = Path(__file__).with_name("nwreport_startup.log")
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.4

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    # Quote the script path for Windows ShellExecute.
    params = f'"{Path(__file__).resolve()}"'
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        str(Path(sys.executable).resolve()),
        params,
        str(Path(__file__).resolve().parent),
        1,
    )
    if result <= 32:
        raise RuntimeError(f"Administrator elevation failed (code {result}).")


def ensure_target_desktop() -> None:
    """Create Desktop 2 when needed, switch to it, and allow it to settle."""
    try:
        # Import only after elevation: pyvda connects to Windows' virtual
        # desktop service during import.
        from pyvda import VirtualDesktop, get_virtual_desktops

        desktops = get_virtual_desktops()
        while len(desktops) < TARGET_DESKTOP_NUMBER:
            VirtualDesktop.create()
            desktops = get_virtual_desktops()
            logging.info(
                "Created virtual desktop %d.",
                len(desktops),
            )

        target = VirtualDesktop(TARGET_DESKTOP_NUMBER)
        target.go()
        logging.info("Switched to virtual desktop %d.", TARGET_DESKTOP_NUMBER)
        time.sleep(DESKTOP_SWITCH_WAIT_SECONDS)
    except Exception as exc:
        logging.exception("Virtual desktop setup failed.")
        raise RuntimeError(
            f"Could not create or switch to Desktop {TARGET_DESKTOP_NUMBER}."
        ) from exc


def process_is_running() -> bool:
    """Check the executable process name, not an unrelated window title."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {APP_PROCESS_NAME}"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return APP_PROCESS_NAME.lower() in result.stdout.lower()
    except Exception:
        logging.exception("Could not check process list.")
        return False


def find_app_window():
    # Require a titled application window; File Explorer's folder title alone
    # should not be enough to count as the application.
    matches = []
    for window in gw.getAllWindows():
        title = (window.title or "").strip()
        if WINDOW_TITLE_PART.lower() in title.lower():
            if "File Explorer" not in title and "Explorer" not in title:
                matches.append(window)
    return matches[0] if matches else None


def launch_app() -> None:
    exe = Path(APP_EXE)
    if not exe.is_file():
        raise FileNotFoundError(
            f"Executable not found:\n{APP_EXE}\n\n"
            "Open the folder containing NWReport_DBWB.exe, click the address "
            "bar, copy the full folder path, and update APP_EXE."
        )

    logging.info("Launching executable: %s", exe)
    # Use the application's own directory as its working directory because
    # bundled apps often need their neighboring DLL/config files.
    subprocess.Popen([str(exe)], cwd=str(exe.parent))
    logging.info("Launch command submitted.")


def wait_for_app_window(timeout_seconds: int):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        window = find_app_window()
        if window is not None:
            logging.info("Found application window: %s", window.title)
            return window
        time.sleep(2)
    return None


def click_start(window) -> None:
    if window.isMinimized:
        window.restore()
        time.sleep(1)

    window.activate()
    time.sleep(1)

    # In this application's bottom action bar, Start is one third of the
    # window width from the left; the window centre is the gap between Start
    # and Stop.  Keep the target relative to the window in case it moves.
    x = window.left + round(window.width / 3)
    y = window.top + window.height - 31

    if window.width < 350 or window.height < 300:
        raise RuntimeError(
            f"Unexpected app window size: {window.width}x{window.height}"
        )

    logging.info("Clicking Start in '%s' at (%d, %d).", window.title, x, y)
    pyautogui.click(x, y)


def main() -> None:
    if not is_admin():
        logging.info("Requesting administrator permission.")
        relaunch_as_admin()
        return

    logging.info("Automation started.")
    ensure_target_desktop()
    exe = Path(APP_EXE)
    if not exe.is_file():
        raise FileNotFoundError(
            f"APP_EXE path is incorrect:\n{APP_EXE}\n"
            "Edit APP_EXE at the top of the script."
        )

    if not process_is_running():
        logging.info("Application process not running; launching it.")
        launch_app()
    else:
        logging.info("Application process is already running; not duplicating it.")

    logging.info("Waiting %d seconds for initialization.", INITIAL_WAIT_SECONDS)
    time.sleep(INITIAL_WAIT_SECONDS)

    window = find_app_window()
    if window is None:
        logging.info(
            "Window not yet found; waiting up to %d more seconds.", WINDOW_WAIT_SECONDS
        )
        window = wait_for_app_window(WINDOW_WAIT_SECONDS)

    if window is None:
        raise RuntimeError(
            "NWReport_DBWB.exe was launched or detected, but its application "
            "window was not found. Check whether a startup dialog is hidden "
            "behind another window and review the log."
        )

    for attempt in range(1, MAX_START_ATTEMPTS + 1):
        # Re-find the window on each attempt so we don't click stale coordinates.
        window = find_app_window()
        if window is None:
            logging.warning("App window disappeared before attempt %d.", attempt)
            break

        logging.info("Start attempt %d/%d.", attempt, MAX_START_ATTEMPTS)
        click_start(window)
        time.sleep(RETRY_WAIT_SECONDS)

        # Save a screenshot after each attempt for diagnostics before the
        # next configured retry.
        screenshot_path = Path(__file__).with_name(
            f"nwreport_after_attempt_{attempt}.png"
        )
        pyautogui.screenshot().save(screenshot_path)
        logging.info("Saved post-click screenshot: %s", screenshot_path)

        if attempt < MAX_START_ATTEMPTS:
            logging.info(
                "Attempt %d completed; retrying after the configured wait if "
                "the application is still open.",
                attempt,
            )
        else:
            logging.info(
                "Completed all %d configured Start attempts.", MAX_START_ATTEMPTS
            )

    logging.info("Automation finished.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Automation failed.")
        raise
