import base64
import binascii
import shutil
import subprocess
from pathlib import Path
from typing import Any


class ScreenshotManager:
    def __init__(self, cache_dir: Path):
        self.screenshot_dir = cache_dir / "browser" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def get_screenshot_path(self, session_id: str, name: str = "page") -> Path:
        path = self.screenshot_dir / f"{session_id}_{name}.png"
        return path

    def save_cdp_capture(self, session_id: str, image_data: str) -> dict[str, Any]:
        path = self.get_screenshot_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(base64.b64decode(image_data, validate=True))
        except (binascii.Error, OSError) as e:
            return {"success": False, "error": f"CDP screenshot decode failed: {e}"}
        return {"success": True, "screenshot_path": str(path), "source": "cdp"}

    def capture_desktop(self, session_id: str) -> dict[str, Any]:
        path = self.get_screenshot_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        import_path = shutil.which("import")
        if import_path:
            result = subprocess.run(
                [import_path, "-window", "root", str(path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return {"success": True, "screenshot_path": str(path), "source": "desktop"}
        gnome_path = shutil.which("gnome-screenshot")
        if gnome_path:
            result = subprocess.run(
                [gnome_path, "-f", str(path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return {"success": True, "screenshot_path": str(path), "source": "desktop"}
        return {"success": False, "error": "no screenshot tool available (try: import, gnome-screenshot, or CDP)"}
