# CLAUDE.md

この repo は Claude Code の skill「gov-doc-style」（省庁風の資料を HTML から PNG・PDF に書き出して検査する）。
使い方は README.md、Claude が読む手順は SKILL.md。

- 作者の手元では Daily-log（個人の管理リポジトリ）と 2 層構成で、PM インデックスは `Daily-log/Project/gov-doc-style/`。
  `~/.claude/skills/gov-doc-style` はこの作業ツリーを指すジャンクションで、毎晩の日報のポンチ絵もこれを使う。
  ここを直すと翌晩の自動生成に効くので、テストが赤いまま push しない
- **public リポジトリ。** 個人の作業内容・手元のパス・トークンを入れない。ひな形の中身は架空にする（「○○省」と架空の数値）
- Python は uv のみ。`uv run --frozen pytest` / `uv run --frozen ruff format .` / `uv run --frozen ruff check . --fix` / `uv run --frozen pyright`
- ひな形を直したら `pytest`（ひな形 4 枚が検査 OK になること）を回す。目安（`specs.py`）は実物の測定値（`docs/measurements.md`）が根拠なので、ひな形に合わせて動かさない
- 画面上の検査は `render.py` の `INSPECT_JS`（Python の文字列の中の JavaScript）。正規表現の `\` は二重に書く
- コミットは Conventional Commits＋日本語。co-authored-by などのツール痕跡は書かない
