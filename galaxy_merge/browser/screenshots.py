from pathlib import Path


class ScreenshotManager:
    def __init__(self, cache_dir: Path):
        self.screenshot_dir = cache_dir / "browser" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def get_screenshot_path(self, session_id: str, name: str = "page") -> Path:
        path = self.screenshot_dir / f"{session_id}_{name}.png"
        return path
