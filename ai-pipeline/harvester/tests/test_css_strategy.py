"""
Unit tests for strategies/css_strategy.py.

Tests CssTemplateRegistry with synthetic templates (no network, no Crawl4AI).
"""

import json
import tempfile
from pathlib import Path

import pytest

from strategies.css_strategy import CssTemplateRegistry


def _create_template(tmpdir: Path, name: str, fields: list[dict] | None = None) -> Path:
    """Create a minimal CSS template JSON file."""
    template = {
        "name": name,
        "baseSelector": "div.main",
        "fields": fields or [
            {"name": "title", "selector": "h1", "type": "text"},
            {"name": "phone", "selector": "a[href^='tel:']", "type": "text"},
        ],
    }
    path = tmpdir / f"{name}.json"
    path.write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
    return path


class TestCssTemplateRegistry:
    def test_empty_dir(self, tmp_path):
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert reg.available_templates == []

    def test_nonexistent_dir(self, tmp_path):
        reg = CssTemplateRegistry(templates_dir=tmp_path / "no_such_dir")
        assert reg.available_templates == []

    def test_load_template(self, tmp_path):
        _create_template(tmp_path, "kcson_socinfo")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert "kcson_socinfo" in reg.available_templates

    def test_has_template(self, tmp_path):
        _create_template(tmp_path, "test_tpl")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert reg.has_template("test_tpl")
        assert not reg.has_template("nonexistent")

    def test_get_template(self, tmp_path):
        _create_template(tmp_path, "mytemplate")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        tpl = reg.get_template("mytemplate")
        assert tpl is not None
        assert tpl["name"] == "mytemplate"
        assert "baseSelector" in tpl
        assert len(tpl["fields"]) == 2

    def test_get_nonexistent(self, tmp_path):
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert reg.get_template("nope") is None

    def test_multiple_templates(self, tmp_path):
        _create_template(tmp_path, "tpl_a")
        _create_template(tmp_path, "tpl_b")
        _create_template(tmp_path, "tpl_c")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert len(reg.available_templates) == 3

    def test_invalid_json_skipped(self, tmp_path):
        (tmp_path / "bad.json").write_text("not a json {{{", encoding="utf-8")
        _create_template(tmp_path, "good")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        assert "good" in reg.available_templates
        assert "bad" not in reg.available_templates

    def test_build_extraction_config(self, tmp_path):
        _create_template(tmp_path, "kcson")
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        config = reg.build_extraction_config("kcson")
        assert config is not None

    def test_build_extraction_config_nonexistent(self, tmp_path):
        reg = CssTemplateRegistry(templates_dir=tmp_path)
        config = reg.build_extraction_config("nope")
        assert config is None
