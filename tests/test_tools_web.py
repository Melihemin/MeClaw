import asyncio

import httpx
import pytest

from meclaw.tools import web
from meclaw.tools.web import check_public_host, fetch, html_to_text
from tests.fakes import make_registry


def public(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34"])


def run_tool(tmp_path):
    reg = make_registry(tmp_path)
    return lambda name, **a: asyncio.run(reg.run(name, a))


def test_html_to_text():
    title, text = html_to_text("<html><head><title>Başlık</title><style>x{}</style></head><body><nav>menü</nav><h1>Selam</h1><p>bir  <b>iki</b></p><script>kötü()</script><footer>alt</footer></body></html>")
    assert title == "Başlık" and "Selam" in text and "bir iki" in text
    assert "menü" not in text and "kötü" not in text and "alt" not in text and "x{}" not in text


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.1.1", "::1", "0.0.0.0", "224.0.0.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1"])
def test_blocked_ips(monkeypatch, ip):
    monkeypatch.setattr(web, "_resolve", lambda host: [ip])
    with pytest.raises(ValueError, match="Blocked address"):
        check_public_host("ornek.com")


def test_literal_ip_blocked():
    assert asyncio.run(fetch("http://127.0.0.1:8000/api")) == "Blocked address: 127.0.0.1"
    assert asyncio.run(fetch("http://[::1]/")) == "Blocked address: ::1"


def test_resolve_failure(monkeypatch):
    def boom(host):
        raise OSError("nope")
    monkeypatch.setattr(web, "_resolve", boom)
    assert asyncio.run(fetch("https://yok.example")) == "Could not resolve host: yok.example"


def test_fetch_rejects_mixed_resolution(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34", "10.0.0.1"])
    assert asyncio.run(fetch("https://ornek.com")) == "Blocked address: ornek.com"


def test_fetch_html(monkeypatch):
    public(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<title>T</title><p>içerik</p>"))
    out = asyncio.run(fetch("https://ornek.com/a", transport=t))
    assert out.startswith("Title: T\nURL: https://ornek.com/a\n") and "içerik" in out


def test_fetch_redirect_followed_relative(monkeypatch):
    public(monkeypatch)

    def handler(r):
        if r.url.path == "/a":
            return httpx.Response(302, headers={"location": "/b"})
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="son")
    assert asyncio.run(fetch("https://ornek.com/a", transport=httpx.MockTransport(handler))) == "son"


def test_fetch_redirect_to_private_blocked(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["192.168.1.2"] if host == "ic.local" else ["93.184.216.34"])
    t = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://ic.local/"}))
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "Blocked address: ic.local"


def test_fetch_redirect_bad_scheme(monkeypatch):
    public(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "file:///etc/passwd"}))
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "Only http and https URLs are supported."


def test_fetch_too_many_redirects(monkeypatch):
    public(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "https://ornek.com/"}))
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "Too many redirects."


def test_fetch_scheme_and_type(monkeypatch):
    public(monkeypatch)
    assert asyncio.run(fetch("file:///etc/passwd")) == "Only http and https URLs are supported."
    t = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"))
    assert asyncio.run(fetch("https://ornek.com/x.pdf", transport=t)) == "Unsupported content type: application/pdf"


def test_fetch_http_error_and_timeout(monkeypatch):
    public(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(404, text="yok"))
    assert asyncio.run(fetch("https://ornek.com", transport=t)) == "HTTP 404"

    def slow(r):
        raise httpx.ReadTimeout("t")
    assert asyncio.run(fetch("https://ornek.com", transport=httpx.MockTransport(slow))) == "Request timed out."


def test_fetch_size_cap(monkeypatch):
    public(monkeypatch)
    t = httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"a" * 3_000_000))
    out = asyncio.run(fetch("https://ornek.com/b", transport=t))
    assert out.endswith("[content truncated at 2 MB]") and len(out) < 2_000_100


def test_web_search(monkeypatch, tmp_path):
    run = run_tool(tmp_path)
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: [{"title": "Başlık", "href": "https://a.com", "body": "özet"}])
    assert run("web_search", query="x") == "1. Başlık\n   https://a.com\n   özet"
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: (_ for _ in ()).throw(RuntimeError("ratelimit")))
    assert run("web_search", query="x") == "Web search failed: ratelimit"


def test_web_search_clamps_and_empty(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(web, "_ddgs_text", lambda q, n: seen.append(n) or [])
    assert run_tool(tmp_path)("web_search", query="x", max_results=99) == "No results found."
    assert seen == [10]


def test_web_tools_only_when_internet(tmp_path):
    assert {"fetch_url", "web_search"} <= make_registry(tmp_path).names()
    assert not {"fetch_url", "web_search"} & make_registry(tmp_path, internet=False).names()
