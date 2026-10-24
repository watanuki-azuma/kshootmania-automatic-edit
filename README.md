# kshootmania-automatic-edit

LLM（Claude / GPT）で K-Shoot MANIA の譜面（KSON）を作るためのツール群（`ksmauto`）と Skills。

音源 → 解析 → LLM が中間 DSL（`.ksmd`）で作譜 → KSON へコンパイル → lint・難易度推定・画像で自己確認 → 修正、のループを回す。人が仕上げるためのブラウザエディタも付く。

## セットアップ

```sh
uv sync --extra audio --extra render
uv sync --extra audio --extra render --extra stems   # 音源分離も使う場合（PyTorch が入る。CPU 版で十分）
uv run python scripts/fetch_corpus.py   # 公式既定曲を corpus/ に取得（任意。テスト・評価用）
uv run pytest
```

## コマンド

| コマンド | 内容 |
|---|---|
| `ksmauto analyze SONG.ogg -o a.json --text a.txt` | BPM・offset・小節頭・帯域別オンセット・セクションを解析 |
| `ksmauto analyze SONG.ogg --tempo 0:141,53:138.2 --offset 1074 ...` | テンポが変わる曲: テンポマップと offset を指定して解析し直す |
| `ksmauto separate SONG.ogg -o stems/` | Demucs でボーカル・ドラム・ベース・その他に分離（`stems` extra。PyTorch CPU 版で 2 分の曲に約 1 分） |
| `ksmauto analyze SONG.ogg --stems stems/ ...` | 分離音源から キック/スネア/ハイハット/ベース/ボーカル/その他 の段と、ボーカルの音程・その他（ピアノ等）の音の高さのレーン（`olane`）を追加 |
| `ksmauto compile draft.ksmd -o chart.kson [--base orig.kson]` | DSL → KSON |
| `ksmauto decompile chart.(kson\|ksh) -o draft.ksmd` | KSON/KSH → DSL |
| `ksmauto convert chart.ksh -o chart.kson` | KSH → KSON |
| `ksmauto lint FILE [--analysis a.json]` | 手が足りない配置・速すぎる縦連・音のない位置のノーツなど |
| `ksmauto stats FILE` | ノーツ数・NPS・推定レベル |
| `ksmauto render FILE --measures 16-47 -o page.png` | 譜面を PNG に描画 |
| `ksmauto validate FILE` / `ksmauto info FILE` | KSON 構造検証 / 概要 |
| `ksmauto edit chart.kson --audio SONG.ogg` | ブラウザで同期再生・手修正 |
| `ksmauto preview FILE [--audio SONG] -o preview.html` | 音源を埋め込んだ単体 HTML の再生プレビュー（サーバー不要。共有用）。KSM v2 と同じ透視・レーザーによる傾きの 3D 表示と、平面表示を切り替えられる |
| `ksmauto sdvxin DIR [-o x.kson]` / `ksmauto sdvxin --report ROOT` | 手元に取得した sdvx.in 譜面（JSON / 画像レイヤー）を KSON に復元 / 公表ノーツ数と照合 |

`FILE` は `.kson` / `.ksh` / `.ksmd` のどれでもよい。

## 参考譜面コーパス（ローカル専用）

`corpus/` は git 管理外で、再配布しない。

- `scripts/fetch_corpus.py` — KSM 公式既定曲（10 曲 36 譜面）
- `scripts/fetch_sdvxin.py --levels 17-20 [--out DIR]` — sdvx.in の Lv17〜20 譜面（1 req/s、取得済みはスキップ、中断しても再実行で続きから）
- `tests/eval/eval_sdvxin.py [ROOT]` — 復元精度の評価。`tests/eval/sdvxin_side_by_side.py DIR` で元画像と復元結果を並べた PNG を `out/sdvxin/` に出す

復元精度（47 譜面: JSON 7 / 画像 40）: JSON はチップ数完全一致、ロング・レーザーのチェイン数も推定モデルとの誤差 3% 以内。画像はチップ数完全一致 34/40（外れは最大 3 個）、ロング 37/40、レーザー 33/40、KSON 検証は全件通過。
ロングのチェイン数は公式の数え方が不明なため、JSON 譜面に合わせた経験式（72 pulse ごと、BPM 255 以上で倍）で照合している。

## Skills

`skills/ksm-chart-authoring/` が正本。`uv run python scripts/sync_skills.py` で `.claude/skills/`（Claude Code）と `.agents/skills/`（Codex）にコピーする。

## ドキュメント

- [docs/design.md](docs/design.md) — 設計
- [docs/draft-format.md](docs/draft-format.md) — 中間 DSL 仕様
- [docs/analysis-format.md](docs/analysis-format.md) — 解析出力仕様と精度評価
- [docs/spec/](docs/spec/) — 公式 KSH/KSON 仕様（CC0）

## 精度（公式既定曲 10 曲）

`uv run python tests/eval/eval_analyze.py`: BPM 10/10、拍の位相 9/10、小節頭 8/10。
`uv run python tests/eval/fit_level.py`: レベル推定の平均誤差 0.7（公式 36 譜面）、0.7（sdvx.in Lv17〜20 の 1607 譜面、手元にある場合）。
`uv run python tests/eval/sdvxin_patterns.py`: 手元の sdvx.in 譜面から配置パターン（レーザー中の空き手のレーン、16 分の形など）を集計。`--chart` で自作譜面も同じ集計にかけられる。
