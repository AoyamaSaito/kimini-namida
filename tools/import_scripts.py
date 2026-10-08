"""台本工房（生成アーティファクト）から読み出した台本を、ゲーム用データに変換する。

使い方:
  1. Claude が ArtifactData で台本を gen_raw/all/scripts/*.json に読み出す
  2. python tools/import_scripts.py   → data/scripts/<花id>.json を作り直す
  3. python tools/build.py            → index.html に流し込む

取り込む条件: プロンプトが v3〜v6、判定がボツ（ng）でないもの。
整形: ツッコミの句読点（「、」削除・文末「。」削除・文中「。」→全角スペース）、台詞の括弧の片割れ削除。
出力形式: { "<理由id>": [ {"l": [["b|g|n", 台詞], ...], "m": 花言葉, "t": 技法, "k": こじつけ度, "s": ツッコミ}, ... ] }
"""
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'gen_raw' / 'all' / 'scripts'
OUT = ROOT / 'data' / 'scripts'
OK_PROMPTS = {'artifact-v3', 'artifact-v4', 'artifact-v5', 'artifact-v6'}
WHO = {'boy': 'b', 'girl': 'g', 'narration': 'n'}
PAIRS = {'「': '」', '『': '』'}


def tidy_tsk(s):
    s = re.sub(r'[、，]', '', str(s).strip())
    s = re.sub(r'[。．]+$', '', s)
    return re.sub(r'[。．]\s*', '　', s)


def fix_brackets(s):
    """対になっていない「」『』を取り除く（生成時の書き損じ対策）"""
    keep, stack = [True] * len(s), []
    closers = {v: k for k, v in PAIRS.items()}
    for i, c in enumerate(s):
        if c in PAIRS:
            stack.append((c, i))
        elif c in closers:
            if stack and stack[-1][0] == closers[c]:
                stack.pop()
            else:
                keep[i] = False
    for _, i in stack:
        keep[i] = False
    return ''.join(c for c, k in zip(s, keep) if k)


def main():
    by_flower = defaultdict(lambda: defaultdict(list))
    stats = defaultdict(int)
    for p in sorted(glob.glob(str(SRC / '*.json'))):
        doc = json.load(open(p, encoding='utf-8'))
        d = doc.get('data', doc)
        if d.get('prompt') not in OK_PROMPTS:
            stats['古い版で除外'] += 1
            continue
        if d.get('status') == 'ng':
            stats['ボツで除外'] += 1
            continue
        lines = [[WHO.get(l['who'], 'n'), fix_brackets(l['text'])] for l in d['lines'] if l.get('text')]
        if len(lines) < 3:
            stats['行不足で除外'] += 1
            continue
        by_flower[d['fid']][d['rid']].append({
            'l': lines, 'm': d['used_meaning'], 't': d['technique'],
            'k': int(d['kojitsuke']), 's': tidy_tsk(d['tsukkomi']), '_c': d['createdAt'],
        })
        stats['採用' if d.get('status') == 'ok' else '未判定'] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.json'):
        old.unlink()
    for fid, rs in sorted(by_flower.items()):
        packed = {rid: [{k: v for k, v in x.items() if k != '_c'} for x in sorted(items, key=lambda x: x['_c'])]
                  for rid, items in sorted(rs.items())}
        (OUT / f'{fid}.json').write_text(
            '{\n' + ',\n'.join(f'  {json.dumps(r)}: {json.dumps(v, ensure_ascii=False)}' for r, v in packed.items()) + '\n}\n',
            encoding='utf-8', newline='\n')
    combos = sum(len(rs) for rs in by_flower.values())
    print(f'取り込み: {dict(stats)} → {len(by_flower)}種・{combos}組み合わせ')


if __name__ == '__main__':
    main()
