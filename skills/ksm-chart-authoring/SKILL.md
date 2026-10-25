---
name: ksm-chart-authoring
description: K-Shoot MANIA の譜面（KSON）を音源から作る・既存譜面（KSH/KSON）を読んで直す。音源解析 → 中間DSL（.ksmd）で作譜 → コンパイル → lint・難易度推定・画像で自己確認 → 修正、のループを ksmauto CLI で回す。「この曲の譜面を作って」「レベル12くらいで」「ksh を直して」「譜面をレビューして」などで使う。
---

# K-Shoot MANIA 譜面作成

ツールはこのリポジトリの `ksmauto` CLI（`uv run ksmauto ...`）。初回は `uv sync --extra audio --extra render --extra stems --extra transcribe --extra beats`。新しいセッションでは extras が消えていることがある。「not installed」が出たらこの sync を再実行する。

## 手順

### 0. 入力を用意する

音源・譜面・作業ファイルは private な `out/曲名/` に置く（以下の `out/work/` は作業先の例）。動画（.mkv/.mp4/.webm）なら先に音声を取り出す:

```sh
ffmpeg -i in.mkv -vn -c:a libvorbis -q:a 6 out/work/song.ogg
```

曲名・作曲者はユーザーの指定か動画のフレームから確認する。目標レベルの指定がなければ質問するか、仮のレベルを明示して進める（例:「今回は Lv17 を目標にします」）。

### 1. 音源を解析する

まず Beat This!（CPU）で拍・小節頭を取り、`beats.json` の `segments` と `warnings` を読む:

```sh
uv run ksmauto beats SONG.ogg -o out/work/beats.json --min-bpm 120 --max-bpm 240
```

`segments` は `[開始小節, BPM, 小節内の拍数]`。倍・半分は指定範囲へ補正し、小節もそのテンポで数える。つなぎの不安定な拍は無視し、変化小節は前後のグリッドが合う位置に置く（`unstable beats ignored` の警告に秒が出るので、そこは耳で確かめる）。拍子変化は報告のみで analyze には適用しない。フェルマータ・リタルダンドの警告が出たら手動で確認する。

```sh
uv run ksmauto separate SONG.ogg -o out/work/stems     # 音源分離（stems extra = demucs が必要）
uv run ksmauto analyze SONG.ogg --beats out/work/beats.json --stems out/work/stems -o out/work/analysis.json --text out/work/analysis.txt
```

ピアノが主役の区間がある曲は 6 ステムに分けてピアノを採譜する（`plane` 列が増える。`other` から拾うより音程・発音ともずっと正確）:

```sh
uv run ksmauto separate SONG.ogg -o out/work/stems --model htdemucs_6s
uv run ksmauto transcribe out/work/stems/piano.wav      # transcribe extra が必要。out/work/stems/piano.notes.json を書く
uv run ksmauto analyze SONG.ogg --beats out/work/beats.json --stems out/work/stems -o out/work/analysis.json --text out/work/analysis.txt
```

`transcribe` が「not installed」で止まるときはまず sync を再実行する。導入できない場合は飛ばし、`plane` の精度が低いことを伝える。

任意で MuScriptor を使うなら、別の Python 3.12 venv に `muscriptor>=0.4` を入れ、`uv run ksmauto transcribe SONG.ogg --engine muscriptor --model small --python /tmp/musvenv/bin/python -o out/work/stems` でミックスを採譜できる（CPU は `small` 推奨）。重みは非商用の CC BY-NC 4.0 で、Hugging Face で使うモデルのライセンス承諾と `HF_TOKEN` の設定が必要。`other` / `piano` の JSON は対応する wav があるとき `analyze --stems` が使い、強さは全音 1.0。

demucs が入っていない（`separate` が「demucs is not installed」で止まる）ときは分離を飛ばし、`--stems` なしで解析する:

```sh
uv run ksmauto analyze SONG.ogg --beats out/work/beats.json -o out/work/analysis.json --text out/work/analysis.txt
```

`analysis.txt` を読む。先頭に BPM・offset・セクション、以下に小節ごとの 16 分グリッド（`X` 強、`x` 弱。3連の小節は 12 分割で `|` 区切り）。

- `low`: ベース・キックの低域。EDM では**裏打ちベース**（16 分の 3・7・11・15 番目）が出ることが多い。
- `mid`: キックのアタック・スネア・ボーカル。表拍の `X` はここに出る。BT の主な根拠にする。
- `high`: ハイハット・刻み。

`--stems` を付けた場合は帯域の 3 段の代わりに楽器ごとの 7 段になる。**何に合わせて何を置くか**はこちらで決める（対応表は `references/charting-guide.md` の「音と配置の対応」）。
- `kick` `snare` `hat`: ドラムを分けたもの。キックと同時に鳴るスネアは見分けが甘い（キックの位置ごとに `snare` が出たら、キック＋クラップの重ねかキックの高域の残り。キックより弱いスネアは逆に消える）。
- `bass` `vocal` `other`: 発音位置（`X`/`x`）と、音が伸びている間の `=`。`other` はシンセ・ギター・ピアノなど。
- `vpitch`: ボーカルの音程を曲の音域の中で 0（低い）〜9（高い）にしたもの。レーザーの位置の目安（低い = 左）。
- `olane`: `other`（ピアノ・シンセなど）の発音を、音の高さで A〜D に割り当てたもの。ピアノやアルペジオが主役の区間は、これを BT の階段の下書きにする（`references/charting-guide.md` の「楽器別の型」）。
- `piano` `plane`: 6 ステム分離のときだけ。ピアノの発音と、その高さの A〜D。ピアノの区間は `olane` より `plane` を使う。

確認すること:
- キックの `X` が拍頭、セクション境界が 4/8 小節線、ピアノの 8 分がグリッドに乗るかを目で確認する。普通の曲で 3 連グリッドの小節が大量に出たら、テンポが違う可能性が高い。
- 倍・半分のテンポを疑う。イントロ・アウトロだけ別テンポ、または自由拍の曲もある。自動検出値をそのまま信用せず、`downbeats` の時刻も確認する。
- 途中でずれるならキックやピアノの間隔から測り、`--beats` を外して `--tempo 0:140,11:190 --offset 486` のように指定し直す。ドラフトは `bpm: 140`、変化小節に `@m11` と `bpm 0 190`（参照: `references/draft-format.md`）。
- 拍が合っても小節頭が 1〜3 拍ずれることがある。セクション境界を見て offset を `+ n * 60000/BPM` ms 調整する。

### 2. 構成と密度を決める（書く前に）

`references/charting-guide.md` の表から、目標レベルの avg NPS・直角の量を決め、セクションごとに方針を一行ずつメモする（例: `m8-23 A: 8分の階段＋表拍にFX、レーザーはゆっくり往復`）。`--stems` があれば区間ごとの主役の楽器と型も決める（例: `m40-47 ピアノ: BT だけ、olane どおりの階段`）。
同じラベルのセクションは `copy`（必要なら `mirror`）で済ませる計画にする。

### 3. ドラフトを書く

形式は `references/draft-format.md`（`.ksmd`）。要点:

```
title: 曲名
artist: 作曲者
level: 12
difficulty: 2
audio: song.ogg
offset: 0
bpm: 180

@m4 "A"
0 A D            # 4/4 なら拍 0〜3。小節番号は 0 始まり
1/2 B
1 C~2            # 2 拍のロング
2 l 0 +2:1>0     # 左レーザー: 0 から 2 拍で 1 へ、そこで 0 に直角
@m12
copy m4-11 -> m12 mirror
```

- 解析テキストの強いオンセット（`X`）を中心に拾う。拾わない音があってよいが、**音の無い所には置かない**。
- 一度に全曲を書かず、セクション単位で書いては 4 の確認を回す。
- 密度の感覚: 4/4・BPM180 前後で「4 分＋ところどころ 8 分」を全編に置くと avg NPS は 4 を超え、Lv12 前後になる。CHALLENGE 以下は 4 分主体にして 8 分は山場だけにする。
- 両つまみとボタンの同時配置は、つまみの傾斜・終点補正とレベル別の公式出現頻度を lint で確認する。

### 4. コンパイルと自己確認

```sh
uv run ksmauto compile out/work/draft.ksmd -o out/work/chart.kson
uv run ksmauto lint out/work/draft.ksmd --analysis out/work/analysis.json
uv run ksmauto stats out/work/draft.ksmd
uv run ksmauto render out/work/draft.ksmd --measures 0-31 -o out/work/page.png
```

- compile エラーは全件まとめて出る。行番号の箇所を直す。
- lint: `hand-impossible`（全公式群で未観測の組合せ、warning）は修正する。`hand-rare`（対象群で0.05/100小節未満、info）は出現頻度と意図を確認する。`fast-jack`（両手）／`fast-jack-one-hand`（片手・mixed・補正利用の assisted）は群別・BT/FX別の公式 p1 未満を info で示す。gentle/ending のつまみは補正利用として別分類する。閾値表は `docs/placement-rules.md`、人手確認候補は `docs/placement-review.md`。`unaligned` が出たら、音の無い位置のノーツを解析と照合して直す。`empty-loud` は意図した休憩でなければ埋める。
- `thin`（歌っているのにボタンが薄い）は「楽器別の型」のボーカルの型で埋めるか、休符だと伝わる締めと入りを作る。
- stats の `level_estimate` が目標 ±1.5 に入るまで密度を調整する。
- render の PNG を開いて目で見る: 同じ形の繰り返しが単調すぎないか、レーザーとボタンが同じ手に重なっていないか、山場で密度が上がっているか。
- FX の使い方を「FX の使い方」の表と比べる: FX チップが BT のついでばかりになっていないか、FX ロング（短いもの）と L+R 同時があるか。
- 配置の偏りを `references/charting-guide.md` の「配置パターン」と比べる。レーザー中の空き手が C/D だけになっていないか（実譜面では FX-R と B が合わせて 3 割強）、16 分が 1 つの形に偏っていないか。手元にコーパスがあれば `uv run python tests/eval/sdvxin_patterns.py --chart out/work/chart.kson` で同じ集計が出る。

### 5. 仕上げ

- 完成した `chart.kson` を音源と同じフォルダに置く（`audio:` は相対ファイル名）。
- 再生して確認・共有する場合: `uv run ksmauto preview out/work/draft.ksmd -o out/work/preview.html`（vendored KSM-WEB-VIEWER のページに音源と譜面を埋め込む。1 ファイルで開ける）。preview ファイルなしで開くなら https://watanuki-azuma.github.io/KSM-WEB-VIEWER/ に譜面と音源（曲フォルダの zip でも可）を渡す（`viewer` コマンドはない）。
- 人が仕上げる場合: `uv run ksmauto edit out/work/chart.kson --audio SONG.ogg --analysis out/work/analysis.json` でブラウザエディタを開く（音源と同期再生・手で修正・保存）。
- FX ロング・レーザーの音のエフェクトと FX チップのキー音は DSL で書ける（`references/draft-format.md` の「オーディオエフェクト」、使い分けは `references/charting-guide.md` の「FX の使い方」）。preview で再生すると近似の音で確かめられる。
- カメラ、背景、エフェクトのパラメータ変化（`param_change`）は DSL の対象外。既存譜面を直す場合は `--base 元.kson` で compile すれば保持される。

## 既存譜面を読む・直す

```sh
uv run ksmauto decompile OLD.ksh -o out/work/old.ksmd      # 読みやすい DSL にする
# 編集して
uv run ksmauto compile out/work/old.ksmd --base OLD.ksh -o out/work/fixed.kson
```

参考にしたい譜面があるときは、同じレベル帯の譜面を decompile して配置を読む（どちらも手元専用。中身をリポジトリや成果物に写さない）:

- Lv16 以下: `corpus/official/` の公式譜面（`.ksh`）
- Lv17〜20: `corpus/sdvxin_full/<フォルダ>/<キー>/`（`meta.json` に曲名・レベル）。`uv run ksmauto sdvxin DIR -o out/work/ref.kson` で KSON に復元してから decompile する。オフセットは無いので配置の読み取り専用

## 参照

- `references/draft-format.md` — DSL の完全な仕様
- `references/charting-guide.md` — レベル別の密度表、音と配置の対応、配置の作法
- `references/example-draft.ksmd` — 音源解析だけから書いた全曲ドラフトの例（BPM180・CHALLENGE Lv12・lint 指摘なし）
- `docs/spec/kson_format.md`（リポジトリ内）— KSON 仕様
