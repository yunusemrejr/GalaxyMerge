import subprocess
from pathlib import Path


def generate_diff(workroot: Path, file_path: str, old_content: str, new_content: str) -> str:
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".old", delete=False) as f:
        f.write(old_content)
        old_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".new", delete=False) as f:
        f.write(new_content)
        new_path = f.name

    try:
        result = subprocess.run(
            ["diff", "-u", old_path, new_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout
    except Exception:
        return ""
    finally:
        Path(old_path).unlink(missing_ok=True)
        Path(new_path).unlink(missing_ok=True)
