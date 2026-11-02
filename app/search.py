
import re
from collections import Counter, defaultdict

from config import MAX_RESULTS, MIN_QUERY_LENGTH
from app.database import get_connection


TOKEN_PATTERN = re.compile(
    r"[a-z0-9_]+|[ぁ-んァ-ヶー一-龠]+",
    re.IGNORECASE,
)

SPLIT_PATTERN = re.compile(
    r"[\s　、。,.!?！？:：;；|｜/／\\・「」『』（）()\[\]【】<>]+"
)


def tokenize(query):
    """
    日本語・英数字を検索語として抽出する。
    """

    query = str(query or "").strip().lower()

    if not query:
        return []

    tokens = TOKEN_PATTERN.findall(query)

    result = []
    seen = set()

    for token in tokens:
        token = token.strip()

        if not token or token in seen:
            continue

        seen.add(token)
        result.append(token)

    return result[:12]


def search_pages(query, limit=None):
    """
    インデックス済みページを検索する。
    """

    query = str(query or "").strip()

    if len(query) < MIN_QUERY_LENGTH:
        return []

    tokens = tokenize(query)

    if not tokens:
        return []

    if limit is None:
        limit = MAX_RESULTS

    limit = max(1, min(int(limit), 100))

    conditions = []
    parameters = []

    for token in tokens:
        pattern = f"%{token}%"

        conditions.append("""
            (
                title LIKE ?
                OR description LIKE ?
                OR content LIKE ?
            )
        """)

        parameters.extend([
            pattern,
            pattern,
            pattern,
        ])

    where_clause = " OR ".join(conditions)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                url,
                title,
                description,
                content,
                indexed_at
            FROM pages
            WHERE {where_clause}
            LIMIT 1000
            """,
            parameters,
        ).fetchall()

    results = []

    for row in rows:
        title = row["title"] or ""
        description = row["description"] or ""
        content = row["content"] or ""
        url = row["url"] or ""

        title_lower = title.lower()
        description_lower = description.lower()
        content_lower = content.lower()
        url_lower = url.lower()

        score = 0

        for token in tokens:
            if token in title_lower:
                score += 12

            if title_lower.startswith(token):
                score += 3

            if token in description_lower:
                score += 5

            if token in content_lower:
                score += 1

        if all(token in title_lower for token in tokens):
            score += 10

        if any(token in url_lower for token in tokens):
            score += 2

        if score <= 0:
            continue

        results.append({
            "id": row["id"],
            "url": url,
            "title": title or url,
            "description": description,
            "content": content,
            "indexed_at": row["indexed_at"],
            "score": score,
        })

    results.sort(
        key=lambda item: (
            item["score"],
            item["title"].lower(),
        ),
        reverse=True,
    )

    return results[:limit]


def get_suggestions(query, limit=7):
    """
    インデックス済みページから検索候補を取得する。
    """

    query = str(query or "").strip()

    if not query:
        return []

    limit = max(1, min(int(limit), 7))
    pattern = f"%{query}%"

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT title, url
            FROM pages
            WHERE
                title LIKE ?
                OR url LIKE ?
            ORDER BY
                CASE
                    WHEN title LIKE ? THEN 0
                    ELSE 1
                END,
                indexed_at DESC
            LIMIT ?
            """,
            (
                pattern,
                pattern,
                f"{query}%",
                limit,
            ),
        ).fetchall()

    suggestions = []
    seen = set()

    for row in rows:
        title = row["title"] or row["url"]
        url = row["url"]

        if not url or url in seen:
            continue

        seen.add(url)

        suggestions.append({
            "title": title,
            "url": url,
        })

    return suggestions


def get_related_tags(query, limit=7):
    """
    検索語に関連するタグをインデックス済みページから生成する。

    ・検索語に一致するタグは除外
    ・重複タグは統合
    ・タイトルに含まれる語句を優先
    ・最大7件まで返す
    ・データベースの内容は変更しない
    """

    query = str(query or "").strip()

    if not query:
        return []

    limit = max(1, min(int(limit), 7))

    query_tokens = set(tokenize(query))

    if not query_tokens:
        return []

    conditions = []
    parameters = []

    for token in query_tokens:
        pattern = f"%{token}%"

        conditions.append("""
            (
                title LIKE ?
                OR description LIKE ?
                OR content LIKE ?
            )
        """)

        parameters.extend([
            pattern,
            pattern,
            pattern,
        ])

    where_clause = " OR ".join(conditions)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT title, description, content
            FROM pages
            WHERE {where_clause}
            LIMIT 500
            """,
            parameters,
        ).fetchall()

    scores = Counter()
    appearances = defaultdict(set)

    for index, row in enumerate(rows):
        title = row["title"] or ""
        description = row["description"] or ""
        content = row["content"] or ""

        # タイトルは強く評価する
        sources = [
            (title, 5),
            (description, 3),
            (content[:3000], 1),
        ]

        page_candidates = set()

        for source, weight in sources:
            if not source:
                continue

            # 区切り文字で分割してフレーズも抽出
            phrases = SPLIT_PATTERN.split(source)

            for phrase in phrases:
                phrase = phrase.strip().lower()

                if not phrase:
                    continue

                if len(phrase) > 40:
                    continue

                for token in tokenize(phrase):
                    if len(token) < 2:
                        continue

                    # 元の検索語そのものは除外
                    if token in query_tokens:
                        continue

                    # 検索語を含むだけのタグも除外
                    if any(
                        query_token in token
                        or token in query_token
                        for query_token in query_tokens
                    ):
                        continue

                    # 長すぎるタグを除外
                    if len(token) > 30:
                        continue

                    page_candidates.add((token, weight))

        # 同一ページ内での重複加点を抑える
        for token, weight in page_candidates:
            scores[token] += weight
            appearances[token].add(index)

    ranked = sorted(
        scores.items(),
        key=lambda item: (
            len(appearances[item[0]]),
            item[1],
            item[0],
        ),
        reverse=True,
    )

    tags = []

    for tag, score in ranked:
        if len(tags) >= limit:
            break

        tags.append({
            "label": tag,
            "query": tag,
            "score": score,
        })

    return tags
