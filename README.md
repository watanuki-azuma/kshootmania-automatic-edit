# kshootmania-automatic-edit

LLM（Claude / GPT）で K-Shoot MANIA の譜面（KSON）を作るためのツール群（`ksmauto`）と Skills。

音源 → 解析 → LLM が中間 DSL（`.ksmd`）で作譜 → KSON へコンパイル → lint・難易度推定・画像で自己確認 → 修正、のループを回す。人が仕上げるためのブラウザエディタも付く。

## セットアップ

```sh
uv sync --extra audio --extra render
uv sync --extra audio --extra render --extra stems   # 音源分離も使う場合（PyTorch が入る。CPU 版で十分）
uv sync --extra audio --extra render --extra stems --extra transcribe   # ピアノの採譜も使う場合
uv run python scripts/fetch_corpus.py   # 公式既定曲を corpus/ に取得（任意。テスト・評価用）
uv run pytest
```

## コマンド

| コマンド | 内容 |
|---|---|
| `ksmauto analyze SONG.ogg -o a.json --text a.txt` | BPM・offset・小節頭・帯域別オンセット・セクションを解析 |
| `ksmauto analyze SONG.ogg --tempo 0:141,53:138.2 --offset 1074 ...` | テンポが変わる曲: テンポマップと offset を指定して解析し直す |
| `ksmauto separate SONG.ogg -o stems/` | Demucs でボーカル・ドラム・ベース・その他に分離（`stems` extra。PyTorch CPU 版で 2 分の曲に約 1 分） |
| `ksmauto separate SONG.ogg -o stems/ --model htdemucs_6s` | 上に加えてピアノ・ギターも分ける（ピアノが主役の区間がある曲向け） |
| `ksmauto transcribe stems/piano.wav` | ピアノのステムを ByteDance のピアノ採譜モデルで音符にする（`transcribe` extra。初回に約 170 MB のモデルを取得。2 分の曲に CPU で 1〜3 分）。`stems/piano.notes.json` に書き、`analyze --stems` が使う |
| `ksmauto transcribe SONG.ogg --engine muscriptor --model small --python /tmp/musvenv/bin/python -o stems/` | ミックスを MuScriptor で採譜し、楽器に応じた `<row>.notes.json` を出す。`--model` は `small`（既定・CPU 向け）/`medium`/`large`。`-o` はディレクトリ（省略時は音源と同じ場所）。導入・ライセンスは下記 |
| `ksmauto analyze SONG.ogg --stems stems/ ...` | 分離音源から キック/スネア/ハイハット/ベース/ボーカル/その他（あればピアノ）の段と、ボーカルの音程・その他とピアノの音の高さのレーン（`olane` `plane`）を追加 |
| `ksmauto compile draft.ksmd -o chart.kson [--base orig.kson]` | DSL → KSON |
| `ksmauto decompile chart.(kson\|ksh) -o draft.ksmd` | KSON/KSH → DSL |
| `ksmauto convert chart.ksh -o chart.kson` | KSH → KSON |
| `ksmauto lint FILE [--analysis a.json]` | 手が足りない配置・速すぎる縦連・音のない位置のノーツなど |
| `ksmauto stats FILE` | ノーツ数・チェイン数（KSM v2 の数え方）・NPS・推定レベル |
| `ksmauto render FILE --measures 16-47 -o page.png` | 譜面を PNG に描画 |
| `ksmauto validate FILE` / `ksmauto info FILE` | KSON 構造検証 / 概要 |
| `ksmauto edit chart.kson --audio SONG.ogg` | ブラウザで同期再生・手修正 |
| `ksmauto preview FILE [--audio SONG] -o preview.html` | 譜面と音源を埋め込んだ単体 HTML ビューア（サーバー不要。共有用）。KSM v2 に基づくカメラ・スクロールと 2D/3D 表示、FX・レーザーの音声エフェクトと FX キー音の近似再生。直角音は既定オン（合成音、up/down/swing/mute・音量変化・幅による自動音量に対応） |
| `ksmauto viewer -o viewer.html` | 譜面を含まない単体 HTML ビューア。KSON / KSH と音源をファイル選択・ドロップで開き、再読み込みせずに切替。フォルダー内の音源は BGM ファイル名で照合（音源が 1 件ならそれを使用）。外部通信不要。GitHub Pages 版: https://watanuki-azuma.github.io/KSM-WEB-VIEWER/ （[ksm-web-viewer](https://github.com/watanuki-azuma/KSM-WEB-VIEWER) にこのコマンドの出力を置いている） |
| `ksmauto sdvxin DIR [-o x.kson]` / `ksmauto sdvxin --report ROOT` | 手元に取得した sdvx.in 譜面（JSON / 画像レイヤー）を KSON に復元 / 公表ノーツ数と照合 |

`FILE` は `.kson` / `.ksh` / `.ksmd` のどれでもよい。

MuScriptor は別の Python 3.12 環境に入れ、`--python` で指定する:

```sh
uv venv /tmp/musvenv --python 3.12
uv pip install --python /tmp/musvenv/bin/python 'muscriptor>=0.4'
```

[MuScriptor](https://github.com/muscriptor/muscriptor) のコードは MIT、重みは非商用の CC BY-NC 4.0。[Hugging Face のモデル一覧](https://huggingface.co/MuScriptor) から使うモデルのライセンスを承諾し、`HF_TOKEN` に読み取りトークンを設定する（初回に重みを取得）。`muscriptor` extra は Python 3.13 / Intel macOS を含む依存解決が通らないため用意していない。出力は MuScriptor の楽器名から piano・guitar・bass・vocal（`voice`）・other（それ以外）にまとめ、ドラムは除外する。強さは全音 1.0。`analyze --stems` が採譜を使うのは、対応する wav がある `other` / `piano` のみ（bass / guitar / vocal の JSON は現状使わない）。

## 参考譜面コーパス（ローカル専用）

`corpus/` は git 管理外で、再配布しない。

- `scripts/fetch_corpus.py` — KSM 公式既定曲（10 曲 36 譜面）
- `scripts/fetch_sdvxin.py --levels 17-20 [--out DIR]` — sdvx.in の Lv17〜20 譜面（1 req/s、取得済みはスキップ、中断しても再実行で続きから）
- `tests/eval/eval_sdvxin.py [ROOT]` — 復元精度の評価。`tests/eval/sdvxin_side_by_side.py DIR` で元画像と復元結果を並べた PNG を `out/sdvxin/` に出す

復元精度（47 譜面: JSON 7 / 画像 40）: JSON はチップ数完全一致、ロング・レーザーのチェイン数も推定モデルとの誤差 3% 以内。画像はチップ数完全一致 34/40（外れは最大 3 個）、ロング 37/40、レーザー 33/40、KSON 検証は全件通過。
sdvx.in の公表チェイン数は SDVX の数え方で、ロングの数え方が KSM と違うため、JSON 譜面に合わせた経験式（72 pulse ごと、BPM 255 以上で倍）で照合している（`stats` の `chains` は KSM v2 の数え方で、こちらとは別）。

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

## ライセンス表記

プレビュー・ビューアの一部は K-Shoot MANIA v2 / libkson（MIT）の実装を参考にしている。[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照。
