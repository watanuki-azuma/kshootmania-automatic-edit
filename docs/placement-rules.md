# 公式譜面の配置採掘（phase 1）

左手＝L つまみ・FL・BT A/B、右手＝R つまみ・FR・BT C/D を基本とする。つまみの「操作中」は `lint._moving_laser_ranges`（傾斜、直角の前30〜後31 pulse未満）。自側 long の保持も手を占有する。片つまみ中は空いた手が全レーンを担当できるが、同時押しの必要手数は `_hands_for_buttons`（隣接2位置、FL は B、FR は C の位置）による。

ジャックは基本の担当手を用い、その手が全区間つまみ中かつ反対つまみが空なら担当を反転する。反対手の連続占有が区間全体を覆えば片手、占有も区間途中の自側打鍵もなければ両手。部分的な占有・途中の自側打鍵だけのものは mixed として別集計する。実際の運指を断定するものではない。

小節は `TimingMap` の **0 始まり**。分母は pulse 0 から最後のボタン終端／レーザー端を含む小節まで（空小節も含む）。時間は BPM 変化を積分し、音源 offset は用いない。占有区間は半開区間。hold-and-chip と既存 lint の保持判定だけは保持開始の同時刻も除く。1 拍＝240 pulse。grid の 1/16・1/12 は全音符基準（60・80 pulse）、「1/16 拍後」は15 pulse、「1/8 拍未満」は30 pulse と区別する。

判定は全群で0なら **never**、それ以外は各群で100小節あたり1未満 **または** 出現譜面率5%未満なら **rare**、残りは **common**。ある群だけ0の場合は rare。これは出現頻度の仮判定であり、許可／禁止の結論ではない。間隔に上限を置かないため、jack の common は高速連打の許容を意味しない。

表の頻度＝「出現数 / 該当譜面数（%） / 100小節あたり」。間隔の分布＝[min/p0.1/p1/p5/p50] ms、長さ＝[max/p99/p99.9]、譜面別最大密度・stream16・最長trill＝[p50/p99/max]。分位点は線形補間。

| 群 | 譜面数 | 小節数 | レベル（譜面数） |
|---|---:|---:|---|
| 17 | 732 | 66,640 | 17.0: 370、17.5: 362 |
| 18 | 672 | 67,793 | 18.0: 32、18.1: 61、18.2: 80、18.3: 102、18.4: 104、18.5: 102、18.6: 90、18.7: 57、18.8: 37、18.9: 7 |
| 19-20 | 203 | 22,924 | 19.0: 11、19.1: 20、19.2: 26、19.3: 24、19.4: 28、19.5: 18、19.6: 20、19.7: 18、19.8: 4、19.9: 3、20.0: 3、20.1: 1、20.2: 6、20.3: 4、20.4: 1、20.5: 3、20.6: 8、20.7: 2、20.8: 1、20.9: 2 |
| ksm | 36 | 3,237 | 3: 2、4: 3、5: 2、6: 2、7: 1、9: 3、10: 3、11: 2、12: 2、13: 2、14: 4、15: 4、16: 3、17: 1、18: 1、19: 1 |

SDVX: 1706 統計行中 usable 不適合 99（元 decode エラー 5 を含む）。採掘時エラー／欠落 0 件。曲線レーザー採用 5 譜面。usable は chip 数・最高 BPM の検査であり、レーザー・long の転記精度までは保証しない。KSM は別群で集計する。

再現: `uv run python tests/eval/placement_rules.py`。入力のサイズ・mtime、コード、メタ情報が変わるとキャッシュを無効化する。全形状・レーン内訳・群ごと最大5例は `out/placement_rules.json`、譜面別キャッシュは `out/placement_rules_cache.jsonl`（どちらもローカル専用）。

## 1. hand-overload

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| hand-overload | 既存 lint と同じ、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 17 | 8,339 / 653 (89.2%) / 12.514 | —<br>cause:slam-padding-only: 15<br>cause:without-slam-padding: 8,324 | common |
| hand-overload | 既存 lint と同じ、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 18 | 12,458 / 656 (97.6%) / 18.377 | —<br>cause:slam-padding-only: 42<br>cause:without-slam-padding: 12,416 | common |
| hand-overload | 既存 lint と同じ、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | 19-20 | 5,453 / 201 (99.0%) / 23.787 | —<br>cause:slam-padding-only: 37<br>cause:without-slam-padding: 5,416 | common |
| hand-overload | 既存 lint と同じ、開始時刻のつまみ数＋保持中を含むボタン必要手数 > 2（時刻数） | ksm | 11 / 5 (13.9%) / 0.34 | —<br>cause:without-slam-padding: 11 | rare |

例: 「ALBIDA Powerless Mix」m37、「Broken 8cmix」m3、「Ganymede kamome mix」m4

## 2. jack-two-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 17 | 46,311 / 730 (99.7%) / 69.494 | BT_interval_ms [58.594/68.182/80.214/93.75/176.471]<br>FX_interval_ms [56.497/68.695/81.081/94.787/187.5]<br><75ms: 94 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 18 | 54,858 / 672 (100.0%) / 80.92 | BT_interval_ms [22.523/33.784/70.755/82.873/157.895]<br>FX_interval_ms [16.892/33.784/75/88.235/166.667]<br><75ms: 883 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | 19-20 | 23,579 / 203 (100.0%) / 102.857 | BT_interval_ms [47.17/50.251/64.103/73.171/136.364]<br>FX_interval_ms [45.455/56.818/67.568/78.947/142.857]<br><75ms: 1,199 | common |
| jack-two-hand | 同レーンの直前 chip／long 終端→chip。反対手が全区間自由（BT/FX 別、間隔上限なし） | ksm | 2,206 / 35 (97.2%) / 68.15 | BT_interval_ms [96.774/96.774/157.068/157.068/314.136]<br>FX_interval_ms [105.634/110.056/153.984/157.068/264.706]<br><75ms: 0 | common |

例: 「smooooch・∀・ KN mix」m44、「Garakuta Doll Play」m67、「Fly far bounce」m59

## 3. jack-one-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| jack-one-hand | 同じ反復で反対手が全区間、つまみまたは自側 long に占有されるもの | 17 | 35,092 / 729 (99.6%) / 52.659 | BT_interval_ms [64.935/81.081/100/130.435/274.39]<br>FX_interval_ms [78.534/81.081/93.75/141.509/315.789]<br><75ms: 3 | common |
| jack-one-hand | 同じ反復で反対手が全区間、つまみまたは自側 long に占有されるもの | 18 | 40,235 / 671 (99.9%) / 59.35 | BT_interval_ms [33.784/70.261/87.719/114.504/241.935]<br>FX_interval_ms [7.508/78.947/97.561/127.119/285.714]<br><75ms: 46 | common |
| jack-one-hand | 同じ反復で反対手が全区間、つまみまたは自側 long に占有されるもの | 19-20 | 17,320 / 202 (99.5%) / 75.554 | BT_interval_ms [62.5/62.5/79.762/106.383/212.264]<br>FX_interval_ms [65.789/74.247/87.209/108.108/236.842]<br><75ms: 55 | common |
| jack-one-hand | 同じ反復で反対手が全区間、つまみまたは自側 long に占有されるもの | ksm | 1,467 / 26 (72.2%) / 45.32 | BT_interval_ms [96.774/104.712/157.068/157.068/333.333]<br>FX_interval_ms [129.032/129.032/129.032/157.068/314.136]<br><75ms: 0 | common |

例: 「Sephirot」m42、「Awakening」m88、「オムニシエント・ゼロ」m66

## 4. trill-one-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 17 | 7,406 / 709 (96.9%) / 11.113 | run_hits [27/8/12]<br>hit_interval_ms [36.496/52.632/63.291/73.892/99.502]<br>chart_longest_run_hits [5/12/27] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 18 | 7,683 / 658 (97.9%) / 11.333 | run_hits [28/9/16]<br>hit_interval_ms [16.892/33.784/54.545/66.667/90.909]<br>chart_longest_run_hits [5/16/28] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | 19-20 | 3,055 / 200 (98.5%) / 13.327 | run_hits [47/11/23]<br>hit_interval_ms [21.739/33.333/45.732/54.348/79.787]<br>chart_longest_run_hits [6/23/47] | common |
| trill-one-hand | 反対手が全区間占有された AB／CD／BC の交互 chip、3 打以上の最大連鎖（連鎖数） | ksm | 218 / 19 (52.8%) / 6.735 | run_hits [19/9/17.481]<br>hit_interval_ms [78.534/78.534/78.534/78.534/157.068]<br>chart_longest_run_hits [3.5/16.55/19] | common |

例: 「rhythmology study」m78、「HAELEQUIN」m75、「Fiat Lux」m42

## 5. stream-density

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 17 | 732 / 732 (100.0%) / 1.098 | peak_1s_nps [13/19.69/27]<br>peak_4s_nps [10/14.75/15.75]<br>stream16_max_sec [1.635/9.641/12.61] | common |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 18 | 672 / 672 (100.0%) / 0.991 | peak_1s_nps [15/24/54]<br>peak_4s_nps [11.5/15.75/47.5]<br>stream16_max_sec [2.08/11.772/13.26] | rare |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | 19-20 | 203 / 203 (100.0%) / 0.886 | peak_1s_nps [18/26.98/28]<br>peak_4s_nps [13.75/19.99/20.5]<br>stream16_max_sec [2.51/15.371/35.63] | rare |
| stream-density | ボタン開始時刻を和音＝1 として数える 1 秒／4 秒窓の最大 NPS（譜面数） | ksm | 36 / 36 (100.0%) / 1.112 | peak_1s_nps [7.5/15.6/17]<br>peak_4s_nps [5.75/10/10]<br>stream16_max_sec [0.17/2.659/3.16] | common |

例: 「ロマンシングエスケープ」m2、「Harpuia」m44、「Sephirot」m71

## 6. chord-shapes

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 17 | 442,336 / 732 (100.0%) / 663.77 | —<br>free:flag:3plus-BT: 1,449<br>free:flag:4-BT: 656<br>free:flag:FX+two-home-BT: 91<br>free:flag:same-side-BT-FX: 9,231<br>knob:flag:3plus-BT: 110<br>knob:flag:4-BT: 12<br>knob:flag:FX+two-home-BT: 17<br>knob:flag:same-side-BT-FX: 2,246 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 18 | 467,766 / 672 (100.0%) / 689.992 | —<br>free:flag:3plus-BT: 2,655<br>free:flag:4-BT: 959<br>free:flag:FX+two-home-BT: 157<br>free:flag:same-side-BT-FX: 14,353<br>knob:flag:3plus-BT: 355<br>knob:flag:4-BT: 20<br>knob:flag:FX+two-home-BT: 30<br>knob:flag:same-side-BT-FX: 3,283 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | 19-20 | 172,365 / 203 (100.0%) / 751.898 | —<br>free:flag:3plus-BT: 1,350<br>free:flag:4-BT: 398<br>free:flag:FX+two-home-BT: 281<br>free:flag:same-side-BT-FX: 6,347<br>knob:flag:3plus-BT: 250<br>knob:flag:4-BT: 16<br>knob:flag:FX+two-home-BT: 56<br>knob:flag:same-side-BT-FX: 1,267 | common |
| chord-shapes | ボタン開始集合を、つまみ無し／片つまみに分けて全形状集計（単押しも含む時刻数） | ksm | 11,668 / 36 (100.0%) / 360.457 | —<br>free:flag:3plus-BT: 84<br>free:flag:4-BT: 12<br>free:flag:FX+two-home-BT: 21<br>free:flag:same-side-BT-FX: 113<br>knob:flag:FX+two-home-BT: 3<br>knob:flag:same-side-BT-FX: 17 | common |

例: 「ALBIDA Powerless Mix」m0、「good high school」m0、「Broken 8cmix」m0

## 7. knob-crossing-press

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 17 | 9,641 / 704 (96.2%) / 14.467 | —<br>A: 2,707<br>FL: 6,934 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 18 | 13,285 / 671 (99.9%) / 19.596 | —<br>A: 4,279<br>FL: 9,006 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | 19-20 | 5,600 / 201 (99.0%) / 24.429 | —<br>A: 1,883<br>FL: 3,717 | common |
| knob-crossing-press | 片つまみ中、反対手によるつまみ側の A または FL の開始（左右反転、レーン数） | ksm | 154 / 14 (38.9%) / 4.757 | —<br>A: 39<br>FL: 115 | common |

例: 「ALBIDA Powerless Mix」m37、「good high school」m8、「Broken 8cmix」m1

## 8. both-knobs-and-button

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 17 | 5,844 / 569 (77.7%) / 8.77 | —<br>lane:A: 1,008<br>lane:B: 1,963<br>lane:C: 1,783<br>lane:D: 810<br>lane:FL: 1,028<br>lane:FR: 963 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 18 | 8,945 / 617 (91.8%) / 13.195 | —<br>lane:A: 1,473<br>lane:B: 2,787<br>lane:C: 2,673<br>lane:D: 1,256<br>lane:FL: 1,677<br>lane:FR: 1,670 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | 19-20 | 3,913 / 190 (93.6%) / 17.069 | —<br>lane:A: 634<br>lane:B: 1,157<br>lane:C: 1,155<br>lane:D: 587<br>lane:FL: 797<br>lane:FR: 807 | common |
| both-knobs-and-button | 両つまみが動く時刻のボタン開始（時刻数、レーン別内訳） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「good high school」m37、「smooooch・∀・ KN mix」m34、「Broken 8cmix」m22

## 9. slam-with-button

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 17 | 45,327 / 730 (99.7%) / 68.018 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 18 | 51,455 / 671 (99.9%) / 75.9 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | 19-20 | 18,369 / 202 (99.5%) / 80.13 | — | common |
| slam-with-button | 直角と同 pulse のボタン開始集合（直角数、右直角を左右反転） | ksm | 403 / 23 (63.9%) / 12.45 | — | common |

例: 「ALBIDA Powerless Mix」m5、「Broken 8cmix」m17、「Evans VolteX Pf arrange」m5

## 10. slam-interval

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 17 | 88,415 / 729 (99.6%) / 132.676 | interval_ms [22.727/45.455/76.923/108.108/606.061]<br>section_start_ms [0/0/0/0/0]<br>開始後<15pulse: 31,026 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 18 | 99,239 / 672 (100.0%) / 146.385 | interval_ms [7.508/30.612/61.224/90.909/521.739]<br>section_start_ms [0/0/0/0/0]<br>開始後<15pulse: 32,059 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | 19-20 | 35,208 / 202 (99.5%) / 153.586 | interval_ms [7.508/31.915/61.475/81.081/450]<br>section_start_ms [0/0/0/0/0]<br>開始後<15pulse: 10,816 | common |
| slam-interval | 同側の連続直角間隔（区間をまたぐ）。別途、区間開始から < 1/16 拍の直角も数える | ksm | 1,519 / 34 (94.4%) / 46.926 | interval_ms [88.235/88.235/88.235/157.068/1,548.387]<br>section_start_ms [0/0/0/0/0]<br>開始後<15pulse: 543 | common |

例: 「Lucky*Clover」m90、「感情の魔天楼 ～ Arr.Demetori」m39、「銃弾は解を撃ち抜いて」m73

## 11. laser-zigzag

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 17 | 79,701 / 730 (99.7%) / 119.599 | reversal_interval_ms [2.841/4.032/5.459/6.757/113.636]<br>chart_min_reversal_ms [2.841/2.94/4.167/4.921/6.944] | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 18 | 89,517 / 672 (100.0%) / 132.045 | reversal_interval_ms [1.408/3.289/4.864/6.25/81.081]<br>chart_min_reversal_ms [1.408/2.209/3.638/4.638/6.41] | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | 19-20 | 30,098 / 202 (99.5%) / 131.295 | reversal_interval_ms [2.5/2.604/4.529/5.631/59.055]<br>chart_min_reversal_ms [2.5/2.596/3.894/4.371/5.896] | common |
| laser-zigzag | 同一区間の非直角傾斜の方向反転（反転数）。直角で連鎖を切り、静止は方向を保つ | ksm | 1,295 / 36 (100.0%) / 40.006 | reversal_interval_ms [157.068/157.068/157.068/157.068/352.941]<br>chart_min_reversal_ms [157.068/157.068/157.068/157.068/333.333] | common |

例: 「ALBIDA Powerless Mix」m8、「good high school」m0、「Broken 8cmix」m1

## 12. laser-crossing

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 17 | 15,468 / 725 (99.0%) / 23.211 | duration_ms [613,861.299/2,550.602/5,125.824]<br>合計 5,136.62秒、開始 13,380時刻/16,786ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 18 | 19,008 / 672 (100.0%) / 28.038 | duration_ms [10,541.424/2,340.02/5,099.668]<br>合計 5,117.012秒、開始 19,901時刻/25,398ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | 19-20 | 6,695 / 202 (99.5%) / 29.205 | duration_ms [10,378.378/2,566.128/4,913.99]<br>合計 1,725.691秒、開始 9,111時刻/12,041ボタン | common |
| laser-crossing | 両レーザー有効中に左の表示位置 > 右となる連続区間（区間数・秒・交差中の開始） | ksm | 274 / 27 (75.0%) / 8.465 | duration_ms [6,760.563/3,280.626/6,125.635]<br>合計 166.027秒、開始 269時刻/360ボタン | common |

例: 「恋愛＝精度×認識力」m61、「LittleGameStar」m2、「キリカ」m95

## 13. laser-gap

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 17 | 32,131 / 729 (99.6%) / 48.216 | gap_ms [29.412/41.667/106.383/200/1,357.143] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 18 | 34,227 / 672 (100.0%) / 50.488 | gap_ms [22.059/40.541/83.799/181.452/1,125] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | 19-20 | 11,377 / 202 (99.5%) / 49.629 | gap_ms [21.368/21.368/60.436/151.654/1,018.519] | common |
| laser-gap | 同側の隣接区間の端点が通常幅の > 0.25 飛ぶもの（隙間 ms、0 も含む） | ksm | 576 / 36 (100.0%) / 17.794 | gap_ms [83.333/83.333/83.333/387.097/3,096.774] | common |

例: 「CUTE-Reflection」m68、「Xinca」m67、「Burst Λnd reBoost」m17

## 14. hold-and-chip

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 17 | 33,786 / 721 (98.5%) / 50.699 | —<br>leave: 2230 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 18 | 37,712 / 664 (98.8%) / 55.628 | —<br>leave: 2723 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | 19-20 | 15,580 / 202 (99.5%) / 67.964 | —<br>leave: 1446 | common |
| hold-and-chip | 保持手の到達範囲の他レーン chip、および反対手占有中に到達範囲を超える chip（hold×chip 対数） | ksm | 938 / 20 (55.6%) / 28.977 | —<br>leave: 60 | common |

例: 「ALBIDA Powerless Mix」m20、「smooooch・∀・ KN mix」m63、「TYCOON」m23

## 15. long-end-to-chip

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 17 | 43,424 / 724 (98.9%) / 65.162 | interval_ms [56.497/75/114.504/168.539/681.818]<br><75ms: 34 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 18 | 46,707 / 671 (99.9%) / 68.896 | interval_ms [16.892/68.001/101.351/151.515/592.105]<br><75ms: 91 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | 19-20 | 15,203 / 202 (99.5%) / 66.319 | interval_ms [43.478/63.669/81.081/136.364/510.638]<br><75ms: 104 | common |
| long-end-to-chip | 同レーン直前 long の終端→次の chip（間に別の同レーン開始なし、間隔上限なし） | ksm | 531 / 31 (86.1%) / 16.404 | interval_ms [105.634/132.894/157.068/185.009/1,153.846]<br><75ms: 0 | common |

例: 「smooooch・∀・ KN mix」m44、「Garakuta Doll Play」m67、「continew」m38

## 16. short-long

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 17 | 0 / 0 (0.0%) / 0 | all_long_beats [29/6/14] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 18 | 0 / 0 (0.0%) / 0 | all_long_beats [40/7/14.589] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | 19-20 | 29 / 4 (2.0%) / 0.127 | all_long_beats [48/8/16.5]<br>short_beats [0.083/0.083/0.083] | rare |
| short-long | 長さ < 1/8 拍 = 30 pulse の BT/FX long（ノート数、全 long の長さも集計） | ksm | 0 / 0 (0.0%) / 0 | all_long_beats [18/6.94/16.047] | rare |

例: 「色を喪った街」m37、「すべてが幻になった後で」m21、「色を喪った街」m38

## 17. offgrid

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 17 | 10,770 / 564 (77.0%) / 16.161 | —<br>1/24: 5,294<br>1/32: 2,018<br>1/48: 2,885<br>1/64: 508<br>1/96: 65 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 18 | 17,965 / 577 (85.9%) / 26.5 | —<br>1/24: 7,232<br>1/32: 3,942<br>1/48: 5,581<br>1/64: 908<br>1/96: 302 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | 19-20 | 12,110 / 187 (92.1%) / 52.827 | —<br>1/24: 4,983<br>1/32: 3,100<br>1/48: 3,393<br>1/64: 511<br>1/96: 123 | common |
| offgrid | 全音符 1/16 (=60 pulse)・1/12 (=80 pulse) のどちらにも乗らないボタン開始（レーン数） | ksm | 4 / 1 (2.8%) / 0.124 | —<br>1/32: 4 | rare |

例: 「ALBIDA Powerless Mix」m1、「smooooch・∀・ KN mix」m17、「Broken 8cmix」m8

## 18. fx-long-with-bt-chips

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 17 | 25,933 / 720 (98.4%) / 38.915 | —<br>100ボタン開始あたり 4.647 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 18 | 27,587 / 663 (98.7%) / 40.693 | —<br>100ボタン開始あたり 4.514 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | 19-20 | 10,027 / 202 (99.5%) / 43.74 | —<br>100ボタン開始あたり 4.382 | common |
| fx-long-with-bt-chips | FL 保持中の A/B chip、および FR 保持中の C/D chip（対数） | ksm | 761 / 20 (55.6%) / 23.509 | —<br>100ボタン開始あたり 5.22 | common |

例: 「ALBIDA Powerless Mix」m8、「smooooch・∀・ KN mix」m2、「Broken 8cmix」m9

## 19. button-during-slam-same-hand

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 17 | 0 / 0 (0.0%) / 0 | — | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 18 | 2 / 1 (0.1%) / 0.003 | delay_ms [45.455/45.455/45.455/45.455/45.455] | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | 19-20 | 2 / 2 (1.0%) / 0.009 | delay_ms [9.728/9.728/9.728/9.731/9.766] | rare |
| button-during-slam-same-hand | 直角の手の自側レーンの開始で、直角から 0 < Δpulse ≤ 1/16 拍 = 15（直角×開始対数） | ksm | 0 / 0 (0.0%) / 0 | — | rare |

例: 「Little Red Riding Hood」m21、「DEUX EX MĀXHINĀ」m101、「End to end」m117

## 20. wide-laser

| id | 何を数えるか | 群 | 頻度 | 分布・閾値 | 仮判定 |
|---|---|---|---|---|---|
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 17 | 11,160 / 615 (84.0%) / 16.747 | duration_ms [29,561.404/10,111.643/18,856.213] | common |
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 18 | 14,145 / 622 (92.6%) / 20.865 | duration_ms [49,406.25/10,714.286/21,106.491] | common |
| wide-laser | 幅指定が 2 のレーザー区間（区間数） | 19-20 | 5,036 / 189 (93.1%) / 21.968 | duration_ms [24,714.286/10,428.513/19,174.21] | common |
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
| 17 | 396,034 | 731 | 594.289 |
| 18 | 434,107 | 672 | 640.342 |
| 19-20 | 161,859 | 203 | 706.068 |
| ksm | 8,839 | 35 | 273.061 |

## 判断が割れそうなもの

- **hand-overload**: ほぼ0という予想に反して多い。直角前後の占有余白だけによる件数を主表で分離した（26,261件）。例: 「ALBIDA Powerless Mix」m37、「Broken 8cmix」m3、「Ganymede kamome mix」m4。
- **jack-mixed**: 途中だけ占有される区間は片手／両手へ無理に二分できない（1,000,839件）。例: 「Non RolicK!!大冒険」m21、「Awakening」m31、「Quietus Ray」m76。
- **jack-one-hand**: 短い間隔でも担当手は推定。反対側つまみ・long の連続占有と実際の運指は区別したい（94,114件）。例: 「Sephirot」m42、「Awakening」m88、「オムニシエント・ゼロ」m66。
- **hold-and-chip**: leave は固定の保持手を仮定した結果で、持ち替え・つまみ余白の影響があり得る（6,459件）。例: 「ALBIDA Powerless Mix」m20、「smooooch・∀・ KN mix」m63、「TYCOON」m23。
- **button-during-slam-same-hand**: 直角の直後にホーム側の開始があっても、反対手で拾う運指はあり得る（4件）。例: 「Little Red Riding Hood」m21、「DEUX EX MĀXHINĀ」m101、「End to end」m117。
- **laser-crossing**: 見た目の交差と手の交差は別。幅2・瞬間だけの交差も含む（41,445件）。例: 「恋愛＝精度×認識力」m61、「LittleGameStar」m2、「キリカ」m95。
- **short-long**: 1/8拍未満は高難度群だけに少数見つかる。最低値だけで禁止閾値を決めない（29件）。例: 「色を喪った街」m37、「すべてが幻になった後で」m21、「色を喪った街」m38。
- **stream-density**: 出現単位が譜面なので100小節あたりの機械判定は曲長に依存する。rareでも密度の配置が稀とはいえない（1,643件）。例: 「ロマンシングエスケープ」m2、「Harpuia」m44、「Sephirot」m71。
