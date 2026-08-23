import ast
from pathlib import Path

root = Path('backend/app')
problems = []

# 已知需要 await 的异步方法名（可扩展）
ASYNC_METHODS = {"flush", "snapshot", "execute", "commit", "rollback"}

for path in root.rglob('*.py'):
    if '__pycache__' in path.parts:
        continue
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except Exception:
        continue

    # 收集所有被 Await 包裹的 Call 节点的 id()
    awaited_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            value = node.value
            if isinstance(value, ast.Call):
                awaited_calls.add(id(value))

    # 检查所有 Call 节点，若方法名在 ASYNC_METHODS 中且未被 await，则报告
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if id(node) in awaited_calls:
                continue  # 已经 await 了，跳过
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in ASYNC_METHODS:
                    # 仅报告我们明确关心的 metrics 对象，避免大量误报
                    obj = func.value
                    if isinstance(obj, ast.Name) and obj.id == 'metrics':
                        problems.append(f'{path}:{node.lineno} metrics.{func.attr}() 缺少 await')

if problems:
    print('发现的问题：')
    print('\n'.join(problems))
else:
    print('没有发现明显问题')
