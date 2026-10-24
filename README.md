# kshootmania-automatic-edit

LLM（Claude / GPT）で K-Shoot MANIA の譜面（KSON）を作るためのツール群と Skills。

- 設計: [docs/design.md](docs/design.md)
- フォーマット仕様（公式, CC0）: [docs/spec/](docs/spec/)

## セットアップ

```sh
uv sync --extra audio
uv run python scripts/fetch_corpus.py   # 公式既定曲を corpus/ に取得（任意）
uv run pytest
```
