"""Web tools: fetch_url (with a private-address guard) and DuckDuckGo web_search."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from meclaw.tools.base import ToolContext, ToolSpec, as_int

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2_000_000
TOTAL_DEADLINE_SECONDS = 20
TIMEOUT_SECONDS = 10
MAX_SEARCH_RESULTS = 10
USER_AGENT = "MeClaw/1.0"

_SKIP_TAGS = {"script", "style", "noscript", "svg"}
_BUFFER_TAGS = {"nav", "footer"}  # dropped only when properly closed
_BLOCK_TAGS = {
    "p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article",
}
_REDIRECT_CODES = {301, 302, 303, 307, 308}
_TEXT_TYPES = {"text/plain", "application/json"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._parts: list[str] = []
        self._skip: list[str] = []
        self._buffered: list[tuple[str, int]] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        self._in_title = tag == "title"
        if tag in _BUFFER_TAGS:
            self._buffered.append((tag, len(self._parts)))
        elif tag in _SKIP_TAGS:
            self._skip.append(tag)
        elif tag in _BLOCK_TAGS and not self._skip:
            self._parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_TAGS and not self._skip:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _BUFFER_TAGS:
            for i in range(len(self._buffered) - 1, -1, -1):
                if self._buffered[i][0] == tag:
                    del self._parts[self._buffered[i][1]:]
                    del self._buffered[i:]
                    break
        elif tag in _SKIP_TAGS:
            if tag in self._skip:
                while self._skip and self._skip.pop() != tag:
                    pass
        elif tag in _BLOCK_TAGS and not self._skip:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(self._parts).split("\n")]
        out: list[str] = []
        for line in lines:
            if line or (out and out[-1]):
                out.append(line)
        return "\n".join(out).strip()


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return re.sub(r"\s+", " ", parser.title).strip(), parser.text()


def _resolve(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        if _is_blocked(ip.ipv4_mapped):
            return True
    return (
        not ip.is_global
        or getattr(ip, "is_site_local", False)
        or ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def check_public_host(host: str) -> None:
    """Raise ValueError if host is, or resolves to, a non-public address.

    Note: checking before connecting leaves a small DNS-rebinding window.
    """
    try:
        addresses = [str(ipaddress.ip_address(host))]  # literal IP: no DNS lookup
    except ValueError:
        try:
            addresses = _resolve(host)
        except OSError:
            raise ValueError(f"Could not resolve host: {host}") from None
        if not addresses:
            raise ValueError(f"Could not resolve host: {host}")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            raise ValueError(f"Blocked address: {host}") from None
        if _is_blocked(ip):
            raise ValueError(f"Blocked address: {host}")


async def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are supported.")
    if not parts.hostname:
        raise ValueError("Invalid URL.")
    await asyncio.to_thread(check_public_host, parts.hostname)


async def _read_body(response: httpx.Response) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return b"".join(chunks)[:MAX_BODY_BYTES], True
    return b"".join(chunks), False


def _decode(response: httpx.Response, body: bytes) -> str:
    encoding = response.charset_encoding or "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def fetch(url: str, transport: httpx.AsyncBaseTransport | None = None) -> str:
    """Fetch a public web page as text. Never raises; errors are returned as text."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=TIMEOUT_SECONDS,
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            trust_env=False,
        ) as client, asyncio.timeout(TOTAL_DEADLINE_SECONDS):
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                await _check_url(current)
                async with client.stream("GET", current) as response:
                    location = response.headers.get("location")
                    if response.status_code in _REDIRECT_CODES and location:
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        return f"HTTP {response.status_code}"
                    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                    if content_type != "text/html" and content_type not in _TEXT_TYPES:
                        return f"Unsupported content type: {content_type or 'unknown'}"
                    body, truncated = await _read_body(response)
                    text = _decode(response, body)
                    if content_type == "text/html":
                        title, text = html_to_text(text)
                        text = f"Title: {title}\nURL: {current}\n\n{text}"
                    if truncated:
                        text += "\n[content truncated at 2 MB]"
                    return text
            return "Too many redirects."
    except ValueError as exc:
        return str(exc)
    except (httpx.TimeoutException, TimeoutError):
        return "Request timed out."
    except Exception as exc:
        return f"Request failed: {exc}"


def _ddgs_text(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    return DDGS().text(query, region="tr-tr", max_results=max_results)


async def fetch_url(ctx: ToolContext, url: str) -> str:
    return await fetch(url)


async def web_search(ctx: ToolContext, query: str, max_results: int | str | None = 5) -> str:
    try:
        limit = max(1, min(as_int(max_results, 5), MAX_SEARCH_RESULTS))
        results = await asyncio.to_thread(_ddgs_text, query, limit)
    except Exception as exc:
        return f"Web search failed: {exc}"
    if not results:
        return "No results found."
    return "\n".join(
        f"{i}. {r.get('title', '')}\n   {r.get('href', '')}\n   {r.get('body', '')}"
        for i, r in enumerate(results, 1)
    )


WEB_TOOLS: list[ToolSpec] = [
    ToolSpec(
        "fetch_url",
        "Fetch a public web page (http/https) and return its readable text. "
        "Local, private and LAN addresses are blocked.",
        {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Full http or https URL."}},
            "required": ["url"],
        },
        fetch_url,
    ),
    ToolSpec(
        "web_search",
        "Search the web (DuckDuckGo) and return titles, URLs and snippets.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {"type": "integer", "description": "Number of results (default 5, max 10)."},
            },
            "required": ["query"],
        },
        web_search,
    ),
]
