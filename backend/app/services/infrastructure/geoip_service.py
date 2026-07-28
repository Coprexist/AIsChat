"""
IP 地理位置解析服务（轻量级）
- 调用 ip-api.com 免费 JSON API（无需 Key，45 次/分钟限制）
- 内网 IP 直接跳过
- LRU 内存缓存减少重复请求
"""
import json
import logging
import time
from collections import OrderedDict
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# LRU 缓存
_CACHE: OrderedDict[str, dict | None] = OrderedDict()
_CACHE_MAX = 500
_CACHE_TTL = 86400  # 24 小时
_CACHE_TIME: dict[str, float] = {}

# 内网/保留地址段
_PRIVATE_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "127.", "0.", "::1", "fe80:", "fc00:", "fd00:",
)

_API_URL = "http://ip-api.com/json/{ip}?fields=status,country,city,isp,query"


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in _PRIVATE_PREFIXES)


async def resolve(ip: str) -> dict | None:
    """解析 IP 地理位置，返回 {country, city, isp} 或 None"""
    if not ip or _is_private(ip):
        return None

    now = time.time()

    # 缓存命中
    if ip in _CACHE:
        if now - _CACHE_TIME.get(ip, 0) < _CACHE_TTL:
            return _CACHE[ip]
        # 过期了删掉
        del _CACHE[ip]
        _CACHE_TIME.pop(ip, None)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(_API_URL.format(ip=quote(ip)))
            if resp.status_code != 200:
                logger.warning(f"IP geo lookup failed ({resp.status_code}): {ip}")
                return _cache_set(ip, None)

            data = resp.json()
            if data.get("status") != "success":
                logger.debug(f"IP geo lookup unsuccessful: {ip} -> {data}")
                return _cache_set(ip, None)

            result = {
                "country": data.get("country"),
                "city": data.get("city"),
                "isp": data.get("isp"),
            }
            return _cache_set(ip, result)

    except Exception as e:
        logger.debug(f"IP geo lookup error: {ip} -> {e}")
        return _cache_set(ip, None)


def _cache_set(ip: str, value: dict | None) -> dict | None:
    """写入 LRU 缓存"""
    if ip in _CACHE:
        _CACHE.move_to_end(ip)
    else:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.popitem(last=False)
    _CACHE[ip] = value
    _CACHE_TIME[ip] = time.time()
    return value


async def batch_resolve(ips: list[str], provider_url: str | None = None) -> dict[str, dict | None]:
    """批量解析（带 50ms 间隔防限流），返回 {ip: result}"""
    results: dict[str, dict | None] = {}
    for i, ip in enumerate(set(ips)):
        if ip in _CACHE:
            now = time.time()
            if now - _CACHE_TIME.get(ip, 0) < _CACHE_TTL:
                results[ip] = _CACHE[ip]
                continue
        results[ip] = await resolve(ip, provider_url=provider_url)
        if i < len(set(ips)) - 1:
            await asyncio.sleep(0.05)
    return results
