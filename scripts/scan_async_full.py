import ast
from pathlib import Path

root = Path('backend/app')
problems = []

# 只检查这些常见对象名，避免误报
OBJ_NAMES = {"db", "repo", "session", "audit_repo", "content_repo", "world_repo", "memory_repo", "skill_repo", "friend_repo", "user_repo", "invitation_repo", "search_repo", "cap_repo", "invite_repo", "export_repo", "infra_repo", "plugin_repo", "federation_repo"}
# 这些方法通常是异步的
ASYNC_METHODS = {"execute", "commit", "rollback", "get"}

for path in root.rglob('*.py'):
    if '__pycache__' in path.parts:
        continue
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except Exception:
        continue

    # 收集已被 await 的调用
    awaited_calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Await):
            value = node.value
            if isinstance(value, ast.Call):
                awaited_calls.add(id(value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if id(node) in awaited_calls:
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in ASYNC_METHODS:
                    obj = func.value
                    if isinstance(obj, ast.Name) and obj.id in OBJ_NAMES:
                        problems.append(f'{path}:{node.lineno} {obj.id}.{func.attr}() 缺少 await')

if problems:
    print('发现疑似遗漏：')
    print('\n'.join(problems))
else:
    print('没有发现明显问题')
