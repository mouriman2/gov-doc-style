from collections import Counter

import pytest

from gov_doc_style.measure import PageMetrics, a4_scale, count_tou, font_family, summarize_text, weighted_percentile


def test_a4_scale_landscape_powerpoint_a4() -> None:
    # PowerPoint の「A4」(275×190mm) は横幅で決まり、A4 に刷ると 1.08 倍になる
    assert a4_scale(275, 190) == pytest.approx(297 / 275)


def test_a4_scale_portrait_a4_is_one() -> None:
    assert a4_scale(210, 297) == pytest.approx(1.0)


def test_count_tou_skips_compounds() -> None:
    assert count_tou("対象者、補助率等。高等学校、男女均等、同等の扱い等") == 2


def test_count_tou_skips_quoted_mentions() -> None:
    assert count_tou("「等」の頻度を測る。撮影、テキスト化等") == 1


def test_weighted_percentile_uses_char_weights() -> None:
    sizes: Counter[float] = Counter({7.0: 10, 12.0: 90})
    assert weighted_percentile(sizes, 0.05) == 7.0
    assert weighted_percentile(sizes, 0.5) == 12.0
    assert weighted_percentile(Counter(), 0.5) == 0.0


def test_font_family_strips_subset_prefix() -> None:
    assert font_family("ABCDEF+MeiryoUI") == "MeiryoUI"
    assert font_family("MS-Mincho") == "MS-Mincho"


def test_summarize_text_counts_years() -> None:
    page = PageMetrics(1, 275, 190, 100, 12, 8, [("MeiryoUI", 100)])
    doc = summarize_text([page], "令和８年度から令和 12 年度まで。2026年に開始。")
    assert (doc.wareki, doc.seireki) == (2, 1)
