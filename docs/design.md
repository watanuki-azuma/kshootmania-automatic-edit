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
