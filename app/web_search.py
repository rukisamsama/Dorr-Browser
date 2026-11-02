
"""
DorrSearch - Web Search Engine

DuckDuckGo HTML検索を優先し、結果が取得できない場合は
Bing RSS検索にフォールバックする。

検索結果はDorrSearchのAPIに返し、外部検索ページへは移動しない。
"""

from __future__ import annotations

from urllib.parse import (
    parse_qs,
    unquote,
    urlsplit,
)

import httpx
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET


DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
BING_RSS_URL = "https://www.bing.com/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

CATEGORY_PARAMS = {
    "web": {},
    "images": {"iax": "images", "ia": "images"},
    "videos": {"iax": "videos", "ia": "videos"},
    "news": {"iar": "news", "ia": "news"},
}


def _clean_url(url: str) -> str:
    """検索エンジンのリダイレクトURLを解決する。"""

    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    try:
        parsed = urlsplit(url)

        if parsed.scheme not in ("http", "https"):
            return ""

        hostname = (parsed.hostname or "").lower()

        if hostname.endswith("duckduckgo.com"):
            if parsed.path.startswith("/l/"):
                target = parse_qs(parsed.query).get("uddg")
                if target:
                    return _clean_url(unquote(target[0]))

        if hostname.endswith("bing.com"):
            if parsed.path.lower() == "/ck/a":
                target = parse_qs(parsed.query).get("u")
                if target:
                    value = target[0]
                    if value.startswith("a1"):
                        import base64
                        try:
                            decoded = base64.urlsafe_b64decode(
                                value[2:] + "=="
                            ).decode("utf-8", errors="ignore")
                            if decoded.startswith(("http://", "https://")):
                                return decoded
                        except Exception:
                            pass

        return url

    except Exception:
        return ""


def _make_result(
    url: str,
    title: str,
    description: str = "",
    source: str = "Web",
    category: str = "web",
    image: str = "",
) -> dict | None:
    """検索結果を共通形式に整える。"""

    url = _clean_url(url)

    if not url:
        return None

    title = " ".join(str(title or "").split()).strip()
    description = " ".join(
        str(description or "").split()
    ).strip()

    if not title:
        title = url

    return {
        "url": url,
        "title": title,
        "description": description,
        "content": description,
        "image": _clean_url(image) if image else "",
        "source": source,
        "type": category,
    }


def _extract_duckduckgo(
    html: str,
    category: str,
    limit: int,
) -> list[dict]:
    """DuckDuckGo HTMLから検索結果を抽出する。"""

    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    selectors = [
        ".result",
        ".web-result",
        ".results_links",
        ".result--web",
        ".tile",
    ]

    nodes = []

    for selector in selectors:
        found = soup.select(selector)
        if found:
            nodes = found
            break

    # HTML構造が変わっている場合のフォールバック
    if not nodes:
        nodes = soup.select("a.result__a, a.result-link")

    for node in nodes:
        if getattr(node, "name", "") == "a":
            anchor = node
            parent = node.parent
        else:
            anchor = node.select_one(
                "a.result__a, "
                "a.result-link, "
                "a.result__url, "
                "a.tile--img__title"
            )
            parent = node

        if anchor is None:
            continue

        url = _clean_url(anchor.get("href", ""))

        if not url or url in seen:
            continue

        title = anchor.get_text(" ", strip=True)

        description_node = parent.select_one(
            ".result__snippet, "
            ".result-snippet, "
            ".result__body, "
            ".tile__description"
        )

        description = ""

        if description_node:
            description = description_node.get_text(
                " ",
                strip=True,
            )

        image_node = parent.select_one("img")
        image_url = ""

        if image_node:
            image_url = (
                image_node.get("data-src")
                or image_node.get("data-original")
                or image_node.get("src")
                or ""
            )

        item = _make_result(
            url=url,
            title=title,
            description=description,
            source="DuckDuckGo",
            category=category,
            image=image_url,
        )

        if item:
            seen.add(url)
            results.append(item)

        if len(results) >= limit:
            break

    return results


def _extract_bing_rss(
    xml_text: str,
    limit: int,
) -> list[dict]:
    """Bing RSSからWeb検索結果を抽出する。"""

    results = []
    seen = set()

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.findall(".//item"):
        title = item.findtext("title", default="")
        url = item.findtext("link", default="")
        description = item.findtext(
            "description",
            default="",
        )

        result = _make_result(
            url=url,
            title=title,
            description=BeautifulSoup(
                description,
                "html.parser",
            ).get_text(" ", strip=True),
            source="Bing",
            category="web",
        )

        if not result:
            continue

        if result["url"] in seen:
            continue

        seen.add(result["url"])
        results.append(result)

        if len(results) >= limit:
            break

    return results


async def _search_duckduckgo(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    safe_search: bool,
    category: str,
) -> list[dict]:
    params = {
        "q": query,
        "kl": "jp-jp",
        "kp": "1" if safe_search else "-2",
        **CATEGORY_PARAMS.get(category, {}),
    }

    response = await client.get(
        DUCKDUCKGO_URL,
        params=params,
    )
    response.raise_for_status()

    return _extract_duckduckgo(
        response.text,
        category,
        limit,
    )


async def _search_bing(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    safe_search: bool,
) -> list[dict]:
    params = {
        "q": query,
        "format": "rss",
        "setlang": "ja",
        "cc": "JP",
        "safeSearch": "Strict" if safe_search else "Off",
    }

    response = await client.get(
        BING_RSS_URL,
        params=params,
    )
    response.raise_for_status()

    return _extract_bing_rss(
        response.text,
        limit,
    )


async def search_web(
    query: str,
    limit: int = 20,
    safe_search: bool = True,
    category: str = "web",
) -> list[dict]:
    """
    Web検索を実行する。

    1. DuckDuckGoを検索
    2. 結果が0件ならBing RSSを検索
    3. 両方の結果を統合して返す

    外部検索ページへのリダイレクトは行わない。
    """

    query = str(query or "").strip()

    if not query:
        return []

    if category not in CATEGORY_PARAMS:
        category = "web"

    limit = max(1, min(int(limit), 50))

    timeout = httpx.Timeout(
        15.0,
        connect=7.0,
    )

    errors = []

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=timeout,
        follow_redirects=True,
    ) as client:

        results = []

        try:
            results = await _search_duckduckgo(
                client,
                query,
                limit,
                safe_search,
                category,
            )
        except httpx.HTTPError as exc:
            errors.append(f"DuckDuckGo: {exc}")
        except Exception as exc:
            errors.append(f"DuckDuckGo解析: {exc}")

        # Web検索で0件の場合はBing RSSを使用
        if category == "web" and len(results) < limit:
            try:
                bing_results = await _search_bing(
                    client,
                    query,
                    limit,
                    safe_search,
                )

                seen = {
                    item["url"]
                    for item in results
                }

                for item in bing_results:
                    if item["url"] in seen:
                        continue

                    seen.add(item["url"])
                    results.append(item)

                    if len(results) >= limit:
                        break

            except httpx.HTTPError as exc:
                errors.append(f"Bing: {exc}")
            except Exception as exc:
                errors.append(f"Bing解析: {exc}")

    if not results and errors:
        raise RuntimeError(
            "検索サービスから結果を取得できませんでした。"
            + " / ".join(errors)
        )

    return results[:limit]


async def get_live_suggestions(
    query: str,
    limit: int = 7,
    language: str = "ja",
) -> list[str]:
    """Googleの公開サジェストから検索候補を取得する。"""

    query = str(query or "").strip()[:300]

    if not query:
        return []

    params = {
        "client": "firefox",
        "q": query,
        "hl": (
            "ja"
            if language.lower().startswith("ja")
            else "en"
        ),
    }

    try:
        async with httpx.AsyncClient(
            headers={
                "User-Agent": HEADERS["User-Agent"]
            },
            timeout=httpx.Timeout(
                4.0,
                connect=2.0,
            ),
            follow_redirects=True,
        ) as client:

            response = await client.get(
                "https://suggestqueries.google.com/complete/search",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        raw = (
            payload[1]
            if isinstance(payload, list)
            and len(payload) > 1
            else []
        )

        results = []
        seen = set()

        for value in raw:
            if not isinstance(value, str):
                continue

            value = value.strip()
            key = value.casefold()

            if value and key not in seen:
                seen.add(key)
                results.append(value)

            if len(results) >= max(
                1,
                min(int(limit), 7),
            ):
                break

        return results

    except (
        httpx.HTTPError,
        ValueError,
        TypeError,
        IndexError,
    ):
        return []
