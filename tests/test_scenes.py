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
    refusals = scenes.rank(rows, '红包 不想收', '红包与送礼')
    assert any(r['id'] == 'C0059' for r in refusals)
    assert scenes.rank(rows, '上课走神', '家长与老师')[0]['id'] == 'C0082'
    only = scenes.rank(rows, '红包', '红包与送礼', '拒收转账')
    assert only and all(r['intent'] == '拒收转账' for r in only)
    assert all(r['category'] == '红包与送礼' for r in refusals)
    assert len(scenes.rank(rows, '', limit=3)) == 3

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        for name in ['scenes', 'tunes', 'references', 'scripts']:
            shutil.copytree(ROOT / name, temp / name)
        path = temp / 'scenes/cards/C0059.md'
        original = path.read_text()
        raw, body = original[4:].split('\n---\n', 1)
        row = json.loads(raw)

        def put(data, text=body):
            path.write_text('---\n' + json.dumps(data, ensure_ascii=False) + '\n---\n' + text)

        for changes, error in [({'tunes': ['S999']}, '曲目不存在'),
                               ({'sources': ['B99']}, '来源编号不存在'),
                               ({'category': '不存在'}, '分类或状态错误'),
                               ({'id': 'C0001'}, '编号重复或文件名不匹配'),
                               ({'source_kind': '原创迁移', 'sources': []}, '原创迁移须有来源'),
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
    assert len(scenes.rank(large, '红包 不想收', '红包与送礼')) == 5
    elapsed = time.perf_counter() - start
    assert json.loads(scenes.generated(large, tunes)['scenes/catalog.json']) == large
    print(f'通过：真实库检索、坏数据拒绝、索引过期与只读检查；1000 条合成元数据检索 {elapsed:.4f}s（不代表语义质量）。')


if __name__ == '__main__':
    main()
