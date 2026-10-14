"""Fetch a URL safely (SR-4).

Only http/https; no credentials in the URL; never localhost, private, link-local or otherwise
non-public addresses; redirects are followed by hand and every hop is checked again; the
connection goes to the address that was checked (so DNS cannot change its answer between check
and use); responses are capped at 20 MB.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "LocalNotebook/0.1 (+personal research notebook; user-initiated fetch)"

Resolver = Callable[[str], Awaitable[list[str]]]


class UnsafeURL(Exception):
    """The URL must not be fetched. The message is user-readable."""


class FetchError(Exception):
    """The fetch failed for a reason outside our control. The message is user-readable."""


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    content: bytes
    content_type: str


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"))
    )


def check_syntax(url: str) -> tuple[str, str, int]:
    """(scheme, host, port) of a URL that is plausibly safe, else UnsafeURL."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError as e:
        raise UnsafeURL(f"'{url}' is not a valid web address.") from e
    if parts.scheme not in ("http", "https"):
        raise UnsafeURL(f"Only http and https addresses can be imported ('{url}').")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeURL(f"'{url}' is not a valid web address.")
    if parts.username or parts.password:
        raise UnsafeURL("Addresses with a username or password are not allowed.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise UnsafeURL("Addresses on this computer or local network are not allowed.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not is_public_ip(literal):
        raise UnsafeURL("Addresses on this computer or local network are not allowed.")
    return parts.scheme, host, port or (443 if parts.scheme == "https" else 80)


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError(f"Could not find the website '{host}'.") from e
    return sorted({info[4][0] for info in infos})


async def resolve_public(host: str, resolver: Resolver = system_resolver) -> list[str]:
    """Addresses for `host`, refusing if any of them is not public."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    addresses = await resolver(host)
    if not addresses:
        raise FetchError(f"Could not find the website '{host}'.")
    for address in addresses:
        if not is_public_ip(ipaddress.ip_address(address)):
            raise UnsafeURL("Addresses on this computer or local network are not allowed.")
    return addresses


async def check_url(url: str, resolver: Resolver = system_resolver) -> None:
    """Everything that can be checked without fetching: syntax, then where the name points."""
    _, host, _ = check_syntax(url)
    await resolve_public(host, resolver)


async def fetch(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BYTES,
    resolver: Resolver = system_resolver,
    transport: httpx.AsyncBaseTransport | None = None,
    verify: ssl.SSLContext | bool = True,
) -> FetchResult:
    current = url.strip()
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        transport=transport,
        verify=verify,
        trust_env=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.5"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            scheme, host, port = check_syntax(current)
            address = (await resolve_public(host, resolver))[0]
            parts = urlsplit(current)
            netloc_host = f"[{address}]" if ":" in address else address
            pinned = urlunsplit(
                (scheme, f"{netloc_host}:{port}", parts.path or "/", parts.query, "")
            )
            try:
                async with client.stream(
                    "GET",
                    pinned,
                    headers={"Host": parts.netloc.split("@")[-1]},
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("The website sent an invalid redirect.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise FetchError(
                            f"The website returned an error (HTTP {response.status_code})."
                        )
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError("The page is larger than the 20 MB limit.")
                    body = bytearray()
                    async for block in response.aiter_bytes():
                        body += block
                        if len(body) > max_bytes:
                            raise FetchError("The page is larger than the 20 MB limit.")
                    return FetchResult(
                        current, bytes(body), response.headers.get("content-type", "")
                    )
            except httpx.TimeoutException as e:
                raise FetchError("The website took too long to respond.") from e
            except httpx.HTTPError as e:
                raise FetchError(f"Could not reach the website ({e.__class__.__name__}).") from e
    raise FetchError("The website redirected too many times.")
