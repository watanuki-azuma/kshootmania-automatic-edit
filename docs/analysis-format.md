# 音源解析の出力仕様 v0

`ksmauto analyze song.ogg -o analysis.json [--text analysis.txt]`

LLM が「どこに何を置くか」を判断するための材料を出す。JSON は機械用（compile/lint/render が使う）、テキストは LLM が直接読む用。

## JSON

```jsonc
{
  "version": 0,
  "audio": {"path": "song.ogg", "duration_sec": 134.2, "sample_rate": 44100},
  "tempo": {
    "bpm": 191.0,                  // 主テンポ（整数・0.5 刻みに近ければ丸める）
    "confidence": 0.92,            // 0-1
    "candidates": [[191.0, 0.92], [95.5, 0.40]],
    "changes": [],                 // テンポ変化 [{"measure": 40, "bpm": 200.0}]（検出時のみ）
    "time_sig": [4, 4]
  },
  "offset_ms": 132,                // 推奨 audio.bgm.offset（pulse 0 = 小節 0 の頭が音源の何 ms 目か）
  "measures": [                    // 小節ごとの情報。index = KSON の measure index
    {
      "index": 0,
      "start_sec": 0.132,
      "energy": 0.12,              // 小節の RMS（曲全体の最大で 0-1 正規化）
      "onsets": {                  // 各帯域の発音位置。値は小節内の拍位置（グリッドに量子化済み）と強さ
        "low":  [[0, 0.9], [2, 0.8]],      // キック・ベース帯
        "mid":  [[1, 0.7], [3, 0.7]],      // スネア・ボーカル帯
        "high": [[0.5, 0.4], [1.5, 0.4]],  // ハイハット帯
        "all":  [[0, 1.0], [1, 0.8]]
      },
      "sustain": {"low": [], "mid": [[0, 2]], "high": []}   // 長く伸びる音 [開始拍, 長さ拍]
    }
  ],
  "sections": [                    // 構造区間（似た小節のまとまり）
    {"start": 0, "end": 8, "label": "A", "energy": 0.3},
    {"start": 8, "end": 16, "label": "B", "energy": 0.7}
  ]
}
```

- グリッド量子化: 各オンセットは 1/4 拍（16分）と 1/3 拍（3連）のうち近い方へスナップし、ずれが大きいものは除外する。
- `sections.label` は同じ文字なら似た区間（繰り返し）。`copy` 指示の根拠になる。

## テキスト（LLM 用）

```
BPM 191 (conf 0.92)  offset 132ms  4/4  duration 134.2s  measures 0-107
sections: A m0-7 (0.30) | B m8-15 (0.70) | A m16-23 (0.32) ...

m   energy  low              mid              high
0   0.12    x...x...x...x... ....x.......x... x.x.x.x.x.x.x.x.
1   0.15    x...x...x..xx... ....x.......x... x.x.x.x.x.x.x.x.
```

- 16分グリッドで、強さ 0.6 以上を `X`、0.3 以上を `x`、未満と無音を `.` で表す。3連が多い小節は 12 分割（`|` 区切り）で出す。

## 精度評価

公式既定曲（`corpus/official/`）の譜面の `t=` / `o=` を正解として、`tests/eval/` で BPM と offset の誤差を測る。
既定曲はすべて `o=0`（音源の先頭が小節頭）で、BPM 変化はない。
offset は「拍の位相」（1拍の長さで割った余り）と「小節頭の位相」（1小節の長さで割った余り）に分けて評価する。
目標は BPM 誤差 ±0.5 以内（倍・半分は誤りとする）、拍の位相の誤差 ±15 ms 以内、それぞれ 8/10 曲以上。小節頭の位相は参考値として記録する。
