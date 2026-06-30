"""Unit tests for workspace extras — TaskScope, FileSummarizer."""

import pytest
from pathlib import Path

from galaxy_merge.workspace.scope import TaskScope
from galaxy_merge.workspace.summaries import FileSummarizer

pytestmark = [pytest.mark.unit]


class TestTaskScope:
    def test_empty_scope_contains_all_under_workroot(self, tmp_path):
        scope = TaskScope(tmp_path)
        assert scope.contains(tmp_path / "any" / "file.py") is True

    def test_empty_scope_rejects_outside_workroot(self, tmp_path):
        scope = TaskScope(tmp_path)
        assert scope.contains(Path("/tmp/outside.py")) is False

    def test_set_from_plan_limits_scope(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")
        (tmp_path / "src" / "other.py").write_text("y")
        scope = TaskScope(tmp_path)
        scope.set_from_plan(["src/main.py"])
        assert scope.contains(tmp_path / "src" / "main.py") is True

    def test_set_from_plan_rejects_unrelated_files(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("y")
        scope = TaskScope(tmp_path)
        scope.set_from_plan(["src/main.py"])
        # test_main.py is not in scope (different directory)
        assert scope.contains(tmp_path / "tests" / "test_main.py") is False

    def test_set_from_plan_includes_parent_directory(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")
        (tmp_path / "src" / "utils.py").write_text("y")
        scope = TaskScope(tmp_path)
        scope.set_from_plan(["src/main.py"])
        # utils.py is in the same directory as main.py, so it's in scope
        assert scope.contains(tmp_path / "src" / "utils.py") is True

    def test_to_dict_returns_expected_keys(self, tmp_path):
        scope = TaskScope(tmp_path)
        d = scope.to_dict()
        assert "scope_paths" in d
        assert "scope_files" in d

    def test_to_dict_after_set_from_plan(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")
        scope = TaskScope(tmp_path)
        scope.set_from_plan(["src/main.py"])
        d = scope.to_dict()
        assert len(d["scope_files"]) == 1
        assert len(d["scope_paths"]) == 1


class TestFileSummarizer:
    def test_summarize_python_file(self, tmp_path):
        (tmp_path / "main.py").write_text("import os\nfrom sys import argv\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "main.py")
        assert summary["type"] == "python"
        assert summary["extension"] == ".py"
        assert summary["imports"] == 2

    def test_summarize_javascript_file(self, tmp_path):
        (tmp_path / "app.js").write_text("import y from 'z'\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "app.js")
        assert summary["type"] == "javascript"
        assert summary["imports"] == 1

    def test_summarize_typescript_file(self, tmp_path):
        (tmp_path / "app.ts").write_text("import { x } from 'y'\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "app.ts")
        assert summary["type"] == "typescript"
        assert summary["imports"] == 1

    def test_summarize_markdown_file(self, tmp_path):
        (tmp_path / "README.md").write_text("# Hello\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "README.md")
        assert summary["type"] == "markdown"

    def test_summarize_json_file(self, tmp_path):
        (tmp_path / "config.json").write_text('{"key": "value"}\n')
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "config.json")
        assert summary["type"] == "json"

    def test_summarize_yaml_file(self, tmp_path):
        (tmp_path / "config.yaml").write_text("key: value\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "config.yaml")
        assert summary["type"] == "yaml"

    def test_summarize_html_file(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "index.html")
        assert summary["type"] == "html"

    def test_summarize_css_file(self, tmp_path):
        (tmp_path / "style.css").write_text("body { color: red; }\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "style.css")
        assert summary["type"] == "css"

    def test_summarize_unknown_extension(self, tmp_path):
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "data.bin")
        assert summary["type"] == "other"

    def test_summarize_reports_size(self, tmp_path):
        content = "a" * 1000
        (tmp_path / "big.py").write_text(content)
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "big.py")
        assert summary["size"] == 1000

    def test_summarize_relative_path(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("import os\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "src" / "main.py")
        assert summary["path"] == "src/main.py"

    def test_summarize_tsx_file(self, tmp_path):
        (tmp_path / "App.tsx").write_text("import React from 'react'\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "App.tsx")
        assert summary["type"] == "typescript"

    def test_summarize_jsx_file(self, tmp_path):
        (tmp_path / "App.jsx").write_text("import React from 'react'\n")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "App.jsx")
        assert summary["type"] == "javascript"

    def test_count_imports_empty_file(self, tmp_path):
        (tmp_path / "empty.py").write_text("")
        summarizer = FileSummarizer(tmp_path)
        summary = summarizer.summarize(tmp_path / "empty.py")
        assert summary["imports"] == 0
