
from __future__ import annotations

from urllib.parse import (
    urljoin,
    urlparse,
    urldefrag,
)

from bs4 import BeautifulSoup


def _clean_text(value: str, limit: int) -> str:
    return " ".join(
        (value or "").split()
    )[:limit]


def parse_page(html: str, base_url: str) -> dict:
    """ページ情報・本文・同一ホストのリンクを抽出する。"""

    soup = BeautifulSoup(
        html or "",
        "html.parser",
    )

    # 検索に不要な要素を削除
    for element in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "template",
        "canvas",
        "form",
        "nav",
        "footer",
    ]):
        element.decompose()

    # タイトル取得
    title_tag = soup.find("title")

    title = (
        title_tag.get_text(" ", strip=True)
        if title_tag
        else ""
    )

    # Open Graphのタイトルを予備として使用
    if not title:

        og_title = soup.find(
            "meta",
            attrs={"property": "og:title"},
        )

        if og_title:
            title = og_title.get("content", "")

    # 説明文取得
    description = ""

    for attrs in (
        {"name": "description"},
        {"property": "og:description"},
    ):

        meta = soup.find(
            "meta",
            attrs=attrs,
        )

        if meta and meta.get("content"):
            description = meta["content"]
            break

    # 本文抽出
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.body
        or soup
    )

    content = _clean_text(
        main.get_text(" ", strip=True),
        100_000,
    )

    # 開始URLのホスト・ポート
    base_parsed = urlparse(base_url)

    base_host = (
        base_parsed.hostname or ""
    ).lower()

    base_port = base_parsed.port or (
        443
        if base_parsed.scheme == "https"
        else 80
    )

    links: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):

        href = (
            tag.get("href") or ""
        ).strip()

        if not href:
            continue

        if href.startswith((
            "#",
            "mailto:",
            "tel:",
            "javascript:",
            "data:",
        )):
            continue

        absolute_url = urljoin(
            base_url,
            href,
        )

        absolute_url, _ = urldefrag(
            absolute_url
        )

        parsed = urlparse(absolute_url)

        port = parsed.port or (
            443
            if parsed.scheme == "https"
            else 80
        )

        if parsed.scheme not in ("http", "https"):
            continue

        if not parsed.hostname:
            continue

        if parsed.username or parsed.password:
            continue

        if parsed.hostname.lower() != base_host:
            continue

        if port != base_port:
            continue

        if absolute_url not in seen:

            seen.add(absolute_url)
            links.append(absolute_url)

    return {
        "title": _clean_text(title, 500),
        "description": _clean_text(description, 1000),
        "content": content,
        "links": links[:2000],
    }
