"""Decode locally downloaded sdvx.in transcriptions (drawLasers.v1 or PNG layers).

The official counts are used only for diagnostics, never to change decoded notes.
Image dependencies are deliberately lazy; JSON import needs only the stdlib.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import Counter
from fractions import Fraction
from pathlib import Path


def _base(meta):
    level = float(meta['level'])
    return {
        'format_version': 1,
        'meta': {'title': meta['title'], 'artist': meta['artist'],
                 'chart_author': 'sdvx.in transcription', 'difficulty': 3,
                 'level': math.floor(level), 'disp_bpm': str(meta.get('bpm', '')),
                 'information': f'sdvx.in {level:g}'},
        'beat': {'bpm': [], 'time_sig': [[0, [4, 4]]]},
        'note': {'bt': [[] for _ in range(4)], 'fx': [[], []], 'laser': [[], []]},
    }


def _json_chart(data, meta):
    if data.get('version') != 'drawLasers.v1':
        raise ValueError(f"unsupported sdvx.in JSON version: {data.get('version')!r}")
    chart = _base(meta)
    for kind, field in [('notes', 'pulse'), ('holds', 'pulse')]:
        for obj in data.get(kind, []):
            bt = obj['type'].startswith('BT')
            lane = ('ABCD' if bt else 'LR').index(obj['lane'])
            start = round(obj[field])
            end = round(obj['pulseEnd']) if kind == 'holds' else start
            if end < start:
                start, end = end, start
            chart['note']['bt' if bt else 'fx'][lane].append([start, end - start])
    for i, side in enumerate(('left', 'right')):
        for section in data.get('lasers', {}).get(side, []):
            start, points, *width = copy.deepcopy(section)
            pts = []
            for pt in sorted(points, key=lambda p: p[0]):
                p = [round(pt[0]), pt[1]]
                if len(pt) > 2 and isinstance(pt[2], list):
                    # The viewer's [0.5, 0.55] sentinel means a wrapped joint.
                    if pt[2] != [0.5, 0.55]:
                        p.append(pt[2])
                if pts and pts[-1][0] == p[0]:
                    old = pts.pop()[1]
                    p[1] = [old[0] if isinstance(old, list) else old,
                            p[1][-1] if isinstance(p[1], list) else p[1]]
                pts.append(p)
            chart['note']['laser'][i].append([round(start), pts, 2 if width and width[0] in (2, '2x') else 1])
    bpm = {round(b.get('y', b.get('pulse', 0))): float(b.get('v', b.get('bpm')))
           for b in data.get('bpm', [])}
    if not bpm:
        bpm[0] = float(meta['bpm'])
    chart['beat']['bpm'] = sorted(map(list, bpm.items()))
    sigs = []
    if data.get('bars'):
        for m, bar in enumerate(data['bars']):
            sig = [int(bar.get('num', 4)), int(bar.get('den', 4))]
            if not sigs or sig != sigs[-1][1]:
                sigs.append([m, sig])
    else:
        pulse, measure, previous = 0, 0, [4, 4]
        for at, sig in sorted(data.get('timeSig', [[0, [4, 4]]])):
            length = 960 * previous[0] / previous[1]
            delta = (at - pulse) / length
            if abs(delta - round(delta)) > 1e-6:
                raise ValueError(f'time signature at {at} is not on a measure boundary')
            measure += round(delta)
            sigs.append([measure, sig])
            pulse, previous = at, sig
    chart['beat']['time_sig'] = sigs or [[0, [4, 4]]]
    _sort_notes(chart)
    return chart


def _sort_notes(chart):
    for lanes in chart['note'].values():
        for lane in lanes:
            lane.sort(key=lambda n: n[0])


# 7-pixel bold decimal glyphs harvested from the green labels of constant-BPM
# charts. These describe the viewer's font, not any chart geometry or note data.
_DIGITS = {
    '0': '01110/11011/11011/11011/11011/11011/01110',
    '1': '0110/1110/0110/0110/0110/0110/1111',
    '2': '01110/10011/00011/00110/01100/11000/11111',
    '3': '01110/10011/00011/01110/00011/10011/01110',
    '4': '000110/001110/010110/100110/111111/000110/000110',
    '5': '11111/11000/11110/00011/00011/10011/01110',
    '6': '01110/11000/11110/11011/11011/11011/01110',
    '7': '11111/00011/00110/00110/01100/01100/11000',
    '8': '01110/11011/11011/01110/11011/11011/01110',
    '9': '01110/11011/11011/11011/01111/00011/01110',
}


def _runs(mask):
    import numpy as np
    a = np.flatnonzero(mask)
    return [(int(v[0]), int(v[-1]) + 1)
            for v in np.split(a, np.where(np.diff(a) > 1)[0] + 1) if len(v)]


def _read_number(mask):
    import numpy as np
    if mask.shape[0] != 7:
        raise ValueError('decimal label must be seven pixels high')
    templates = {d: np.array([[c == '1' for c in row] for row in rows.split('/')])
                 for d, rows in _DIGITS.items()}
    memo = {}
    def match(x):
        while x < mask.shape[1] and not mask[:, x].any():
            x += 1
        if x == mask.shape[1]:
            return 0, ''
        if x in memo:
            return memo[x]
        best = (float('inf'), '')
        for digit, template in templates.items():
            w = template.shape[1]
            if x+w <= mask.shape[1]:
                score = int((template != mask[:, x:x+w]).sum())
                tail, text = match(x+w)
                candidate = score+tail, digit+text
                if candidate[0] < best[0]:
                    best = candidate
        memo[x] = best
        return best
    error, text = match(0)
    if not text or error > 3:
        raise ValueError('unrecognized decimal label in sdvx.in bar layer')
    return float(text)


def _layers(chart_dir, meta):
    import numpy as np
    from PIL import Image
    root = chart_dir.parent.parent
    paths = [root / p for p in meta['layers']]
    by_kind = {('obj' if '/obj/' in p.as_posix() else 'bar' if p.stem.endswith('bar') else 'bg'): p
               for p in paths}
    return {k: np.array(Image.open(p).convert('RGBA')) for k, p in by_kind.items()}


def _layout(bg, bar):
    import numpy as np
    gray = (bg[:, :, 0] == bg[:, :, 1]) & (bg[:, :, 1] == bg[:, :, 2]) & (bg[:, :, 0] > 0)
    xs = np.flatnonzero(gray.sum(axis=0) > 40)
    groups = [v for v in np.split(xs, np.where(np.diff(xs) > 12)[0] + 1) if len(v) >= 5]
    cols = []
    for g in groups:
        # Four BT lanes are bounded by five vertical separators.
        left, right = int(g[0]) + 1, int(g[-1]) + 1
        white = (bar[:, max(0, left-32):left-4, 0] == 255) & (bar[:, max(0, left-32):left-4, 1] == 255)
        labels = _runs(white.any(axis=1))
        boundaries = [b + 1 for a, b in reversed(labels)]
        if len(boundaries) >= 2:
            cols.append({'left': left, 'right': right, 'boundaries': boundaries})
    if not cols:
        raise ValueError('no measure labels / lane columns found')
    spacing = min(b['left']-a['left'] for a,b in zip(cols,cols[1:])) if len(cols)>1 else 110
    for col in cols:
        col['margin'] = min(31,(spacing-40)//2)
    last = cols[-1]
    extent = np.flatnonzero(bg[:, last['left']+3, 3])
    if len(extent) and extent[0] < last['boundaries'][-1]-20:
        last['boundaries'].append(int(extent[0]))
    return cols


def _snap(pulse):
    # Prefer the coarsest straight/triplet subdivision within one image pixel.
    for step in (240, 120, 80, 60, 40, 30, 20, 15, 10):
        nearest = round(pulse / step) * step
        if abs(nearest - pulse) <= 5.1:
            return max(0, nearest)
    return max(0, round(pulse))


def _image_chart(chart_dir, meta):
    import numpy as np
    layers = _layers(chart_dir, meta)
    bg, bar, obj = (layers[k] for k in ('bg', 'bar', 'obj'))
    cols = _layout(bg, bar)
    chart = _base(meta)
    # The bar layer carries measure numbers (and BPM), rather than bar lines.
    # The horizontal grid in the background supplies the beat spacing.
    lengths = []
    for col in cols:
        x = col['left'] + 3
        gray = bg[:, x, 0]
        ys = np.flatnonzero((gray > 0) & (bg[:, x, 0] == bg[:, x, 1]) & (bg[:, x, 1] == bg[:, x, 2]))
        diffs = np.diff(ys)
        col['beat_px'] = Counter(int(d) for d in diffs if d >= 12).most_common(1)[0][0]
        col['p0'] = sum(lengths)
        col['m0'] = len(lengths)
        col['lengths'] = []
        for a, b in zip(col['boundaries'], col['boundaries'][1:]):
            length = round((a-b) / col['beat_px'] * 240)
            col['lengths'].append(length)
            lengths.append(length)
    sigs = []
    for m, length in enumerate(lengths):
        f = Fraction(length, 960)
        sig = [f.numerator, f.denominator]
        if sig[1] < 4:
            sig = [sig[0] * (4 // sig[1]), 4]
        if not sigs or sig != sigs[-1][1]:
            sigs.append([m, sig])
    chart['beat']['time_sig'] = sigs

    for col in cols:
        left, right = col['left'], col['right']
        bottom, top = col['boundaries'][0], col['boundaries'][-1]
        scale = 240 / col['beat_px']
        def pulse(y):
            return _snap(col['p0'] + (bottom-y)*scale)
        data = obj[max(0, top-4):min(obj.shape[0], bottom+1), left:right]
        origin = max(0, top-4)
        rgb = data[:, :, :3].astype(int)
        opaque = data[:, :, 3] == 255
        # BT bodies are opaque light grey, but a laser drawn over them tints
        # them; any opaque pixel without the FX chip's orange counts.
        neutral = opaque & (rgb.min(axis=2) > 90)
        orange = (rgb[:, :, 0] > 170) & (rgb[:, :, 1] > 85) & (rgb[:, :, 2] < 90) & (data[:, :, 3] > 200)
        width = (right-left)//4
        for lane in range(4):
            region = data[:, lane*width:(lane+1)*width-1]
            region_neutral = neutral[:, lane*width:(lane+1)*width-1]
            border=(region[:,:,0]==151)&(region[:,:,1]==153)&(region[:,:,2]==150)&(region[:,:,3]==255)
            chiprows=border.sum(axis=1)>=7
            chiprows[1:-1]|=chiprows[:-2]&chiprows[2:]
            body = region_neutral.sum(axis=1)>=3
            for a,b in _runs(chiprows):
                if b-a == 3 and not (a>=4 and body[a-4:a].all()) and not (b+4<=len(body) and body[b:b+4].all()):
                    chart['note']['bt'][lane].append([pulse(origin+b),0])
                    body[a:b] = False
            for a,b in _runs(body):
                if b-a > 4:
                    start,end = pulse(origin+b),pulse(origin+a)
                    if end>start:
                        chart['note']['bt'][lane].append([start,end-start])
        for lane in range(2):
            fill = data[:, lane*width*2:(lane+1)*width*2-1]
            chip = (fill[:,:,0]>170)&(fill[:,:,1]>85)&(fill[:,:,2]<90)&(fill[:,:,3]==255)
            chiprows = chip[:,width-1]
            for a,b in _runs(chiprows):
                chart['note']['fx'][lane].append([pulse(origin+b),0])
            af=fill[:,:,3].astype(float)/255
            longmask=(fill[:,:,0]>240)&(fill[:,:,1]>140)&(fill[:,:,1]<190)&(fill[:,:,2]<70)&(fill[:,:,3]==107)
            fore=(af-107/255)/(1-107/255)
            for laser_color in ((69,107,249),(250,68,171)):
                predicted=(np.array((255,159,7))[None,None,:]*(107/255)*(1-fore[:,:,None])
                           +np.array(laser_color)[None,None,:]*fore[:,:,None])/np.maximum(af[:,:,None],1/255)
                distance=abs(predicted-fill[:,:,:3]).max(axis=2)
                longmask|=(distance<15)&(fill[:,:,3]>107)&(fill[:,:,3]<250)
            for a,b in _runs(longmask[:,width-1]):
                if b-a > 4:
                    start,end=pulse(origin+b),pulse(origin+a)
                    if end>start:
                        chart['note']['fx'][lane].append([start,end-start])
        green = (bar[:,:,0]==102)&(bar[:,:,1]==255)&(bar[:,:,2]==0)&(bar[:,:,3]>0)
        # BPM text sits just right of this column (older pages overlap its edge).
        label = green[:, right-20:min(bar.shape[1],right+34)]
        for a,b in _runs(label.any(axis=1)):
            if b-a != 7:
                continue
            chart['beat']['bpm'].append([pulse(b+1),_read_number(label[a:b])])
        _image_lasers(chart, obj, col, pulse, top, bottom)
    if not chart['beat']['bpm']:
        chart['beat']['bpm'] = [[0,float(meta['bpm'])]]
    bpms = dict(sorted(chart['beat']['bpm']))
    chart['beat']['bpm'] = [list(v) for i,v in enumerate(bpms.items())
                           if i==0 or v[1]!=list(bpms.values())[i-1]]
    if chart['beat']['bpm'][0][0] != 0:
        chart['beat']['bpm'].insert(0,[0,chart['beat']['bpm'][0][1]])
    _sort_notes(chart)
    _join_image_notes(chart)
    return chart


def _image_lasers(chart, obj, col, pulse, top, bottom):
    import numpy as np
    left, right = col['left'], col['right']
    margin = col['margin']
    x0, x1 = max(0,left-margin), min(obj.shape[1],right+margin)
    cut = obj[max(0,top-7):min(obj.shape[0],bottom),x0:x1].astype(int)
    y0 = max(0,top-7)
    r,g,b,alpha = (cut[:,:,i] for i in range(4))
    crossing = (alpha>180)&(abs(r-b)<80)&(b>g+70)&(r>g+50)
    white = (r==255)&(g==255)&(b==255)&(alpha==255)
    # A laser drawn over an FX long is the laser colour composited onto the
    # translucent orange; undo that blend to recognise it.
    fx_alpha = 107/255
    a_total = alpha/255
    a_laser = np.clip((a_total-fx_alpha)/(1-fx_alpha), 0, 1)
    over_fx = []
    for laser_color in ((69,107,249),(250,68,171)):
        predicted = (np.array((255,159,7))[None,None,:]*fx_alpha*(1-a_laser[:,:,None])
                     + np.array(laser_color)[None,None,:]*a_laser[:,:,None])/np.maximum(a_total[:,:,None],1/255)
        distance = abs(predicted-cut[:,:,:3]).max(axis=2)
        over_fx.append((distance<15)&(alpha>140)&(alpha<230))
    for side,color in enumerate(((b>r+70)&(b>g+70), (r>g+100)&(b>g+50)&(r>b+25))):
        mask = (color&(alpha>=90)&(alpha<=180))|crossing|over_fx[side]
        # A white cap and a one-pixel arrow tip mark the section's entry.
        for yy in np.flatnonzero(white.any(axis=1)):
            if yy+6>=len(mask):
                continue
            for xa,xb in _runs(white[yy]):
                if 7<=xb-xa<=9:
                    centre=(xa+xb-1)//2
                    lo,hi=max(0,centre-4),min(mask.shape[1],centre+5)
                    if mask[yy+1,lo:hi].sum()==1 and mask[yy+2,lo:hi].sum()<=3:
                        mask[yy:yy+7,lo:hi]=False
        spans=[]
        for yy in range(len(mask)):
            xs=np.flatnonzero(mask[yy])
            spans.append((int(xs[0])+x0,int(xs[-1])+x0) if len(xs) else None)
        active=mask.any(axis=1)
        # Recover the short gaps left by an opaque button chip.
        for a,b in _runs(~active):
            if a>0 and b<len(active) and b-a<=3:
                active[a:b]=True
        for a,b in _runs(active):
            rows=[(y,*spans[y]) for y in range(a,b) if spans[y] is not None]
            wide=min(v[1] for v in rows)<left-9 or max(v[2] for v in rows)>right+8
            travel,base=(92,left-27) if wide else (46,left-4)
            def pos(x):
                return round(min(1,max(0,(x-base)/travel)),4)
            slam_blocks=[]
            widths=np.array([spans[y] is not None and spans[y][1]-spans[y][0]>11 for y in range(a,b)])
            for sa,sb in _runs(widths):
                sa+=a
                sb+=a
                signatures=Counter(spans[y] for y in range(sa,sb) if spans[y] is not None)
                if max(signatures.values())<3:
                    continue
                if sb-sa<=8:
                    slam_blocks.append((sa,sb))
                else:
                    run=sa
                    for yy in range(sa+1,sb+1):
                        if yy==sb or spans[yy]!=spans[run]:
                            if yy-run>=3:
                                if slam_blocks and run-slam_blocks[-1][1]<3 and yy-slam_blocks[-1][0]<=8:
                                    slam_blocks[-1]=(slam_blocks[-1][0],yy)
                                else:
                                    slam_blocks.append((run,yy))
                            run=yy
            slam_y={y for sa,sb in slam_blocks for y in range(sa,sb)}
            pts={}
            for yy,xa,xb in reversed(rows):
                if yy not in slam_y:
                    pts.setdefault(pulse(y0+yy+1),pos((xa+xb)/2))
            for sa,sb in slam_blocks:
                segment=[v for v in rows if sa<=v[0]<sb]
                lo,hi=min(v[1] for v in segment)+4,max(v[2] for v in segment)-4
                after=[v for v in rows if v[0]<sa and v[0] not in slam_y]
                before=[v for v in rows if v[0]>=sb and v[0] not in slam_y]
                target=(after[-1][1]+after[-1][2])/2 if after else hi if side==0 else lo
                source=(before[0][1]+before[0][2])/2 if before else lo if abs(target-hi)<abs(target-lo) else hi
                pts[pulse(y0+sb)]=[pos(source),pos(target)]
            if not pts:
                continue
            start=pulse(y0+b)
            start=min(start,min(pts))
            if start not in pts:
                pts[start]=next(iter(pts.values()))
            points=[[p-start,v] for p,v in sorted(pts.items())]
            chart['note']['laser'][side].append([start,_simplify_points(points),2 if wide else 1])


def _simplify_points(points):
    # Keep discontinuities and approximate raster curves to under half a pixel.
    result=[]
    for point in points:
        result.append(point)
        while len(result)>=3:
            a,b,c=result[-3:]
            if isinstance(b[1],list):
                break
            va=a[1][-1] if isinstance(a[1],list) else a[1]
            vc=c[1][0] if isinstance(c[1],list) else c[1]
            expected=va+(vc-va)*(b[0]-a[0])/(c[0]-a[0])
            if abs(expected-b[1])>0.005:
                break
            result.pop(-2)
    return result


def _join_image_notes(chart):
    for kind in ('bt','fx'):
        for lane in chart['note'][kind]:
            result=[]
            for p,length in lane:
                if result and result[-1][1] and length and p<=sum(result[-1]):
                    result[-1][1]=max(sum(result[-1]),p+length)-result[-1][0]
                elif result and p==result[-1][0]:
                    result[-1][1]=max(result[-1][1],length)
                else:
                    result.append([p,length])
            lane[:]=result
    for lane in chart['note']['laser']:
        result=[]
        for start,points,width in lane:
            if result and start<=result[-1][0]+result[-1][1][-1][0]:
                if width!=result[-1][2]:
                    if width==1:
                        points=[[p, [0.25+v0/2 for v0 in v] if isinstance(v,list) else 0.25+v/2] for p,v in points]
                    else:
                        result[-1][1]=[[p, [0.25+v0/2 for v0 in v] if isinstance(v,list) else 0.25+v/2] for p,v in result[-1][1]]
                    result[-1][2]=2
                prev=result[-1]
                mapping={p:v for p,v in prev[1]}
                mapping.update({p+start-prev[0]:v for p,v in points})
                prev[1]=[[p,v] for p,v in sorted(mapping.items())]
            else:
                result.append([start,points,width])
        lane[:]=result


def load_sdvxin(chart_dir) -> dict:
    """Read one downloaded chart directory and return a plain KSON dictionary."""
    chart_dir = Path(chart_dir)
    meta = json.loads((chart_dir/'meta.json').read_text(encoding='utf-8'))
    if meta['kind']=='json':
        return _json_chart(json.loads((chart_dir/'chart.json').read_text(encoding='utf-8')),meta)
    if meta['kind']=='image':
        return _image_chart(chart_dir,meta)
    raise ValueError(f"unsupported chart kind: {meta['kind']!r}")


def sdvx_counts(kson) -> dict:
    """Estimate SDVX chain counts from geometry, independently of source counts.

    Laser chains tick every sixteenth note (an eighth at BPM >= 255); a slam
    replaces the regular tick at its pulse and a terminal slam adds one chain.
    Hold chains are empirical: ceil(length / 72 pulses) (doubled at BPM >= 255)
    matches the exact JSON charts within ~2%, while one-per-sixteenth
    overcounts long holds by ~1/6.
    """
    bpms=kson['beat']['bpm']
    def ticks(start,end):
        total=0
        for i,(at,bpm) in enumerate(bpms):
            nxt=bpms[i+1][0] if i+1<len(bpms) else end
            a,b=max(start,at),min(end,nxt)
            if b>a:
                step=120 if bpm>=255 else 60
                total+=(b-a)/step
        return total
    chip=hold=laser=0
    for kind in ('bt','fx'):
        for lane in kson.get('note',{}).get(kind,[]):
            for note in lane:
                p,length=(note,0) if isinstance(note,int) else note
                if length:
                    hold+=max(1,math.ceil(ticks(p,p+length)*60/72-1e-8))
                else:
                    chip+=1
    for lane in kson.get('note',{}).get('laser',[]):
        for p,pts,*_ in lane:
            last=0
            for pt in pts:
                v=pt[1]
                if isinstance(v,list) and v[0]!=v[1]:
                    laser+=math.ceil(ticks(p+last,p+pt[0])-1e-8)
                    last=pt[0]
            laser+=math.ceil(ticks(p+last,p+pts[-1][0])-1e-8)
            v=pts[-1][1]
            laser+=int(isinstance(v,list) and v[0]!=v[1])
    return {'chip':chip,'hold':hold,'laser':laser}


def decode_report(chart_dir) -> dict:
    """Compare decoded chains with the published counts and validate the chart."""
    from .kson import validate
    chart_dir=Path(chart_dir)
    meta=json.loads((chart_dir/'meta.json').read_text(encoding='utf-8'))
    chart=load_sdvxin(chart_dir)
    decoded=sdvx_counts(chart)
    official={k:int(meta['counts'][k]) for k in ('chip','hold','laser')}
    # Chips are exact counts. The laser rule matches the JSON charts within
    # ~1%; the hold rule is an empirical fit, so it only flags gross errors.
    tolerance={'chip':0,'hold':0.05,'laser':0.03}
    matches={k:abs(decoded[k]-official[k])<=tolerance[k]*official[k] for k in decoded}
    errors=[{'path':i.path,'message':i.message} for i in validate(chart) if i.level=='error']
    return {'key':meta.get('key',chart_dir.name),'kind':meta['kind'],'level':meta['level'],
            'decoded':decoded,'official':official,'matches':matches,'errors':errors,
            'ok':all(matches.values()) and not errors}


def report(root, stream=None):
    """Print the same per-chart report used by the CLI and evaluation script."""
    import sys
    stream=stream or sys.stdout
    rows=[]
    for path in sorted(Path(root).glob('*/*/meta.json')):
        row=decode_report(path.parent)
        rows.append(row)
        counts=' '.join(f'{k}={row["decoded"][k]}/{row["official"][k]}' for k in ('chip','hold','laser'))
        print(f'{row["key"]} {row["level"]:g} {counts} {"OK" if row["ok"] else "NG"}',file=stream)
    for kind in ('json','image'):
        group=[r for r in rows if r['kind']==kind]
        if group:
            rates=' '.join(f'{k}={sum(r["matches"][k] for r in group)}/{len(group)}' for k in ('chip','hold','laser'))
            print(f'{kind}: {rates} valid={sum(not r["errors"] for r in group)}/{len(group)}',file=stream)
    return rows


def main(argv=None):
    from .kson import dumps_kson,save_kson
    parser=argparse.ArgumentParser(prog='ksmauto sdvxin')
    parser.add_argument('directory',type=Path)
    parser.add_argument('-o','--output',type=Path)
    parser.add_argument('--report',action='store_true')
    args=parser.parse_args(argv)
    if args.report:
        report(args.directory)
    else:
        chart=load_sdvxin(args.directory)
        if args.output:
            save_kson(chart,args.output)
        else:
            print(dumps_kson(chart),end='')
    return 0
