"""
聊天链尺时间判定模块

v2: 红黑树 + 有序链表实现。
- 红黑树索引尺时间值（key = ruler_time），O(log N) 查找边界
- 双向链表按尺时间升序串联所有 AI，O(K) 遍历唤醒
- 树节点指向该尺时间值的最后一个链表节点

接口与 v1 完全兼容。
"""
import asyncio
import logging
from time import time as now

logger = logging.getLogger(__name__)

MAX_CONCURRENT_PER_GROUP = 3

# ── 红黑树颜色 ──
RED, BLACK = True, False


class ChainNode:
    """双向链表节点——一个 AI"""
    __slots__ = ("agent_id", "prev", "next")

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.prev: "ChainNode | None" = None
        self.next: "ChainNode | None" = None


class TreeEntry:
    """红黑树节点——尺时间值 → 链表末节点"""
    __slots__ = ("ruler_time", "chain_tail", "color", "left", "right", "parent")

    def __init__(self, ruler_time: int, chain_tail: ChainNode):
        self.ruler_time = ruler_time
        self.chain_tail = chain_tail
        self.color = RED
        self.left: "TreeEntry | None" = None
        self.right: "TreeEntry | None" = None
        self.parent: "TreeEntry | None" = None


class RulerTree:
    """尺时间红黑树。O(log N) 插入/删除/查找。"""

    def __init__(self):
        self._nil = TreeEntry(0, None)
        self._nil.color = BLACK
        self._nil.left = self._nil.right = self._nil.parent = self._nil
        self._root: TreeEntry = self._nil

    def insert(self, ruler_time: int, chain_tail: ChainNode) -> TreeEntry:
        existing = self._find(ruler_time)
        if existing is not self._nil:
            existing.chain_tail = chain_tail
            return existing

        node = TreeEntry(ruler_time, chain_tail)
        node.left = node.right = self._nil

        parent, curr = self._nil, self._root
        while curr is not self._nil:
            parent = curr
            curr = curr.left if ruler_time < curr.ruler_time else curr.right

        node.parent = parent
        if parent is self._nil:
            self._root = node
        elif ruler_time < parent.ruler_time:
            parent.left = node
        else:
            parent.right = node
        self._fix_insert(node)
        return node

    def remove(self, ruler_time: int) -> bool:
        node = self._find(ruler_time)
        if node is self._nil:
            return False
        self._delete_node(node)
        return True

    def find_le(self, ruler_time: int) -> TreeEntry | None:
        """找 <= ruler_time 的最大节点"""
        best = self._nil
        curr = self._root
        while curr is not self._nil:
            if curr.ruler_time <= ruler_time:
                best = curr
                curr = curr.right
            else:
                curr = curr.left
        return best if best is not self._nil else None

    def _find(self, rt: int) -> TreeEntry:
        curr = self._root
        while curr is not self._nil:
            if rt == curr.ruler_time:
                return curr
            curr = curr.left if rt < curr.ruler_time else curr.right
        return self._nil

    def _minimum(self, node: TreeEntry) -> TreeEntry:
        while node.left is not self._nil:
            node = node.left
        return node

    def _transplant(self, u: TreeEntry, v: TreeEntry):
        if u.parent is self._nil:
            self._root = v
        elif u is u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        v.parent = u.parent

    def _delete_node(self, z: TreeEntry):
        y_orig_color = z.color
        if z.left is self._nil:
            x = z.right
            self._transplant(z, x)
        elif z.right is self._nil:
            x = z.left
            self._transplant(z, x)
        else:
            y = self._minimum(z.right)
            y_orig_color = y.color
            x = y.right
            if y.parent is z:
                x.parent = y
            else:
                self._transplant(y, y.right)
                y.right = z.right
                y.right.parent = y
            self._transplant(z, y)
            y.left = z.left
            y.left.parent = y
            y.color = z.color
        if y_orig_color == BLACK:
            self._fix_delete(x)

    def _fix_insert(self, n: TreeEntry):
        while n.parent.color == RED:
            if n.parent is n.parent.parent.left:
                u = n.parent.parent.right
                if u.color == RED:
                    n.parent.color = u.color = BLACK
                    n.parent.parent.color = RED
                    n = n.parent.parent
                else:
                    if n is n.parent.right:
                        n = n.parent
                        self._rot_left(n)
                    n.parent.color = BLACK
                    n.parent.parent.color = RED
                    self._rot_right(n.parent.parent)
            else:
                u = n.parent.parent.left
                if u.color == RED:
                    n.parent.color = u.color = BLACK
                    n.parent.parent.color = RED
                    n = n.parent.parent
                else:
                    if n is n.parent.left:
                        n = n.parent
                        self._rot_right(n)
                    n.parent.color = BLACK
                    n.parent.parent.color = RED
                    self._rot_left(n.parent.parent)
        self._root.color = BLACK

    def _fix_delete(self, n: TreeEntry):
        while n is not self._root and n.color == BLACK:
            if n is n.parent.left:
                s = n.parent.right
                if s.color == RED:
                    s.color = BLACK
                    n.parent.color = RED
                    self._rot_left(n.parent)
                    s = n.parent.right
                if s.left.color == BLACK and s.right.color == BLACK:
                    s.color = RED
                    n = n.parent
                else:
                    if s.right.color == BLACK:
                        s.left.color = BLACK
                        s.color = RED
                        self._rot_right(s)
                        s = n.parent.right
                    s.color = n.parent.color
                    n.parent.color = BLACK
                    s.right.color = BLACK
                    self._rot_left(n.parent)
                    n = self._root
            else:
                s = n.parent.left
                if s.color == RED:
                    s.color = BLACK
                    n.parent.color = RED
                    self._rot_right(n.parent)
                    s = n.parent.left
                if s.right.color == BLACK and s.left.color == BLACK:
                    s.color = RED
                    n = n.parent
                else:
                    if s.left.color == BLACK:
                        s.right.color = BLACK
                        s.color = RED
                        self._rot_left(s)
                        s = n.parent.left
                    s.color = n.parent.color
                    n.parent.color = BLACK
                    s.left.color = BLACK
                    self._rot_right(n.parent)
                    n = self._root
        n.color = BLACK

    def _rot_left(self, x: TreeEntry):
        y = x.right
        x.right = y.left
        if y.left is not self._nil:
            y.left.parent = x
        y.parent = x.parent
        if x.parent is self._nil:
            self._root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _rot_right(self, y: TreeEntry):
        x = y.left
        y.left = x.right
        if x.right is not self._nil:
            x.right.parent = y
        x.parent = y.parent
        if y.parent is self._nil:
            self._root = x
        elif y is y.parent.right:
            y.parent.right = x
        else:
            y.parent.left = x
        x.right = y
        y.parent = x


class ChatChainManager:
    """
    v2: 红黑树 + 双向链表。

    每群一个 RulerTree（索引）+ 一个哨兵 head ChainNode。
    """

    def __init__(self):
        self._trees: dict[int, RulerTree] = {}
        self._heads: dict[int, ChainNode] = {}
        self._nodes: dict[int, dict[int, ChainNode]] = {}
        self._last_reply: dict[int, dict[int, dict]] = {}
        self._processing: dict[int, set[int]] = {}
        self._semaphores: dict[int, asyncio.Semaphore] = {}
        self._priority_sem: dict[int, asyncio.Semaphore] = {}

    def get_wake_candidates(self, group_id: int, msg_time: float | None = None) -> list[int]:
        if msg_time is None:
            msg_time = now()

        head = self._heads.get(group_id)
        last = self._last_reply.get(group_id, {})
        if not head or not head.next:
            return []

        wake_list = []
        curr = head.next
        while curr is not head:
            cfg = last.get(curr.agent_id, {})
            gap = msg_time - cfg.get("last_reply_at", 0.0)
            if gap >= cfg.get("ruler_time", 120):
                wake_list.append(curr.agent_id)
            curr = curr.next

        return wake_list

    def register_ai(self, agent_id: int, group_id: int, ruler_time: int = 120) -> None:
        ruler_time = max(10, ruler_time)
        if group_id not in self._nodes:
            self._nodes[group_id] = {}
            self._trees[group_id] = RulerTree()
            head = ChainNode(0)
            head.prev = head.next = head
            self._heads[group_id] = head
            self._last_reply[group_id] = {}

        if agent_id in self._nodes[group_id]:
            self._remove_chain(agent_id, group_id)

        last = self._last_reply[group_id]
        last[agent_id] = {"ruler_time": ruler_time, "last_reply_at": 0.0}

        head = self._heads[group_id]
        node = ChainNode(agent_id)
        self._nodes[group_id][agent_id] = node

        curr = head.next
        while curr is not head:
            cr = last.get(curr.agent_id, {}).get("ruler_time", 120)
            if ruler_time < cr:
                break
            curr = curr.next

        node.prev = curr.prev
        node.next = curr
        curr.prev.next = node
        curr.prev = node

        self._trees[group_id].insert(ruler_time, node)

    def update_ruler_time(self, agent_id: int, group_id: int, new_ruler_time: int) -> bool:
        if agent_id not in self._nodes.get(group_id, {}):
            return False
        self._remove_chain(agent_id, group_id)
        self.register_ai(agent_id, group_id, max(10, new_ruler_time))
        return True

    def _remove_chain(self, agent_id: int, group_id: int):
        node = self._nodes[group_id].get(agent_id)
        if not node:
            return
        ruler = self._last_reply[group_id][agent_id].get("ruler_time", 120)

        # 检查是否是最后一个同值节点
        tree = self._trees[group_id]
        entry = tree.find_le(ruler)
        head = self._heads[group_id]

        count = 0
        if entry and entry.ruler_time == ruler:
            curr = entry.chain_tail
            while curr is not head:
                r = self._last_reply[group_id].get(curr.agent_id, {}).get("ruler_time", 120)
                if r == ruler:
                    count += 1
                curr = curr.prev

        node.prev.next = node.next
        node.next.prev = node.prev

        if entry and entry.ruler_time == ruler:
            if count <= 1:
                tree.remove(ruler)
            elif node is entry.chain_tail:
                new_tail = node.prev
                while new_tail is not head:
                    r = self._last_reply[group_id].get(new_tail.agent_id, {}).get("ruler_time", 120)
                    if r == ruler:
                        entry.chain_tail = new_tail
                        break
                    new_tail = new_tail.prev

        del self._nodes[group_id][agent_id]

    def mark_replied(self, agent_id: int, group_id: int) -> None:
        cfg = self._last_reply.get(group_id, {}).get(agent_id)
        if cfg:
            cfg["last_reply_at"] = now()

    def should_wake(self, agent_id: int, group_id: int, msg_time: float | None = None) -> bool:
        if msg_time is None:
            msg_time = now()
        cfg = self._last_reply.get(group_id, {}).get(agent_id)
        return (msg_time - cfg["last_reply_at"]) >= cfg["ruler_time"] if cfg else True

    def remove_ai(self, agent_id: int, group_id: int) -> None:
        self._remove_chain(agent_id, group_id)
        self._last_reply.get(group_id, {}).pop(agent_id, None)

    def get_ruler_time(self, agent_id: int, group_id: int) -> int:
        cfg = self._last_reply.get(group_id, {}).get(agent_id)
        return cfg["ruler_time"] if cfg else 120

    def try_claim(self, agent_id: int, group_id: int) -> bool:
        proc = self._processing.setdefault(group_id, set())
        if agent_id in proc:
            return False
        proc.add(agent_id)
        return True

    def release_claim(self, agent_id: int, group_id: int) -> None:
        proc = self._processing.get(group_id)
        if proc:
            proc.discard(agent_id)

    def get_semaphore(self, group_id: int, limit: int = 0) -> asyncio.Semaphore:
        cap = limit if limit and limit > 0 else MAX_CONCURRENT_PER_GROUP
        if group_id not in self._semaphores:
            self._semaphores[group_id] = asyncio.Semaphore(cap)
        return self._semaphores[group_id]



    def try_claim_priority(self, agent_id: int, group_id: int) -> bool:
        """尝试进 @优先通道。已在普通通道则不重复触发（LLM跑完自然看到@的消息）。"""
        proc = self._processing.setdefault(group_id, set())
        if agent_id not in proc:
            proc.add(agent_id)
            return True
        return False

    def get_priority_semaphore(self, group_id: int) -> asyncio.Semaphore:
        if group_id not in self._priority_sem:
            self._priority_sem[group_id] = asyncio.Semaphore(1)
        return self._priority_sem[group_id]
chat_chain_manager = ChatChainManager()
