"""
身份系统世界程序 — 把访问界面的用户与世界里的角色对应起来

页面（identity.js）发身份命令（群消息，天然带 sender_id）→ 本程序解析 →
存世界数据库 world_data（identity.{user_id} + identity_index 快照）→
发布 identity_state（SSE）→ 所有页面实时看到谁在场、谁的什么角色。
世界 AI 对话时也会读到世界内活跃用户。

群里可用的命令（对世界绑定的群说）：
  身份 签到            → 登记访客（页面进入时自动发；也可手动）
  身份 我叫 旅人        → 绑定世界角色（identity.{user_id}.role = 旅人）
  身份 谁在            → 列出当前登记过的访客与角色

环境变量（沙箱自动注入）：WORLD_API_BASE / WORLD_API_TOKEN / WORLD_ID
"""
import json
import os
import re
import urllib.request
from datetime import datetime

BASE = os.environ["WORLD_API_BASE"]
TOKEN = os.environ["WORLD_API_TOKEN"]


# ── 受控 API（读写 world_data） ──

def _api(method: str, path: str, body=None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode() or "{}")


def _get(key: str):
    return _api("GET", f"/data/{key}").get("value")


def _put(key: str, value) -> None:
    _api("PUT", f"/data/{key}", {"value": value})


def publish(state: dict) -> None:
    """发布世界状态 → 页面 SSE 实时收到"""
    req = urllib.request.Request(
        BASE + "/state", data=json.dumps(state, ensure_ascii=False).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


# ── 身份记录 ──

def _now() -> str:
    return datetime.now().strftime("%H:%M")


def _update_identity(user_id, name: str, role: str | None = None) -> dict:
    """登记/更新身份：合并 identity_index 快照（3 次 API：读 index + 写 identity + 写 index）→ 发布状态"""
    idx = _get("identity_index") or {}
    rec = idx.get(str(user_id)) or {"id": user_id}
    rec.update({"id": user_id, "name": name, "last_seen": _now()})
    if role:
        rec["role"] = role
    _put(f"identity.{user_id}", rec)
    idx[str(user_id)] = rec
    _put("identity_index", idx)
    users = sorted(
        (v for v in idx.values() if isinstance(v, dict)),
        key=lambda u: u.get("last_seen", ""), reverse=True,
    )
    publish({"identity_state": {"users": users, "count": len(users)}})
    return rec


# ── 命令解析 ──

def handle(event: dict) -> dict:
    """群消息钩子入口：解析身份命令"""
    if event.get("type") != "group_message":
        return {"ok": True, "ignored": event.get("type")}
    actions = []
    for msg in event.get("messages", []):
        text = (msg.get("content") or "").strip()
        sender_id = msg.get("sender_id")
        sender_name = msg.get("sender_name") or f"#{sender_id}"
        if not text or sender_id is None:
            continue
        action = _parse_command(text, sender_id, sender_name)
        if action:
            actions.append(action)
    return {"ok": True, "actions": actions}


def _parse_command(text: str, sender_id, sender_name: str) -> dict | None:
    # 1) 身份 签到 / 签到 / 我来了
    if re.match(r"^(?:身份\s*签到|签到|我来了|我来啦)$", text):
        _update_identity(sender_id, sender_name)
        return {"action": "identity_checkin", "user_id": sender_id}

    # 2) 身份 我叫 X / 身份 角色 X / 我是 X
    m = re.match(r"^(?:身份\s*(?:我叫|角色|是)|我是)\s*(.+)", text)
    if m:
        role = m.group(1).strip()[:20]
        if role:
            _update_identity(sender_id, sender_name, role=role)
            return {"action": "identity_bind", "user_id": sender_id, "role": role}
        return None

    # 3) 身份 谁在 / 谁在
    if re.match(r"^(?:身份\s*)?谁在$", text):
        idx = _get("identity_index") or {}
        users = sorted(
            (v for v in idx.values() if isinstance(v, dict)),
            key=lambda u: u.get("last_seen", ""), reverse=True,
        )
        publish({"identity_state": {"users": users, "count": len(users)}})
        return {"action": "identity_list"}

    return None


def on_tick() -> None:
    """常驻推演：身份是事件驱动的，无定时任务"""
    pass
