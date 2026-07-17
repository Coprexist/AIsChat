"""
兼容重导出层 — 原 alarm_service 已迁移至 app.ai.alarm
"""
from app.ai.alarm import (  # noqa: F401
    set_alarm,
    cancel_alarm,
    update_alarm,
    list_alarms,
    get_due_alarms,
    fire_alarm,
    get_next_alarm_time,
    _alarm_wake_event,
    notify_alarm_changed,
)
