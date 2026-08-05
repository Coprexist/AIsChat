"""
世界代码沙箱（阶段 2.1 MVP）— subprocess + resource.rlimit + 超时强制杀进程组

方案（珑哥定）：成本最低、代码最简单，快速验证"世界代码执行"核心流程。
生产加固（后置）：只担心资源耗尽 → 加严配额；需强安全边界 → seccomp+Landlock（evalbox 路线）或容器。

设计参考 sandtrap 的 Policy 模式：
- Policy：timeout / memory_mb / cpu_seconds 集中配置，每世界配额从 worlds.config 读取（默认 24MB）
- 执行：python3 -I 子进程（隔离模式：不吃用户 site、不继承 PYTHON* 环境），start_new_session 独立进程组
- 隔离：cwd 锁世界目录；env 白名单（不泄漏 DATABASE_URL/JWT 等后端密钥）；rlimit 内存/CPU/文件大小/进程数
- 超时：killpg 强杀整个进程组（含子进程/孙进程）
"""
import asyncio
import json
import logging
import os
import resource
import signal
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_MB = 24          # 无人/后台内存配额（sleep_memory_mb 可覆盖）——珑哥定义：没人在时最多给世界配多少
DEFAULT_RUNTIME_MEMORY_MB = 128  # 有人在线内存配额（runtime_memory_mb 可覆盖）——珑哥 2026-08-05 定
DEFAULT_TIMEOUT_SECONDS = 10.0  # 默认墙钟超时
DEFAULT_CPU_SECONDS = 5.0       # 默认 CPU 时间上限
MAX_FSIZE_BYTES = 4 * 1024 * 1024   # 单文件写入上限 4MB（防写爆磁盘）
MAX_NPROC = 16                  # 子进程数上限（防 fork 炸弹）
MAX_OUTPUT_CHARS = 20000        # stdout/stderr 各截断长度


@dataclass
class Policy:
    """沙箱配额（集中配置，参考 sandtrap Policy 模式）

    memory_mb=None 表示不设内存上限（保留能力，当前默认有人在线 128MB）
    """
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_mb: int | None = DEFAULT_RUNTIME_MEMORY_MB
    cpu_seconds: float = DEFAULT_CPU_SECONDS


def policy_for_world(world, background: bool = False) -> Policy:
    """世界配额（worlds.config 可配）：
    - 无人/后台（background=True）：内存 = sleep_memory_mb（默认 24MB）
    - 有人/前台（background=False）：内存 = runtime_memory_mb（默认 128MB，珑哥 2026-08-05 定）
    超时/CPU 恒生效（保护宿主不受死循环拖累）。
    """
    cfg = world.config or {}
    try:
        timeout = float(cfg.get("sandbox_timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    try:
        cpu = float(cfg.get("cpu_quota") or DEFAULT_CPU_SECONDS)
    except (TypeError, ValueError):
        cpu = DEFAULT_CPU_SECONDS

    if background:
        try:
            memory = int(cfg.get("sleep_memory_mb") or DEFAULT_MEMORY_MB)
        except (TypeError, ValueError):
            memory = DEFAULT_MEMORY_MB
        memory = max(8, min(memory, 512))
    else:
        try:
            memory = int(cfg.get("runtime_memory_mb") or DEFAULT_RUNTIME_MEMORY_MB)
        except (TypeError, ValueError):
            memory = DEFAULT_RUNTIME_MEMORY_MB
        memory = max(16, min(memory, 2048))

    return Policy(
        timeout_seconds=max(1.0, min(timeout, 120.0)),
        memory_mb=memory,
        cpu_seconds=max(1.0, min(cpu, 60.0)),
    )


def _world_dir(world_id: int) -> Path:
    """世界文件夹（与 world_file_service 同源：data/worlds/{id}/）"""
    return (Path("data/worlds") / str(world_id)).resolve()


def _apply_rlimits(policy: Policy) -> None:
    """子进程内设置资源限制（preexec_fn 中执行，必须在 exec 之前）"""
    if policy.memory_mb is not None:
        mem_bytes = policy.memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    cpu = int(policy.cpu_seconds)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FSIZE_BYTES, MAX_FSIZE_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (MAX_NPROC, MAX_NPROC))
    except (ValueError, OSError):
        pass  # 部分系统不可用（如非 root 调整 hard limit），尽力而为


def _sanitized_env(world) -> dict:
    """env 白名单：不继承后端密钥（DATABASE_URL/JWT_SECRET/API Key 等），只给运行必需项。

    2.3 受控数据 API：注入 WORLD_API_TOKEN / WORLD_API_BASE（世界代码经代理访问
    世界数据/对话状态；token 每世界一个、只对本世界数据有效，不是后端密钥）。
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "TZ": os.environ.get("TZ", "Asia/Shanghai"),
        "HOME": "/tmp",
        "WORLD_ID": str(world.id),
    }
    cfg = world.config or {}
    token = cfg.get("api_token")
    if isinstance(token, str) and token:
        env["WORLD_API_TOKEN"] = token
        env["WORLD_API_BASE"] = os.environ.get(
            "WORLD_API_BASE", f"http://127.0.0.1:8000/world/{world.id}/api"
        )
    return env


def _truncate(s: str) -> str:
    if len(s) > MAX_OUTPUT_CHARS:
        return s[:MAX_OUTPUT_CHARS] + f"\n…[输出已截断，前 {MAX_OUTPUT_CHARS} 字符]"
    return s


async def run_world_code(
    world,
    code: str | None = None,
    entry: str | None = None,
    background: bool = False,
) -> dict:
    """
    在沙箱中运行世界 Python 代码。

    - code：直接执行的脚本（自动写入世界目录临时文件再跑，世界内相对导入可用）
    - entry：世界文件夹内的入口文件（相对路径，如 main.py）
    - background：True=无人/后台执行（内存按 sleep_memory_mb，默认 24MB）；False=有人在线（MVP 不设内存上限）
    二者必给其一（entry 优先）。

    返回：{success, stdout, stderr, exit_code, duration_ms, timed_out, reason}
    """
    policy = policy_for_world(world, background=background)
    workdir = _world_dir(world.id)
    workdir.mkdir(parents=True, exist_ok=True)

    tmp_file: Path | None = None
    target: Path | None = None
    try:
        if entry:
            target = (workdir / entry).resolve()
            # 防越界：入口必须在世界目录内
            if not str(target).startswith(str(workdir)):
                return {"success": False, "stdout": "", "stderr": "", "exit_code": -1,
                        "duration_ms": 0, "timed_out": False, "reason": f"入口文件越界: {entry}"}
            if not target.exists():
                return {"success": False, "stdout": "", "stderr": "", "exit_code": -1,
                        "duration_ms": 0, "timed_out": False, "reason": f"入口文件不存在: {entry}"}
        elif code:
            tmp_file = workdir / f".sandbox_{uuid.uuid4().hex[:8]}.py"
            tmp_file.write_text(code, encoding="utf-8")
            target = tmp_file
        else:
            return {"success": False, "stdout": "", "stderr": "", "exit_code": -1,
                    "duration_ms": 0, "timed_out": False, "reason": "code 和 entry 至少给一个"}

        cmd = [sys.executable, "-I", "-X", "utf8", str(target)]  # -I 隔离（不吃 site/忽略 PYTHON* 环境）；-X utf8 强制 UTF-8（世界代码 print 中文必需）
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workdir),
            env=_sanitized_env(world),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,          # 独立进程组 → 超时可 killpg 连子进程一起杀
            preexec_fn=lambda: _apply_rlimits(policy),
        )

        t0 = asyncio.get_event_loop().time()
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=policy.timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)   # 强杀整个进程组
            except ProcessLookupError:
                pass
            stdout_b, stderr_b = await proc.communicate()
        duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)

        stdout = _truncate(stdout_b.decode("utf-8", errors="replace"))
        stderr = _truncate(stderr_b.decode("utf-8", errors="replace"))
        return {
            "success": proc.returncode == 0 and not timed_out,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
            "reason": "执行超时，已强制终止进程组" if timed_out else
                      (stderr.strip()[:200] if proc.returncode != 0 else ""),
        }
    except Exception as e:
        logger.warning(f"🌐 世界 #{world.id} 沙箱执行异常: {e}")
        return {"success": False, "stdout": "", "stderr": "", "exit_code": -1,
                "duration_ms": 0, "timed_out": False, "reason": f"沙箱异常: {str(e)[:200]}"}
    finally:
        if tmp_file is not None:
            try:
                tmp_file.unlink(missing_ok=True)
            except Exception:
                pass


# ── 2.2 触发文件约定 ──
# 世界目录 main.py 实现 handle(event) -> dict（可 async），平台 harness 导入并调用。
# 世界代码零框架依赖；print 重定向到 stdout 字段，不污染结果 JSON。
_TRIGGER_HARNESS_TEMPLATE = '''
import importlib, json, sys, asyncio, io, contextlib, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ENTRY = "__ENTRY__"

def _main():
    try:
        mod = importlib.import_module(ENTRY)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "入口导入失败: %s" % e}, ensure_ascii=False))
        return
    if not hasattr(mod, "handle"):
        print(json.dumps({"ok": False, "error": "入口缺少 handle(event) 函数"}, ensure_ascii=False))
        return
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            event = {}
    except Exception:
        event = {}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = mod.handle(event)
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
        print(json.dumps({"ok": True, "result": result, "stdout": buf.getvalue()}, ensure_ascii=False, default=str))
    except Exception as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e), "stdout": buf.getvalue()}, ensure_ascii=False))

_main()
'''


def _fail(reason: str, *, exit_code: int = -1, duration_ms: int = 0, timed_out: bool = False, stdout: str = "") -> dict:
    return {"success": False, "result": None, "stdout": stdout, "error": reason,
            "exit_code": exit_code, "duration_ms": duration_ms, "timed_out": timed_out, "reason": reason}


async def run_world_trigger(
    world,
    event: dict | None = None,
    entry: str = "main.py",
    background: bool = False,
) -> dict:
    """
    2.2 触发文件：执行世界入口的 handle(event)，返回其结果（JSON 序列化）。

    - entry：世界文件夹内入口（默认 main.py），需暴露 handle(event) -> dict（可 async）
    - event：触发事件 dict（经 stdin 注入 harness）
    - background：配额语义同 run_world_code（无人/后台 24MB，有人 128MB）

    返回：{success, result, stdout, error, exit_code, duration_ms, timed_out, reason}
    """
    policy = policy_for_world(world, background=background)
    workdir = _world_dir(world.id)
    workdir.mkdir(parents=True, exist_ok=True)

    target = (workdir / entry).resolve()
    if not str(target).startswith(str(workdir)):
        return _fail(f"入口文件越界: {entry}")
    if not target.exists():
        return _fail(f"入口文件不存在: {entry}")

    harness = _TRIGGER_HARNESS_TEMPLATE.replace("__ENTRY__", target.stem)
    tmp_file = workdir / f".sandbox_trigger_{uuid.uuid4().hex[:8]}.py"
    try:
        tmp_file.write_text(harness, encoding="utf-8")
        cmd = [sys.executable, "-I", "-X", "utf8", str(tmp_file)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workdir),
            env=_sanitized_env(world),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=lambda: _apply_rlimits(policy),
        )
        event_json = json.dumps(event or {}, ensure_ascii=False).encode("utf-8")
        t0 = asyncio.get_event_loop().time()
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(event_json), timeout=policy.timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout_b, stderr_b = await proc.communicate()
        duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        stdout = stdout_b.decode("utf-8", errors="replace").strip()
        stderr = _truncate(stderr_b.decode("utf-8", errors="replace"))
        if timed_out:
            return _fail("执行超时，已强制终止进程组", exit_code=proc.returncode, duration_ms=duration_ms, timed_out=True)
        if proc.returncode != 0:
            return _fail(stderr.strip()[:200] or f"进程退出码 {proc.returncode}", exit_code=proc.returncode,
                         duration_ms=duration_ms, stdout=stdout)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return _fail("入口无有效 JSON 结果", exit_code=proc.returncode, duration_ms=duration_ms, stdout=stdout)
        if not payload.get("ok"):
            err = payload.get("error", "未知错误")
            return {"success": False, "result": None, "stdout": payload.get("stdout", ""), "error": err,
                    "exit_code": proc.returncode, "duration_ms": duration_ms, "timed_out": False, "reason": err}
        return {"success": True, "result": payload.get("result"), "stdout": payload.get("stdout", ""),
                "error": "", "exit_code": 0, "duration_ms": duration_ms, "timed_out": False, "reason": ""}
    except Exception as e:
        logger.warning(f"🌐 世界 #{world.id} 触发执行异常: {e}")
        return _fail(f"沙箱异常: {str(e)[:200]}")
    finally:
        try:
            tmp_file.unlink(missing_ok=True)
        except Exception:
            pass
