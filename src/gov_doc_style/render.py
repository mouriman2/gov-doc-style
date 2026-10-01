"""省庁風の資料の HTML を PDF と PNG に書き出し、はみ出しと見た目の数字を検査する。

使い方: gov-doc-render <資料.html> [--out <フォルダ>] [--type <種類>] [--scale 2]

HTML の決まり（templates/ のひな形はすべて満たしている）:
- 1 枚の紙を <div class="page"> 1 つにする。幅と高さは mm で固定し、@page の size とそろえる
- <meta name="gov-doc-type" content="ponchi-jigyo"> のように種類を書く（--type で上書きできる）
- 中身が溢れたら困る枠は section か [data-fit] にする。.page も含めて、中身が枠より大きいと NG になる
- 表紙・目次・中扉の .page には data-role="cover" / "toc" / "divider" を付ける（字数と文字サイズの目安を当てない）

画面上では、はみ出しのほかに、区画（section）の下の空きと、和文の途中の改行（半角の空白になる）も測る。

出力: <名前>.pdf と、1 枚なら <名前>.png、複数枚なら <名前>-01.png, <名前>-02.png …
終了コード: NG があれば 1、なければ 0（注意だけなら 0）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import unicodedata
from pathlib import Path

from playwright.sync_api import sync_playwright

from gov_doc_style.measure import measure_pdf
from gov_doc_style.specs import SPECS, Gap, Inspection, Level, Overflow, Report, SpaceBreak, judge

BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

INSPECT_JS = """() => {
  const pages = [...document.querySelectorAll('.page')];
  const pageOf = (node) => pages.indexOf(node.closest('.page')) + 1;
  const label = (el) => {
    if (el.matches('.page')) return '紙全体';
    const head = el.querySelector('h1, h2, h3, th');
    const text = el.dataset.fit || (head && head.textContent) || el.className || el.tagName;
    return text.trim().replace(/\\s+/g, ' ').slice(0, 40);
  };

  // 1. はみ出し: 枠の中身が枠より大きい
  const overflows = [];
  for (const el of document.querySelectorAll('.page, .page section, .page [data-fit]')) {
    const dx = el.scrollWidth - el.clientWidth;
    const dy = el.scrollHeight - el.clientHeight;
    if (dx <= 1 && dy <= 1) continue;
    overflows.push({page: pageOf(el), where: label(el), dx: Math.max(dx, 0), dy: Math.max(dy, 0)});
  }

  // 2. 区画の下の空き: 最後の字（と画像・表）の下端から枠の下端まで
  const range = document.createRange();
  const contentBottom = (el) => {
    let bottom = -Infinity;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      if (!walker.currentNode.data.trim()) continue;
      range.selectNodeContents(walker.currentNode);
      for (const r of range.getClientRects()) if (r.height > 0) bottom = Math.max(bottom, r.bottom);
    }
    for (const e of el.querySelectorAll('img, svg, canvas, table')) {
      const r = e.getBoundingClientRect();
      if (r.height > 0) bottom = Math.max(bottom, r.bottom);
    }
    return bottom;
  };
  const gaps = [];
  for (const sec of document.querySelectorAll('.page section')) {
    const bottom = contentBottom(sec);
    if (bottom === -Infinity) continue;
    const inner = sec.getBoundingClientRect().bottom - parseFloat(getComputedStyle(sec).borderBottomWidth);
    gaps.push({page: pageOf(sec), where: label(sec), mm: Math.max(inner - bottom, 0) * 25.4 / 96});
  }

  // 3. 和文の途中の改行: ブラウザは半角の空白にする
  const wide = /[^\\x00-\\x7F]/;
  const isInline = (el) => el && el.nodeType === 1 && getComputedStyle(el).display === 'inline';
  const breaks = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode;
    const parent = n.parentElement;
    if (!parent || parent.closest('style, script, pre, textarea')) continue;
    if (getComputedStyle(parent).whiteSpace.startsWith('pre')) continue;
    const t = n.data;
    let hit = null;
    const m = /[^\\x00-\\x7F][ \\t]*\\n\\s*(?=[^\\x00-\\x7F])/.exec(t);
    if (m) {
      const end = m.index + m[0].length;
      hit = t.slice(Math.max(0, m.index - 7), m.index + 1).trim() + '␣' + t.slice(end, end + 8).trim();
    }
    if (!hit && /[^\\x00-\\x7F][ \\t]*\\n\\s*$/.test(t) && isInline(n.nextSibling)
        && wide.test((n.nextSibling.textContent || '').trim().charAt(0))) {
      hit = t.trim().slice(-8) + '␣' + n.nextSibling.textContent.trim().slice(0, 8);
    }
    if (!hit && /^\\s*\\n[ \\t]*[^\\x00-\\x7F]/.test(t) && isInline(n.previousSibling)
        && wide.test((n.previousSibling.textContent || '').trim().slice(-1))) {
      hit = n.previousSibling.textContent.trim().slice(-8) + '␣' + t.trim().slice(0, 8);
    }
    if (hit && pageOf(parent) > 0) breaks.push({page: pageOf(parent), text: hit});
  }

  const roles = pages.map((p) => p.dataset.role ?? '');
  return {overflows, gaps, breaks, roles};
}"""


def find_browser() -> str:
    override = os.environ.get("GOV_DOC_BROWSER")
    if override:
        return override
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("Chrome も Edge も見つからない。GOV_DOC_BROWSER にブラウザの実行ファイルを指定する")


def render(html: Path, out_dir: Path, doc_type: str | None, scale: float) -> tuple[Report, list[Path]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = html.stem
    pdf_path = out_dir / f"{stem}.pdf"
    pngs: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=find_browser(), headless=True)
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=scale)
            page.goto(html.resolve().as_uri())
            page.evaluate("document.fonts.ready.then(() => true)")
            meta_type = page.evaluate(
                "document.querySelector('meta[name=\"gov-doc-type\"]')?.getAttribute('content') ?? ''"
            )
            key = doc_type or meta_type
            if key not in SPECS:
                raise SystemExit(
                    f"資料の種類が分からない: '{key}'。meta gov-doc-type か --type で {list(SPECS)} から指定する"
                )
            raw = page.evaluate(INSPECT_JS)
            seen = Inspection(
                overflows=[Overflow(**o) for o in raw["overflows"]],
                gaps=[Gap(**g) for g in raw["gaps"]],
                breaks=[SpaceBreak(**b) for b in raw["breaks"]],
                roles=raw["roles"],
            )
            sheets = page.locator(".page")
            count = sheets.count()
            if count == 0:
                raise SystemExit('<div class="page"> が 1 つも無い')
            for i in range(count):
                png = out_dir / (f"{stem}.png" if count == 1 else f"{stem}-{i + 1:02d}.png")
                sheets.nth(i).screenshot(path=str(png))
                pngs.append(png)
            page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        finally:
            browser.close()
    report = judge(measure_pdf(pdf_path), SPECS[key], expected_pages=count, seen=seen)
    return report, [pdf_path, *pngs]


def display_width(text: str) -> int:
    """端末での表示幅。全角は 2 桁と数える。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad(text: str, width: int) -> str:
    return text + " " * (width - display_width(text))


def format_report(report: Report, files: list[Path]) -> str:
    lines = [f"種類: {report.spec.label}", f"比べた実物: {report.spec.reference}", ""]
    width = max(display_width(c.name) for c in report.checks)
    for c in report.checks:
        line = f"[{pad(c.level.value, 4)}] {pad(c.name, width)}  {c.value}  （目安 {c.target}）"
        if c.hint:
            line += f"\n       → {c.hint}"
        lines.append(line)
    lines += ["", "出力:", *[f"  {f}" for f in files], "", f"判定: {report.worst.value}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("html", type=Path)
    parser.add_argument("--out", type=Path, help="書き出し先（既定は HTML と同じフォルダ）")
    parser.add_argument("--type", choices=list(SPECS), help="資料の種類（既定は meta gov-doc-type）")
    parser.add_argument("--scale", type=float, default=2, help="PNG の倍率（既定 2）")
    args = parser.parse_args(argv)
    if not args.html.exists():
        raise SystemExit(f"見つからない: {args.html}")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    report, files = render(args.html, args.out or args.html.parent, args.type, args.scale)
    print(format_report(report, files))
    return 1 if report.worst is Level.NG else 0


if __name__ == "__main__":
    sys.exit(main())
