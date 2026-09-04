"""URL validation helpers for server-side fetches."""

import ipaddress
import os
import socket
from collections.abc import Iterable
from urllib.parse import urlparse


def hosts_from_env(name: str) -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in os.getenv(name, "").split(",")
        if host.strip()
    }


def hosts_from_urls(urls: Iterable[str | None]) -> set[str]:
    hosts = set()
    for url in urls:
        if not url:
            continue
        hostname = urlparse(url).hostname
        if hostname:
            hosts.add(hostname.lower().rstrip("."))
    return hosts


def validate_http_url(
    url: str,
    *,
    allowed_hosts: set[str] | None = None,
) -> str:
    """Validate a URL before the server connects to it.

    An explicit host allowlist may contain private hosts. A wildcard allows
    public hosts only and still blocks loopback, private and reserved IPs.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 http 或 https URL")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL 主机无效或包含凭据")

    hostname = parsed.hostname.lower().rstrip(".")
    if allowed_hosts is not None:
        if not allowed_hosts:
            raise ValueError("远程 URL 导入未启用")
        if "*" not in allowed_hosts and hostname not in allowed_hosts:
            raise ValueError(f"URL 主机不在允许列表中: {hostname}")

        if "*" in allowed_hosts and hostname not in allowed_hosts - {"*"}:
            try:
                addresses = {
                    item[4][0]
                    for item in socket.getaddrinfo(hostname, parsed.port or 443)
                }
            except socket.gaierror as exc:
                raise ValueError(f"无法解析 URL 主机: {hostname}") from exc
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ValueError("通配远程导入禁止访问本机、私网或保留地址")

    return url
