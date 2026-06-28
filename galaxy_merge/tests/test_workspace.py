import pytest

from galaxy_merge.workspace.root import detect_language
from galaxy_merge.workspace.tree import FileTree
from galaxy_merge.workspace.symbols import extract_symbols
from galaxy_merge.workspace.indexer import WorkspaceIndexer

pytestmark = [pytest.mark.unit]


class TestDetectLanguage:
    def test_detect_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("")
        langs = detect_language(tmp_path)
        assert "python" in langs

    def test_detect_javascript(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        langs = detect_language(tmp_path)
        assert "javascript" in langs


class TestFileTree:
    def test_build_tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Test")
        tree = FileTree(tmp_path)
        result = tree.build()
        assert result["type"] == "directory"
        assert len(result["children"]) > 0


class TestExtractSymbols:
    def test_extract_python_symbols(self, tmp_path):
        pyfile = tmp_path / "test.py"
        pyfile.write_text("""
def hello():
    pass

class MyClass:
    def method(self):
        pass
""")
        symbols = extract_symbols(pyfile)
        names = [s["name"] for s in symbols]
        assert "hello" in names
        assert "MyClass" in names


class TestWorkspaceIndexer:
    def test_index_refresh(self, tmp_path):
        (tmp_path / ".gm").mkdir(parents=True)
        (tmp_path / "test.py").write_text("x = 1")
        indexer = WorkspaceIndexer(tmp_path)
        result = indexer.refresh()
        assert result["total_files"] >= 1
