"""
主题选色投票 · 第二轮快投 — 每字段 A/B 二选一（2026-08-16 一轮定稿 ShuAICFR 方案后收窄分歧）

- POST /theme-vote-r2       提交本轮选择（覆盖式：同 user_key 覆盖，不新增）
- GET  /theme-vote-r2/stats 返回本轮所有投票（前端按字段聚合 A/B 头像）

存储：data/theme_votes_r2.json（与第一轮 theme_votes.json 隔离，互不影响）。
身份：同第一轮——前端负责（登录用户调 /auth/me 拿昵称头像，未登录输昵称）。
"""
import json
import os
import threading
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["主题选色投票二轮"])

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
VOTE_FILE = DATA_DIR / "theme_votes_r2.json"
_lock = threading.Lock()


class VoteSubmit(BaseModel):
    colors: dict = Field(..., description="主题色选择 {变量key: hex}")
    user_name: str = Field(..., min_length=1, max_length=30, description="昵称（登录用户=username，未登录=自定义）")
    avatar_url: str | None = Field(None, description="头像 URL（登录用户）")


def _read_votes() -> dict:
    if not VOTE_FILE.exists():
        return {}
    try:
        return json.loads(VOTE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_votes(votes: dict) -> None:
    VOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = VOTE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(votes, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(VOTE_FILE)  # 原子替换


@router.post("/theme-vote-r2")
async def submit_vote(req: VoteSubmit):
    user_key = req.user_name.strip() or "匿名"
    with _lock:
        votes = _read_votes()
        votes[user_key] = {
            "user_key": user_key,
            "user_name": req.user_name.strip(),
            "avatar_url": req.avatar_url or None,
            "colors": req.colors,
        }
        _write_votes(votes)
    return {"ok": True, "count": len(votes)}


@router.get("/theme-vote-r2/stats")
async def vote_stats():
    votes = _read_votes()
    items = sorted(votes.values(), key=lambda v: (v.get("user_name") or ""))
    return {"items": items, "count": len(items)}
