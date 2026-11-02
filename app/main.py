
from contextlib import asynccontextmanager
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from config import (
    APP_NAME,
    APP_VERSION,
    BASE_DIR,
    MAX_RESULTS,
    MIN_QUERY_LENGTH,
    CRAWLER_MAX_PAGES,
)

from app.database import (
    initialize_database,
    get_page_count,
    get_settings,
    update_settings,
    add_history,
    get_history,
    clear_history,
    add_bookmark,
    get_bookmarks,
    delete_bookmark,
)

from app.search import (
    search_pages,
    get_suggestions,
    tokenize,
)

from app.web_search import search_web, get_live_suggestions
from crawler.engine import crawl_website


# ============================================================
# Paths
# ============================================================

TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


# ============================================================
# Configuration
# ============================================================

ALLOWED_SETTINGS = {
    "theme",
    "search_engine",
    "safe_search",
    "animations",
    "language",
}

ALLOWED_SEARCH_ENGINES = {
    "dorr",
    "google",
    "bing",
    "duckduckgo",
}

ALLOWED_THEMES = {
    "dark",
    "light",
    "system",
}


# ============================================================
# Application lifecycle
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    アプリケーション起動時にデータベースを初期化する。
    既存テーブルやデータは削除しない。
    """
    initialize_database()
    yield


# ============================================================
# FastAPI application
# ============================================================

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Dorr Search API",
    lifespan=lifespan,
)


# ============================================================
# Static files and templates
# ============================================================

if not TEMPLATE_DIR.is_dir():
    raise RuntimeError(
        f"Template directory not found: {TEMPLATE_DIR}"
    )

if not STATIC_DIR.is_dir():
    raise RuntimeError(
        f"Static directory not found: {STATIC_DIR}"
    )

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)

templates = Jinja2Templates(
    directory=str(TEMPLATE_DIR)
)


# ============================================================
# Request models
# ============================================================

class SearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=300,
    )

    limit: int = Field(
        default=MAX_RESULTS,
        ge=1,
        le=100,
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("検索語を入力してください。")

        return value


class CrawlRequest(BaseModel):
    url: str = Field(
        min_length=8,
        max_length=2048,
    )

    max_pages: int = Field(
        default=CRAWLER_MAX_PAGES,
        ge=1,
        le=50,
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "URLは http または https で指定してください。"
            )

        if not parsed.hostname:
            raise ValueError("正しいURLを入力してください。")

        if parsed.username or parsed.password:
            raise ValueError(
                "認証情報を含むURLは使用できません。"
            )

        return value


class SettingsRequest(BaseModel):
    values: dict[str, Any] = Field(
        default_factory=dict
    )


class BookmarkRequest(BaseModel):
    title: str = Field(
        default="",
        max_length=500,
    )

    url: str = Field(
        min_length=8,
        max_length=2048,
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "URLは http または https で指定してください。"
            )

        if not parsed.hostname:
            raise ValueError("正しいURLを入力してください。")

        if parsed.username or parsed.password:
            raise ValueError(
                "認証情報を含むURLは使用できません。"
            )

        return value


# ============================================================
# Error handling
# ============================================================

def database_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=message,
    )


# ============================================================
# Settings validation
# ============================================================

def normalize_boolean(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"on", "true", "1"}:
            return True

        if normalized in {"off", "false", "0"}:
            return False

    raise HTTPException(
        status_code=400,
        detail=f"{key} はオンまたはオフで指定してください。",
    )


def validate_setting_values(
    values: dict[str, Any],
) -> dict[str, Any]:

    result = {}

    for key, value in values.items():

        if key not in ALLOWED_SETTINGS:
            continue

        if key == "theme":
            if value not in ALLOWED_THEMES:
                raise HTTPException(
                    status_code=400,
                    detail="無効なテーマ設定です。",
                )

        elif key == "search_engine":
            if value not in ALLOWED_SEARCH_ENGINES:
                raise HTTPException(
                    status_code=400,
                    detail="無効な検索エンジンです。",
                )

        elif key in {"safe_search", "animations"}:
            value = normalize_boolean(value, key)

        elif key == "language":
            if not isinstance(value, str):
                raise HTTPException(
                    status_code=400,
                    detail="言語設定は文字列で指定してください。",
                )

            value = value.strip()

            if not value or len(value) > 20:
                raise HTTPException(
                    status_code=400,
                    detail="言語設定が無効です。",
                )

        result[key] = value

    return result


# ============================================================
# Related search tags
# ============================================================

def generate_related_tags(
    query: str,
    results: list[dict],
    limit: int = 7,
) -> list[dict]:

    query_tokens = set(tokenize(query))
    frequencies = Counter()

    for item in results:
        title = item.get("title", "")
        description = item.get("description", "")
        content = item.get("content", "")

        text = " ".join([
            str(title),
            str(description),
            str(content)[:3000],
        ])

        for token in tokenize(text):
            if token in query_tokens:
                continue

            if len(token) < 2:
                continue

            frequencies[token] += 1

    return [
        {
            "label": token,
            "query": token,
            "count": count,
        }
        for token, count in frequencies.most_common(limit)
    ]


# ============================================================
# Home
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
        },
    )


# ============================================================
# Statistics
# ============================================================

@app.get("/api/stats")
async def stats():
    try:
        page_count = get_page_count()
    except Exception:
        raise database_error(
            "統計情報を取得できませんでした。"
        )

    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "indexed_pages": page_count,
    }


# ============================================================
# Search
# ============================================================

@app.post("/api/search")
async def search(request: SearchRequest):

    query = request.query.strip()

    if len(query) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail="検索語を入力してください。",
        )

    try:
        add_history(query)

        settings = get_settings()

        safe_value = str(
            settings.get("safe_search", "true")
        ).strip().lower()

        safe_search = safe_value not in {
            "false",
            "off",
            "0",
            "no",
        }

        local_results = search_pages(
            query,
            limit=request.limit,
        )

        web_results = []

        try:
            web_results = await search_web(
                query=query,
                limit=request.limit,
                safe_search=safe_search,
            )

        except Exception as error:
            print(f"[DorrSearch] Web検索エラー: {error}")

            if not local_results:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Web検索サービスに接続できませんでした。"
                        "時間をおいて再試行してください。"
                    ),
                ) from error

            web_results = []

        results = []
        seen_urls = set()

        # Web検索結果を優先
        for item in web_results:
            url = item.get("url", "")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)
            results.append(item)

            if len(results) >= request.limit:
                break

        # ローカル検索結果を追加
        for item in local_results:
            url = item.get("url", "")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            item = dict(item)
            item["source"] = "local"

            results.append(item)

            if len(results) >= request.limit:
                break

        related_tags = generate_related_tags(
            query,
            results,
            limit=7,
        )

    except HTTPException:
        raise

    except Exception:
        raise database_error(
            "検索中にエラーが発生しました。"
        )

    return {
        "query": query,
        "count": len(results),
        "results": results,
        "related_tags": related_tags,
        "web_count": len(web_results),
        "local_count": len(local_results),
        "search_type": "web_and_local",
    }


# ============================================================
# Search suggestions
# ============================================================

@app.get("/api/suggestions")
async def suggestions(
    q: str = Query(default="", max_length=300),
    language: str = Query(default="ja", max_length=8),
):
    query = q.strip()
    if not query:
        return {"suggestions": [], "source": "none"}

    # 外部サジェストを先に取得。利用できない場合はローカル履歴にフォールバック。
    live_items = await get_live_suggestions(
        query, limit=7, language=language
    )

    try:
        local_items = get_suggestions(query, limit=7)
    except Exception:
        local_items = []

    merged: list[dict] = []
    seen: set[str] = set()
    for item in live_items:
        label = str(item).strip()
        key = label.casefold()
        if label and key not in seen:
            seen.add(key)
            merged.append({"title": label, "query": label, "source": "live"})
    for item in local_items:
        label = str(item.get("title") or item.get("query") or item).strip()
        key = label.casefold()
        if label and key not in seen:
            seen.add(key)
            merged.append({"title": label, "query": label, "source": "local"})
        if len(merged) >= 7:
            break

    return {
        "suggestions": merged[:7],
        "source": "live" if live_items else "local",
        "external_suggestions_enabled": True,
    }


# ============================================================
# Search history
# ============================================================

@app.get("/api/history")
async def history(
    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
):

    try:
        items = get_history(limit=limit)

    except Exception:
        raise database_error(
            "検索履歴を取得できませんでした。"
        )

    return {
        "history": items,
    }


@app.delete("/api/history")
async def remove_history():

    try:
        clear_history()

    except Exception:
        raise database_error(
            "検索履歴を削除できませんでした。"
        )

    return {
        "success": True,
        "message": "検索履歴を削除しました。",
    }


# ============================================================
# Bookmarks
# ============================================================

@app.get("/api/bookmarks")
async def bookmarks():

    try:
        items = get_bookmarks()

    except Exception:
        raise database_error(
            "ブックマークを取得できませんでした。"
        )

    return {
        "bookmarks": items,
    }


@app.post("/api/bookmarks")
async def create_bookmark(
    request: BookmarkRequest,
):

    try:
        add_bookmark(
            title=request.title.strip(),
            url=request.url.strip(),
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:
        raise database_error(
            "ブックマークを保存できませんでした。"
        )

    return {
        "success": True,
        "message": "ブックマークを保存しました。",
    }


@app.delete("/api/bookmarks/{bookmark_id}")
async def remove_bookmark(
    bookmark_id: int,
):

    if bookmark_id < 1:
        raise HTTPException(
            status_code=400,
            detail="無効なブックマークIDです。",
        )

    try:
        delete_bookmark(bookmark_id)

    except Exception:
        raise database_error(
            "ブックマークを削除できませんでした。"
        )

    return {
        "success": True,
        "message": "ブックマークを削除しました。",
    }


# ============================================================
# Settings
# ============================================================

@app.get("/api/settings")
async def read_settings():

    try:
        settings = get_settings()

    except Exception:
        raise database_error(
            "設定を取得できませんでした。"
        )

    return {
        "settings": settings,
    }


@app.put("/api/settings")
async def write_settings(
    request: SettingsRequest,
):

    values = validate_setting_values(
        request.values
    )

    try:
        if values:
            update_settings(values)

        settings = get_settings()

    except Exception:
        raise database_error(
            "設定を保存できませんでした。"
        )

    return {
        "success": True,
        "settings": settings,
    }


# ============================================================
# Website crawler
# ============================================================

@app.post("/api/crawl")
async def crawl(
    request: CrawlRequest,
):

    try:
        result = await crawl_website(
            request.url.strip(),
            max_pages=request.max_pages,
        )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="クロール中にエラーが発生しました。",
        )

    return result


# ============================================================
# Health check
# ============================================================

@app.get("/api/health")
async def health():

    return {
        "status": "ok",
        "name": APP_NAME,
        "version": APP_VERSION,
    }


# ============================================================
# API information
# ============================================================

@app.get("/api")
async def api_information():

    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "running",
        "features": [
            "search",
            "suggestions",
            "related_tags",
            "history",
            "bookmarks",
            "settings",
            "website_crawler",
        ],
        "endpoints": {
            "home": "/",
            "search": "/api/search",
            "suggestions": "/api/suggestions",
            "stats": "/api/stats",
            "history": "/api/history",
            "bookmarks": "/api/bookmarks",
            "settings": "/api/settings",
            "crawl": "/api/crawl",
            "health": "/api/health",
            "documentation": "/docs",
        },
    }
