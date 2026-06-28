import subprocess
import shutil
from pathlib import Path

GUI_JS_DIR = Path(__file__).resolve().parent.parent / "gui" / "static" / "js"
GUI_STATIC_DIR = Path(__file__).resolve().parent.parent / "gui" / "static"
INDEX_HTML = GUI_STATIC_DIR / "index.html"
APP_JS = GUI_JS_DIR / "app.js"


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


def _html_static_ids():
    import re

    text = INDEX_HTML.read_text()
    return set(re.findall(r'id="([^"]+)"', text))


def test_app_js_does_not_reference_removed_bar_session():
    """Regression: bar-session was removed from index.html; referencing it
    caused `Cannot set properties of null (setting 'textContent')` in the
    browser console at init()."""
    text = APP_JS.read_text()
    assert "bar-session" not in text, (
        "app.js references 'bar-session' which is not present in index.html"
    )


def test_top_bar_static_ids_are_wired_in_app_js():
    """Every static top-bar element id in index.html must be referenced by
    app.js so the top bar is fully populated at runtime."""
    static_ids = _html_static_ids()
    top_bar_ids = {
        "bar-project",
        "bar-workroot",
        "bar-taskscope",
        "bar-goal",
        "bar-connection",
        "bar-safety",
        "bar-providers",
        "session-picker",
    }
    assert top_bar_ids <= static_ids, (
        f"index.html missing top-bar ids: {top_bar_ids - static_ids}"
    )
    text = APP_JS.read_text()
    missing = {i for i in top_bar_ids if f"getElementById('{i}')" not in text}
    assert not missing, f"app.js does not wire top-bar ids: {sorted(missing)}"


def test_app_js_getelementById_targets_exist_or_are_dynamic():
    """Every getElementById target in app.js must either be a static id in
    index.html or be created dynamically by a panel script. This catches
    null-reference bugs like the original bar-session crash."""
    import re

    static_ids = _html_static_ids()
    app_text = APP_JS.read_text()
    referenced = set(re.findall(r"getElementById\('([^']+)'\)", app_text))
    # ids dynamically created by panel scripts (not in index.html)
    dynamic_ids = set()
    for js_file in _all_js_files():
        if js_file == APP_JS:
            continue
        panel_text = js_file.read_text()
        dynamic_ids |= set(re.findall(r'id="([^"]+)"', panel_text))
    missing = referenced - static_ids - dynamic_ids
    assert not missing, (
        f"app.js references getElementById ids not in index.html or any panel: "
        f"{sorted(missing)}"
    )
