# Draft 形式（LLM 向け中間 DSL）仕様 v0

LLM が譜面を書く・読むための行指向テキスト形式。拡張子 `.ksmd`。
`ksmauto compile draft.ksmd -o chart.kson` で KSON に、`ksmauto decompile chart.kson` で逆変換する。

設計意図:

- 小節と拍で位置を書く。pulse や KSH のグリッド行数を LLM に数えさせない。
- 1ノーツ ≒ 1トークン列に収まる密度。長い曲でも出力が膨らみすぎない。
- 曲の繰り返し構造を `copy` で表現でき、同じ配置を何度も書かなくてよい。
- 逆変換（decompile）があるので、既存譜面を読ませて学ばせる・生成譜面を部分修正させることができる。

## 字句

- 1行1文。`#` 以降はコメント。空行は無視。
- トークンは空白区切り。ヘッダの値（`key: value`）だけは行末までを値とする（ダブルクォートで囲んでもよい）。

## 位置

- **小節番号は 0 始まり**（KSON の measure index と同じ）。
- **拍は小節内の 0 始まりの拍位置**。拍の長さは拍子の分母で決まる（4/4 なら四分音符、6/8 なら八分音符）。
- 拍の書き方: 整数 `2`、小数 `1.5`、分数 `3/4`、帯分数 `2+1/3`（三連符などに使う）。
- 絶対位置: `m12:2.5`（12小節目の 2.5 拍）。
- 1拍 = `240 * 4 / 分母` pulse。位置は最も近い整数 pulse に丸める（4/4 なら 1/240 拍単位。1/7 拍なども近似して受理する）。

## ヘッダ（最初の `@m` より前）

```
title: Gram
artist: Blast Smith
chart_author: ksmauto
difficulty: 2          # 0:light 1:challenge 2:extended 3:infinite
level: 16
jacket: gram.jpg
audio: Gram.ogg
offset: 0              # ms。KSON audio.bgm.offset（pulse 0 が音源の何 ms 目か）
volume: 1.0
preview: 59050 12573   # 開始 ms, 長さ ms
bpm: 191               # 曲頭の BPM
time_sig: 4/4          # 曲頭の拍子
disp_bpm: 191          # 省略時は BPM 変化から自動計算
```

`title` `bpm` は必須。他は省略可（KSON の既定値になる）。

## 本体

### 小節カーソル

```
@m12                 # 以降の行は 12 小節目
@m12 "chorus 1"      # ラベルつき（KSON editor.comment に入る）
```

ラベルは1小節に1つ。decompile は同じ小節に複数のコメントがあると先頭だけを出力して警告する（`--base` で compile すれば元のコメントは保持される）。

### テンポ・拍子

```
@m20
bpm 0 200            # 20小節目 0拍で BPM 200
time_sig 7/8         # 20小節目から 7/8（必ず小節頭）
```

解析で `0:140,11:190` ならヘッダは `bpm: 140`、本体は `@m11` の次に `bpm 0 190`。小節番号は 0 始まり。

### ボタンノーツ

レーン名: BT は `A B C D`、FX は `L R`（左 FX / 右 FX）。

```
0     A              # BT-A チップ
0     B C            # 同時押し（BT-B と BT-C）
1/2   L              # FX-L チップ
1     D~2            # BT-D ロング、長さ 2 拍
2     R~m14:0        # FX-R ロング、m14:0 まで
3     A B~1/2 R      # 1行に混在してよい
```

`~` の後は相対長（拍）または絶対位置（`m..:..`）。

### レーザー

レーン名: `l`（左・青）、`r`（右・赤）。2倍幅は `l2` / `r2`。値は 0.0（左端）〜 1.0（右端）。

```
0   l 0 +2:1 +1:1>0 +1/2:0.5
```

- 最初のトークンが始点の値。以降の `+dt:value` は前の点から `dt` 拍後の点。
- `v>vf` は直角（その位置で v から vf へ瞬時に変化）。
- 直角だけの単独レーザーは `0 l 0>1`（KSON 上は 1 点のセクション）。
- 1行で 1 セクション。同じレーンのセクションは重なってはいけない。

### オーディオエフェクト

FX ロング・レーザーにかかる音のエフェクトと、FX チップの打鍵音（キー音）。KSM の組み込み名をそのまま使う。

```
def fx slowstop tapestop speed=20%     # 独自のエフェクト定義（どこに書いてもよい。名前 種類 パラメータ）
def laser lpf2 low_pass_filter v=0%-80%

@m8
0 L~2@gate(wave_length=1/16)           # FX ロングにエフェクト（括弧内はこのノーツだけのパラメータ）
0 R~4@bitcrusher(reduction=10samples)
2 L@clap(vol=0.6)                      # FX チップにキー音（パラメータは vol だけ）
2 fx_effect L@retrigger(wave_length=1/8)   # ロングの途中でエフェクトを切り替える
3 R~1@slowstop
3 L~1@-                                # エフェクトなし
0 laser_effect low_pass_filter         # この位置からレーザーのエフェクトを切り替える（既定は peaking_filter）
```

- FX の組み込み: `retrigger` `gate` `flanger` `pitch_shift` `bitcrusher` `phaser` `wobble` `tapestop` `echo` `sidechain`。
  `retrigger` `gate` `wobble` は `wave_length` を指定しないと何も起きない（既定値 0）。
- レーザーの組み込み: `peaking_filter` `high_pass_filter` `low_pass_filter` `bitcrusher`。
- キー音の組み込み: `clap` `clap_impact` `clap_punchy` `snare` `snare_lo`（音源と同じフォルダのファイル名も可）。
- パラメータの値は KSON と同じ書式（`1/16`、`30%`、`10samples`、`Off>OnMin-OnMax` など）。
- `copy` / `mirror` はエフェクト・キー音も一緒に写す。
- `--base` で compile したときは、ドラフトに書いた `def` / `long_event` / `pulse_event` / `chip_event` で置き換え、それ以外（`param_change` など）は元のまま残す。

### コピー

```
copy m8-11 -> m24              # 8〜11 小節目の全ノーツを 24 小節目以降へ
copy m8-11 -> m24 mirror       # 左右反転（A↔D, B↔C, L↔R, l↔r と値 v→1-v）
copy m8:2-m9:0 -> m30:2        # 拍単位の範囲
copy m8 -> m9                  # 1小節だけ
```

コピー元とコピー先の小節長が異なる場合はエラー。コピーは記述順に展開され、後に書いたノーツと重なればエラー。

## エラー報告

`compile` はエラーに行番号・列・理由を付けて全件出す（最初の1件で止めない）。LLM が一度に直せるようにするため。

## 例

```
title: Example
bpm: 150
offset: 120
level: 10

@m0 "intro"
@m1
0 A
1 B
2 C
3 D
@m2
0 l 0 +4:1
0 A C
2 B D
@m3
copy m1-2 -> m3 mirror
```

## 関連コマンド

`.ksmd` は `lint` / `stats` / `render` にもそのまま渡せる（内部で compile する）。

```sh
ksmauto compile draft.ksmd -o chart.kson [--base original.kson]
ksmauto decompile chart.kson -o draft.ksmd
ksmauto lint draft.ksmd --analysis analysis.json
ksmauto stats draft.ksmd
ksmauto render draft.ksmd --measures 16-47 -o page.png
```
