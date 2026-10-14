"""URL safety (SR-4, QA-1)."""

import ssl

import httpx
import pytest

from app.ingest import safe_fetch
from app.ingest.safe_fetch import FetchError, UnsafeURL

PUBLIC = "93.184.216.34"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "javascript:alert(1)",
        "gopher://example.com",
        "http://",
        "https://user:pass@example.com/",
        "http://localhost/",
        "http://localhost:8000/api",
        "http://app.localhost/",
        "http://printer.local/",
        "http://db.internal/",
        "http://127.0.0.1/",
        "http://127.1.2.3:8080/",
        "http://10.0.0.5/",
        "http://172.16.4.4/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
        "http://100.64.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.1.2.3]/",
        "http://224.0.0.1/",
        "not a url",
    ],
)
def test_unsafe_addresses_are_refused(url):
    with pytest.raises(UnsafeURL):
        safe_fetch.check_syntax(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a?b=c",
        "http://example.com:8080/x",
        f"http://{PUBLIC}/",
        "https://sub.example.co.uk",
    ],
)
def test_ordinary_addresses_pass_the_syntax_check(url):
    scheme, host, port = safe_fetch.check_syntax(url)
    assert scheme in ("http", "https") and host and port


def resolver_for(mapping):
    async def resolve(host):
        return mapping[host]

    return resolve


async def test_names_that_point_inside_are_refused():
    inside = resolver_for(
        {
            "evil.example": ["10.0.0.9"],
            "mixed.example": [PUBLIC, "127.0.0.1"],
            "ok.example": [PUBLIC],
        }
    )
    with pytest.raises(UnsafeURL):
        await safe_fetch.check_url("http://evil.example/", inside)
    with pytest.raises(UnsafeURL):
        await safe_fetch.check_url("http://mixed.example/", inside)  # one bad address is enough
    await safe_fetch.check_url("http://ok.example/", inside)


async def test_unknown_name_is_a_fetch_error_not_a_crash():
    async def nothing(host):
        raise FetchError(f"Could not find the website '{host}'.")

    with pytest.raises(FetchError):
        await safe_fetch.check_url("http://nowhere.example/", nothing)


RESOLVE = resolver_for(
    {"example.com": [PUBLIC], "other.example": ["10.0.0.7"], "good.example": [PUBLIC]}
)


def transport(handler):
    return httpx.MockTransport(handler)


async def test_fetch_connects_to_the_checked_address_and_returns_the_body():
    seen = {}

    def handler(request: httpx.Request):
        seen["host"] = request.url.host
        seen["header"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(
            200, content=b"<html>hi</html>", headers={"content-type": "text/html"}
        )

    result = await safe_fetch.fetch(
        "https://example.com/p?q=1", resolver=RESOLVE, transport=transport(handler)
    )
    assert result.content == b"<html>hi</html>" and result.url == "https://example.com/p?q=1"
    assert seen["host"] == PUBLIC  # pinned: DNS cannot change its answer after the check
    assert seen["header"] == "example.com" and seen["sni"] == "example.com"
    assert "LocalNotebook" in seen["agent"]


async def test_redirects_are_followed_and_every_hop_is_checked():
    def handler(request: httpx.Request):
        if request.headers["host"] == "example.com":
            return httpx.Response(302, headers={"location": "https://good.example/final"})
        return httpx.Response(200, content=b"final")

    result = await safe_fetch.fetch(
        "https://example.com/", resolver=RESOLVE, transport=transport(handler)
    )
    assert result.content == b"final" and result.url == "https://good.example/final"


@pytest.mark.parametrize(
    "location",
    ["http://127.0.0.1/admin", "http://other.example/x", "file:///etc/passwd", "http://localhost/"],
)
async def test_a_redirect_into_the_private_network_is_refused(location):
    def handler(request: httpx.Request):
        return httpx.Response(302, headers={"location": location})

    with pytest.raises(UnsafeURL):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(handler)
        )


async def test_redirect_loops_stop():
    def handler(request: httpx.Request):
        return httpx.Response(302, headers={"location": "https://example.com/again"})

    with pytest.raises(FetchError, match="too many times"):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(handler)
        )


async def test_http_errors_become_readable_messages():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(FetchError, match="HTTP 404"):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(handler)
        )


async def test_response_size_is_capped_by_header_and_by_streaming():
    def declared(request):
        return httpx.Response(200, content=b"x", headers={"content-length": str(50 * 1024 * 1024)})

    with pytest.raises(FetchError, match="20 MB"):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(declared)
        )

    def chunked(request):
        async def body():
            for _ in range(10):
                yield b"x" * 1000

        return httpx.Response(200, content=body())

    with pytest.raises(FetchError, match="20 MB"):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(chunked), max_bytes=5000
        )
    ok = await safe_fetch.fetch(
        "https://example.com/", resolver=RESOLVE, transport=transport(chunked), max_bytes=10_000
    )
    assert len(ok.content) == 10_000


async def test_timeouts_and_connection_errors_are_reported():
    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(FetchError, match="too long"):
        await safe_fetch.fetch("https://example.com/", resolver=RESOLVE, transport=transport(slow))

    def broken(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(FetchError, match="Could not reach"):
        await safe_fetch.fetch(
            "https://example.com/", resolver=RESOLVE, transport=transport(broken)
        )


def test_public_ip_rules():
    import ipaddress

    for address, public in [
        ("93.184.216.34", True),
        ("8.8.8.8", True),
        ("2606:4700::1111", True),
        ("::1", False),
        ("10.1.1.1", False),
    ]:
        assert safe_fetch.is_public_ip(ipaddress.ip_address(address)) is public


# --- real TLS to a pinned address ---------------------------------------------------------------


def _self_signed(tmp_path, name):
    import shutil
    import subprocess

    if not shutil.which("openssl"):
        pytest.skip("openssl is not installed")
    cert, key = tmp_path / f"{name}.pem", tmp_path / f"{name}.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            f"/CN={name}",
            "-addext",
            f"subjectAltName=DNS:{name}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def _serve_tls(cert, key):
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = f"host={self.headers['Host']}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


async def test_tls_is_verified_against_the_name_even_though_we_connect_to_the_checked_address(
    tmp_path, monkeypatch
):
    cert, key = _self_signed(tmp_path, "pinned.test")
    server = _serve_tls(cert, key)
    try:
        port = server.server_address[1]
        monkeypatch.setattr(
            safe_fetch, "is_public_ip", lambda ip: True
        )  # the stand-in server is local
        trust = ssl.create_default_context(cafile=str(cert))

        async def resolve(host):
            return ["127.0.0.1"]

        result = await safe_fetch.fetch(
            f"https://pinned.test:{port}/x", resolver=resolve, verify=trust
        )
        assert (
            result.content == f"host=pinned.test:{port}".encode()
        )  # right Host header, right certificate

        # a name the certificate does not cover must fail verification, not be silently accepted
        with pytest.raises(FetchError, match="Could not reach"):
            await safe_fetch.fetch(f"https://other.test:{port}/x", resolver=resolve, verify=trust)
    finally:
        server.shutdown()
