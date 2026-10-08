"""COMBO 台詞データ（data/combo/<花id>.json）を検査し、index.html に流し込む。

使い方:
  python tools/build.py           検査 → index.html の COMBO 区間を更新 → review_all.md を再生成
  python tools/build.py --check   検査だけ（ファイルは書き換えない）

データ形式: { "<理由id>": [花言葉, 技法, こじつけ, 締め, ひよりの最後, ツッコミ], ... }
理由id・採用花・花言葉は index.html の RID / FL / KEEP_LOW から読む（正本は HTML 側）。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'index.html'
DATA = ROOT / 'data' / 'combo'
REVIEW = ROOT / 'review_all.md'

START, END = '/*COMBO_START*/', '/*COMBO_END*/'
FIELDS = ['花言葉', '技法', 'こじつけ', '締め', 'ひより', 'ツッコミ']
# 既存264本の実測（最大 64/42/31/22）に少し余裕を持たせた上限。超えたらエラー
LIMIT = {2: 70, 3: 45, 4: 35, 5: 22}


def load_master(html):
    dec = json.JSONDecoder()
    fl, _ = dec.raw_decode(html[html.index('const FL=') + 9:])
    rid_src = re.search(r'const RID=\{(.*?)\}', html).group(1)
    rids = [v for _, v in sorted((int(k), v) for k, v in re.findall(r"(\d+):'(\w+)'", rid_src))]
    keep_low = re.findall(r"'(\w+)'", re.search(r'KEEP_LOW=\[(.*?)\]', html).group(1))
    flowers = [f for f in fl if f['d'] >= 3 or f['id'] in keep_low]
    return flowers, rids


def validate(fid, data, flower, rids):
    errs = []
    if flower is None:
        return [f'{fid}: 採用花に存在しない花id']
    for rid, row in data.items():
        at = f'{fid}/{rid}'
        if rid not in rids:
            errs.append(f'{at}: 未知の理由id')
            continue
        if not (isinstance(row, list) and len(row) == 6 and all(isinstance(x, str) and x.strip() for x in row)):
            errs.append(f'{at}: 6要素の空でない文字列配列ではない')
            continue
        if row[0] not in flower['m']:
            errs.append(f'{at}: 花言葉「{row[0]}」がこの花の花言葉 {flower["m"]} に無い')
        for i, n in LIMIT.items():
            if len(row[i]) > n:
                errs.append(f'{at}: {FIELDS[i]} が {len(row[i])}字（上限{n}）')
        if '、' in row[5]:
            errs.append(f'{at}: ツッコミに「、」がある')
        if '{' in ''.join(row):
            errs.append(f'{at}: 置換記号 {{…}} は COMBO では使わない')
    return errs


def write_review(order, combos, flowers_by_id, rids, causes):
    out = ['# COMBO 台詞一覧（tools/build.py が自動生成・手で編集しない）', '']
    total = sum(len(combos[f]) for f in order)
    out += [f'収録 {total} / {len(flowers_by_id) * len(rids)} 本', '']
    for fid in order:
        f = flowers_by_id[fid]
        out += [f'## {f["name"]}（{fid}・★{f["d"]}）{len(combos[fid])}/{len(rids)}', '']
        for rid in rids:
            if rid not in combos[fid]:
                continue
            m, tech, spin, close, fin, tsk = combos[fid][rid]
            out += [f'### {rid}（{causes[rid]}）『{m}』／{tech}', '',
                    f'- 蒼真: {spin}', f'- 締め: {close}', f'- ひより: {fin}', f'- **{tsk}**', '']
    REVIEW.write_text('\n'.join(out), encoding='utf-8', newline='\n')


def main():
    check_only = '--check' in sys.argv
    html = HTML.read_text(encoding='utf-8')
    flowers, rids = load_master(html)
    by_id = {f['id']: f for f in flowers}

    combos, errs = {}, []
    for p in sorted(DATA.glob('*.json')):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            errs.append(f'{p.name}: JSON として読めない ({e})')
            continue
        errs += validate(p.stem, d, by_id.get(p.stem), rids)
        combos[p.stem] = d

    # 花の並びは FL の順、理由の並びは RID の順で固定（差分を安定させる）
    order = [f['id'] for f in flowers if f['id'] in combos]
    total = sum(len(combos[f]) for f in order)
    target = [f for f in flowers if f['d'] >= 3]
    done = sum(1 for f in target if len(combos.get(f['id'], {})) == len(rids))
    partial = [f'{f["id"]}({len(combos[f["id"]])})' for f in target if 0 < len(combos.get(f['id'], {})) < len(rids)]
    print(f'COMBO {total}本 / ★3以上 {done}/{len(target)}種 完成'
          + (f' / 途中: {", ".join(partial)}' if partial else ''))

    if errs:
        print(f'\n検査エラー {len(errs)}件:')
        print('\n'.join('  ' + e for e in errs))
        sys.exit(1)
    if check_only:
        print('検査OK（--check のため書き込みなし）')
        return

    packed = {fid: {rid: combos[fid][rid] for rid in rids if rid in combos[fid]} for fid in order}
    body = 'const COMBO=' + json.dumps(packed, ensure_ascii=False, separators=(',', ':')) + ';'
    i, j = html.index(START) + len(START), html.index(END)
    HTML.write_text(html[:i] + body + html[j:], encoding='utf-8', newline='\n')

    rs, _ = json.JSONDecoder().raw_decode(html[html.index('RS=[') + 3:])
    rid_src = re.search(r'const RID=\{(.*?)\}', html).group(1)
    causes = {v: rs[int(k)]['cause'] for k, v in re.findall(r"(\d+):'(\w+)'", rid_src)}
    write_review(order, packed, by_id, rids, causes)
    print(f'index.html と {REVIEW.name} を更新した')


if __name__ == '__main__':
    main()
