"""
2D 冒险世界程序示例 — 群消息 → 关键词语法提取 → 即时游戏指令

世界程序常驻后台（config resident: true），群里说的话经群消息钩子喂进来，
这里用「关键词语法提取」解析成游戏指令，再经受控 API 发布状态，
游戏页面（EventSource）实时应用：NPC 说话 / NPC 移动 / 世界横幅。

群里可用的命令（对世界绑定的群说）：
  旅人说 你好呀        → 旅人弹出对话（npc_name 匹配游戏里的 NPC 名字）
  旅人移动到 2,3       → 旅人移动到格子 (2,3)
  我去 2,3             → 发送者自己的玩家传送到格子 (2,3)（校验可走）
  玩家移动到 2,3       → 同上（别名）
  公告 冒险开始！       → 页面顶部横幅
  未知内容             → 村长代为回应（世界有自己的回应方式）

环境变量（沙箱自动注入）：WORLD_API_BASE / WORLD_API_TOKEN / WORLD_ID
"""
import json
import os
import re
import urllib.request

BASE = os.environ["WORLD_API_BASE"]
TOKEN = os.environ["WORLD_API_TOKEN"]

# 游戏里的 NPC 名单（与 adventure.js 的 NPCS 名字一致；可按需扩展）
NPC_NAMES = ["村长", "旅人"]


def publish(state: dict) -> None:
    """发布世界状态 → 游戏页面 SSE 实时收到"""
    req = urllib.request.Request(
        BASE + "/state",
        data=json.dumps(state, ensure_ascii=False).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)


def handle(event: dict) -> dict:
    """群消息钩子入口：群里有消息就到这里（处理不处理由世界自己决定）

    节流窗口内多条消息会合并进 event["messages"]，逐条解析。
    """
    if event.get("type") != "group_message":
        return {"ok": True, "ignored": event.get("type")}
    actions = []
    for msg in event.get("messages", []):
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        action = _parse_command(text, msg.get("sender_id"))
        if action:
            actions.append(action)
    return {"ok": True, "actions": actions}


def _parse_command(text: str, sender_id=None) -> dict | None:
    """关键词语法提取：把一句群消息翻译成即时游戏指令（返回发布的状态或 None）"""
    # 1) NPC 说话：<名字>[说|讲|喊|曰|<冒号>] <内容>（动词/冒号至少一个，避免误吞“移动到”等指令）
    m = re.match(rf"({'|'.join(NPC_NAMES)})(?:(?:说|讲|喊|曰)[:：]?|[:：])\s*(.+)", text)
    if m:
        state = {"npc_name": m.group(1), "npc_say": m.group(2).strip()}
        publish(state)
        return {"action": "npc_say", "npc": m.group(1)}

    # 2) NPC 移动：<名字>[(移动到|去|走到)] <x>,<y>
    m = re.match(rf"({'|'.join(NPC_NAMES)})(?:移动到|去|走到)?\s*(\d+)\s*[,，]\s*(\d+)", text)
    if m:
        state = {"npc_name": m.group(1), "npc_move": {"x": int(m.group(2)), "y": int(m.group(3))}}
        publish(state)
        return {"action": "npc_move", "npc": m.group(1)}

    # 2.5) 玩家移动：我去 <x>,<y> / 玩家移动到 <x>,<y>（发送者自己的玩家传送，带 sender_id 供页面比对）
    m = re.match(r"^(?:我去|玩家移动到|玩家去)\s*(\d+)\s*[,，]\s*(\d+)", text)
    if m:
        state = {"player_move": {"x": int(m.group(1)), "y": int(m.group(2)), "sender_id": _sender_id}}
        publish(state)
        return {"action": "player_move", "to": (int(m.group(1)), int(m.group(2)))}

    # 3) 公告/横幅：公告[:：]<内容>
    m = re.match(r"(?:公告|横幅)[:：]?\s*(.+)", text)
    if m:
        publish({"banner": m.group(1).strip()})
        return {"action": "banner"}

    # 4) 未知内容：村长代为回应（世界自己的方式）
    publish({"npc_name": "村长", "npc_say": f"「{text}」——这个世界的旅人们听到了你的话。"})
    return {"action": "fallback"}


def on_tick() -> None:
    """常驻推演：世界时间流动 / NPC 自主活动（示例：旅人每 30 秒换一个位置）"""
    import random
    x = random.randint(1, 14)
    y = random.randint(0, 10)
    publish({"npc_name": "旅人", "npc_move": {"x": x, "y": y}})
