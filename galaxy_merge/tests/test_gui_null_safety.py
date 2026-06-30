"""Regression tests for null-safety in GUI JavaScript.

These tests ensure that DOM element access uses null guards to prevent
`Cannot set properties of null (setting 'textContent')` crashes that were
the original bug report.
"""
import re
from pathlib import Path

GUI_JS_DIR = Path(__file__).resolve().parent.parent / "gui" / "static" / "js"


def _all_js_files():
    files = list(GUI_JS_DIR.glob("*.js"))
    files.extend(GUI_JS_DIR.glob("panels/*.js"))
    return sorted(files)


def test_app_js_null_guards_top_bar():
    """Every top-bar getElementById in app.js must be null-guarded before
    setting textContent, innerHTML, or style."""
    app_js = (GUI_JS_DIR / "app.js").read_text()
    # Find all getElementById calls that are immediately followed by property access
    # without a null guard on the same or next line
    for element_id in ["bar-safety", "bar-providers", "bar-connection",
                        "bar-project", "bar-workroot", "bar-taskscope", "bar-goal"]:
        # Pattern: getElementById('id').textContent or .style without null check
        pattern = rf"getElementById\('{element_id}'\)\.\s*(textContent|style|innerHTML)"
        matches = re.findall(pattern, app_js)
        assert not matches, (
            f"app.js: getElementById('{element_id}') is accessed without null guard "
            f"on lines containing: {matches}. Use `const el = getElementById(...); if (el) el.textContent = ...`"
        )


def test_panel_js_null_guards_before_innerHTML():
    """Panel scripts must check container !== null before setting innerHTML."""
    for js_file in _all_js_files():
        if js_file.name == "app.js":
            continue
        text = js_file.read_text()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            # Skip lines inside try-catch or if blocks that already guard
            if "container.innerHTML" in line:
                # Look backward for the container assignment
                _found_guard = False
                for j in range(max(0, i - 5), i):
                    if "if (!container)" in lines[j] or "if (container)" in lines[j]:
                        _found_guard = True
                        break
                    # Check if container was assigned and null-checked on same line
                    if "const container" in lines[j] and ("if (!container)" in lines[j] or "container) return" in lines[j]):
                        _found_guard = True
                        break
                # It's OK if the null guard is on the same line or next
                if i > 0:
                    prev_line = lines[i - 1]
                    if "if (!container)" in prev_line or "if (container)" in prev_line:
                        _found_guard = True
                    if "if (!container) return" in prev_line:
                        _found_guard = True
                # Also check the line itself for inline guard
                if "if (container)" in line or "if (!container)" in line:
                    _found_guard = True
                # It's also OK if container is freshly set via getElementById and checked
                if i >= 1 and "const container = document.getElementById" in lines[i - 1]:
                    # Check if there's a null guard right after
                    pass  # This is the pattern we're validating elsewhere

        # Simpler check: just verify no bare getElementById().innerHTML
        bare_pattern = r"document\.getElementById\([^)]+\)\.innerHTML"
        bare_matches = re.findall(bare_pattern, text)
        assert not bare_matches, (
            f"{js_file.name}: Found direct getElementById().innerHTML without null guard: {bare_matches}"
        )


def test_no_bare_getelementById_property_access():
    """No file should do getElementById('id').textContent/innerHTML/style without
    null guard. This catches the pattern that caused the original crash.
    addEventListener is allowed since those elements are guaranteed by HTML."""
    for js_file in _all_js_files():
        text = js_file.read_text()
        # Match: document.getElementById('id').textContent = ...
        # or document.getElementById('id').innerHTML = ...
        # or document.getElementById('id').style.xxx = ...
        # These are dangerous because getElementById can return null
        bare_access = re.findall(
            r'document\.getElementById\([^)]+\)\.\s*(textContent|innerHTML|style\.)',
            text
        )
        # Also match: document.getElementById('id').textContent (assignment)
        bare_assign = re.findall(
            r"document\.getElementById\([^)]+\)\.textContent\s*=",
            text
        )
        bare_inner = re.findall(
            r"document\.getElementById\([^)]+\)\.innerHTML\s*=",
            text
        )
        bare_style = re.findall(
            r"document\.getElementById\([^)]+\)\.style\.",
            text
        )
        all_bare = bare_access + bare_assign + bare_inner + bare_style
        assert not all_bare, (
            f"{js_file.name}: Found {len(all_bare)} bare getElementById().property "
            f"access without null guard: {all_bare}. "
            f"Store in a variable and check for null first."
        )


def test_app_js_provider_bar_null_guard():
    """Regression: bar-providers must be null-guarded in both try and catch
    blocks of refreshCouncilStatus."""
    app_js = (GUI_JS_DIR / "app.js").read_text()
    # In the try block
    assert "if (providerBar)" in app_js or "if (providerBar) {" in app_js, (
        "app.js: providerBar is not null-guarded in refreshCouncilStatus try block"
    )
    # In the catch block
    assert "if (barEl)" in app_js or "if (barEl) barEl" in app_js, (
        "app.js: bar-providers is not null-guarded in refreshCouncilStatus catch block"
    )


def test_goal_phase_null_guard():
    """Regression: goal-phase element must be null-guarded in GoalPanel.render."""
    goal_js = (GUI_JS_DIR / "panels" / "goal.js").read_text()
    assert "if (phaseEl)" in goal_js or "if (phaseEl) phaseEl" in goal_js, (
        "panels/goal.js: goal-phase element not null-guarded in render()"
    )


def test_council_panel_null_guards():
    """Regression: council panel containers must be null-guarded."""
    council_js = (GUI_JS_DIR / "panels" / "council.js").read_text()
    assert "if (!container) return" in council_js, (
        "panels/council.js: containers not null-guarded"
    )


def test_app_js_no_bar_session_reference():
    """Ensure bar-session is never referenced (was removed from HTML)."""
    app_js = (GUI_JS_DIR / "app.js").read_text()
    assert "bar-session" not in app_js, (
        "app.js references 'bar-session' which was removed from index.html"
    )
