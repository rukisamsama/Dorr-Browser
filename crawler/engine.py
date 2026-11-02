
from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx

from config import (
    CRAWLER_USER_AGENT,
    CRAWLER_TIMEOUT,
    CRAWLER_MAX_CONTENT_LENGTH,
    CRAWLER_MAX_PAGES,
    CRAWLER_DELAY,
)
from app.database import save_page
from crawler.parser import parse_page


def _validated_host(url: str) -> tuple[str, int] | None:
    """公開HTTP(S)のホストとポートを検証する。"""
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None

        if parsed.username or parsed.password:
            return None

        host = parsed.hostname.rstrip(".").lower()

        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal")
        ):
            return None

        port = parsed.port or (
            443 if parsed.scheme == "https" else 80
        )

        answers = socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )

        if not answers:
            return None

        for answer in answers:
            address = ipaddress.ip_address(
                answer[4][0].split("%", 1)[0]
            )

            if not address.is_global:
                return None

        return host, port

    except (ValueError, OSError, socket.gaierror):
        return None


def is_public_url(url: str) -> bool:
    return _validated_host(url) is not None


def _normalize_url(url: str) -> str:
    url, _fragment = urldefrag(url.strip())
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    if not parsed.hostname:
        return ""

    if parsed.username or parsed.password:
        return ""

    return parsed.geturl()


async def fetch_robots(
    client: httpx.AsyncClient,
    base_url: str,
) -> RobotFileParser:

    parsed_base = urlparse(base_url)

    robots_url = (
        f"{parsed_base.scheme}://{parsed_base.netloc}/robots.txt"
    )

    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = await client.get(
            robots_url,
            follow_redirects=False,
        )

        if response.status_code == 200:
            parser.parse(response.text.splitlines())

        elif response.status_code in (404, 410):
            parser.parse([
                "User-agent: *",
                "Disallow:",
            ])

        else:
            parser.parse([
                "User-agent: *",
                "Disallow: /",
            ])

    except httpx.HTTPError:
        parser.parse([
            "User-agent: *",
            "Disallow: /",
        ])

    return parser


async def _read_limited(
    response: httpx.Response,
    limit: int,
) -> bytes | None:

    chunks: list[bytes] = []
    total = 0

    async for chunk in response.aiter_bytes():
        total += len(chunk)

        if total > limit:
            return None

        chunks.append(chunk)

    return b"".join(chunks)


async def crawl_website(
    start_url: str,
    max_pages: int | None = None,
):

    start_url = _normalize_url(start_url)

    if not start_url or not is_public_url(start_url):
        raise ValueError(
            "公開されているHTTP/HTTPSサイトのみ指定できます。"
        )

    parsed_start = urlparse(start_url)

    start_host = (parsed_start.hostname or "").lower()

    start_port = parsed_start.port or (
        443 if parsed_start.scheme == "https" else 80
    )

    page_limit = (
        CRAWLER_MAX_PAGES
        if max_pages is None
        else max_pages
    )

    page_limit = max(
        1,
        min(int(page_limit), CRAWLER_MAX_PAGES),
    )

    queue = deque([start_url])
    queued = {start_url}
    visited: set[str] = set()

    indexed = 0
    skipped = 0
    errors = 0

    headers = {
        "User-Agent": CRAWLER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate",
    }

    timeout = httpx.Timeout(CRAWLER_TIMEOUT)

    limits = httpx.Limits(
        max_connections=4,
        max_keepalive_connections=2,
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
        trust_env=False,
    ) as client:

        robots = await fetch_robots(client, start_url)

        while queue and indexed < page_limit:

            current_url = queue.popleft()

            if current_url in visited:
                continue

            visited.add(current_url)

            parsed = urlparse(current_url)

            current_host = (
                parsed.hostname or ""
            ).lower()

            current_port = parsed.port or (
                443 if parsed.scheme == "https" else 80
            )

            # 開始地点と同じホスト・ポートだけを巡回
            if (
                current_host != start_host
                or current_port != start_port
            ):
                skipped += 1
                continue

            if not is_public_url(current_url):
                skipped += 1
                continue

            if not robots.can_fetch(
                CRAWLER_USER_AGENT,
                current_url,
            ):
                skipped += 1
                continue

            try:
                async with client.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                ) as response:

                    if response.is_redirect:

                        location = response.headers.get("location")

                        if location:
                            target = _normalize_url(
                                urljoin(current_url, location)
                            )

                            target_parsed = urlparse(target)

                            target_port = target_parsed.port or (
                                443
                                if target_parsed.scheme == "https"
                                else 80
                            )

                            if (
                                target
                                and (
                                    target_parsed.hostname or ""
                                ).lower() == start_host
                                and target_port == start_port
                                and is_public_url(target)
                                and target not in queued
                                and target not in visited
                            ):
                                queue.append(target)
                                queued.add(target)

                        skipped += 1
                        continue

                    if response.status_code != 200:
                        skipped += 1
                        continue

                    content_type = response.headers.get(
                        "content-type",
                        "",
                    ).lower()

                    if "text/html" not in content_type:
                        skipped += 1
                        continue

                    content_length = response.headers.get(
                        "content-length"
                    )

                    if content_length:
                        try:
                            if (
                                int(content_length)
                                > CRAWLER_MAX_CONTENT_LENGTH
                            ):
                                skipped += 1
                                continue
                        except ValueError:
                            pass

                    body = await _read_limited(
                        response,
                        CRAWLER_MAX_CONTENT_LENGTH,
                    )

                    if body is None:
                        skipped += 1
                        continue

                    charset = response.encoding or "utf-8"

                    html = body.decode(
                        charset,
                        errors="replace",
                    )

                page = parse_page(html, current_url)

                save_page(
                    url=current_url,
                    title=page["title"],
                    description=page["description"],
                    content=page["content"][
                        :CRAWLER_MAX_CONTENT_LENGTH
                    ],
                )

                indexed += 1

                for link in page["links"]:

                    normalized = _normalize_url(link)
                    link_parsed = urlparse(normalized)

                    link_port = link_parsed.port or (
                        443
                        if link_parsed.scheme == "https"
                        else 80
                    )

                    if (
                        normalized
                        and (
                            link_parsed.hostname or ""
                        ).lower() == start_host
                        and link_port == start_port
                        and normalized not in queued
                        and normalized not in visited
                    ):
                        queue.append(normalized)
                        queued.add(normalized)

            except (
                httpx.HTTPError,
                OSError,
                ValueError,
                UnicodeError,
            ):
                errors += 1

            if queue and CRAWLER_DELAY > 0:
                await asyncio.sleep(CRAWLER_DELAY)

    return {
        "success": True,
        "start_url": start_url,
        "indexed": indexed,
        "skipped": skipped,
        "errors": errors,
        "message": f"{indexed} ページを登録しました。",
    }
