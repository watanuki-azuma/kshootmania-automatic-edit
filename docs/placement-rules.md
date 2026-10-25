# 公式譜面の配置採掘（phase 1 + 2）

## lint に反映した規則

- 開始＋保持のボタン最小手数を span-3 の窓 A–C / B–D と、その下の FX （FX-L は A/B、FX-R は C/D）で計算する。開始／保持・正確なレーン集合はキーに入れない。キーは強い側を左にしたつまみ需要・ボタン手数・crossing。crossing は需要の軽い側の手で押すために自側の窓を越える場合。このモデルは全6ボタンを2手で覆え、A+D+両FXも2手（3手以上にする追加制約は未指定）。
- 実効手数＝ボタン手数＋slam/steep 各1＋gentle/ending 各0.5。2以下は頻度検査をしない。2超で全公式群（KSM含む）未観測なら `hand-impossible` warning、対象群で0.05/100小節未満なら `hand-rare` info。
- レーザーの phase 2 定義を維持: slam は前30〜後31 pulse未満、ending は連続移動終点まで50 ms以内、steep は32通常幅/秒超、その他の移動はgentle、静止・無しはstill。slam→ending→steepの順に優先。速度は局所BPM・幅・曲線の微分を使い、傾斜途中の点は移動終点にしない。
- `fast-jack`（両手）／`fast-jack-one-hand`（片手・mixed・assisted）: 群・BT/FX別の従来p1未満をinfo。同群の5譜面以上で観測された最短帯の下端未満だけwarning。帯は <60 / 60–70 / 70–80 / 80–90 / 90–100 / 100–120 / 120 ms以上。assistedは反対手の占有がgentle/endingのみ、mixedは片手分布へ合算。
- `placement_verdicts.json` のカテゴリ／ジャック行キーに人手判断があれば優先する。`allow` は抑制、`forbid` は `placement-forbidden` warning、`{"min_level": x}` はx未満で `placement-min-level` warning、x以上なら抑制（xは群で比較し、18は17.5以上）。ジャック行は `{"warn_ms": x, "info_ms": y}` で閾値を置き換える（null はその段階なし）。初期値は空。
- 群: 17〜17.4→17、17.5〜18.9→18、19以上→19-20、17未満→ksm。別群へのフォールバックはしない。欠測のジャック閾値は判定しない。
- `short-long` warning（1/8拍未満）と音源指定時の after-audio / unaligned / empty-loud / thin は維持。

全34カテゴリ、実効手数>2は20カテゴリ。集計値のみのパッケージ表は `src/ksmauto/data/hand_categories.json`。群別の件数・譜面数・頻度と各群最大3例、およびジャックp1は [placement-review.md](placement-review.md)。

### コーパスでの実行結果

学習と同じコーパスへの再適用。出自によらず入力のmeta.levelで学習・検査の群を選ぶ。目標はwarning 0、info <1/100小節。手数規則と全lintを分けて示す。

| 群 | 手数 warning /100小節 | 手数 info /100小節 | 全 warning /100小節 | 全 info /100小節 |
|---|---:|---:|---:|---:|
| 17 | 0.14620 | 0.00000 | 0.24765 | 6.62092 |
| 18 | 0.00000 | 0.00000 | 0.27396 | 7.16836 |
| 19-20 | 0.00000 | 0.00000 | 0.19990 | 8.09143 |
| ksm | 0.00000 | 0.00000 | 0.54127 | 2.02977 |

目標未達の内訳（件数ではなく100小節あたり。頻度境界は目標に合わせて変更しない）:

| 群 | カテゴリ／既存規則 | warning /100小節 | info /100小節 |
|---|---|---:|---:|
| 17 | ending,ending&#124;2&#124;home | 0.10145 | 0.00000 |
| 17 | gentle,ending&#124;2&#124;home | 0.04177 | 0.00000 |
| 17 | jack:17:assisted:BT | 0.01193 | 0.52812 |
| 17 | jack:17:assisted:FX | 0.02089 | 0.08056 |
| 17 | jack:17:one-hand:BT | 0.00895 | 4.49649 |
| 17 | jack:17:one-hand:FX | 0.00298 | 0.99060 |
| 17 | jack:17:two-hand:BT | 0.02984 | 0.42966 |
| 17 | jack:17:two-hand:FX | 0.02685 | 0.09548 |
| 17 | slam,slam&#124;2&#124;home | 0.00298 | 0.00000 |
| 18 | jack:18:assisted:BT | 0.01385 | 0.51033 |
| 18 | jack:18:assisted:FX | 0.00198 | 0.10187 |
| 18 | jack:18:one-hand:BT | 0.17802 | 4.75814 |
| 18 | jack:18:one-hand:FX | 0.06330 | 1.03154 |
| 18 | jack:18:two-hand:BT | 0.00000 | 0.61121 |
| 18 | jack:18:two-hand:FX | 0.01681 | 0.15527 |
| 19-20 | jack:19-20:assisted:BT | 0.01738 | 0.53450 |
| 19-20 | jack:19-20:assisted:FX | 0.01304 | 0.10429 |
| 19-20 | jack:19-20:one-hand:BT | 0.00869 | 5.25813 |
| 19-20 | jack:19-20:one-hand:FX | 0.00435 | 1.20807 |
| 19-20 | jack:19-20:two-hand:BT | 0.00000 | 0.79524 |
| 19-20 | jack:19-20:two-hand:FX | 0.03042 | 0.19120 |
| 19-20 | short-long | 0.12602 | 0.00000 |
| ksm | jack:ksm:assisted:BT | 0.03383 | 0.00000 |
| ksm | jack:ksm:one-hand:BT | 0.30447 | 1.69147 |
| ksm | jack:ksm:one-hand:FX | 0.00000 | 0.03383 |
| ksm | jack:ksm:two-hand:BT | 0.16915 | 0.27064 |
| ksm | jack:ksm:two-hand:FX | 0.03383 | 0.03383 |

以下の phase 1 比較表は旧手数モデルも残す。現在の lint 規則は上節のとおり。左手＝L つまみ・FL・BT A/B、右手＝R つまみ・FR・BT C/D を基本とする。つまみの「操作中」は `lint._moving_laser_ranges`（傾斜、直角の前30〜後31 pulse未満）。自側 long の保持も手を占有する。片つまみ中は空いた手が全レーンを担当できるが、同時押しの必要手数は `_legacy_hands_for_buttons`（隣接2位置、FL は B、FR は C の位置）による。

ジャックは基本の担当手を用い、その手が全区間つまみ中かつ反対つまみが空なら担当を反転する。反対手の連続占有が区間全体を覆えば片手、占有も区間途中の自側打鍵もなければ両手。gentle/endingのみの占有はassisted、部分占有・途中の自側打鍵だけはmixed。lintではmixedを片手へ合算する。実運指は断定しない。

小節は `TimingMap` の **0 始まり**。分母は pulse 0 から最後のボタン終端／レーザー端を含む小節まで（空小節も含む）。時間は BPM 変化を積分し、音源 offset は用いない。占有区間は半開区間。hold-and-chip と組合せ表の保持判定だけは保持開始の同時刻も除く。1 拍＝240 pulse。grid の 1/16・1/12 は全音符基準（60・80 pulse）、「1/16 拍後」は15 pulse、「1/8 拍未満」は30 pulse と区別する。

判定は全群で0なら **never**、それ以外は各群で100小節あたり1未満 **または** 出現譜面率5%未満なら **rare**、残りは **common**。ある群だけ0の場合は rare。これは出現頻度の仮判定であり、許可／禁止の結論ではない。間隔に上限を置かないため、jack の common は高速連打の許容を意味しない。

表の頻度＝「出現数 / 該当譜面数（%） / 100小節あたり」。間隔の分布＝[min/p0.1/p1/p5/p50] ms、長さ＝[max/p99/p99.9]、譜面別最大密度・stream16・最長trill＝[p50/p99/max]。分位点は線形補間。

| 群 | 譜面数 | 小節数 | レベル（譜面数） |
|---|---:|---:|---|
| 17 | 371 | 33,515 | 17.0: 370、17: 1 |
| 18 | 1035 | 101,111 | 17.5: 362、18.0: 32、18: 1、18.1: 61、18.2: 80、18.3: 102、18.4: 104、18.5: 102、18.6: 90、18.7: 57、18.8: 37、18.9: 7 |
| 19-20 | 204 | 23,012 | 19.0: 11、19: 1、19.1: 20、19.2: 26、19.3: 24、19.4: 28、19.5: 18、19.6: 20、19.7: 18、19.8: 4、19.9: 3、20.0: 3、20.1: 1、20.2: 6、20.3: 4、20.4: 1、20.5: 3、20.6: 8、20.7: 2、20.8: 1、20.9: 2 |
| ksm | 33 | 2,956 | 3: 2、4: 3、5: 2、6: 2、7: 1、9: 3、10: 3、11: 2、12: 2、13: 2、14: 4、15: 4、16: 3 |

SDVX: 1706 統計行中 usable 不適合 99（元 decode エラー 5 を含む）。採掘時エラー／欠落 0 件。曲線レーザー採用 5 譜面。usable は chip 数・最高 BPM の検査であり、レーザー・long の転記精度までは保証しない。KSM も meta.level で同じ群に集計する。

再現: `uv run python tests/eval/placement_rules.py`。入力のサイズ・mtime、コード、メタ情報が変わるとキャッシュを無効化する。全形状・レーン内訳・群ごと最大5例は `out/placement_rules.json`、譜面別キャッシュは `out/placement_rules_cache.jsonl`（どちらもローカル専用）。

## 1. hand-overload

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| hand-overload | 旧 lint 比較用、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 17 | 4,478 / 334 (90.0%) / 13.361 | —<br>cause:slam-padding-only: 4<br>cause:without-slam-padding: 4,474 | common |
| hand-overload | 旧 lint 比較用、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 18 | 16,321 / 976 (94.3%) / 16.142 | —<br>cause:slam-padding-only: 53<br>cause:without-slam-padding: 16,268 | common |
| hand-overload | 旧 lint 比較用、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 19-20 | 5,453 / 201 (98.5%) / 23.696 | —<br>cause:slam-padding-only: 37<br>cause:without-slam-padding: 5,416 | common |
| hand-overload | 旧 lint 比較用、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | ksm | 9 / 4 (12.1%) / 0.304 | —<br>cause:without-slam-padding: 9 | rare |

例: 「TYCOON」m39、「ALBIDA Powerless Mix」m37、「Ganymede kamome mix」m4

## 2. jack-two-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 17 | 20,360 / 370 (99.7%) / 60.749 | BT_interval_ms [66.667/71.429/83.333/100/180.18]<br>FX_interval_ms [65.217/68.182/80.214/100/191.083]<br><75ms: 42 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 18 | 81,036 / 1034 (99.9%) / 80.146 | BT_interval_ms [22.523/33.784/73.171/85.47/161.29]<br>FX_interval_ms [16.892/62.5/75.992/90.909/170.455]<br><75ms: 935 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 19-20 | 23,716 / 204 (100.0%) / 103.059 | BT_interval_ms [47.17/50.251/64.103/73.171/136.364]<br>FX_interval_ms [45.455/56.818/67.568/78.947/142.857]<br><75ms: 1,199 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | ksm | 1,842 / 32 (97.0%) / 62.314 | BT_interval_ms [96.774/96.774/157.068/166.667/329.67]<br>FX_interval_ms [105.634/109.518/147.536/157.068/290.323]<br><75ms: 0 | common |

例: 「Circuit Surfer」m29、「Demetel (Erixa ”MYTH” Remix)」m22、「君は Fantasista」m68

## 3. jack-one-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| jack-one-hand | 反対手が全区間占有。lint閾値ではmixedも含める | 17 | 13,020 / 369 (99.5%) / 38.848 | BT_interval_ms [64.935/88.235/105.263/136.364/300]<br>FX_interval_ms [78.947/81.659/112.5/149.254/322.581]<br><75ms: 1 | common |
| jack-one-hand | 反対手が全区間占有。lint閾値ではmixedも含める | 18 | 46,521 / 1030 (99.5%) / 46.01 | BT_interval_ms [33.784/75/92.025/115.385/255.319]<br>FX_interval_ms [7.508/81.081/94.937/129.87/298.507]<br><75ms: 40 | common |
| jack-one-hand | 反対手が全区間占有。lint閾値ではmixedも含める | 19-20 | 13,413 / 203 (99.5%) / 58.287 | BT_interval_ms [62.5/62.5/81.081/107.143/217.391]<br>FX_interval_ms [72.115/76.306/90.361/109.091/260.87]<br><75ms: 45 | common |
| jack-one-hand | 反対手が全区間占有。lint閾値ではmixedも含める | ksm | 475 / 22 (66.7%) / 16.069 | BT_interval_ms [104.712/104.712/117.647/166.667/333.333]<br>FX_interval_ms [157.068/157.068/157.068/157.068/176.471]<br><75ms: 0 | common |

例: 「Sephirot」m42、「Inscape」m27、「孤月群雲に沈む」m45

## 4. jack-assisted

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| jack-assisted | 反対手の占有がgentle/endingのみの反復（別分布） | 17 | 21,563 / 371 (100.0%) / 64.338 | BT_interval_ms [78.947/88.235/118.11/150/392.157]<br>FX_interval_ms [85.714/87.209/115.385/150/572.338] | common |
| jack-assisted | 反対手の占有がgentle/endingのみの反復（別分布） | 18 | 65,114 / 1030 (99.5%) / 64.399 | BT_interval_ms [33.784/76.923/101.351/138.889/333.333]<br>FX_interval_ms [65.217/80.781/100/136.364/382.816] | common |
| jack-assisted | 反対手の占有がgentle/endingのみの反復（別分布） | 19-20 | 16,215 / 203 (99.5%) / 70.463 | BT_interval_ms [57.252/70.62/82.418/113.208/285.714]<br>FX_interval_ms [43.478/72.89/90.09/108.696/285.714] | common |
| jack-assisted | 反対手の占有がgentle/endingのみの反復（別分布） | ksm | 894 / 29 (87.9%) / 30.244 | BT_interval_ms [96.774/142.296/157.068/176.213/471.204]<br>FX_interval_ms [129.032/129.032/129.032/157.068/477.538] | common |

例: 「β」m91、「Re:Rose Gun Shoooot!」m72、「Next infection」m37

## 5. trill-one-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 17 | 5,257 / 365 (98.4%) / 15.686 | run_hits [19/9/16]<br>hit_interval_ms [36.496/55.855/68.182/75/142.857]<br>chart_longest_run_hits [5/16.3/19] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 18 | 17,287 / 1021 (98.6%) / 17.097 | run_hits [30/11/16]<br>hit_interval_ms [16.892/42.007/58.658/68.493/100]<br>chart_longest_run_hits [6/16.66/30] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 19-20 | 4,256 / 203 (99.5%) / 18.495 | run_hits [47/11/21.215]<br>hit_interval_ms [21.739/33.333/46.584/55.556/84.746]<br>chart_longest_run_hits [7/23/47] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | ksm | 164 / 16 (48.5%) / 5.548 | run_hits [12/7/11.185]<br>hit_interval_ms [78.534/78.534/78.534/78.534/166.667]<br>chart_longest_run_hits [0/10.4/12] | common |

例: 「Re*harpoon」m3、「Game Over」m24、「Melty Sweets」m65

## 6. stream-density

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 17 | 371 / 371 (100.0%) / 1.107 | peak_1s_nps [12/17/18]<br>peak_4s_nps [9.25/13.75/14.75]<br>stream16_max_sec [1.42/9.86/12.61] | common |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 18 | 1,035 / 1035 (100.0%) / 1.024 | peak_1s_nps [14/22/54]<br>peak_4s_nps [11.25/15.75/47.5]<br>stream16_max_sec [2.07/11.249/13.26] | common |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 19-20 | 204 / 204 (100.0%) / 0.886 | peak_1s_nps [18/26.97/28]<br>peak_4s_nps [13.75/19.985/20.5]<br>stream16_max_sec [2.505/15.327/35.63] | rare |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | ksm | 33 / 33 (100.0%) / 1.116 | peak_1s_nps [7/13/13]<br>peak_4s_nps [5.5/10/10]<br>stream16_max_sec [0.11/2.702/3.16] | common |

例: 「ロマンシングエスケープ」m2、「Sephirot」m71、「cross the future」m58

## 7. chord-shapes

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 17 | 215,751 / 371 (100.0%) / 643.745 | —<br>free:flag:3plus-BT: 681<br>free:flag:4-BT: 289<br>free:flag:FX+two-home-BT: 42<br>free:flag:same-side-BT-FX: 4,779<br>knob:flag:3plus-BT: 34<br>knob:flag:4-BT: 3<br>knob:flag:FX+two-home-BT: 2<br>knob:flag:same-side-BT-FX: 1,254 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 18 | 695,513 / 1035 (100.0%) / 687.871 | —<br>free:flag:3plus-BT: 3,438<br>free:flag:4-BT: 1,327<br>free:flag:FX+two-home-BT: 220<br>free:flag:same-side-BT-FX: 18,853<br>knob:flag:3plus-BT: 431<br>knob:flag:4-BT: 29<br>knob:flag:FX+two-home-BT: 45<br>knob:flag:same-side-BT-FX: 4,280 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 19-20 | 172,902 / 204 (100.0%) / 751.356 | —<br>free:flag:3plus-BT: 1,389<br>free:flag:4-BT: 403<br>free:flag:FX+two-home-BT: 281<br>free:flag:same-side-BT-FX: 6,350<br>knob:flag:3plus-BT: 250<br>knob:flag:4-BT: 16<br>knob:flag:FX+two-home-BT: 56<br>knob:flag:same-side-BT-FX: 1,267 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | ksm | 9,969 / 33 (100.0%) / 337.246 | —<br>free:flag:3plus-BT: 30<br>free:flag:4-BT: 6<br>free:flag:FX+two-home-BT: 7<br>free:flag:same-side-BT-FX: 62<br>knob:flag:FX+two-home-BT: 3<br>knob:flag:same-side-BT-FX: 12 | common |

例: 「cloud」m0、「TYCOON」m0、「ALBIDA Powerless Mix」m0

## 8. knob-crossing-press

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 17 | 4,468 / 357 (96.2%) / 13.331 | —<br>A: 1,154<br>FL: 3,314 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 18 | 18,486 / 1020 (98.6%) / 18.283 | —<br>A: 5,839<br>FL: 12,647 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 19-20 | 5,637 / 202 (99.0%) / 24.496 | —<br>A: 1,899<br>FL: 3,738 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | ksm | 89 / 11 (33.3%) / 3.011 | —<br>A: 16<br>FL: 73 | common |

例: 「cloud」m9、「ALBIDA Powerless Mix」m37、「good high school」m8

## 9. both-knobs-and-button

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 17 | 3,271 / 300 (80.9%) / 9.76 | —<br>lane:A: 566<br>lane:B: 1,120<br>lane:C: 1,001<br>lane:D: 453<br>lane:FL: 595<br>lane:FR: 551 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 18 | 11,518 / 886 (85.6%) / 11.391 | —<br>lane:A: 1,915<br>lane:B: 3,630<br>lane:C: 3,455<br>lane:D: 1,613<br>lane:FL: 2,110<br>lane:FR: 2,082 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 19-20 | 3,913 / 190 (93.1%) / 17.004 | —<br>lane:A: 634<br>lane:B: 1,157<br>lane:C: 1,155<br>lane:D: 587<br>lane:FL: 797<br>lane:FR: 807 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「天ノ弱」m34、「レトロスペクティビリー・メリーゴーランド」m52、「good high school」m37

## 10. slam-with-button

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 17 | 24,083 / 371 (100.0%) / 71.857 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 18 | 72,761 / 1032 (99.7%) / 71.962 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 19-20 | 18,396 / 203 (99.5%) / 79.941 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | ksm | 314 / 20 (60.6%) / 10.622 | — | common |

例: 「cloud」m0、「TYCOON」m7、「ALBIDA Powerless Mix」m5

## 11. slam-interval

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 17 | 44,943 / 371 (100.0%) / 134.098 | interval_ms [25/48.428/75/114.504/666.667]<br>section_start_ms [0/0/0/0/0]<br>短間隔除外: 41<br>開始後<15pulse: 16,373 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 18 | 142,455 / 1031 (99.6%) / 140.89 | interval_ms [16.892/40.541/70.922/95.238/532.544]<br>section_start_ms [0/0/0/0/0]<br>短間隔除外: 365<br>開始後<15pulse: 46,748 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 19-20 | 35,217 / 203 (99.5%) / 153.038 | interval_ms [26.596/36.9/62.5/82.418/450]<br>section_start_ms [0/0/0/0/0]<br>短間隔除外: 69<br>開始後<15pulse: 10,853 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | ksm | 1,291 / 31 (93.9%) / 43.674 | interval_ms [88.235/88.235/88.235/165.751/1,588.235]<br>section_start_ms [0/0/0/0/0]<br>短間隔除外: 0<br>開始後<15pulse: 470 | common |

例: 「Lucky*Clover」m90、「君は Fantasista」m40、「ARISE」m97

## 12. laser-zigzag

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 17 | 17,686 / 371 (100.0%) / 52.77 | reversal_interval_ms [7.508/9.058/11.871/17.689/198.529]<br>chart_min_reversal_ms [7.508/7.884/9.711/11.333/19.381]<br>短反転除外: 23,128 | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 18 | 54,994 / 1032 (99.7%) / 54.39 | reversal_interval_ms [2.815/6.522/9.294/13.853/162.162]<br>chart_min_reversal_ms [2.815/5.01/7.788/9.294/17.241]<br>短反転除外: 73,548 | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 19-20 | 12,233 / 203 (99.5%) / 53.159 | reversal_interval_ms [5.01/5.01/7.508/9.804/105.21]<br>chart_min_reversal_ms [5.01/5.05/7.508/8.741/12.5]<br>短反転除外: 17,929 | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | ksm | 1,093 / 33 (100.0%) / 36.976 | reversal_interval_ms [157.068/157.068/157.068/176.471/352.941]<br>chart_min_reversal_ms [157.068/157.068/157.068/160.175/350.877]<br>短反転除外: 0 | common |

例: 「cloud」m4、「TYCOON」m28、「ALBIDA Powerless Mix」m22

## 13. laser-crossing

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 17 | 8,014 / 370 (99.7%) / 23.912 | duration_ms [8,302.326/2,280.702/4,684.505]<br>合計 2,240.277秒、開始 6,318時刻/7,979ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 18 | 26,509 / 1029 (99.4%) / 26.218 | duration_ms [613,861.299/2,480.196/5,342.198]<br>合計 8,046.28秒、開始 27,085時刻/34,386ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 19-20 | 6,705 / 203 (99.5%) / 29.137 | duration_ms [10,378.378/2,571.203/4,911.726]<br>合計 1,736.688秒、開始 9,135時刻/12,068ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | ksm | 217 / 24 (72.7%) / 7.341 | duration_ms [6,760.563/3,006.765/6,148.449]<br>合計 122.105秒、開始 123時刻/152ボタン | common |

例: 「LittleGameStar」m2、「キリカ」m95、「星の詩」m20

## 14. laser-gap

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 17 | 17,221 / 371 (100.0%) / 51.383 | gap_ms [36.496/47.792/112.5/200/1,363.636] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 18 | 49,167 / 1032 (99.7%) / 48.627 | gap_ms [22.059/39.474/86.207/187.5/1,186.047] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 19-20 | 11,398 / 203 (99.5%) / 49.531 | gap_ms [21.368/21.368/61.345/151.654/1,019.022] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | ksm | 525 / 33 (100.0%) / 17.76 | gap_ms [83.333/83.333/83.333/505.882/3,096.774] | common |

例: 「Pixelated Platform」m60、「Ö<3rf10₩」m37、「革命パッショネイト」m5

## 15. hold-and-chip

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 17 | 16,147 / 367 (98.9%) / 48.178 | —<br>leave: 1029 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 18 | 55,588 / 1020 (98.6%) / 54.977 | —<br>leave: 3943 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 19-20 | 15,640 / 203 (99.5%) / 67.965 | —<br>leave: 1450 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | ksm | 641 / 17 (51.5%) / 21.685 | —<br>leave: 37 | common |

例: 「TYCOON」m23、「天ノ弱」m89、「レトロスペクティビリー・メリーゴーランド」m5

## 16. long-end-to-chip

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 17 | 23,654 / 369 (99.5%) / 70.577 | interval_ms [64.935/78.125/136.364/175.439/693.642]<br><75ms: 16 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 18 | 66,524 / 1028 (99.3%) / 65.793 | interval_ms [16.892/69.444/101.351/156.25/611.111]<br><75ms: 109 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 19-20 | 15,226 / 203 (99.5%) / 66.165 | interval_ms [43.478/63.682/81.081/136.364/510.638]<br><75ms: 104 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | ksm | 461 / 28 (84.8%) / 15.595 | interval_ms [105.634/129.294/157.068/211.268/1,166.667]<br><75ms: 0 | common |

例: 「Sephirot」m42、「Circuit Surfer」m29、「Demetel (Erixa ”MYTH” Remix)」m22

## 17. short-long

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 17 | 0 / 0 (0.0%) / 0 | all_long_beats [25.375/6/12] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 18 | 0 / 0 (0.0%) / 0 | all_long_beats [40/7/15] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 19-20 | 29 / 4 (2.0%) / 0.126 | all_long_beats [48/8/16.5]<br>short_beats [0.083/0.083/0.083] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | ksm | 0 / 0 (0.0%) / 0 | all_long_beats [18/6.13/16.157] | rare |

例: 「色を喪った街」m37、「すべてが幻になった後で」m21、「色を喪った街」m38

## 18. offgrid

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 17 | 3,592 / 296 (79.8%) / 10.718 | —<br>1/24: 1,627<br>1/32: 397<br>1/48: 1,486<br>1/64: 50<br>1/96: 32 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 18 | 25,147 / 846 (81.7%) / 24.871 | —<br>1/24: 10,899<br>1/32: 5,567<br>1/48: 6,980<br>1/64: 1,366<br>1/96: 335 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 19-20 | 12,110 / 187 (91.7%) / 52.625 | —<br>1/24: 4,983<br>1/32: 3,100<br>1/48: 3,393<br>1/64: 511<br>1/96: 123 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「レトロスペクティビリー・メリーゴーランド」m9、「ALBIDA Powerless Mix」m1、「smooooch・∀・ KN mix」m17

## 19. fx-long-with-bt-chips

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 17 | 12,469 / 366 (98.7%) / 37.204 | —<br>100ボタン開始あたり 4.55 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 18 | 41,231 / 1019 (98.5%) / 40.778 | —<br>100ボタン開始あたり 4.598 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 19-20 | 10,065 / 203 (99.5%) / 43.738 | —<br>100ボタン開始あたり 4.383 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | ksm | 543 / 17 (51.5%) / 18.369 | —<br>100ボタン開始あたり 4.476 | common |

例: 「cloud」m21、「TYCOON」m4、「ALBIDA Powerless Mix」m8

## 20. button-during-slam-same-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 17 | 0 / 0 (0.0%) / 0 | — | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 18 | 2 / 1 (0.1%) / 0.002 | delay_ms [45.455/45.455/45.455/45.455/45.455] | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 19-20 | 2 / 2 (1.0%) / 0.009 | delay_ms [9.728/9.728/9.728/9.731/9.766] | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「Little Red Riding Hood」m21、「DEUX EX MĀXHINĀ」m101、「End to end」m117

## 21. wide-laser

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 17 | 6,745 / 337 (90.8%) / 20.125 | duration_ms [29,561.404/9,365.333/23,461.615] | common |
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 18 | 18,560 / 900 (87.0%) / 18.356 | duration_ms [49,406.25/10,808.066/20,422.865] | common |
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 19-20 | 5,036 / 189 (92.6%) / 21.884 | duration_ms [24,714.286/10,428.513/19,174.21] | common |
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「銃弾は解を撃ち抜いて」m44、「AYAKASHI」m48、「ヒミツダイヤル」m21

## 分類と読み方の補足

- trill は単独 chip の交互列が3打以上。担当手の他の開始・同時押し・担当側のつまみで切る。AB/CD は自側の手、BC はどちらの手でも調べる。間隔の上限は置かない。
- 密度窓は `(t−W,t]`、曲端でも W 秒で割る。stream16 は既存 `stats()` の値をそのまま用いる。
- 和音表は long 開始も含む。全形状はローカル JSON に保存。3+BT と4BT、同側BT+FXのフラグは重複する。片つまみ・直角は操作つまみを左に反転し、直角の向きも反転する。
- 交差は幅2を中心から2倍に拡大した表示座標で、線形補間の交点を解く。曲線は既存プレビューと同じ2次 Bézier。交点計算では表示位置誤差 1e-9 幅以内の折れ線へ細分化し、ボタン時刻の位置は曲線式で直接評価する。直角後の値も評価し、瞬間だけの交差は長さ0の区間とする。
- hold-and-chip は保持開始・終端と同時刻を除く。自側の他レーン、または反対手占有中に隣接2位置へ収まる組を reach、反対手占有中に2位置を超える組を leave とする。保持手の実際の持ち替えは推測しない。
- short-long は全 long の拍数分布と、30 pulse 未満だけの分布を併記する。offgrid の 1/N は `N=960/gcd(960,pulse)` の既約全音符分母（絶対 pulse 基準）。

jack-mixed（主表の2分類に入らない区間）:

| 群 | 出現数 | 譜面数 | 100小節あたり |
|---|---:|---:|---:|
| 17 | 176,815 | 371 | 527.57 |
| 18 | 583,686 | 1034 | 577.273 |
| 19-20 | 150,149 | 204 | 652.481 |
| ksm | 7,088 | 32 | 239.783 |

## 判断が割れそうなもの

- **hand-overload**: ほぼ0という予想に反して多い。直角前後の占有余白だけによる件数を主表で分離した（26,261件）。例: 「TYCOON」m39、「ALBIDA Powerless Mix」m37、「Ganymede kamome mix」m4。
- **jack-mixed**: 途中だけ占有される区間。lintでは保守的に片手へ合算（917,738件）。例: 「轟け！恋のビーンボール！！」m30、「INDEPENDENT SKY」m92、「惑星ループ (花芽すみれ Cover)」m42。
- **jack-one-hand**: 短い間隔でも担当手は推定。反対側つまみ・long の連続占有と実際の運指は区別したい（73,429件）。例: 「Sephirot」m42、「Inscape」m27、「孤月群雲に沈む」m45。
- **hold-and-chip**: leave は固定の保持手を仮定した結果で、持ち替え・つまみ余白の影響があり得る（6,459件）。例: 「TYCOON」m23、「天ノ弱」m89、「レトロスペクティビリー・メリーゴーランド」m5。
- **button-during-slam-same-hand**: 直角の直後にホーム側の開始があっても、反対手で拾う運指はあり得る（4件）。例: 「Little Red Riding Hood」m21、「DEUX EX MĀXHINĀ」m101、「End to end」m117。
- **laser-crossing**: 見た目の交差と手の交差は別。幅2・瞬間だけの交差も含む（41,445件）。例: 「LittleGameStar」m2、「キリカ」m95、「星の詩」m20。
- **short-long**: 1/8拍未満は高難度群だけに少数見つかる。最低値だけで禁止閾値を決めない（29件）。例: 「色を喪った街」m37、「すべてが幻になった後で」m21、「色を喪った街」m38。
- **stream-density**: 出現単位が譜面なので100小節あたりの機械判定は曲長に依存する。rareでも密度の配置が稀とはいえない（1,643件）。例: 「ロマンシングエスケープ」m2、「Sephirot」m71、「cross the future」m58。
