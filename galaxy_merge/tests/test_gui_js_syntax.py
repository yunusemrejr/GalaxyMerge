import subprocess
import shutil
from pathlib import Path

GUI_JS_DIR = Path(__file__).resolve().parent.parent / "gui" / "static" / "js"


def _all_js_files():
    files = list(GUI_JS_DIR.glob("*.js"))
    files.extend(GUI_JS_DIR.glob("panels/*.js"))
    return sorted(files)


def test_node_available():
    assert shutil.which("node"), "node is required to check JS syntax"


def test_all_js_files_have_valid_syntax():
    errors = []
    for js_file in _all_js_files():
        rel = js_file.relative_to(GUI_JS_DIR.parent.parent.parent)
        result = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            errors.append(f"{rel}: {result.stderr.strip()}")
    assert not errors, "JS syntax errors:\n" + "\n".join(errors)


def test_no_duplicate_async_keywords():
    errors = []
    for js_file in _all_js_files():
        text = js_file.read_text()
        for i, line in enumerate(text.splitlines(), 1):
            if "async  async" in line or "async\tasync" in line:
                rel = js_file.relative_to(GUI_JS_DIR.parent.parent.parent)
                errors.append(f"{rel}:{i}: duplicate async keyword")
    assert not errors, "Found duplicate async keywords:\n" + "\n".join(errors)
