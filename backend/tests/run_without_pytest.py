"""无 pytest 环境下的最小运行器（后端容器里没装 pytest）。

pytest 能做的事很多，这里只补我们真正用到的那一小撮：`pytest.mark.anyio`、
`pytest.fixture`，以及 conftest 里的 `migrated_db`。需要参数化/插件就该去装 pytest，
别往这里加功能——它只是"没有 pytest 时也能跑既有用例"的兜底。

用法（在后端容器内跑，指向测试库）：

    T=postgresql+asyncpg://ai_chat:<pwd>@postgres:5432/ai_group_chat_test
    docker exec -e TEST_DATABASE_URL=$T \
                -e TEST_DATABASE_URL_SYNC=${T/+asyncpg/} \
                ai_group_backend python tests/run_without_pytest.py

安全阀：库名不以 `_test` 结尾直接拒绝启动——本运行器会 drop_all + TRUNCATE。
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
import traceback
import types
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


class _Marker:
    """pytest.mark.xxx —— 既当值用（pytestmark = pytest.mark.anyio）也当装饰器用。"""

    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn


class _MarkRegistry:
    """pytest.mark 本体：点任意名字都得到一个 _Marker。"""

    def __getattr__(self, name: str) -> _Marker:
        return _Marker(name)


def _install_pytest_stub() -> None:
    """必须在 import conftest 之前调用（conftest 顶部就 import pytest）。"""
    pytest = types.ModuleType("pytest")

    def fixture(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn

    pytest.mark = _MarkRegistry()
    pytest.fixture = fixture
    sys.modules["pytest"] = pytest


def _guard_test_db() -> None:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        sys.exit("缺少 TEST_DATABASE_URL —— 本运行器只允许跑测试库（会 drop_all + TRUNCATE）")
    dbname = url.rsplit("/", 1)[-1].split("?")[0]
    if not dbname.endswith("_test"):
        sys.exit(f"拒绝启动：库名必须以 _test 结尾（会 drop_all + TRUNCATE），当前 = {dbname}")


def _load(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _FixtureResolver:
    """按名字解析 conftest 里的 fixture，只支持我们实际用的三种形态。"""

    def __init__(self, conftest):
        self._conftest = conftest
        self._cache: dict[str, object] = {}
        self._teardowns: list = []

    async def resolve(self, name: str):
        if name in self._cache:
            return self._cache[name]
        fn = getattr(self._conftest, name, None)
        if fn is None:
            raise LookupError(f"未定义的 fixture: {name}")
        if inspect.isasyncgenfunction(fn):
            gen = fn()
            value = await gen.__anext__()
            self._teardowns.append(gen)
        elif inspect.iscoroutinefunction(fn):
            value = await fn()
        else:
            value = fn()
        self._cache[name] = value
        return value

    async def teardown(self) -> None:
        for gen in reversed(self._teardowns):
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass
            except Exception:
                traceback.print_exc()


async def _run() -> int:
    conftest = _load("conftest", TESTS_DIR / "conftest.py")
    resolver = _FixtureResolver(conftest)

    passed, failures = 0, []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        module = _load(path.stem, path)
        for name in sorted(n for n in dir(module) if n.startswith("test_")):
            fn = getattr(module, name)
            if not callable(fn):
                continue
            try:
                kwargs = {
                    p: await resolver.resolve(p)
                    for p in inspect.signature(fn).parameters
                }
                result = fn(**kwargs)
                if inspect.isawaitable(result):
                    await result
                passed += 1
                print(f"  PASS  {path.name}::{name}")
            except Exception:
                failures.append(f"{path.name}::{name}")
                print(f"  FAIL  {path.name}::{name}")
                traceback.print_exc()
    await resolver.teardown()

    print()
    print(f"RESULT passed={passed} failed={len(failures)}")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    _guard_test_db()
    _install_pytest_stub()
    sys.exit(asyncio.run(_run()))
