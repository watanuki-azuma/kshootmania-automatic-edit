# ksmauto 設計メモ

LLM（Claude / GPT）が音源から K-Shoot MANIA の譜面を作るためのツール群。

## 基本方針

- **標準形式は KSON**（`docs/spec/kson_format.md`, format_version 1）。内部表現も KSON の JSON 構造そのもの（`dict`）とし、独自のオブジェクトモデルは作らない。LLM が読み書きする形と内部が一致するため、変換層での情報欠落が起きない。
- **KSH は取り込み専用**（`docs/spec/ksh_format.md`）。既存資産を KSON に変換して読む。KSH への書き出しは当面作らない。
- 正しさの基準は公式実装 libkson（MIT）。`tests/fixtures/libkson/` に libkson のテスト用譜面（Gram）を同梱し、`Gram_ex.ksh` → `Gram_ex.kson` の一致を回帰テストにする。
- 時間の単位は pulse（1拍 = 240、4/4 の1小節 = 960）。

## パイプライン

```
audio ──analyze──▶ analysis.json ──(LLM)──▶ draft (中間DSL) ──compile──▶ chart.kson
                                                                         │
                         ◀──── lint / stats / render(PNG/SVG) ◀─────────┘
                                         │
                                    editor (人の手で修正)
```

| モジュール | 役割 | フェーズ |
|---|---|---|
| `ksmauto.kson` | KSON の読み書き・正規化・構造検証 | 1 |
| `ksmauto.timing` | pulse ⇔ 秒 ⇔ 小節 の変換（BPM・拍子変化対応） | 1 |
| `ksmauto.ksh` | KSH → KSON 変換 | 1 |
| `ksmauto.analyze` | 音源解析（BPM・オフセット・拍・オンセット・セクション・帯域別エネルギー） | 3 |
| `ksmauto.draft` | LLM 向け中間 DSL → KSON コンパイル | 4 |
| `ksmauto.lint` / `stats` | 運指・配置の問題検出、密度・難易度の統計 | 5 |
| `ksmauto.render` | 譜面の画像化（LLM の自己確認用） | 6 |
| `editor/` | ブラウザで動く簡易プレビュー・編集ツール | 6 |

## コーパス

- `scripts/fetch_corpus.py` が公式配布物から既定曲（10曲 / 36譜面、音源つき）を `corpus/official/` に取り出す。
- `corpus/` は再配布しない（`.gitignore` 済み）。コーパスに依存するテストは、無ければ skip する。

## 拍・テンポマップ

`uv sync --extra beats` で [Beat This!](https://github.com/CPJKU/beat_this)（コード・重み MIT）を導入。
`ksmauto beats SONG -o beats.json [--model final0|small0] [--min-bpm 120 --max-bpm 240]`
は File2Beats を遅延 import し CPU・dbn=False で実行する。
拍間隔の移動中央値でテンポが 3% 以内に続く拍の並び（8 拍以上）を区間とし、区間ごとに拍時刻へ直線を当てる
（裏拍に乗った・余分な拍はグリッドから外れるので除く）。区間 BPM は指定範囲へ倍・半分補正し、
補正後のテンポで小節を数える（半分テンポで追った区間は 1 downbeat 間が 2 小節になる）。
拍子と小節頭の位相は区間内の downbeat から取る。隣の区間と 2% 以内で直線が乗るなら 1 区間にまとめる。
変化点の小節は前区間のグリッドを延ばした小節線のうち、次区間の小節線と位相が最も合うものにする。
このため不安定な拍（つなぎ・フィル）は無視しても後ろの小節番号はずれない。
JSON は生の beats/downbeats（秒）、offset_ms（最初の区間の小節線）、segments（小節・BPM・拍数）、tempo_arg、warnings。
無視した区間・倍半分補正・長い拍間（フェルマータ・ブレイク）・拍子変化の疑い・徐々なテンポ変化は警告し、手動確認する。拍子変化は報告のみ。
`analyze --beats beats.json` は segments の BPM と最初の拍数、offset を読み、`--tempo/--offset` 相当で解析する。
従来の `analyze --beats 4` も受理する。JSON と明示 tempo/offset の併用はエラー。
自動テンポ推定時は前後 1/3 の推定が倍・半分補正後も 3% 超異なると警告する。
