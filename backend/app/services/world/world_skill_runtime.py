"""
文件式 skill/tool 运行时 — 世界能力动态扩展（2026-08-06）

两个作用域（造物主 ≠ 居民）：
- 设计侧：data/world_ai_skills/<name>/   → 世界设计 AI（造物主）的工具库，全局共享，
  造物主在世界之外设计世界，其工具不混入世界内容
- 世界侧：data/worlds/{id}/skills/<name>/ → 世界颁布的能力（居民/管理者/物品），
  world_command 等世界内能力属于这里

skill 目录约定（每目录一个 skill）：
- manifest.json:
    {
      "name": "skill 名（工具名）",
      "description": "给 LLM 看的描述",
      "arguments": { "type": "object", "properties": {...}, "required": [...] },  # json-schema
      "permissions": ["file:read", "file:write", "world:read", "group:send", ...] # 能力清单
    }
- code.py:
    async def run(args: dict, ctx) -> dict
    ctx 只包含 manifest.permissions 声明过的能力（capability-based，能力最小化）

安全模型（v1 进程内 harness）：
- import 白名单（ast 扫描 code.py 的 import，仅标准库安全子集）
- builtins 收紧（禁 open/eval/exec/compile/input/breakpoint/__import__ 等）
- ctx 能力注入：无任何宿主对象/模块引用，唯一出口是 ctx
- 超时强杀（asyncio.wait_for）
- 信任边界：世界创作者（或其 AI）编写的代码——防"AI 生成代码越权乱来"；
  对抗性恶意代码需后置 subprocess/seccomp 沙箱（2.1 生产加固，待珑哥定）
"""
from __future__ import annotations

import ast
import asyncio
import builtins
import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

AI_SKILLS_DIR = Path("data/world_ai_skills")
WORLDS_DIR = Path("data/worlds")
SKILL_TIMEOUT = 30  # skill 单次执行超时（秒）

# ── import 白名单（标准库安全子集：不碰文件系统/网络/进程） ──
SAFE_IMPORTS = {
    "abc", "array", "asyncio", "base64", "binascii", "bisect", "collections",
    "contextlib", "copy", "dataclasses", "datetime", "decimal", "difflib",
    "enum", "functools", "hashlib", "heapq", "itertools", "json", "math",
    "operator", "random", "re", "statistics", "string", "textwrap", "time",
    "typing", "unicodedata", "urllib.parse", "uuid", "zoneinfo",
}
# 明确拒绝（防御性名单，白名单之外本就拒绝）
FORBIDDEN_IMPORTS = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "glob", "io",
    "pickle", "marshal", "shelve", "sqlite3", "ctypes", "cffi", "importlib",
    "builtins", "threading", "multiprocessing", "signal", "resource",
    "http", "urllib.request", "urllib.error", "requests", "aiohttp",
    "ftplib", "smtplib", "telnetlib", "ssl", "cryptography", "tempfile",
    "platform", "pwd", "grp", "webbrowser", "tkinter", "curses",
}
# builtins 禁用清单（open 等是进程内 harness 的根本出口）
FORBIDDEN_BUILTINS = {
    "open", "eval", "exec", "compile", "input", "breakpoint", "help",
    "memoryview", "exit", "quit", "copyright", "credits", "license",
}


@dataclass
class SkillDef:
    name: str
    description: str
    arguments: dict
    permissions: list[str] = field(default_factory=list)
    code_path: Path = None  # type: ignore[assignment]
    scope: str = "world"  # "ai" = 设计侧（造物主） | "world" = 世界侧（居民）


# ── manifest 解析 ──
def _load_manifest(dir_path: Path, scope: str) -> SkillDef | None:
    manifest_path = dir_path / "manifest.json"
    code_path = dir_path / "code.py"
    if not (manifest_path.exists() and code_path.exists()):
        return None
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = str(m.get("name") or "").strip()
        if not name or not name.replace("_", "").isalnum():
            logger.warning(f"📦 skill manifest 非法名字: {manifest_path}")
            return None
        return SkillDef(
            name=name,
            description=str(m.get("description") or "").strip(),
            arguments=m.get("arguments") or {"type": "object", "properties": {}},
            permissions=[str(p) for p in (m.get("permissions") or [])],
            code_path=code_path,
            scope=scope,
        )
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"📦 skill manifest 解析失败 {manifest_path}: {e}")
        return None


def list_ai_skills() -> list[SkillDef]:
    """设计侧（造物主工具库，全局共享，所有世界的设计 AI 可用）"""
    if not AI_SKILLS_DIR.is_dir():
        return []
    return [
        s for d in sorted(AI_SKILLS_DIR.iterdir())
        if d.is_dir() and (s := _load_manifest(d, "ai")) is not None
    ]


def list_world_skills(world_id: int) -> list[SkillDef]:
    """世界侧（世界颁布的居民能力）"""
    skills_dir = WORLDS_DIR / str(world_id) / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        s for d in sorted(skills_dir.iterdir())
        if d.is_dir() and (s := _load_manifest(d, "world")) is not None
    ]


def build_skill_tools(world_id: int) -> list[dict]:
    """把该世界可用的文件式 skill 转成 function calling 定义（合并进 WORLD_TOOLS）"""
    tools = []
    for skill in [*list_ai_skills(), *list_world_skills(world_id)]:
        tools.append({
            "type": "function",
            "function": {
                "name": skill.name,
                "description": skill.description,
                "parameters": skill.arguments,
            },
        })
    return tools


def find_skill(world_id: int, name: str) -> SkillDef | None:
    for skill in [*list_ai_skills(), *list_world_skills(world_id)]:
        if skill.name == name:
            return skill
    return None


# ── 安全加载 ──
class SkillSecurityError(ValueError):
    pass


def _check_imports(code_src: str, path: str) -> None:
    """ast 扫描 import：白名单之外一律拒绝"""
    try:
        tree = ast.parse(code_src)
    except SyntaxError as e:
        raise SkillSecurityError(f"skill 代码语法错误: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0] if alias.name else ""
                _check_module(mod, path)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_module(node.module, path)


def _check_module(module: str, path: str) -> None:
    top = module.split(".")[0]
    if top in FORBIDDEN_IMPORTS or module not in SAFE_IMPORTS:
        raise SkillSecurityError(f"skill {path} 禁止导入模块: {module}")


def _load_code(skill: SkillDef):
    """安全加载 code.py：import 白名单 + builtins 收紧 → 返回 run 函数"""
    code_src = skill.code_path.read_text(encoding="utf-8")
    _check_imports(code_src, skill.code_path.name)

    safe_builtins = dict(vars(builtins))
    for k in FORBIDDEN_BUILTINS:
        safe_builtins.pop(k, None)

    def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if level != 0:
            raise SkillSecurityError("相对导入禁止")
        _check_module(name, skill.code_path.name)
        return _real_import(name, globals, locals, fromlist, level)

    _real_import = builtins.__import__
    safe_builtins["__import__"] = _safe_import

    namespace = {
        "__builtins__": safe_builtins,
        "__name__": f"world_skill_{skill.name}",
        "__file__": str(skill.code_path),
    }
    exec(compile(code_src, str(skill.code_path), "exec"), namespace)
    run_fn = namespace.get("run")
    if not callable(run_fn):
        raise SkillSecurityError(f"skill {skill.name} 未定义 async def run(args, ctx)")
    return run_fn


# ── ctx 能力注入（capability-based） ──
class _FileCtx:
    """世界文件夹受控访问（隔离目录 + 扩展名白名单，复用 world_file_service）"""

    def __init__(self, world_id: int, perms: set[str]):
        self._world_id = world_id
        self._perms = perms

    def _need(self, perm: str) -> None:
        if perm not in self._perms:
            raise PermissionError(f"未声明权限 {perm}（manifest.permissions 里加上才能用）")

    def list(self, prefix: str = "") -> list:
        self._need("file:list")
        from app.services.world.world_file_service import list_files
        return list_files(self._world_id, prefix)

    def read(self, path: str) -> str:
        self._need("file:read")
        from app.services.world.world_file_service import read_file
        return read_file(self._world_id, path).get("content", "")

    def write(self, path: str, content: str) -> None:
        self._need("file:write")
        from app.services.world.world_file_service import write_file
        write_file(self._world_id, path, content)

    def delete(self, path: str) -> None:
        self._need("file:delete")
        from app.services.world.world_file_service import delete_file
        delete_file(self._world_id, path)


class _WorldCtx:
    """世界信息读取/更新"""

    def __init__(self, db, world, perms: set[str]):
        self._db = db
        self._world = world
        self._perms = perms

    def get(self) -> dict:
        self._need("world:read")
        return {"id": self._world.id, "name": self._world.name,
                "description": self._world.description, "status": self._world.status}

    async def update(self, **patch: str) -> dict:
        self._need("world:update")
        from app.services.world.world_service import update_world
        return await update_world(self._db, self._world.id, self._world.owner_id, **patch)

    def _need(self, perm: str) -> None:
        if perm not in self._perms:
            raise PermissionError(f"未声明权限 {perm}")


class _GroupCtx:
    """绑定群消息（以世界主人身份，默认本世界绑定群）"""

    def __init__(self, db, world, perms: set[str]):
        self._db = db
        self._world = world
        self._perms = perms

    async def send(self, content: str) -> dict:
        self._need("group:send")
        from app.chat.message import create_message, get_group
        from app.models.world import WorldBinding
        from sqlalchemy import select
        rows = (await self._db.execute(
            select(WorldBinding.group_id).where(WorldBinding.world_id == self._world.id)
        )).scalars().all()
        if not rows:
            return {"success": False, "error": "本世界未绑定任何群聊"}
        gid = rows[0]
        group = await get_group(self._db, gid)
        if not group:
            return {"success": False, "error": "绑定群不存在"}
        msg = await create_message(self._db, gid, self._world.owner_id, content,
                                   sender_type="user", sender_id=str(self._world.owner_id))
        return {"success": True, "message_id": getattr(msg, "id", None)}

    def _need(self, perm: str) -> None:
        if perm not in self._perms:
            raise PermissionError(f"未声明权限 {perm}")


def _build_ctx(db, world, permissions: list[str]):
    """按 manifest.permissions 构造受控 ctx（属性访问风格：ctx.file.list() / ctx.group.send()）"""
    from types import SimpleNamespace

    perms = set(permissions)
    ctx: dict = {
        "log": lambda *a: logger.info(f"🌐 skill[{world.id}] " + " ".join(str(x) for x in a)),
    }
    if perms & {"file:read", "file:write", "file:list", "file:delete"}:
        ctx["file"] = _FileCtx(world.id, perms)
    if perms & {"world:read", "world:update"}:
        ctx["world"] = _WorldCtx(db, world, perms)
    if "group:send" in perms:
        ctx["group"] = _GroupCtx(db, world, perms)
    return SimpleNamespace(**ctx)


# ── 执行入口 ──
async def execute_skill(db, world, name: str, arguments: str) -> dict | None:
    """执行文件式 skill；名字不匹配任何 skill 时返回 None（由调用方走未知工具兜底）"""
    skill = find_skill(world.id, name)
    if skill is None:
        return None
    try:
        args = json.loads(arguments or "{}") if isinstance(arguments, str) else (arguments or {})
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        return {"success": False, "error": "参数解析失败"}

    try:
        run_fn = _load_code(skill)
    except (SkillSecurityError, OSError) as e:
        logger.warning(f"🌐 skill {name} 加载失败: {e}")
        return {"success": False, "error": f"skill 加载失败: {e}"}

    ctx = _build_ctx(db, world, skill.permissions)
    try:
        result = await asyncio.wait_for(run_fn(args, ctx), timeout=SKILL_TIMEOUT)
    except asyncio.TimeoutError:
        return {"success": False, "error": f"skill {name} 执行超时（{SKILL_TIMEOUT}s）"}
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 —— skill 代码是外部输入，错误要兜住
        logger.warning(f"🌐 skill {name} 执行出错: {e!r}")
        return {"success": False, "error": f"skill 执行出错: {e}"}

    if not isinstance(result, dict):
        result = {"success": True, "result": result}
    return result
