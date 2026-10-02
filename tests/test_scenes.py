#!/usr/bin/env python3
"""运行：python3 tests/test_scenes.py；只在临时目录注入坏数据。"""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('scenes', ROOT / 'scripts/scenes.py')
scenes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scenes)


def rejected(root, message):
    try:
        scenes.load(root)
    except ValueError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('坏数据未被拒绝: ' + message)


def main():
    rows, tunes = scenes.load()
    assert len({r['id'] for r in rows}) == len(rows)
    assert scenes.rank(rows, 'qzxw_unrelated_932') == []
    matches = scenes.rank(rows, '红包 不想收', '红包与送礼')
    assert matches and matches[0]['id'] == 'C0101'
    assert matches[0]['source_kind'] == '用户素材'
    assert all(r['id'] != 'C0059' for r in matches)
    assert all(r['status'] != '待重审' for r in scenes.rank(rows, '', limit=1000))
    refusals = scenes.rank(rows, '红包 不想收', '红包与送礼', include_drafts=True)
    assert any(r['id'] == 'C0059' for r in refusals)
    assert scenes.rank(rows, '上课走神', '家长与老师', include_drafts=True)[0]['id'] == 'C0082'
    assert scenes.rank(rows, '朋友刚换工作 中秋祝福 不想约饭')[0]['id'] == 'C0135'
    assert scenes.rank(rows, '孩子最近不愿读英语 怎么问老师')[0]['id'] == 'C0136'
    assert scenes.rank(rows, '开会结束 谁负责 什么时候完成')[0]['id'] == 'C0128'
    assert scenes.rank(rows, '孩子说你烦不烦 少管我')[0]['id'] == 'C0134'
    assert scenes.rank(rows, '刚才没听你说完 怎么重新聊')[0]['id'] == 'C0137'
    assert scenes.rank(rows, '同事总不靠谱 数据没给')[0]['id'] == 'C0139'
    assert scenes.rank(rows, '孩子漏记作业 我们在家会做 请老师配合')[0]['id'] == 'C0141'
    assert scenes.rank(rows, '客户说和家人商量 销售怎么回')[0]['id'] == 'C0143'
    assert scenes.rank(rows, '会议跑题 时间不够')[0]['id'] == 'C0144'
    assert scenes.rank(rows, '对象让我去家里 我只想在外面见')[0]['id'] == 'C0071'
    assert scenes.rank(rows, '相亲见了一次没眼缘 不想往下处')[0]['id'] == 'C0074'
    assert scenes.rank(rows, '下属发感谢红包 我不想拿')[0]['id'] == 'C0145'
    assert scenes.rank(rows, '和另一半吵架 我一直抢话 怎么道歉')[0]['id'] == 'C0138'
    assert scenes.rank(rows, '爱人总加班 我想让他陪我')[0]['id'] == 'C0146'
    assert scenes.rank(rows, '爸妈说给我买了最爱喝的饮料 怎么回')[0]['id'] == 'C0149'
    only = scenes.rank(rows, '红包', '红包与送礼', '拒收转账', include_drafts=True)
    assert only and all(r['intent'] == '拒收转账' for r in only)
    assert all(r['category'] == '红包与送礼' for r in refusals)
    assert len(scenes.rank(rows, '', limit=3)) == 3

    reviewed = copy.deepcopy(next(r for r in rows if r['id'] == 'C0101'))
    plain = copy.deepcopy(reviewed)
    reviewed['id'] = 'C9999'
    reviewed['review_priority'] = True
    plain['id'] = 'C0000'
    plain.pop('review')
    plain.pop('review_priority')
    assert scenes.rank([plain, reviewed], '红包', limit=2)[0]['id'] == 'C9999'

    cold_cases = json.loads((ROOT / 'tests/cold-read-cases.json').read_text())
    assert len(cold_cases) == 30
    assert len({case['id'] for case in cold_cases}) == 30
    assert {case['category'] for case in cold_cases} == set(scenes.CATEGORIES)
    by_id = {row['id']: row for row in rows}
    for case in cold_cases:
        assert set(case) == {'id', 'category', 'prompt', 'decision', 'allowed', 'forbidden', 'expected_scene', 'anchor'}
        assert all(isinstance(case[key], str) and case[key].strip() for key in ['id', 'category', 'prompt', 'decision', 'expected_scene', 'anchor'])
        assert case['allowed'] and all(isinstance(value, str) and value for value in case['allowed'])
        assert all(isinstance(value, str) and value for value in case['forbidden'])
        assert not any(value in case['anchor'] for value in case['forbidden'])
        expected = by_id[case['expected_scene']]
        assert expected['category'] == case['category'] and expected['status'] != '待重审'
        matches = scenes.rank(rows, case['prompt'])
        assert matches and matches[0]['id'] == case['expected_scene'], (case['id'], [row['id'] for row in matches])

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        for name in ['scenes', 'tunes', 'references', 'scripts', 'tests']:
            shutil.copytree(ROOT / name, temp / name)
        path = temp / 'scenes/cards/C0059.md'
        original = path.read_text()
        raw, body = original[4:].split('\n---\n', 1)
        row = json.loads(raw)

        def put(data, text=body):
            path.write_text('---\n' + json.dumps(data, ensure_ascii=False) + '\n---\n' + text)

        for changes, error in [({'tunes': ['S999']}, '曲目不存在'),
                               ({'status': '候选'}, '纯原创未经验收应为待重审'),
                               ({'sources': ['B99']}, '来源编号不存在'),
                               ({'category': '不存在'}, '分类或状态错误'),
                               ({'id': 'C0001'}, '编号重复或文件名不匹配'),
                               ({'source_kind': '原创迁移', 'sources': []}, '原创迁移须有来源'),
                               ({'review_priority': True}, '反馈优先须有正向反馈记录'),
                               ({'status': '已验收', 'review': '../../outside.md'}, '人工反馈文件不存在或越界')]:
            put(dict(row, **changes)); rejected(temp, error)
        put(row, body + '\n[丢失文件](missing.md)\n'); rejected(temp, '无效本地链接')
        put(row)
        duplicate = dict(row, id='C9999')
        (temp / 'scenes/cards/C9999.md').write_text('---\n'+json.dumps(duplicate, ensure_ascii=False)+'\n---\n'+body)
        rejected(temp, '重复场景')
        (temp / 'scenes/cards/C9999.md').unlink()
        path.write_text('---\n{invalid}\n---\n'+body); rejected(temp, 'Expecting')
        path.write_text(original)
        command = [sys.executable, str(temp / 'scripts/scenes.py')]
        for action in ['build', 'check']:
            result = subprocess.run(command + [action], capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
        result = subprocess.run(command + ['search', '红包', '--category', '红包与送礼'], capture_output=True, text=True)
        assert result.returncode == 0 and 'C0059' not in result.stdout
        result = subprocess.run(command + ['search', '红包', '--category', '红包与送礼', '--include-drafts'], capture_output=True, text=True)
        assert result.returncode == 0 and '待重审/原创场景' in result.stdout
        catalog = temp / 'scenes/catalog.json'
        catalog.write_text('[]\n')
        result = subprocess.run(command + ['check'], capture_output=True, text=True)
        assert result.returncode != 0 and '索引过期' in result.stderr
        assert catalog.read_text() == '[]\n', 'check 不得写入文件'
        result = subprocess.run(command + ['search', '红包', '--limit', '0'], capture_output=True, text=True)
        assert result.returncode != 0

    # ponytail: 合成元数据只验证千条检索可运行，不证明语义命中率。
    large = [dict(copy.deepcopy(rows[i % len(rows)]), id=f'C{i+1:04}') for i in range(1000)]
    start = time.perf_counter()
    assert len(scenes.rank(large, '红包 不想收', '红包与送礼', include_drafts=True)) == 5
    elapsed = time.perf_counter() - start
    assert json.loads(scenes.generated(large, tunes)['scenes/catalog.json']) == large
    print(f'通过：30 条冷读路由、用户反馈优先、真实库检索、坏数据拒绝、索引过期与只读检查；1000 条合成元数据检索 {elapsed:.4f}s（不代表语义质量）。')


if __name__ == '__main__':
    main()
