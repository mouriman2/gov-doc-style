"""書き出した PDF の見た目を測る。

物差しは、省庁の公開 PDF 10 本を測ったとき（docs/measurements.md）と同じ。
文字サイズは「A4 に収まるよう拡大縮小して刷ったとき」の大きさに直す（スライドの大きさが資料ごとに違うため）。

pdfplumber は一部の漢字を康熙部首（「日」→「⽇」など）として読むので、文字列は NFKC で正規化してから数える。
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber

MIN_CHARS = 50  # これ未満のページ（表紙・画像だけのページ）は字数の検査から外す
PT_PER_MM = 72 / 25.4
COMPOUND_TOU = re.compile(r"高等|均等|初等|中等|平等|同等|対等|等級|優等|等分|等し|等価")
WAREKI = re.compile(r"(?:令和|平成|昭和)\s*[0-9０-９元]+\s*年")
SEIREKI = re.compile(r"(?:19|20)[0-9]{2}\s*年")
SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")


def a4_scale(width_mm: float, height_mm: float) -> float:
    """その用紙を A4（横長なら横、縦長なら縦）にぴったり収めて刷るときの倍率。"""
    if width_mm > height_mm:
        return min(297 / width_mm, 210 / height_mm)
    return min(210 / width_mm, 297 / height_mm)


def count_tou(text: str) -> int:
    """「等」の数。「高等」「均等」などの熟語と、かぎ括弧で引いた「等」そのものは数えない。"""
    return COMPOUND_TOU.sub("", text.replace("「等」", "")).count("等")


def weighted_percentile(counter: Counter[float], q: float) -> float:
    """字数で重みをつけた分位点（q=0.5 で中央値）。"""
    total = sum(counter.values())
    if total == 0:
        return 0.0
    acc = 0
    for size in sorted(counter):
        acc += counter[size]
        if acc >= total * q:
            return size
    return max(counter)


def font_family(name: str) -> str:
    """PDF に埋め込まれた書体名から、サブセットの印（ABCDEF+）を外す。"""
    return SUBSET_PREFIX.sub("", name)


@dataclass(frozen=True)
class PageMetrics:
    number: int
    width_mm: float
    height_mm: float
    chars: int
    size_median_pt: float
    size_p05_pt: float
    top_fonts: list[tuple[str, int]]  # (書体, 字数の割合 %)


@dataclass(frozen=True)
class DocMetrics:
    pages: list[PageMetrics]
    total_chars: int
    tou_per_1000: float
    wareki: int
    seireki: int

    @property
    def text_pages(self) -> list[PageMetrics]:
        return [p for p in self.pages if p.chars >= MIN_CHARS]


def normalize(text: str) -> str:
    """康熙部首・全角英数を通常の文字にし、空白を除く。"""
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", text))


def measure_page(page: Any, number: int) -> tuple[PageMetrics, str]:
    """pdfplumber のページを測る。"""
    width_mm = float(page.width) / PT_PER_MM
    height_mm = float(page.height) / PT_PER_MM
    scale = a4_scale(width_mm, height_mm)
    sizes: Counter[float] = Counter()
    fonts: Counter[str] = Counter()
    for ch in page.chars:
        if not ch["text"].strip():
            continue
        sizes[round(float(ch["size"]) * scale * 2) / 2] += 1
        fonts[font_family(ch["fontname"])] += 1
    chars = sum(sizes.values())
    top = [(f, round(n / chars * 100)) for f, n in fonts.most_common(3)] if chars else []
    metrics = PageMetrics(
        number=number,
        width_mm=round(width_mm, 1),
        height_mm=round(height_mm, 1),
        chars=chars,
        size_median_pt=weighted_percentile(sizes, 0.5),
        size_p05_pt=weighted_percentile(sizes, 0.05),
        top_fonts=top,
    )
    return metrics, normalize(page.extract_text() or "")


def summarize_text(pages: list[PageMetrics], text: str) -> DocMetrics:
    return DocMetrics(
        pages=pages,
        total_chars=len(text),
        tou_per_1000=round(count_tou(text) / max(len(text), 1) * 1000, 1),
        wareki=len(WAREKI.findall(text)),
        seireki=len(SEIREKI.findall(text)),
    )


def measure_pdf(path: Path) -> DocMetrics:
    pages: list[PageMetrics] = []
    text = ""
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            metrics, page_text = measure_page(page, i)
            pages.append(metrics)
            text += page_text
    return summarize_text(pages, text)
