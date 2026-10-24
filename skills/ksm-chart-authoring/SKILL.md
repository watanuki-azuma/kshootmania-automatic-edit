---
name: ksm-chart-authoring
description: K-Shoot MANIA の譜面（KSON）を音源から作る・既存譜面（KSH/KSON）を読んで直す。音源解析 → 中間DSL（.ksmd）で作譜 → コンパイル → lint・難易度推定・画像で自己確認 → 修正、のループを ksmauto CLI で回す。「この曲の譜面を作って」「レベル12くらいで」「ksh を直して」「譜面をレビューして」などで使う。
---

# K-Shoot MANIA 譜面作成

ツールはこのリポジトリの `ksmauto` CLI（`uv run ksmauto ...`）。初回は `uv sync --extra audio --extra render`。

## 手順

### 1. 音源を解析する

```sh
uv run ksmauto separate SONG.ogg -o work/stems     # 音源分離（stems extra = demucs が必要）
uv run ksmauto analyze SONG.ogg --stems work/stems -o work/analysis.json --text work/analysis.txt
```

ピアノが主役の区間がある曲は 6 ステムに分けてピアノを採譜する（`plane` 列が増える。`other` から拾うより音程・発音ともずっと正確）:

```sh
uv run ksmauto separate SONG.ogg -o work/stems --model htdemucs_6s
uv run ksmauto transcribe work/stems/piano.wav      # transcribe extra が必要。work/stems/piano.notes.json を書く
uv run ksmauto analyze SONG.ogg --stems work/stems -o work/analysis.json --text work/analysis.txt
```

`transcribe` が「not installed」で止まるときは飛ばしてよい（`plane` は音から取った精度の低いものになる）。

demucs が入っていない（`separate` が「demucs is not installed」で止まる）ときは分離を飛ばし、`--stems` なしで解析する:

```sh
uv run ksmauto analyze SONG.ogg -o work/analysis.json --text work/analysis.txt
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
- BPM の信頼度（conf）が低い、候補が割れている → 候補の倍・半分を疑う。曲のノリ（体感テンポ）が 120〜240 に入る方を取る。
- **途中でテンポが変わる曲**: 解析は一定テンポを仮定する。ある小節から先でグリッドの `X` が拍頭から一様にずれていく（裏拍や 3 連グリッドばかりになる）ならテンポ変化を疑い、キックの間隔からテンポを測って `uv run ksmauto analyze SONG --tempo 0:141,53:138.2,63:141 --offset 1074 ...` で解析し直す。ドラフトにも同じ位置に `bpm 0 138.2` を書く。
- **小節の頭がずれていることがある**（拍は合っているが 1〜3 拍ずれる）。`low` の `X` が拍頭に揃い、セクション境界が 4・8 小節の区切りに来るように offset を `+ n * 60000/BPM` ms 調整する。

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
- 小節頭に左右同時の直角を置いたら、その瞬間のボタンは避ける（`hand-overload` になる）。

### 4. コンパイルと自己確認

```sh
uv run ksmauto compile work/draft.ksmd -o work/chart.kson
uv run ksmauto lint work/draft.ksmd --analysis work/analysis.json
uv run ksmauto stats work/draft.ksmd
uv run ksmauto render work/draft.ksmd --measures 0-31 -o work/page.png
```

- compile エラーは全件まとめて出る。行番号の箇所を直す。
- lint: `hand-overload`（手が 3 本要る）、`fast-jack`（縦連が速すぎ）は原則ゼロにする。`unaligned` が出たら、音の無い位置のノーツを解析と照合して直す。`empty-loud` は意図した休憩でなければ埋める。
- `thin`（歌っているのにボタンが薄い）は「楽器別の型」のボーカルの型で埋めるか、休符だと伝わる締めと入りを作る。
- stats の `level_estimate` が目標 ±1.5 に入るまで密度を調整する。
- render の PNG を開いて目で見る: 同じ形の繰り返しが単調すぎないか、レーザーとボタンが同じ手に重なっていないか、山場で密度が上がっているか。
- FX の使い方を「FX の使い方」の表と比べる: FX チップが BT のついでばかりになっていないか、FX ロング（短いもの）と L+R 同時があるか。
- 配置の偏りを `references/charting-guide.md` の「配置パターン」と比べる。レーザー中の空き手が C/D だけになっていないか（実譜面では FX-R と B が合わせて 3 割強）、16 分が 1 つの形に偏っていないか。手元にコーパスがあれば `uv run python tests/eval/sdvxin_patterns.py --chart work/chart.kson` で同じ集計が出る。

### 5. 仕上げ

- 完成した `chart.kson` を音源と同じフォルダに置く（`audio:` は相対ファイル名）。
- 再生して確認・共有する場合: `uv run ksmauto preview work/draft.ksmd -o work/preview.html`（音源は `audio:` から自動で埋め込む。1 ファイルで開ける）。
- 人が仕上げる場合: `uv run ksmauto edit work/chart.kson --audio SONG.ogg --analysis work/analysis.json` でブラウザエディタを開く（音源と同期再生・手で修正・保存）。
- FX ロング・レーザーの音のエフェクトと FX チップのキー音は DSL で書ける（`references/draft-format.md` の「オーディオエフェクト」、使い分けは `references/charting-guide.md` の「FX の使い方」）。preview で再生すると近似の音で確かめられる。
- カメラ、背景、エフェクトのパラメータ変化（`param_change`）は DSL の対象外。既存譜面を直す場合は `--base 元.kson` で compile すれば保持される。

## 既存譜面を読む・直す

```sh
uv run ksmauto decompile OLD.ksh -o work/old.ksmd      # 読みやすい DSL にする
# 編集して
uv run ksmauto compile work/old.ksmd --base OLD.ksh -o work/fixed.kson
```

参考にしたい譜面があるときは、同じレベル帯の譜面を decompile して配置を読む（どちらも手元専用。中身をリポジトリや成果物に写さない）:

- Lv16 以下: `corpus/official/` の公式譜面（`.ksh`）
- Lv17〜20: `corpus/sdvxin_full/<フォルダ>/<キー>/`（`meta.json` に曲名・レベル）。`uv run ksmauto sdvxin DIR -o work/ref.kson` で KSON に復元してから decompile する。オフセットは無いので配置の読み取り専用

## 参照

- `references/draft-format.md` — DSL の完全な仕様
- `references/charting-guide.md` — レベル別の密度表、音と配置の対応、配置の作法
- `references/example-draft.ksmd` — 音源解析だけから書いた全曲ドラフトの例（BPM180・CHALLENGE Lv12・lint 指摘なし）
- `docs/spec/kson_format.md`（リポジトリ内）— KSON 仕様
