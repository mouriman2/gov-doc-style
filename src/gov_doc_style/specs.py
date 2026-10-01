"""資料の種類ごとの目安と、測った値との照合。

目安の範囲は、省庁の公開 PDF 10 本を測った値から取った（docs/measurements.md）。
文字サイズはすべて A4 に刷ったときの換算値。

NG は直さないと資料として崩れているもの（はみ出し・用紙・読めないほど小さい字）。
注意は型から外れているが、意図してそうしたなら残してよいもの（字数・「等」・西暦など）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from gov_doc_style.measure import DocMetrics

PAPER_TOLERANCE_MM = 1.5
FRONT_MATTER = frozenset({"cover", "toc", "divider"})  # 字数と文字サイズの目安を当てないページ（表紙・目次・中扉）


class Level(Enum):
    OK = "OK"
    WARN = "注意"
    NG = "NG"


@dataclass(frozen=True)
class Range:
    low: float | None = None
    high: float | None = None

    def contains(self, value: float) -> bool:
        return (self.low is None or value >= self.low) and (self.high is None or value <= self.high)

    def describe(self, unit: str = "") -> str:
        if self.low is not None and self.high is not None:
            return f"{self.low:g}〜{self.high:g}{unit}"
        if self.low is not None:
            return f"{self.low:g}{unit} 以上"
        if self.high is not None:
            return f"{self.high:g}{unit} 以下"
        return "指定なし"


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    paper_mm: tuple[float, float]
    chars: Range  # 文字のあるページ 1 枚あたり
    size_median: Range
    size_floor: float  # 字数の 5% 目の大きさがこれ未満なら NG
    tou_per_1000: Range
    fonts: tuple[str, ...]  # 主な書体の名前に含まれていてほしい文字列
    reference: str = ""


SPECS: dict[str, Spec] = {
    "ponchi-jigyo": Spec(
        key="ponchi-jigyo",
        label="ポンチ絵（予算の事業説明型）",
        paper_mm=(275, 190),
        chars=Range(700, 1600),
        size_median=Range(11, 16),
        size_floor=6.5,
        tou_per_1000=Range(4, 15),
        fonts=("Meiryo",),
        reference="経産省 PR 資料 789 字・15pt、財務省 862 字・13pt、厚労省 1,116 字・11.5pt",
    ),
    "ponchi-gaiyo": Spec(
        key="ponchi-gaiyo",
        label="ポンチ絵（概要一覧型）",
        paper_mm=(275, 190),
        chars=Range(1500, 2800),
        size_median=Range(7.5, 11.5),
        size_floor=5.5,
        tou_per_1000=Range(4, 15),
        fonts=("Meiryo",),
        reference="内閣府 骨太の方針の概要 2,719 字・9.0pt、デジタル庁 重点計画の概要 2,021 字・7.5pt",
    ),
    "deck": Spec(
        key="deck",
        label="複数枚の説明資料",
        paper_mm=(275, 190),
        chars=Range(400, 1600),
        size_median=Range(10.5, 16),
        size_floor=6.5,
        tou_per_1000=Range(4, 15),
        fonts=("Meiryo",),
        reference="財務省 予算のポイント 862 字・13pt、国交省 855 字・11.5pt、厚労省 保険局 689 字・13pt",
    ),
    "tsuchi": Spec(
        key="tsuchi",
        label="通知文（A4 縦・記書き）",
        paper_mm=(210, 297),
        chars=Range(300, 1440),
        size_median=Range(10.5, 12.5),
        size_floor=8,
        tou_per_1000=Range(None, 15),
        fonts=("Mincho", "明朝"),
        reference="Word の A4 既定（10.5pt・40 字×36 行）で 1 ページ 1,440 字。公用文の手引きの本文は 10.5pt 明朝",
    ),
}


GAP_WARN_MM = 8.0  # 区画の下の空きがこれを超えたら注意（本文 1 行は 6mm 前後）
MM_PER_CSS_PX = 25.4 / 96


@dataclass(frozen=True)
class Overflow:
    """画面上で、枠の中身が枠より大きかった箇所。dx・dy は CSS の px。"""

    page: int
    where: str
    dx: int
    dy: int


@dataclass(frozen=True)
class Gap:
    """区画（section）の中で、最後の字より下に残った空き。"""

    page: int
    where: str
    mm: float


@dataclass(frozen=True)
class SpaceBreak:
    """HTML の中で和文の途中を改行した箇所。ブラウザは改行を半角の空白にする。"""

    page: int
    text: str


@dataclass
class Inspection:
    """画面上で測ったもの。PDF からは分からない。"""

    overflows: list[Overflow] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    breaks: list[SpaceBreak] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)  # .page ごとの data-role


@dataclass(frozen=True)
class Check:
    name: str
    level: Level
    value: str
    target: str
    hint: str = ""


@dataclass
class Report:
    spec: Spec
    checks: list[Check] = field(default_factory=list)

    @property
    def worst(self) -> Level:
        levels = {c.level for c in self.checks}
        for level in (Level.NG, Level.WARN):
            if level in levels:
                return level
        return Level.OK


def mm(css_px: float) -> str:
    return f"{css_px * MM_PER_CSS_PX:.1f}mm"


def judge(doc: DocMetrics, spec: Spec, expected_pages: int, seen: Inspection | None = None) -> Report:
    report = Report(spec)
    seen = seen or Inspection()
    roles = seen.roles
    add = report.checks.append

    if seen.overflows:
        for o in seen.overflows:
            parts = [f"縦 {mm(o.dy)}" if o.dy > 0 else "", f"横 {mm(o.dx)}" if o.dx > 0 else ""]
            add(
                Check(
                    f"はみ出し（{o.page} 枚目）",
                    Level.NG,
                    f"{o.where}: {'・'.join(p for p in parts if p)}",
                    "0mm",
                    "説明の言葉を削る → 字を小さくする（下限まで） → 枠の幅・高さを配分し直す、の順で直す",
                )
            )
    else:
        add(Check("はみ出し", Level.OK, "なし", "なし"))

    if len(doc.pages) != expected_pages:
        add(
            Check(
                "枚数",
                Level.NG,
                f"PDF {len(doc.pages)} 枚",
                f"{expected_pages} 枚（.page の数）",
                "中身が次の紙にこぼれている。.page の高さと overflow を確かめる",
            )
        )

    w, h = spec.paper_mm
    bad_paper = [
        p for p in doc.pages if abs(p.width_mm - w) > PAPER_TOLERANCE_MM or abs(p.height_mm - h) > PAPER_TOLERANCE_MM
    ]
    if bad_paper:
        p = bad_paper[0]
        add(
            Check(
                "用紙",
                Level.NG,
                f"{p.width_mm:g}×{p.height_mm:g}mm（{p.number} 枚目）",
                f"{w:g}×{h:g}mm",
                "@page の size と .page の幅・高さをそろえる",
            )
        )
    else:
        add(Check("用紙", Level.OK, f"{w:g}×{h:g}mm", f"{w:g}×{h:g}mm"))

    for p in doc.text_pages:
        tag = f"（{p.number} 枚目）" if len(doc.pages) > 1 else ""
        front = p.number <= len(roles) and roles[p.number - 1] in FRONT_MATTER
        if not front:
            if spec.chars.contains(p.chars):
                add(Check(f"字数{tag}", Level.OK, f"{p.chars:,} 字", spec.chars.describe(" 字")))
            else:
                too_many = spec.chars.high is not None and p.chars > spec.chars.high
                hint = (
                    "多い。説明の言葉を削るか 2 枚に分ける"
                    if too_many
                    else "少ない。区画や補足を足すか、字を大きくする"
                )
                add(Check(f"字数{tag}", Level.WARN, f"{p.chars:,} 字", spec.chars.describe(" 字"), hint))

            level = Level.OK if spec.size_median.contains(p.size_median_pt) else Level.WARN
            add(
                Check(
                    f"文字サイズ{tag}",
                    level,
                    f"{p.size_median_pt:g}pt（A4 換算の中央値）",
                    spec.size_median.describe("pt"),
                    "" if level is Level.OK else "本文の font-size を見直す",
                )
            )

        if p.size_p05_pt < spec.size_floor:
            add(
                Check(
                    f"小さすぎる字{tag}",
                    Level.NG,
                    f"5% 目が {p.size_p05_pt:g}pt",
                    f"{spec.size_floor:g}pt 以上",
                    "注や表の字を下限まで戻す。入らなければ言葉を削る",
                )
            )

        if p.top_fonts:
            font, share = p.top_fonts[0]
            level = Level.OK if any(f.lower() in font.lower() for f in spec.fonts) else Level.WARN
            add(
                Check(
                    f"書体{tag}",
                    level,
                    f"{font}（{share}%）",
                    " または ".join(spec.fonts),
                    "" if level is Level.OK else "指定した書体が無く、別の書体に置き換わっている",
                )
            )

    wide = [g for g in seen.gaps if g.mm > GAP_WARN_MM]
    for g in wide:
        add(
            Check(
                f"下の空き（{g.page} 枚目）",
                Level.WARN,
                f"{g.where}: {g.mm:.0f}mm",
                f"{GAP_WARN_MM:g}mm 以下",
                "省庁の資料は余白を残さない。中身を足す・字を大きくする・区画の高さの配分を変える",
            )
        )
    if seen.gaps and not wide:
        add(Check("下の空き", Level.OK, f"最大 {max(g.mm for g in seen.gaps):.0f}mm", f"{GAP_WARN_MM:g}mm 以下"))

    if seen.breaks:
        shown = "／".join(f"{b.page} 枚目「{b.text}」" for b in seen.breaks[:3])
        more = f" ほか {len(seen.breaks) - 3} か所" if len(seen.breaks) > 3 else ""
        add(
            Check(
                "改行の空白",
                Level.WARN,
                shown + more,
                "0 か所",
                "HTML の中で和文の途中を改行すると、半角の空白が入る。その文は 1 行で書く",
            )
        )

    level = Level.OK if spec.tou_per_1000.contains(doc.tou_per_1000) else Level.WARN
    add(
        Check(
            "「等」の頻度",
            level,
            f"千字に {doc.tou_per_1000:g} 回",
            spec.tou_per_1000.describe(" 回"),
            "" if level is Level.OK else "実物の予算資料は千字に 8.8〜11.7 回（100 字に 1 回）",
        )
    )

    if doc.seireki:
        add(
            Check(
                "年の書き方",
                Level.WARN,
                f"西暦 {doc.seireki} 回・和暦 {doc.wareki} 回",
                "和暦",
                "省庁の資料は和暦が慣行（9 本で和暦 895 回・西暦 114 回）",
            )
        )
    else:
        add(Check("年の書き方", Level.OK, f"和暦 {doc.wareki} 回・西暦 0 回", "和暦"))

    return report
