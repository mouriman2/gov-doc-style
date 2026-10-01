"""ひな形 4 枚が、そのまま書き出して検査を通ること（Chrome か Edge が要る）。"""

from pathlib import Path

import pytest

from gov_doc_style.render import find_browser, render
from gov_doc_style.specs import Level

TEMPLATES = sorted((Path(__file__).parent.parent / "templates").glob("*.html"))


def browser_available() -> bool:
    try:
        find_browser()
    except SystemExit:
        return False
    return True


@pytest.mark.skipif(not browser_available(), reason="Chrome も Edge も無い")
@pytest.mark.parametrize("template", TEMPLATES, ids=[t.stem for t in TEMPLATES])
def test_template_passes_checks(template: Path, tmp_path: Path) -> None:
    report, files = render(template, tmp_path, doc_type=None, scale=1)
    problems = [f"{c.name}: {c.value}" for c in report.checks if c.level is not Level.OK]
    assert report.worst is Level.OK, problems
    assert all(f.exists() for f in files)


def test_all_four_templates_exist() -> None:
    assert [t.stem for t in TEMPLATES] == ["deck", "ponchi-gaiyo", "ponchi-jigyo", "tsuchi"]
