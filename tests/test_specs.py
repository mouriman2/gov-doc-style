from gov_doc_style.measure import DocMetrics, PageMetrics
from gov_doc_style.specs import SPECS, Gap, Inspection, Level, Overflow, Range, SpaceBreak, judge


def page(
    number: int = 1,
    chars: int = 1000,
    size: float = 13,
    floor: float = 8,
    w: float = 275,
    h: float = 190,
    font: str = "MeiryoUI",
) -> PageMetrics:
    return PageMetrics(number, w, h, chars, size, floor, [(font, 80)])


def doc(*pages: PageMetrics, tou: float = 10, wareki: int = 3, seireki: int = 0) -> DocMetrics:
    return DocMetrics(list(pages), sum(p.chars for p in pages), tou, wareki, seireki)


def levels(report_checks: list, name: str) -> list[Level]:
    return [c.level for c in report_checks if c.name.startswith(name)]


def test_clean_document_is_ok() -> None:
    report = judge(doc(page()), SPECS["ponchi-jigyo"], expected_pages=1)
    assert report.worst is Level.OK


def test_overflow_is_ng() -> None:
    seen = Inspection(overflows=[Overflow(1, "成果目標・事業期間", 0, 40)])
    report = judge(doc(page()), SPECS["ponchi-jigyo"], 1, seen)
    assert levels(report.checks, "はみ出し") == [Level.NG]
    assert "縦 10.6mm" in report.checks[0].value  # 40 CSS px = 10.6mm
    assert report.worst is Level.NG


def test_spilled_page_is_ng() -> None:
    report = judge(doc(page(1), page(2)), SPECS["ponchi-jigyo"], expected_pages=1)
    assert levels(report.checks, "枚数") == [Level.NG]


def test_wrong_paper_is_ng() -> None:
    report = judge(doc(page(w=297, h=210)), SPECS["ponchi-jigyo"], 1)
    assert levels(report.checks, "用紙") == [Level.NG]


def test_tiny_text_is_ng_but_density_is_only_a_warning() -> None:
    report = judge(doc(page(chars=3000, floor=5)), SPECS["ponchi-jigyo"], 1)
    assert levels(report.checks, "小さすぎる字") == [Level.NG]
    assert levels(report.checks, "字数") == [Level.WARN]


def test_cover_and_toc_skip_density_checks() -> None:
    pages = (page(1, chars=60), page(2, chars=80), page(3, chars=700))
    report = judge(doc(*pages), SPECS["deck"], 3, Inspection(roles=["cover", "toc", ""]))
    assert [c.name for c in report.checks if c.name.startswith("字数")] == ["字数（3 枚目）"]


def test_style_deviations_are_warnings() -> None:
    report = judge(doc(page(font="ArialMT"), tou=25, seireki=2), SPECS["ponchi-jigyo"], 1)
    assert levels(report.checks, "書体") == [Level.WARN]
    assert levels(report.checks, "「等」") == [Level.WARN]
    assert levels(report.checks, "年の書き方") == [Level.WARN]
    assert report.worst is Level.WARN


def test_range_describe() -> None:
    assert Range(700, 1600).describe(" 字") == "700〜1600 字"
    assert Range(None, 15).describe(" 回") == "15 回 以下"


def test_report_columns_align_with_wide_characters() -> None:
    from gov_doc_style.render import display_width, pad

    assert display_width("字数") == 4
    assert display_width(pad("OK", 4)) == display_width(pad("注意", 4)) == 4


def test_wide_gap_under_a_section_is_a_warning() -> None:
    seen = Inspection(gaps=[Gap(1, "事業目的・概要", 20.0), Gap(1, "事業スキーム", 3.0)])
    report = judge(doc(page()), SPECS["ponchi-jigyo"], 1, seen)
    gaps = [c for c in report.checks if c.name.startswith("下の空き")]
    assert [(c.level, c.value) for c in gaps] == [(Level.WARN, "事業目的・概要: 20mm")]


def test_small_gaps_are_ok() -> None:
    report = judge(doc(page()), SPECS["ponchi-jigyo"], 1, Inspection(gaps=[Gap(1, "a", 5.0)]))
    assert levels(report.checks, "下の空き") == [Level.OK]


def test_line_break_spaces_are_listed() -> None:
    seen = Inspection(breaks=[SpaceBreak(1, f"例{i}␣続き") for i in range(5)])
    report = judge(doc(page()), SPECS["ponchi-jigyo"], 1, seen)
    check = next(c for c in report.checks if c.name == "改行の空白")
    assert check.level is Level.WARN
    assert check.value.endswith("ほか 2 か所")
