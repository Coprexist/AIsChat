"""出站目标守卫（纯函数，只判断"是不是内网"）。

**为什么需要它**（2026-09-13）：用户可填的 base_url 会让服务器替他们发请求。
不设限就等于给每个注册用户一个内网端口扫描器——用无效 key 探测状态码
（200/401/404/302/连接拒绝/超时）就能画出内网服务地图，实测已确认可行。

**为什么不能简单"一律只许公网"**：平台自己就在合法使用内网地址
（preset 的 Ollama http://localhost:11434、本实例的 embedding http://172.18.0.1:11434），
而用户也合法地指向自己的局域网 LLM。所以分界线不是"URL 长什么样"，
而是"**这个地址是不是用户已经声明过要用的那一个**"——见 base_url_registry。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

# 明显是本机的名字（DNS 之前先挡掉，省一次解析）
_LOCAL_NAMES = ("localhost", "localhost.localdomain")
_LOCAL_SUFFIXES = (".local", ".internal", ".lan", ".home")


def _split(url: str):
    raw = (url or "").strip()
    if "://" not in raw:
        raw = "http://" + raw
    return urlsplit(raw)


def host_port(url: str) -> str:
    """规范化成 host:port，用于白名单比较（默认端口按 scheme 补全）。"""
    p = _split(url)
    host = (p.hostname or "").lower()
    port = p.port or (443 if p.scheme == "https" else 80)
    return f"{host}:{port}"


def _ip_is_internal(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # is_private 覆盖 10/8、172.16/12、192.168/16、100.64/10、169.254/16(链路本地，含云元数据段)、
    # fd00::/8 等；回环/保留/组播/未指定再单独兜一遍
    return bool(
        a.is_private or a.is_loopback or a.is_link_local
        or a.is_reserved or a.is_multicast or a.is_unspecified
    )


def is_private_target(url: str) -> bool:
    """目标是否指向内网/本机。

    域名会做一次 DNS 解析（解析失败 → ``不当私网``，交给请求阶段报"无法连接"，
    免得把"域名写错了"也误报成安全拦截）。
    """
    p = _split(url)
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host in _LOCAL_NAMES or host.endswith(_LOCAL_SUFFIXES):
        return True
    if _looks_like_ip(host):
        return _ip_is_internal(host)  # IP 字面量：直接判，不用解析
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return any(_ip_is_internal(info[4][0]) for info in infos)


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
