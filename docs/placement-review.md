# 配置の人手レビュー

開始時刻のボタン集合（開始＋保持中、終端は除く）を物理カテゴリで集約。片手は BT の連続3レーン A–C または B–D と、その窓に下側2レーンが収まる FX を覆う（A–C は FX-L、B–D は FX-R）。左右の手はどちらの窓にも移動できる。必要手数は最小被覆。実効手数＝ボタン手数＋slam/steep 各1＋gentle/ending 各0.5。ending は移動終点まで50 ms以内、steep は32通常幅/秒超。

この被覆モデルでは全6ボタンを両窓で覆えるため、ボタンだけで3手以上になる集合はない。例の A+D+両FX は A+FX-L と D+FX-R の2手になる。追加の運指制約は仮定しない。

キーは `左需要,右需要|ボタン手数|home/crossing`。需要の強い側を左へ反転。crossing は1手で押す際、需要の軽い側の手を使うには自側の窓を越える必要があること。2手のボタンは両手を必要とし、busy なつまみ側の手も必要になる。各群のセルは「件数 / 譜面数 / 100小節あたり」。例は曲名と0始まりの小節、群ごと最大3件。表は観測された実効手数>2の全カテゴリ。判断は人が記入する。

`src/ksmauto/data/placement_verdicts.json` に表のキーを写し、`"allow"` は頻度検査を抑制、`"forbid"` は `placement-forbidden` warning、`{"min_level": 18}` は18未満で `placement-min-level` warning（18以上は抑制）。判定があれば実効手数・頻度・ジャック閾値より優先。初期値は空。ジャックは各群の行キーを使い、その行の全反復に適用する。

| カテゴリキー | 実効手数 | 17 | 18 | 19-20 | ksm | 例（群ごと最大3） | 判断 |
|---|---:|---|---|---|---|---|---|
| ending,ending&#124;2&#124;home | 3 | 34 / 20 / 0.10175 | 210 / 66 / 0.20789 | 80 / 19 / 0.34898 | 0 / 0 / 0.00000 | 17: 「LittleGameStar」m90、「The setting sun」m17、「Fáfnir」m51<br>18: 「good high school」m63、「香港功夫大旋風」m19、「AA BlackY mix」m15<br>19-20: 「XROSS INFECTION」m37、「幸せになれる隠しコマンドがあるらしい」m21、「2 MINUTES FIGHTERS」m77 | 未判定 |
| ending,still&#124;2&#124;home | 2.5 | 283 / 113 / 0.84690 | 957 / 383 / 0.94737 | 241 / 88 / 1.05130 | 0 / 0 / 0.00000 | 17: 「TYCOON」m61、「Grip & Break down !! - SDVX Edit. -」m14、「色は匂へど散りぬるを」m44<br>18: 「Evans VolteX Pf arrange」m18、「冥 Rockin' SWING REMIX」m66、「neu BSP style」m6<br>19-20: 「Ganymede kamome mix」m61、「音楽 -resolve-」m70、「Booths of Fighters」m31 | 未判定 |
| gentle,ending&#124;2&#124;home | 3 | 14 / 5 / 0.04190 | 16 / 15 / 0.01584 | 18 / 14 / 0.07852 | 0 / 0 / 0.00000 | 17: 「LittleGameStar」m98、「AYAKASHI」m53、「蟲の棲む処」m49<br>18: 「ボルテ体操第一」m90、「キモチコネクト」m61、「ムラサキグルマ」m42<br>19-20: 「Booths of Fighters」m56、「Quietus Ray」m96、「VILE CAT」m37 | 未判定 |
| gentle,gentle&#124;2&#124;home | 3 | 105 / 43 / 0.31422 | 384 / 154 / 0.38013 | 163 / 47 / 0.71105 | 0 / 0 / 0.00000 | 17: 「Next infection」m20、「LittleGameStar」m86、「Appliqué」m67<br>18: 「smooooch・∀・ KN mix」m47、「Broken 8cmix」m22、「Xepher Light and Darkness Dragon REMIX」m14<br>19-20: 「Joyeuse」m66、「音楽 -resolve-」m36、「Booths of Fighters」m52 | 未判定 |
| gentle,still&#124;2&#124;home | 2.5 | 527 / 176 / 1.57709 | 2333 / 632 / 2.30951 | 605 / 139 / 2.63916 | 30 / 8 / 0.92678 | 17: 「レトロスペクティビリー・メリーゴーランド」m19、「dreamin' feat.Ryu☆」m23、「Grip & Break down !! - SDVX Edit. -」m14<br>18: 「ALBIDA Powerless Mix」m40、「smooooch・∀・ KN mix」m75、「Broken 8cmix」m27<br>19-20: 「Ganymede kamome mix」m61、「ラクガキスト」m76、「音楽 -resolve-」m12<br>ksm: 「AZ Drei」m30、「Flavor of Youth」m86、「Mercury」m85 | 未判定 |
| slam,ending&#124;1&#124;crossing | 2.5 | 28 / 17 / 0.08379 | 155 / 79 / 0.15344 | 52 / 34 / 0.22684 | 0 / 0 / 0.00000 | 17: 「LittleGameStar」m100、「Discloze」m30、「UROBØROS」m13<br>18: 「neu BSP style」m6、「EGG」m76、「魔理沙は大変なものを盗んでいきました」m35<br>19-20: 「音楽 -壊音楽 mix-」m59、「Booths of Fighters」m62、「Quietus Ray」m17 | 未判定 |
| slam,ending&#124;1&#124;home | 2.5 | 848 / 220 / 2.53771 | 2531 / 640 / 2.50552 | 797 / 165 / 3.47671 | 0 / 0 / 0.00000 | 17: 「天ノ弱」m45、「レトロスペクティビリー・メリーゴーランド」m52、「イカサマライフゲイム」m92<br>18: 「smooooch・∀・ KN mix」m34、「Xepher Light and Darkness Dragon REMIX」m12、「冥 Rockin' SWING REMIX」m62<br>19-20: 「ラクガキスト」m18、「音楽 -resolve-」m46、「Quietus Ray」m48 | 未判定 |
| slam,ending&#124;2&#124;home | 3.5 | 2 / 2 / 0.00599 | 20 / 13 / 0.01980 | 11 / 8 / 0.04798 | 0 / 0 / 0.00000 | 17: 「セイシュンライナー」m25、「Devastated Territory」m38<br>18: 「Qubism」m64、「おお われら喜び讃うべし、主よ」m81、「ちくわパフェだよ☆ＣＫＰ」m44<br>19-20: 「幸せになれる隠しコマンドがあるらしい」m18、「veRtrageS」m76、「極圏」m47 | 未判定 |
| slam,gentle&#124;1&#124;crossing | 2.5 | 10 / 6 / 0.02993 | 69 / 33 / 0.06831 | 32 / 16 / 0.13959 | 0 / 0 / 0.00000 | 17: 「LittleGameStar」m92、「ヒミツダイヤル」m22、「御伽噺に幕切れを」m51<br>18: 「smooooch・∀・ KN mix」m48、「Evans VolteX Pf arrange」m37、「冥 Rockin' SWING REMIX」m73<br>19-20: 「音楽 -resolve-」m59、「Booths of Fighters」m50、「U.N.オーエンは彼女なのか？haru_naba Remix」m28 | 未判定 |
| slam,gentle&#124;1&#124;home | 2.5 | 228 / 96 / 0.68231 | 850 / 323 / 0.84144 | 382 / 103 / 1.66638 | 0 / 0 / 0.00000 | 17: 「Grip & Break down !! - SDVX Edit. -」m55、「croiX」m32、「色は匂へど散りぬるを」m32<br>18: 「smooooch・∀・ KN mix」m38、「Evans VolteX Pf arrange」m37、「Xepher Light and Darkness Dragon REMIX」m12<br>19-20: 「ラクガキスト」m82、「音楽 -resolve-」m36、「Booths of Fighters」m50 | 未判定 |
| slam,gentle&#124;2&#124;home | 3.5 | 6 / 5 / 0.01796 | 44 / 28 / 0.04356 | 9 / 7 / 0.03926 | 0 / 0 / 0.00000 | 17: 「INFINITY OVERDRIVE」m66、「AYAKASHI」m55、「ANTI THE∞HOLiC」m14<br>18: 「#Fairy_dancing_in_lake」m65、「ムーニャポヨポヨスッポコニャーゴ」m46、「Hellfire」m12<br>19-20: 「音楽 -resolve-」m58、「Booths of Fighters」m50、「幸せになれる隠しコマンドがあるらしい」m25 | 未判定 |
| slam,slam&#124;1&#124;home | 3 | 5 / 4 / 0.01496 | 24 / 21 / 0.02376 | 7 / 7 / 0.03054 | 0 / 0 / 0.00000 | 17: 「scary night」m11、「Sparkling Laser Beam」m61、「DISTORDER」m84<br>18: 「Hellfire」m12、「Idola」m77、「Growth Memories」m4<br>19-20: 「VILE CAT」m22、「Everlasting Message」m87、「Sayonara Planet Wars」m5 | 未判定 |
| slam,slam&#124;2&#124;home | 4 | 1 / 1 / 0.00299 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 17: 「メテオライツ・プレリュード」m37 | 未判定 |
| slam,still&#124;2&#124;home | 3 | 480 / 174 / 1.43644 | 1959 / 588 / 1.93928 | 585 / 156 / 2.55191 | 19 / 6 / 0.58696 | 17: 「TYCOON」m34、「レトロスペクティビリー・メリーゴーランド」m53、「イカサマライフゲイム」m8<br>18: 「smooooch・∀・ KN mix」m79、「FLOWER REDALiCE Remix」m9、「Ignited Night burst」m49<br>19-20: 「大宇宙ステージ」m7、「ラクガキスト」m73、「Joyeuse」m98<br>ksm: 「AZ Drei」m13、「JURER」m91、「JURER」m83 | 未判定 |
| steep,ending&#124;1&#124;crossing | 2.5 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 1 / 1 / 0.00436 | 0 / 0 / 0.00000 | 19-20: 「APØCALYPSE RAY」m81 | 未判定 |
| steep,ending&#124;1&#124;home | 2.5 | 0 / 0 / 0.00000 | 5 / 4 / 0.00495 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 18: 「The EXworld of sound」m16、「We Are All The Dreamer」m42、「メズマライザー」m100 | 未判定 |
| steep,ending&#124;2&#124;home | 3.5 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 1 / 1 / 0.00436 | 0 / 0 / 0.00000 | 19-20: 「Gryphone」m97 | 未判定 |
| steep,gentle&#124;1&#124;home | 2.5 | 0 / 0 / 0.00000 | 1 / 1 / 0.00099 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 18: 「The star in eclipse」m67 | 未判定 |
| steep,steep&#124;1&#124;home | 3 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 1 / 1 / 0.00436 | 0 / 0 / 0.00000 | 19-20: 「APØCALYPSE RAY」m80 | 未判定 |
| steep,still&#124;2&#124;home | 3 | 0 / 0 / 0.00000 | 0 / 0 / 0.00000 | 4 / 3 / 0.01745 | 0 / 0 / 0.00000 | 19-20: 「XHRONOXAPSULΞ」m153、「QQ」m74、「Circuit Surfer」m22 | 未判定 |

ジャックは mixed を one-hand に合算。各時間帯セルは100小節あたり、p1 は従来の1パーセンタイル（ms）。警告下限は同群の5譜面以上に現れた最短帯の下端。帯は左端を含み右端を含まない。120 ms以上も下限導出のため集計する。

| 行キー | <60 | 60–70 | 70–80 | 80–90 | 90–100 | 100–120 ms | p1 ms | 警告下限 ms | 判断 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| jack:17:two-hand:BT | 0.000 | 0.030 | 0.251 | 0.736 | 1.218 | 2.433 | 83.333 | 70.000 | 未判定 |
| jack:17:two-hand:FX | 0.000 | 0.027 | 0.096 | 0.174 | 0.299 | 0.560 | 80.214 | 70.000 | 未判定 |
| jack:17:assisted:BT | 0.000 | 0.000 | 0.012 | 0.051 | 0.132 | 0.368 | 117.888 | 80.000 | 未判定 |
| jack:17:assisted:FX | 0.000 | 0.000 | 0.000 | 0.021 | 0.039 | 0.102 | 115.227 | 90.000 | 未判定 |
| jack:17:one-hand:BT | 0.000 | 0.003 | 0.006 | 0.069 | 0.186 | 1.362 | 141.509 | 80.000 | 未判定 |
| jack:17:one-hand:FX | 0.000 | 0.000 | 0.003 | 0.024 | 0.003 | 0.180 | 142.857 | 80.000 | 未判定 |
| jack:18:two-hand:BT | 0.115 | 0.288 | 1.562 | 2.550 | 2.568 | 5.734 | 73.171 | 0.000 | 未判定 |
| jack:18:two-hand:FX | 0.017 | 0.037 | 0.288 | 0.467 | 0.589 | 1.601 | 75.938 | 60.000 | 未判定 |
| jack:18:assisted:BT | 0.002 | 0.012 | 0.085 | 0.172 | 0.193 | 0.655 | 101.351 | 70.000 | 未判定 |
| jack:18:assisted:FX | 0.000 | 0.002 | 0.009 | 0.024 | 0.069 | 0.148 | 100.000 | 70.000 | 未判定 |
| jack:18:one-hand:BT | 0.178 | 0.167 | 0.062 | 0.355 | 0.553 | 3.338 | 120.482 | 60.000 | 未判定 |
| jack:18:one-hand:FX | 0.045 | 0.019 | 0.011 | 0.070 | 0.119 | 0.622 | 125.000 | 70.000 | 未判定 |
| jack:19-20:two-hand:BT | 0.284 | 2.281 | 4.109 | 3.874 | 4.899 | 12.995 | 64.103 | 0.000 | 未判定 |
| jack:19-20:two-hand:FX | 0.031 | 0.349 | 1.008 | 0.694 | 1.335 | 3.232 | 67.568 | 60.000 | 未判定 |
| jack:19-20:assisted:BT | 0.017 | 0.039 | 0.375 | 0.279 | 0.798 | 1.963 | 82.003 | 60.000 | 未判定 |
| jack:19-20:assisted:FX | 0.004 | 0.009 | 0.039 | 0.065 | 0.305 | 1.121 | 90.090 | 70.000 | 未判定 |
| jack:19-20:one-hand:BT | 0.009 | 0.135 | 0.449 | 1.021 | 2.076 | 13.401 | 105.263 | 60.000 | 未判定 |
| jack:19-20:one-hand:FX | 0.004 | 0.000 | 0.061 | 0.100 | 0.493 | 4.013 | 107.143 | 70.000 | 未判定 |
| jack:ksm:two-hand:BT | 0.000 | 0.000 | 0.000 | 0.000 | 0.154 | 0.000 | 157.068 | 120.000 | 未判定 |
| jack:ksm:two-hand:FX | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.031 | 153.984 | 120.000 | 未判定 |
| jack:ksm:assisted:BT | 0.000 | 0.000 | 0.000 | 0.000 | 0.031 | 0.000 | 157.068 | 120.000 | 未判定 |
| jack:ksm:assisted:FX | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 129.032 | 120.000 | 未判定 |
| jack:ksm:one-hand:BT | 0.000 | 0.000 | 0.000 | 0.000 | 0.031 | 0.309 | 157.068 | 120.000 | 未判定 |
| jack:ksm:one-hand:FX | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 157.068 | 120.000 | 未判定 |
