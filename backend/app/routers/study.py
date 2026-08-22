"""
自习室数据 API — 在线同学 + 学习时长（近 15 天 / 累计）

- 在线：内存表（user_id → last_seen），5 分钟窗口过期，无需落库
- 学习时长：study_records 表按 用户+日期 累计，跨设备持久化
"""
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import get_current_user
from app.models.study_record import StudyRecord

router = APIRouter(prefix="/study", tags=["自习室"])

ONLINE_TTL = 300          # 在线窗口（秒）：5 分钟无心跳视为下线
ONLINE: dict[int, float] = {}       # user_id -> last_seen epoch

# 清理在线表：超过 TTL 的惰性剔除（在查询时顺便清理，无需定时任务）
def _prune_online() -> None:
    now = time.time()
    stale = [uid for uid, t in list(ONLINE.items()) if now - t > ONLINE_TTL]
    for uid in stale:
        ONLINE.pop(uid, None)


class RecordRequest(BaseModel):
    """学习时长上报（分钟，1~600）"""
    minutes: int = Field(1, ge=1, le=600)


@router.post("/heartbeat")
async def heartbeat(current_user: dict = Depends(get_current_user)):
    """在线心跳：更新本人在线时间，返回当前在线同学列表。"""
    uid = current_user["user_id"]
    ONLINE[uid] = time.time()
    _prune_online()
    now = time.time()
    online_ids = [u for u, t in ONLINE.items() if now - t <= ONLINE_TTL]
    return {"online_count": len(online_ids), "online_ids": online_ids}


@router.post("/record")
async def record(
    req: RecordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习完成上报：按 用户+当天 累计分钟（upsert）。"""
    uid = current_user["user_id"]
    today = date.today().isoformat()

    row = (await db.execute(
        select(StudyRecord).where(
            StudyRecord.user_id == uid, StudyRecord.date == today,
        )
    )).scalar_one_or_none()

    if row is None:
        db.add(StudyRecord(user_id=uid, date=today, minutes=req.minutes))
    else:
        row.minutes += req.minutes
    await db.commit()
    return {"ok": True, "today_minutes": (row.minutes if row else req.minutes)}


@router.get("/summary")
async def summary(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """统计：今日分钟 / 累计分钟 / 近 15 天每日分钟 / 在线同学数。"""
    uid = current_user["user_id"]

    # 今日与累计
    today = date.today().isoformat()
    today_row = (await db.execute(
        select(StudyRecord).where(StudyRecord.user_id == uid, StudyRecord.date == today),
    )).scalar_one_or_none()
    total = (await db.execute(
        select(func.coalesce(func.sum(StudyRecord.minutes), 0)).where(StudyRecord.user_id == uid),
    )).scalar_one()

    # 近 15 天（含今天，按天补零）
    start = date.today() - timedelta(days=14)
    rows = (await db.execute(
        select(StudyRecord.date, StudyRecord.minutes).where(
            StudyRecord.user_id == uid, StudyRecord.date >= start.isoformat(),
        )
    )).all()
    by_date = {r[0]: r[1] for r in rows}
    days = []
    for i in range(15):
        d = (start + timedelta(days=i)).isoformat()
        days.append({"date": d, "minutes": by_date.get(d, 0)})

    _prune_online()
    now = time.time()
    online_ids = [u for u, t in ONLINE.items() if now - t <= ONLINE_TTL]

    return {
        "today_minutes": today_row.minutes if today_row else 0,
        "total_minutes": int(total or 0),
        "days": days,
        "online_count": len(online_ids),
    }
