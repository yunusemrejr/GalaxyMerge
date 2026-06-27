import subprocess
import shutil
import webbrowser


def open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception:
        for browser in ("xdg-open", "google-chrome", "firefox", "chromium"):
            path = shutil.which(browser)
            if path:
                try:
                    subprocess.Popen([path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    continue
                break
