# kshootmania-automatic-edit

LLM（Claude / GPT）で K-Shoot MANIA の譜面（KSON）を作るためのツール群（`ksmauto`）と Skills。

音源 → 解析 → LLM が中間 DSL（`.ksmd`）で作譜 → KSON へコンパイル → lint・難易度推定・画像で自己確認 → 修正、のループを回す。人が仕上げるためのブラウザエディタも付く。

## セットアップ

```sh
uv sync --extra audio --extra render
uv run python scripts/fetch_corpus.py   # 公式既定曲を corpus/ に取得（任意。テスト・評価用）
uv run pytest
```

## コマンド

| コマンド | 内容 |
|---|---|
| `ksmauto analyze SONG.ogg -o a.json --text a.txt` | BPM・offset・小節頭・帯域別オンセット・セクションを解析 |
| `ksmauto compile draft.ksmd -o chart.kson [--base orig.kson]` | DSL → KSON |
| `ksmauto decompile chart.(kson\|ksh) -o draft.ksmd` | KSON/KSH → DSL |
| `ksmauto convert chart.ksh -o chart.kson` | KSH → KSON |
| `ksmauto lint FILE [--analysis a.json]` | 手が足りない配置・速すぎる縦連・音のない位置のノーツなど |
| `ksmauto stats FILE` | ノーツ数・NPS・推定レベル |
| `ksmauto render FILE --measures 16-47 -o page.png` | 譜面を PNG に描画 |
| `ksmauto validate FILE` / `ksmauto info FILE` | KSON 構造検証 / 概要 |
| `ksmauto edit chart.kson --audio SONG.ogg` | ブラウザで同期再生・手修正 |

`FILE` は `.kson` / `.ksh` / `.ksmd` のどれでもよい。

## Skills

`skills/ksm-chart-authoring/` が正本。`uv run python scripts/sync_skills.py` で `.claude/skills/`（Claude Code）と `.agents/skills/`（Codex）にコピーする。

## ドキュメント

- [docs/design.md](docs/design.md) — 設計
- [docs/draft-format.md](docs/draft-format.md) — 中間 DSL 仕様
- [docs/analysis-format.md](docs/analysis-format.md) — 解析出力仕様と精度評価
- [docs/spec/](docs/spec/) — 公式 KSH/KSON 仕様（CC0）

## 精度（公式既定曲 10 曲）

`uv run python tests/eval/eval_analyze.py`: BPM 10/10、拍の位相 9/10、小節頭 8/10。
`uv run python tests/eval/fit_level.py`: レベル推定の誤差 ±1 程度（36 譜面）。
