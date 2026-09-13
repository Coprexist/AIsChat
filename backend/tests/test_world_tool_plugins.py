"""世界工具插件的结构守卫（静态检查，不依赖数据库、不需要 pytest 插件）。

机械拆分和手写都可能留下**只有真正调用时才炸**的名字错误——比如 import 用了别名却按原名调用。
这里用标准库 symtable 做作用域分析，把「引用了但没定义」的名字挡在 CI：
社区作者手写插件时同样受益（名字写错，测试直接指出来）。
"""
from __future__ import annotations

import builtins
import pathlib
import symtable

WORLD_TOOLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "app" / "tools" / "world"
_FRAMEWORK = {"base.py", "shared.py", "__init__.py", "_template.py"}


def _plugin_files() -> list[pathlib.Path]:
    return [p for p in sorted(WORLD_TOOLS_DIR.glob("*.py")) if p.name not in _FRAMEWORK]


def _undefined_names(path: pathlib.Path) -> list[str]:
    top = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
    module_names = {
        s.get_name() for s in top.get_symbols()
        if s.is_assigned() or s.is_imported() or s.is_namespace()
    }

    def walk(table: symtable.SymbolTable, bad: list[str]) -> None:
        for sym in table.get_symbols():
            name = sym.get_name()
            if not sym.is_referenced():
                continue
            if sym.is_local() or sym.is_parameter() or sym.is_imported() or sym.is_namespace():
                continue
            if sym.is_free() or name in module_names or hasattr(builtins, name):
                continue
            bad.append(name)
        for child in table.get_children():
            walk(child, bad)

    bad: list[str] = []
    walk(top, bad)
    return sorted(set(bad))


def test_plugin_files_and_registration():
    """一个工具一个文件：文件在，且都真的注册出了同名插件"""
    from app.tools.world import WorldToolRegistry

    files = _plugin_files()
    assert len(files) >= 30, f"世界工具文件少得可疑：{len(files)}"

    missing = [p.name for p in files if WorldToolRegistry.get(p.stem) is None]
    assert not missing, f"这些文件没有注册出同名插件：{missing}"


def test_plugin_has_no_undefined_names():
    """引用了但没定义的名字（只有运行时才会炸的那种）"""
    offenders = {p.name: _undefined_names(p) for p in _plugin_files()}
    bad = {k: v for k, v in offenders.items() if v}
    assert not bad, f"这些插件引用了未定义的名字：{bad}"
