"""
数据库备份/恢复服务
使用 pg_dump / psql 进行 PostgreSQL 数据库的导出和导入
"""
import asyncio
import os
import tempfile
import logging
from app.config import settings

logger = logging.getLogger(__name__)

BACKUP_TIMEOUT = 120  # 备份超时（秒）
RESTORE_TIMEOUT = 300  # 恢复超时（秒）

# PostgreSQL 17+ 新增参数，在 PG16 及以下版本中不存在
# pg_dump 17 导出时会在文件头部写入这些 SET 语句，需过滤以确保跨版本兼容
_PG17_PLUS_SETTINGS = [
    b"SET transaction_timeout",
]


def _filter_pg_version_specific(sql: bytes) -> bytes:
    """
    从 pg_dump 输出中移除高版本 PG 专有的 SET 语句，
    使备份文件可在低版本 PG 上恢复（如 PG17 导出 → PG16 导入）。
    """
    lines = sql.split(b"\n")
    filtered = [
        line for line in lines
        if not any(line.strip().startswith(s) for s in _PG17_PLUS_SETTINGS)
    ]
    return b"\n".join(filtered)


async def create_backup() -> bytes:
    """
    执行 pg_dump，导出整个数据库为 SQL 字节。
    使用 settings.database_url_sync 连接数据库。
    超时 120 秒。
    """
    db_url = settings.database_url_sync

    # 解析数据库连接信息：postgresql://user:pass@host:port/dbname
    # 示例：postgresql://ai_chat:password@postgres:5432/ai_group_chat
    url = db_url.replace("postgresql://", "")
    # 分离 user:pass@host:port/dbname
    auth_host, dbname = url.rsplit("/", 1)
    user_pass, host_port = auth_host.rsplit("@", 1)
    user, password = user_pass.split(":", 1)
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")

    cmd = [
        "pg_dump",
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
        "--no-owner",
        "--no-acl",
        "--clean",
        "--if-exists",
        "--encoding=UTF8",
    ]

    logger.info(f"开始备份数据库: {dbname}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PGPASSWORD": password},
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=BACKUP_TIMEOUT
        )

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            logger.error(f"pg_dump 失败 (code={proc.returncode}): {err_msg}")
            raise RuntimeError(f"数据库备份失败: {err_msg[:500]}")

        # 过滤高版本 PG 专有参数，确保备份可跨版本恢复（如 PG17 → PG16）
        sql_bytes = _filter_pg_version_specific(stdout)

        logger.info(f"数据库备份完成: {len(sql_bytes)} bytes")
        return sql_bytes

    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("数据库备份超时（超过 120 秒）")
    except FileNotFoundError:
        raise RuntimeError("pg_dump 未安装，请检查 postgresql-client 是否已安装")


async def restore_backup(sql_content: bytes) -> dict:
    """
    执行 psql 恢复数据库。
    ⚠️ 此操作会覆盖当前数据库所有数据，需谨慎使用。
    恢复前先清空 public schema，避免 "relation already exists" 错误。
    超时 300 秒。
    """
    db_url = settings.database_url_sync

    url = db_url.replace("postgresql://", "")
    auth_host, dbname = url.rsplit("/", 1)
    user_pass, host_port = auth_host.rsplit("@", 1)
    user, password = user_pass.split(":", 1)
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")

    _env = {**os.environ, "PGPASSWORD": password}

    # ---- 第一步：清空 public schema（避免与 init-db.sql 建的表冲突）----
    logger.info(f"恢复前清空数据库 public schema: {dbname}")
    clean_proc = await asyncio.create_subprocess_exec(
        "psql",
        "-h", host, "-p", port, "-U", user, "-d", dbname,
        "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_env,
    )
    clean_stdout, clean_stderr = await clean_proc.communicate()
    if clean_proc.returncode != 0:
        err = clean_stderr.decode("utf-8", errors="replace")
        logger.warning(f"清空 schema 警告（可能是空库）: {err[:200]}")

    # ---- 第二步：执行恢复 ----
    # 将 SQL 写入临时文件，psql 从文件读取更稳定
    tmp_path = None
    try:
        # 过滤高版本 PG 专有参数（用户可能上传外部 PG17 导出的备份）
        sql_content = _filter_pg_version_specific(sql_content)

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".sql", delete=False, prefix="aischat_restore_"
        ) as f:
            f.write(sql_content)
            tmp_path = f.name

        cmd = [
            "psql",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", dbname,
            "-f", tmp_path,
            "-v", "ON_ERROR_STOP=1",
        ]

        logger.info(f"开始恢复数据库: {dbname}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=RESTORE_TIMEOUT
        )

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            logger.error(f"psql 恢复失败 (code={proc.returncode}): {err_msg}")
            raise RuntimeError(f"数据库恢复失败: {err_msg[:500]}")

        logger.info("数据库恢复完成")
        return {"success": True, "message": "数据库已恢复，请刷新页面"}

    except asyncio.TimeoutError:
        raise RuntimeError("数据库恢复超时（超过 300 秒）")
    except FileNotFoundError:
        raise RuntimeError("psql 未安装，请检查 postgresql-client 是否已安装")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ============================================================
# 完整备份（数据库 + 文件）
# ============================================================

async def create_full_backup() -> tuple[bytes, int, int]:
    """
    创建完整备份（.tar.gz）：
    - 包含 pg_dump 导出的 .sql 文件
    - 包含 /app/data/ 目录下所有文件
    返回 (tar_bytes, sql_size, file_count)
    """
    import tarfile
    import io

    # 1. 先导出数据库
    logger.info("开始创建完整备份...")
    sql_bytes = await create_backup()
    sql_size = len(sql_bytes)
    logger.info(f"数据库导出完成: {sql_size} bytes")

    # 2. 打包为 tar.gz
    data_dir = settings.data_dir
    buf = io.BytesIO()
    file_count = 0

    try:
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            # 添加数据库 dump
            sql_info = tarfile.TarInfo(name="backup.sql")
            sql_info.size = len(sql_bytes)
            tar.addfile(sql_info, io.BytesIO(sql_bytes))
            logger.info("  ✅ backup.sql 已打包")

            # 添加 data/ 目录下所有文件
            if os.path.isdir(data_dir):
                for root, dirs, files in os.walk(data_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        # 计算相对路径（在 tar 中以 data/ 为前缀）
                        arcname = os.path.join("data", os.path.relpath(fpath, data_dir))
                        # 替换 Windows 反斜杠为 Unix 正斜杠
                        arcname = arcname.replace("\\", "/")
                        tar.add(fpath, arcname=arcname)
                        file_count += 1
            logger.info(f"  ✅ {file_count} 个文件已打包")

    except Exception as e:
        logger.error(f"创建完整备份失败: {e}")
        raise RuntimeError(f"打包备份失败: {str(e)}")

    tar_bytes = buf.getvalue()
    logger.info(f"完整备份创建完成: {len(tar_bytes)} bytes (SQL={sql_size}, files={file_count})")
    return tar_bytes, sql_size, file_count


async def restore_full_backup(tar_bytes: bytes) -> dict:
    """
    从完整备份 .tar.gz 恢复：
    - 从 backup.sql 恢复数据库
    - 将所有 data/ 下的文件还原到 /app/data/
    ⚠️ 覆盖当前所有数据
    """
    import tarfile
    import io
    import shutil

    data_dir = settings.data_dir
    sql_bytes = None
    restored_files = 0

    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name == "backup.sql":
                    # 提取 SQL
                    f = tar.extractfile(member)
                    if f:
                        sql_bytes = f.read()
                    logger.info(f"  📄 读取 backup.sql: {len(sql_bytes)} bytes" if sql_bytes else "  ❌ backup.sql 为空")
                elif member.name.startswith("data/"):
                    # 提取文件到 /app/data/
                    # 去掉 "data/" 前缀，得到相对路径
                    rel_path = member.name[5:]  # 去掉 "data/"
                    dest = os.path.join(data_dir, rel_path)
                    # 安全：拒绝绝对路径和目录穿越
                    dest = os.path.normpath(dest)
                    if not dest.startswith(os.path.normpath(data_dir)):
                        logger.warning(f"  ⚠️ 拒绝不安全路径: {member.name} → {dest}")
                        continue
                    if member.isdir():
                        os.makedirs(dest, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        f = tar.extractfile(member)
                        if f:
                            with open(dest, "wb") as out:
                                shutil.copyfileobj(f, out)
                            restored_files += 1

        if sql_bytes is None:
            raise RuntimeError("备份文件中未找到 backup.sql，无法恢复数据库")

        logger.info(f"文件还原完成: {restored_files} 个文件")
        logger.info("开始恢复数据库...")
        result = await restore_backup(sql_bytes)
        logger.info("完整备份恢复完成")

        return {
            "success": True,
            "message": f"完整备份已恢复：数据库 + {restored_files} 个文件",
            "restored_files": restored_files,
        }

    except tarfile.ReadError as e:
        raise RuntimeError(f"无法读取备份文件（可能已损坏或不是 .tar.gz 格式）: {str(e)}")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"完整备份恢复失败: {e}", exc_info=True)
        raise RuntimeError(f"恢复失败: {str(e)}")
