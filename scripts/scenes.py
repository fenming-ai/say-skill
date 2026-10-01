#!/usr/bin/env python3
"""场景 Markdown 是唯一编辑源；索引可重建。仅使用 Python 标准库。"""
import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ['父母与亲戚', '朋友与人情', '红包与送礼', '认识与约会', '相亲与关系选择', '家长与老师', '父母与孩子', '工作与日常事务']
REQUIRED = {'id', 'title', 'category', 'topic', 'intent', 'relationship', 'decision', 'tunes', 'source_kind', 'sources', 'status', 'keywords'}


def load(root=ROOT):
    tunes = {}
    for path in sorted((root / 'tunes').glob('S[0-9]*.md')):
        tid = path.name.split('-')[0]
        if tid in tunes:
            raise ValueError(f'重复曲目 ID: {tid}')
        text = path.read_text()
        if not re.fullmatch(r'S\d{3,}', tid) or not text.startswith(f'# {tid}｜'):
            raise ValueError(f'{path.name}: 曲目标题或编号错误')
        if not re.search(r'^- 状态：(待重审|候选|已验收)$', text, re.M):
            raise ValueError(f'{tid}: 曲目状态错误')
        tunes[tid] = path
    rows, seen, signatures = [], set(), set()
    source_text = (root / 'references/sources.md').read_text()
    for path in sorted((root / 'scenes/cards').glob('*.md')):
        text = path.read_text()
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            raise ValueError(f'{path.name}: 缺少 JSON frontmatter')
        raw, body = text[4:].split('\n---\n', 1)
        row = json.loads(raw)
        if not isinstance(row, dict) or REQUIRED - row.keys():
            raise ValueError(f'{path.name}: 缺少必要字段')
        for key in REQUIRED - {'tunes', 'sources', 'keywords'}:
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f'{path.name}: {key} 必须为非空字符串')
        for key in ['tunes', 'sources', 'keywords']:
            if not isinstance(row[key], list) or any(not isinstance(x, str) or not x.strip() for x in row[key]):
                raise ValueError(f'{path.name}: {key} 必须为字符串数组')
        sid = row['id']
        if not re.fullmatch(r'C\d{4,}', sid) or path.stem != sid or sid in seen:
            raise ValueError(f'{path.name}: 编号重复或文件名不匹配')
        seen.add(sid)
        if row['category'] not in CATEGORIES or row['status'] not in ['待重审', '候选', '已验收']:
            raise ValueError(f'{sid}: 分类或状态错误')
        if row['source_kind'] not in ['用户素材', '原创迁移', '原创场景']:
            raise ValueError(f'{sid}: 来源类型错误')
        if not row['tunes'] or any(x not in tunes for x in row['tunes']):
            raise ValueError(f'{sid}: 曲目不存在')
        if row['source_kind'] == '原创场景' and row['status'] == '候选':
            raise ValueError(f'{sid}: 纯原创未经验收应为待重审，不能自动升级候选')
        if row['source_kind'] == '原创迁移' and not row['sources']:
            raise ValueError(f'{sid}: 原创迁移须有来源')
        for source in row['sources']:
            if not re.fullmatch(r'[ABX]\d{2}[a-z]?', source) or not re.search(r'\b' + re.escape(source) + r'\b', source_text):
                raise ValueError(f'{sid}: 来源编号不存在: {source}')
        for heading in ['## 适用条件', '## 场景样例', '## 追问与不适用', '## 来源与状态']:
            if heading not in body or not body.split(heading, 1)[1].split('\n## ', 1)[0].strip():
                raise ValueError(f'{sid}: 缺少内容 {heading}')
        if '参考表达：' not in body or 'WHY：' not in body:
            raise ValueError(f'{sid}: 缺少表达或解释')
        if row['status'] == '已验收':
            review = row.get('review')
            if not isinstance(review, str) or not review:
                raise ValueError(f'{sid}: 已验收须链接具体反馈记录')
            feedback = (root / review).resolve()
            if not feedback.is_relative_to(root.resolve()) or feedback.suffix != '.md' or not feedback.is_file():
                raise ValueError(f'{sid}: 人工反馈文件不存在或越界')
        for link in re.findall(r'\]\(([^\s)]+)\)', body):
            if '://' not in link and not link.startswith('#'):
                target = (path.parent / link.split('#')[0]).resolve()
                if not target.is_relative_to(root.resolve()) or not target.is_file():
                    raise ValueError(f'{sid}: 无效本地链接 {link}')
        signature = (row['category'], row['title'], row['intent'], row['decision'])
        if signature in signatures:
            raise ValueError(f'{sid}: 重复场景，合并或说明不同条件')
        signatures.add(signature)
        row['path'] = str(path.relative_to(root))
        rows.append(row)
    if not rows:
        raise ValueError('场景库为空')
    return rows, tunes


def generated(rows, tunes):
    outputs = {'scenes/catalog.json': json.dumps(rows, ensure_ascii=False, indent=2) + '\n'}
    counts = collections.Counter(r['status'] for r in rows)
    intro = ['# 场景分类入口', '', '<!-- 由 scripts/scenes.py build 生成，请编辑 cards 中的场景文件。 -->', '',
             f'共保留 **{len(tunes)} 首曲子、{len(rows)} 个场景**；待重审 {counts["待重审"]}，候选 {counts["候选"]}，已验收 {counts["已验收"]}。数量是材料库存，不是优质样本数。曲目内的场景链接不重复计数。', '',
             '先选分类，再按话题与意图筛选，通常读 1—3 张卡及关联曲子。相似标题不代表条件相同；确认用户是否决定、是否答应过、哪些背景能公开。', '',
             '可运行 `python3 scripts/scenes.py search "红包 不想收" --category 红包与送礼`，默认排除待重审，最多 5 条；返回候选元数据，不自动套用话术。无结果可换关键词或浏览分类，不编造匹配。', '',
             '待重审仅供维护时用 `--include-drafts` 查看，不能从曲目链接绕过限制照搬草稿；有来源的原创迁移也不等于作者原句。没有合适样本时依据当前处境直接表达。', '',
             '这是词面检索，不能识别否定、隐含意图或所有同义词，最终选择由 AI 阅读条件判断。无需 Python 时直接打开下面的分类页。', '']
    for cat in CATEGORIES:
        subset = [r for r in rows if r['category'] == cat]
        name = f'scenes/categories/{cat}.md'
        drafts = sum(r['status'] == '待重审' for r in subset)
        intro.append(f'- [{cat}](categories/{cat}.md)：{len(subset)} 个场景，其中待重审 {drafts}。')
        lines = [f'# {cat}', '', '<!-- 自动生成。只列标题和条件，不加载全部话术。 -->', '']
        active = [r for r in subset if r['status'] != '待重审']
        if not active:
            lines += ['当前只有待重审草稿，没有可作默认范本的卡片；按 SKILL.md 判断处境，不强套。', '']
        for topic in sorted({r['topic'] for r in active}):
            lines += [f'## {topic}', '']
            for r in active:
                if r['topic'] == topic:
                    lines.append(f'- [{r["id"]} {r["title"]}](../cards/{r["id"]}.md) — [{r["status"]} / {r["source_kind"]}] {r["intent"].rstrip("。；")}；{r["decision"].rstrip("。；")}。')
            lines.append('')
        if drafts:
            lines += ['## 待重审草稿（仅维护查阅）', '', '以下不进入默认检索，不代表已认可的说法。', '']
            lines += [f'- [{r["id"]} {r["title"]}](../cards/{r["id"]}.md) — 待重审 / {r["source_kind"]}' for r in subset if r['status'] == '待重审']
        outputs[name] = '\n'.join(lines)
    outputs['scenes/README.md'] = '\n'.join(intro) + '\n'
    return outputs


def rank(rows, query, category=None, intent=None, limit=5, include_drafts=False):
    # ponytail: 词面排序不理解否定；先读候选条件，实际漏召回再补关键词。
    terms = re.findall(r'[\w]+', query.lower())
    scored = []
    for row in rows:
        if row['status'] == '待重审' and not include_drafts:
            continue
        if category and row['category'] != category or intent and row['intent'] != intent:
            continue
        title = row['title'].lower()
        hay = ' '.join([title, row['topic'], row['intent'], row['relationship'], row['decision'], *row['keywords']]).lower()
        score = sum(10 for term in terms if term in hay)
        grams = {term[i:i+2] for term in terms for i in range(len(term)-1)}
        score += sum(2 if gram in title else 1 for gram in grams if gram in hay)
        if score or not terms:
            scored.append((score, row))
    return [r for _, r in sorted(scored, key=lambda x: (-x[0], x[1]['id']))[:limit]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['build', 'check', 'search'])
    p.add_argument('query', nargs='?', default='')
    p.add_argument('--category', choices=CATEGORIES)
    p.add_argument('--intent')
    p.add_argument('--include-drafts', action='store_true', help='维护时查待重审草稿，不作为正常答复范本')
    p.add_argument('--limit', type=int, default=5)
    args = p.parse_args()
    try:
        if not 1 <= args.limit <= 20:
            raise ValueError('--limit 需为 1—20')
        if args.command == 'search':
            rows = json.loads((ROOT / 'scenes/catalog.json').read_text())
            results = rank(rows, args.query, args.category, args.intent, args.limit, args.include_drafts)
            for row in results:
                print(f'{row["id"]} | {row["status"]}/{row["source_kind"]} | {row["category"]} | {row["title"]} | {row["decision"]} | {row["path"]} | {",".join(row["tunes"])}')
            if not results:
                print('没有可用匹配；请换关键词或浏览分类。有些分类仅有待重审草稿，不应强套。')
            return
        rows, tunes = load()
        outputs = generated(rows, tunes)
        # 只替换曲目索引的自动区，维护说明仍由人编辑。
        tune_index = ROOT / 'tunes/README.md'
        text = tune_index.read_text()
        header = ['<!-- catalog:start -->', f'当前 **{len(tunes)} 首曲子、{len(rows)} 个独立场景**。场景分类和状态见[场景入口](../scenes/README.md)。', '', '| ID | 曲目 | 状态 |', '|---|---|---|']
        for tid, path in tunes.items():
            t = path.read_text(); title = t.splitlines()[0].split('｜', 1)[1]
            status = re.search(r'^- 状态：(.*)', t, re.M)
            header.append(f'| {tid} | [{title}]({path.name}) | {status[1] if status else "候选"} |')
        header.append('<!-- catalog:end -->')
        if '<!-- catalog:start -->' not in text:
            raise ValueError('曲目索引缺少自动区标记')
        outputs['tunes/README.md'] = re.sub(r'<!-- catalog:start -->.*?<!-- catalog:end -->', '\n'.join(header), text, flags=re.S)
        stale = []
        for name, content in outputs.items():
            path = ROOT / name
            if args.command == 'build':
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            elif not path.exists() or path.read_text() != content:
                stale.append(name)
        if stale:
            raise ValueError('索引过期，请运行 build：' + ', '.join(stale))
        print(f'{args.command}: {len(tunes)} 首曲子，{len(rows)} 个场景；分类、编号、来源与引用通过')
    except (ValueError, OSError, KeyError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
