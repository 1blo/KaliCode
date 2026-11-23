"""WebFetch and WebSearch - Claude Code's web tools with an independent backend.

Search backends (tried in order, first one with results wins):
  1. Bing HTML        - https://www.bing.com/search       (primary, no API key)
  2. DuckDuckGo HTML  - https://html.duckduckgo.com/html/  (legacy fallback)
  3. DuckDuckGo Lite  - https://lite.duckduckgo.com/lite/
  4. Wikipedia API    - https://en.wikipedia.org/w/api.php  (knowledge lookups)

DuckDuckGo started returning HTTP 202 anti-bot challenges (no result markup),
so Bing is the default. Each backend is isolated: a failure returns an empty
list and the next backend is tried.
"""
from __future__ import annotations

import asyncio
import base64
import html as html_mod
import json
import re
import urllib.parse

import httpx

from .base import Tool, ToolResult, ToolContext, STR, BOOL, ARR, _s

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

# Bing "ck/a" redirect URLs embed the destination as base64 in the `u=a1...`
# query parameter. This regex pulls that payload out.
_BING_REDIRECT = re.compile(r"[?&]u=a1([A-Za-z0-9+/=_-]+)")


def html_to_text(html: str, limit: int = 100000) -> str:
    """Stdlib HTML -> readable text (no bs4 dependency)."""
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    # preserve structure of common tags
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|section|article|li|tr|h[1-6]|pre|blockquote)>", "\n", html, flags=re.I)
    html = re.sub(r"<(h[1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)[1]) + " ", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "- ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = html_mod.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()[:limit]


def _clean(text: str) -> str:
    """Strip tags + entities and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def _decode_bing_url(href: str) -> str:
    """Unwrap Bing's /ck/a?...&u=a1<base64> redirect into the real URL."""
    if "bing.com/ck/a" not in href:
        return href
    m = _BING_REDIRECT.search(href)
    if not m:
        return href
    payload = m.group(1)
    # Bing uses a url-safe-ish base64 without standard padding.
    padded = payload + "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        try:
            raw = base64.b64decode(padded.encode("ascii"))
        except Exception:
            return href
    try:
        url = raw.decode("utf-8")
    except UnicodeDecodeError:
        return href
    return url if url.startswith("http") else href


# Filler words that make Bing treat a query as a dictionary/definition lookup
# ("official python docs" -> Merriam-Webster entries instead of docs.python.org).
_QUERY_FILLER = re.compile(
    r"^\s*(?:please\s+)?(?:the\s+)?"
    r"(?:official\s+|primary\s+|main\s+|best\s+|canonical\s+|"
    r"docs?\s+(?:for\s+|of\s+|page\s+)?|documentation\s+(?:for\s+|of\s+|page\s+)?|"
    r"reference\s+(?:for\s+|of\s+)?|"
    r"find\s+(?:the\s+)?|search\s+(?:for\s+)?|look\s+up\s+(?:the\s+)?|"
    r"locate\s+(?:the\s+)?|get\s+(?:the\s+)?|fetch\s+(?:the\s+)?|show\s+me\s+)",
    re.I,
)


def _normalize_query(query: str) -> str:
    """Strip leading filler so the search engine returns topical results."""
    out = query.strip()
    for _ in range(3):  # peel at most a few stacked filler phrases
        new = _QUERY_FILLER.sub("", out).strip()
        if new == out or not new:
            break
        out = new
    return out


# Matches a domain-ish token: "docs.python.org", "example.co.uk", "roblox.com".
_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})\b", re.I)


def _domain_tokens(query: str) -> list[str]:
    """Extract domain-like tokens from a query (e.g. docs.python.org)."""
    out: list[str] = []
    for m in _DOMAIN_RE.finditer(query or ""):
        d = m.group(1).lower()
        # Skip common filename extensions that are not domains.
        if d.rsplit(".", 1)[-1] in {"png", "jpg", "jpeg", "gif", "pdf", "zip",
                                    "py", "js", "ts", "html", "htm", "md",
                                    "json", "txt", "exe", "dll", "cs", "lua"}:
            continue
        if d not in out:
            out.append(d)
    return out


class WebFetch(Tool):
    name = "WebFetch"
    # Spec section 2.3 [VERBATIM 1.x def - still accurate for 2.x params];
    # the 2.x description was RECONSTRUCTED in the spec, so the 1.x wording is
    # the closest verified text.
    description = """- Fetches content from a specified URL and processes it using an AI model
- Takes a URL and a prompt as input
- Fetches the URL content, converts HTML to markdown
- Processes the content with the prompt using a small, fast model
- Returns the model's response about the content
- Use this tool when you need to retrieve and analyze web content

Usage notes:
  - IMPORTANT: If an MCP-provided web fetch tool is available, prefer using that tool instead of this one, as it may have fewer restrictions. All MCP-provided tools start with "mcp__".
  - The URL must be a fully-formed valid URL
  - HTTP URLs will be automatically upgraded to HTTPS
  - The prompt should describe what information you want to extract from the page
  - This tool is read-only and does not modify any files
  - Results may be summarized if the content is very large
  - Includes a self-cleaning 15-minute cache for faster responses when repeatedly accessing the same URL"""
    schema = _s(
        {
            "url": {**STR, "description": "The HTTP or HTTPS URL to fetch"},
            "prompt": {**STR, "description": "What to extract from the page"},
        },
        required=["url", "prompt"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        url = args["url"].strip()
        prompt = args.get("prompt", "")
        if not re.match(r"^https?://", url):
            return ToolResult("Error: URL must start with http:// or https://", error=True)
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=45.0, headers={"User-Agent": UA}) as client:
                resp = await client.get(url)
        except httpx.HTTPError as e:
            return ToolResult(f"Request failed: {e}", error=True)
        ctype = resp.headers.get("content-type", "")
        body = resp.text
        if "json" in ctype:
            try:
                text = json.dumps(resp.json(), indent=2)[:100000]
            except Exception:
                text = body[:100000]
        elif "html" in ctype or "<html" in body[:500].lower():
            text = html_to_text(body)
        else:
            text = body[:100000]

        header = f"Fetched {url} (HTTP {resp.status_code}, {len(text):,} chars)"
        note = f"\n\n[Prompt: {prompt}]\nReview the content above with this prompt in mind."
        return ToolResult(header + "\n\n" + text[:100000] + note)


class WebSearch(Tool):
    name = "WebSearch"
    # Verbatim from the Sonnet 4.6 CLI leak (spec section 2.1).
    description = """- Allows Claude to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks, including links as markdown hyperlinks
- Use this tool for accessing information beyond Claude's knowledge cutoff
- Searches are performed automatically within a single API call

CRITICAL REQUIREMENT - You MUST follow this:
  - After answering the user's question, you MUST include a "Sources:" section at the end of your response
  - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: `[Title](URL)`
  - This is MANDATORY - never skip including sources in your response

Usage notes:
  - Domain filtering is supported to include or block specific websites
  - Web search is only available in the US

IMPORTANT - Use the correct year in search queries:
  - The current month is (provided in the conversation below). You MUST use this year when searching for recent information, documentation, or current events."""
    schema = _s(
        {
            "query": {"type": "string", "minLength": 2, "description": "The search query to use"},
            "allowed_domains": {"type": "array", "items": {"type": "string"}, "description": "Only include search results from these domains"},
            "blocked_domains": {"type": "array", "items": {"type": "string"}, "description": "Never include search results from these domains"},
            "mode": {"type": "string", "enum": ["standard", "extended"], "description": "\"standard\": the normal web search: quick and cheap; right for straightforward lookups (reference facts, official pages, documentation, well-known people, places and topics) and simple follow-up lookups. \"extended\": a thorough, fresh search at several times the cost and latency."},
        },
        required=["query", "mode"],
    )

    async def run(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return ToolResult("Error: query is required", error=True)
        allowed = [str(d).lower().lstrip(".") for d in (args.get("allowed_domains") or [])]
        blocked = [str(d).lower().lstrip(".") for d in (args.get("blocked_domains") or [])]
        extended = str(args.get("mode", "standard")).lower() == "extended"

        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, self._search, query, extended)

        if not results:
            return ToolResult(
                f"No results for: {query}\n\n"
                "All search backends returned no usable results. "
                "Try a different query, or use WebFetch with a direct URL."
            )

        # Apply domain filters (the schema advertises them, so honour them).
        filtered = []
        for r in results:
            host = urllib.parse.urlparse(r["url"]).hostname or ""
            host = host.lower()
            if host.startswith("www."):
                host = host[4:]
            if allowed and not any(host == d or host.endswith("." + d) for d in allowed):
                continue
            if blocked and any(host == d or host.endswith("." + d) for d in blocked):
                continue
            filtered.append(r)

        if not filtered:
            return ToolResult(
                f"No results for: {query}\n\n"
                f"({len(results)} results found, but all were filtered out by "
                "allowed_domains / blocked_domains.)"
            )

        lines = []
        for r in filtered[:10]:
            lines.append(f"{r['title']}\n  {r['url']}\n  {r['snippet']}")
        header = f"Web search results for: {query}\n({len(filtered[:10])} results)\n"
        return ToolResult(header + "\n\n".join(lines))

    # ------------------------------------------------------------- backends
    @classmethod
    def _search(cls, query: str, extended: bool = False) -> list[dict]:
        """Try each backend in order until one returns *relevant* results.

        Some engines occasionally serve an unrelated cached SERP (Bing has
        been observed returning Switch-hacking results for a hardware query,
        and dictionary definitions for a query starting with "official").
        A result set whose titles share no meaningful token with the query is
        treated as a miss and the next backend is tried.

        Wikipedia is a genuine search engine but it is encyclopaedic, so it
        is tried LAST: it must never displace real web results.
        """
        # Leading filler words make Bing treat the query as a definition
        # lookup ("official python docs" -> dictionary entries). Strip them.
        attempts = [query]
        normalized = _normalize_query(query)
        if normalized and normalized != query:
            attempts.append(normalized)

        # A query that names a domain ("docs.python.org asyncio") is treated
        # by Bing as plain search terms and returns unrelated hits
        # (docs.google.com). The `site:` operator gets the real answer.
        domains = _domain_tokens(query)
        if domains:
            rest = _normalize_query(re.sub(r"\b[a-z0-9.-]+\.[a-z]{2,}\b", " ", query,
                                           flags=re.I)).strip()
            site_query = f"site:{domains[0]}"
            if rest:
                site_query += f" {rest}"
            attempts.append(site_query)

        search_backends = (cls._bing_search, cls._ddg_search, cls._ddg_lite_search)
        fallback: list[dict] = []

        for q in attempts:
            for backend in search_backends:
                try:
                    results = backend(q, extended)
                except Exception:
                    results = []
                if not results:
                    continue
                if cls._is_dictionary_serp(results):
                    # A dictionary page is never the right answer for a
                    # technical/web lookup - keep looking.
                    continue
                if cls._looks_relevant(q, results):
                    return results
                if not fallback:
                    fallback = results

        # Last resort: Wikipedia (encyclopaedic, but always available).
        for q in attempts:
            try:
                results = cls._wikipedia_search(q, extended)
            except Exception:
                results = []
            if results:
                return results

        return fallback

    # ------------------------------------------------------------ relevance
    @staticmethod
    def _looks_relevant(query: str, results: list[dict]) -> bool:
        """Heuristic: do any result titles/URLs share a token with the query?

        The query is normalised first, so filler words like "official" or
        "docs" (which match dictionary-definition SERPs) do not count as a
        relevance signal. Domain-like tokens ("docs.python.org") are matched
        against the result host specifically.
        """
        stop = {
            "the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "are",
            "how", "what", "when", "where", "which", "who", "why", "with", "from",
            "latest", "new", "best", "top", "get", "use", "using", "you", "your",
            "site", "com", "www", "http", "https",
            # filler / intent words that appear on dictionary pages
            "official", "documentation", "tutorial", "guide", "reference",
            "example", "examples", "intro", "introduction", "overview",
            "meaning", "definition", "define", "dictionary",
        }
        raw = _normalize_query(query).lower()
        # "docs.python.org" -> host-ish tokens the URL must contain
        domain_tokens = set(_domain_tokens(raw))
        qtokens = {
            t for t in re.findall(r"[a-z0-9]{3,}", raw)
            if t not in stop
        }
        if not qtokens and not domain_tokens:
            return True  # nothing meaningful to compare against

        for r in results[:5]:
            url = r.get("url", "")
            host = (urllib.parse.urlparse(url).hostname or "").lower()
            # A domain in the query must appear in the result host.
            if domain_tokens:
                if not any(d in host or host.endswith("." + d.lstrip(".")) or
                           d.lstrip(".") in host for d in domain_tokens):
                    continue
                return True
            blob = (r.get("title", "") + " " + url + " "
                    + r.get("snippet", "")).lower()
            rtokens = set(re.findall(r"[a-z0-9]{3,}", blob))
            if qtokens & rtokens:
                return True
        return False

    # Dictionary SERPs (Merriam-Webster, Cambridge, ...) are not useful
    # answers to a technical query - treat them as a miss.
    _DICTIONARY_HOSTS = (
        "merriam-webster.com", "dictionary.cambridge.org", "dictionary.com",
        "thesaurus.com", "vocabulary.com", "wordreference.com",
        "collinsdictionary.com", "definitions.net", "urbandictionary.com",
    )

    @classmethod
    def _is_dictionary_serp(cls, results: list[dict]) -> bool:
        """True when every top result is a dictionary/definition page."""
        top = results[:3]
        if not top:
            return False
        hits = 0
        for r in top:
            host = (urllib.parse.urlparse(r.get("url", "")).hostname or "").lower()
            if any(h in host for h in cls._DICTIONARY_HOSTS):
                hits += 1
        return hits >= max(1, len(top) - 1)

    @staticmethod
    def _bing_search(query: str, extended: bool = False) -> list[dict]:
        """Primary backend: Bing's HTML SERP.

        Result blocks look like <li class="b_algo">...<h2><a href=...>Title
        </a></h2>...<p class="b_lineclamp...">snippet</p>...</li>.
        """
        results: list[dict] = []
        count = 20 if extended else 10
        resp = httpx.get(
            "https://www.bing.com/search",
            params={"q": query, "count": count, "setlang": "en"},
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=30.0,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        blocks = re.findall(
            r'<li class="b_algo".*?(?=<li class="b_algo"|</ol>)', resp.text, re.S
        )
        for block in blocks:
            a = re.search(
                r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S
            )
            if not a:
                continue
            href = html_mod.unescape(a.group(1))
            title = _clean(a.group(2))
            if not title:
                continue
            url = _decode_bing_url(href)

            snippet = ""
            sn = re.search(r'<p class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.S)
            if not sn:
                sn = re.search(r'<div class="b_caption".*?<p[^>]*>(.*?)</p>', block, re.S)
            if not sn:
                sn = re.search(r'<div class="b_snippet".*?<p[^>]*>(.*?)</p>', block, re.S)
            if sn:
                snippet = _clean(sn.group(1))
            if not snippet:
                # Fall back to the <cite> breadcrumb.
                cite = re.search(r"<cite[^>]*>(.*?)</cite>", block, re.S)
                if cite:
                    snippet = _clean(cite.group(1))

            results.append({"title": title, "url": url, "snippet": snippet})
        return results

    @staticmethod
    def _ddg_search(query: str, extended: bool = False) -> list[dict]:
        """DuckDuckGo HTML endpoint - no API key required.

        NOTE: DuckDuckGo now answers most requests with an HTTP 202
        anti-bot challenge, so this is a fallback only.
        """
        results: list[dict] = []
        try:
            resp = httpx.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"User-Agent": UA},
                timeout=30.0,
                follow_redirects=True,
            )
            for m in re.finditer(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                resp.text, re.S,
            ):
                href = m.group(1)
                # DDG wraps URLs: //duckduckgo.com/l/?uddg=<encoded>&rut=...
                if "uddg=" in href:
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = q.get("uddg", [href])[0]
                title = _clean(m.group(2))
                snippet = _clean(m.group(3))
                results.append({"title": title, "url": href, "snippet": snippet})
        except Exception:
            pass
        return results

    @staticmethod
    def _ddg_lite_search(query: str, extended: bool = False) -> list[dict]:
        """DuckDuckGo's lighter HTML endpoint (another fallback)."""
        results: list[dict] = []
        try:
            resp = httpx.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={"User-Agent": UA},
                timeout=30.0,
                follow_redirects=True,
            )
            rows = re.findall(
                r'<a[^>]+class="result-link"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S
            )
            for href, title_html in rows:
                if "uddg=" in href:
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = q.get("uddg", [href])[0]
                results.append({
                    "title": _clean(title_html),
                    "url": href,
                    "snippet": "",
                })
        except Exception:
            pass
        return results

    @staticmethod
    def _wikipedia_search(query: str, extended: bool = False) -> list[dict]:
        """Wikipedia's search API - always available, good for definitions."""
        results: list[dict] = []
        try:
            resp = httpx.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 10 if extended else 5,
                    "format": "json",
                },
                headers={"User-Agent": "KaliCode/1.0 (https://github.com/kali-code)"},
                timeout=30.0,
                follow_redirects=True,
            )
            data = resp.json()
            for hit in (data.get("query") or {}).get("search") or []:
                title = hit.get("title", "")
                slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
                snippet = _clean(re.sub(r"<[^>]+>", " ", hit.get("snippet", "")))
                results.append({
                    "title": title,
                    "url": f"https://en.wikipedia.org/wiki/{slug}",
                    "snippet": snippet,
                })
        except Exception:
            pass
        return results
