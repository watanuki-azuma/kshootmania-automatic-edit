# Agent notes (Claude / Codex 共通)

- Python >= 3.11, パッケージ管理は uv。`uv run pytest` でテスト、`uv run ksmauto ...` で CLI。
- 設計方針は `docs/design.md`、フォーマット仕様は `docs/spec/`（公式仕様の写し。編集しない）。
- KSON は plain な `dict` / `list` で扱う。独自クラス階層を作らない。
- 実行時依存は標準ライブラリのみ（音源解析は `audio` extra: numpy / scipy / librosa / soundfile）。
- `corpus/` は手元専用。コーパス依存のテストは `pytest.skip` で無い環境に対応する。
- 既存コードの命名・コメント量に合わせる。仕様にない拡張や汎用化をしない。
