
"use strict";

const $ = (selector) => document.querySelector(selector);

const API = {
    search: "/api/search",
    suggestions: "/api/suggestions",
    history: "/api/history",
    bookmarks: "/api/bookmarks",
    settings: "/api/settings",
    stats: "/api/stats"
};

const state = {
    settings: {
        theme: "dark",
        search_engine: "dorr",
        safe_search: true,
        animations: true
    },
    suggestionItems: [],
    selectedSuggestion: -1,
    suggestionTimer: null,
    panelTimer: null
};

const el = {
    searchForm: $("#search-form"),
    searchInput: $("#search-input"),
    searchEngine: $("#search-engine"),
    suggestions: $("#suggestions"),
    resultsSection: $("#results-section"),
    resultsTitle: $("#results-title"),
    resultsCount: $("#results-count"),
    resultsList: $("#results-list"),
    relatedSection: $("#related-tags-section"),
    relatedTags: $("#related-tags"),
    panel: $("#panel-section"),
    panelTitle: $("#panel-title"),
    panelContent: $("#panel-content"),
    panelClose: $("#panel-close"),
    historyButton: $("#history-button"),
    bookmarksButton: $("#bookmarks-button"),
    settingsButton: $("#settings-button"),
    shortcutsButton: $("#shortcuts-button"),
    pageCount: $("#page-count")
};



async function api(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(
            data.detail ||
            data.message ||
            `通信エラー (${response.status})`
        );
    }

    return data;
}

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[char]);
}

function asBoolean(value, fallback = true) {
    if (typeof value === "boolean") return value;

    if (["true", "on", "1", "yes"].includes(String(value).toLowerCase())) {
        return true;
    }

    if (["false", "off", "0", "no"].includes(String(value).toLowerCase())) {
        return false;
    }

    return fallback;
}

function applyTheme(theme) {
    if (theme === "system") {
        const light = window.matchMedia(
            "(prefers-color-scheme: light)"
        ).matches;

        document.documentElement.dataset.theme =
            light ? "light" : "dark";
    } else {
        document.documentElement.dataset.theme = theme || "dark";
    }
}

function applyAnimations(enabled) {
    document.documentElement.dataset.animations =
        enabled ? "on" : "off";
}

function showMessage(message) {
    let node = $("#dorr-toast");

    if (!node) {
        node = document.createElement("div");
        node.id = "dorr-toast";
        node.className = "dorr-toast";
        document.body.appendChild(node);
    }

    node.textContent = message;
    node.classList.add("show");

    clearTimeout(node.hideTimer);

    node.hideTimer = setTimeout(() => {
        node.classList.remove("show");
    }, 2600);
}

/* --------------------------------
   検索候補
-------------------------------- */

function closeSuggestions() {
    if (!el.suggestions) return;

    el.suggestions.classList.add("hidden");
    el.suggestions.innerHTML = "";

    state.suggestionItems = [];
    state.selectedSuggestion = -1;
}

function normalizeSuggestion(item) {
    if (typeof item === "string") {
        return {
            title: item,
            query: item
        };
    }

    if (!item || typeof item !== "object") {
        return null;
    }

    const title = String(
        item.title ||
        item.query ||
        item.url ||
        ""
    ).trim();

    if (!title) return null;

    return {
        ...item,
        title,
        query: String(item.query || title)
    };
}

function mergeSuggestions(remoteItems, query) {
    const normalizedQuery = String(query || "").trim().toLocaleLowerCase();
    const items = Array.isArray(remoteItems)
        ? remoteItems.map(normalizeSuggestion).filter(Boolean)
        : [];
    const merged = [];
    const seen = new Set();

    for (const item of items) {
        const label = String(item.title || item.query || "").trim();
        const key = label.toLocaleLowerCase();
        if (!label || seen.has(key)) continue;
        // サーバー側の候補を優先し、入力語に一致する候補だけを表示する。
        if (normalizedQuery && !label.toLocaleLowerCase().includes(normalizedQuery)) continue;
        seen.add(key);
        merged.push({ ...item, title: label, query: item.query || label });
        if (merged.length >= 7) break;
    }
    return merged;
}

function renderSuggestions(items) {
    if (!el.suggestions) return;

    state.suggestionItems = Array.isArray(items)
        ? items.slice(0, 7)
        : [];

    state.selectedSuggestion = -1;

    if (!state.suggestionItems.length) {
        closeSuggestions();
        return;
    }

    el.suggestions.innerHTML = state.suggestionItems.map(
        (item, index) => {
            const label =
                item.title ||
                item.query ||
                item.url ||
                "";

            return `
                <button
                    type="button"
                    class="suggestion-item"
                    role="option"
                    aria-selected="false"
                    data-index="${index}"
                >
                    <span class="suggestion-symbol">⌕</span>
                    <span class="suggestion-label">
                        ${escapeHTML(label)}
                    </span>
                    <span class="suggestion-enter">検索</span>
                </button>
            `;
        }
    ).join("");

    el.suggestions.classList.remove("hidden");

    el.suggestions
        .querySelectorAll(".suggestion-item")
        .forEach(button => {
            button.addEventListener("click", () => {
                const item =
                    state.suggestionItems[
                        Number(button.dataset.index)
                    ];

                if (!item) return;

                const query =
                    item.query ||
                    item.title ||
                    item.url ||
                    "";

                el.searchInput.value = query;

                closeSuggestions();
                performSearch(query);
            });
        });
}

async function fetchSuggestions(query) {
    const trimmedQuery = query.trim();

    if (!trimmedQuery) {
        closeSuggestions();
        return;
    }

    let remoteItems = [];

    try {
        const data = await api(
            `${API.suggestions}?q=${encodeURIComponent(trimmedQuery)}&language=${encodeURIComponent(state.settings.language || "ja")}`
        );

        remoteItems =
            data.suggestions ||
            data.results ||
            [];
    } catch (error) {
        console.warn(
            "検索候補APIを利用できません:",
            error
        );
    }

    // 入力が変わっていたら古い候補を表示しない
    if (
        el.searchInput.value.trim() !== trimmedQuery
    ) {
        return;
    }

    const merged = mergeSuggestions(
        remoteItems,
        trimmedQuery
    );

    renderSuggestions(merged);
}

function selectSuggestion(direction) {
    const items =
        el.suggestions?.querySelectorAll(
            ".suggestion-item"
        );

    if (!items?.length) return;

    state.selectedSuggestion += direction;

    if (state.selectedSuggestion < 0) {
        state.selectedSuggestion = items.length - 1;
    }

    if (state.selectedSuggestion >= items.length) {
        state.selectedSuggestion = 0;
    }

    items.forEach((item, index) => {
        const selected =
            index === state.selectedSuggestion;

        item.classList.toggle("selected", selected);

        item.setAttribute(
            "aria-selected",
            String(selected)
        );
    });
}

/* --------------------------------
   検索結果
-------------------------------- */

function renderRelatedTags(tags) {
    if (!el.relatedSection || !el.relatedTags) return;

    if (!Array.isArray(tags) || !tags.length) {
        el.relatedSection.classList.add("hidden");
        el.relatedTags.innerHTML = "";
        return;
    }

    el.relatedTags.innerHTML = tags.slice(0, 7).map(tag => {
        const label =
            typeof tag === "string"
                ? tag
                : tag.label;

        const query =
            typeof tag === "string"
                ? tag
                : (tag.query || tag.label);

        return `
            <button
                type="button"
                class="related-tag"
                data-query="${escapeHTML(query)}"
            >
                <span>#</span>${escapeHTML(label)}
            </button>
        `;
    }).join("");

    el.relatedSection.classList.remove("hidden");

    el.relatedTags
        .querySelectorAll(".related-tag")
        .forEach(button => {
            button.addEventListener("click", () => {
                const query = button.dataset.query;

                el.searchInput.value = query;
                performSearch(query);
            });
        });
}

function getDisplayURL(url) {
    try {
        const parsed = new URL(url);

        return parsed.href;
    } catch {
        return String(url || "");
    }
}

function renderResults(results) {
    if (!Array.isArray(results) || !results.length) {
        el.resultsList.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">⌕</div>
                <h3>検索結果が見つかりませんでした</h3>
                <p>
                    キーワードを変えて、
                    もう一度検索してみてください。
                </p>
            </div>
        `;

        return;
    }

    el.resultsList.innerHTML = results.map(
        (result, index) => {
            const url = result.url || "#";
            const displayURL = getDisplayURL(url);
            const title = result.title || url;

            const description =
                result.description ||
                "説明はありません。";

            let hostname = url;

            try {
                hostname = new URL(url).hostname;
            } catch {
                // URL形式でない場合は元の値を使用
            }

            return `
                <article
                    class="result-card"
                    style="--index:${index}"
                >
                    <div class="result-site">
                        <span class="result-site-icon">
                            ${escapeHTML(
                                hostname.slice(0, 1).toUpperCase()
                            )}
                        </span>

                        <span>
                            ${escapeHTML(hostname)}
                        </span>
                    </div>

                    <div
                        class="result-url"
                        title="${escapeHTML(displayURL)}"
                    >
                        ${escapeHTML(displayURL)}
                    </div>

                    <a
                        class="result-title"
                        href="${escapeHTML(url)}"
                    >
                        ${escapeHTML(title)}
                    </a>

                    <p class="result-description">
                        ${escapeHTML(description)}
                    </p>

                    <div class="result-bottom">
                        <span class="result-score">
                            関連度
                            ${escapeHTML(result.score ?? "-")}
                        </span>

                        <button
                            type="button"
                            class="bookmark-add"
                            data-title="${escapeHTML(title)}"
                            data-url="${escapeHTML(url)}"
                        >
                            ☆ 保存
                        </button>
                    </div>
                </article>
            `;
        }
    ).join("");

    el.resultsList
        .querySelectorAll(".bookmark-add")
        .forEach(button => {
            button.addEventListener("click", () => {
                addBookmark(
                    button.dataset.title,
                    button.dataset.url
                );
            });
        });
}

async function performSearch(rawQuery) {
    const query = String(rawQuery || "").trim();

    if (!query) {
        el.searchInput.focus();
        return;
    }

    closeSuggestions();

    el.resultsSection.classList.remove("hidden");

    el.resultsTitle.textContent =
        `「${query}」の検索結果`;

    el.resultsCount.textContent = "検索中...";

    el.resultsList.innerHTML = `
        <div class="loading-state">
            <span class="loading-spinner"></span>
            <p>検索しています...</p>
        </div>
    `;

    el.relatedSection.classList.add("hidden");
    el.relatedTags.innerHTML = "";

    // 検索は常にDorrSearch内で実行する。
    // Google等の外部検索ページを新しいウィンドウで開かない。
    const engine = "dorr";
    if (el.searchEngine) {
        el.searchEngine.value = "dorr";
    }

    try {
        const data = await api(API.search, {
            method: "POST",
            body: JSON.stringify({ query })
        });

        const results = data.results || [];

        el.resultsCount.textContent =
            `${data.count ?? results.length} 件`;

        renderResults(results);

        renderRelatedTags(
            data.related_tags || []
        );
    } catch (error) {
        el.resultsCount.textContent = "エラー";

        el.resultsList.innerHTML = `
            <div class="empty-state error-state">
                <h3>検索に失敗しました</h3>
                <p>${escapeHTML(error.message)}</p>
            </div>
        `;
    }
}

/* --------------------------------
   共通パネル
-------------------------------- */

function openPanel(title, html) {
    clearTimeout(state.panelTimer);

    el.panelTitle.textContent = title;
    el.panelContent.innerHTML = html;

    el.panel.classList.remove("hidden");

    requestAnimationFrame(() => {
        el.panel.classList.add("is-open");
    });

    document.body.classList.add("panel-visible");
}

function closePanel() {
    if (el.panel.classList.contains("hidden")) return;

    el.panel.classList.remove("is-open");
    document.body.classList.remove("panel-visible");

    state.panelTimer = setTimeout(() => {
        el.panel.classList.add("hidden");
        el.panelContent.innerHTML = "";
    }, 420);
}

/* --------------------------------
   履歴
-------------------------------- */

async function openHistory() {
    try {
        const data = await api(API.history);

        const items =
            data.history ||
            data.items ||
            [];

        const html = items.length ? `
            <div class="panel-list">
                ${items.map(item => {
                    const query =
                        typeof item === "string"
                            ? item
                            : item.query || "";

                    return `
                        <button
                            class="history-entry"
                            type="button"
                            data-query="${escapeHTML(query)}"
                        >
                            <span class="entry-icon">◷</span>
                            <span>${escapeHTML(query)}</span>
                            <span class="entry-arrow">›</span>
                        </button>
                    `;
                }).join("")}
            </div>

            <button
                class="danger-action"
                id="clear-history"
            >
                履歴をすべて削除
            </button>
        ` : `
            <div class="panel-empty">
                <span>◷</span>
                <h3>履歴はまだありません</h3>
                <p>
                    検索すると、ここに履歴が表示されます。
                </p>
            </div>
        `;

        openPanel("検索履歴", html);

        el.panelContent
            .querySelectorAll(".history-entry")
            .forEach(button => {
                button.addEventListener("click", () => {
                    const query = button.dataset.query;

                    closePanel();

                    el.searchInput.value = query;
                    performSearch(query);
                });
            });

        $("#clear-history")?.addEventListener(
            "click",
            clearHistory
        );
    } catch (error) {
        openPanel(
            "検索履歴",
            `<p class="panel-error">${escapeHTML(error.message)}</p>`
        );
    }
}

async function clearHistory() {
    if (!confirm("検索履歴をすべて削除しますか？")) {
        return;
    }

    try {
        await api(API.history, {
            method: "DELETE"
        });

        showMessage("履歴を削除しました。");
        openHistory();
    } catch (error) {
        showMessage(error.message);
    }
}

/* --------------------------------
   ブックマーク
-------------------------------- */

async function addBookmark(title, url) {
    try {
        await api(API.bookmarks, {
            method: "POST",
            body: JSON.stringify({ title, url })
        });

        showMessage("ブックマークに保存しました。");
    } catch (error) {
        showMessage(error.message);
    }
}

async function openBookmarks() {
    try {
        const data = await api(API.bookmarks);

        const items =
            data.bookmarks ||
            data.items ||
            [];

        const html = items.length ? `
            <div class="panel-list">
                ${items.map(item => `
                    <div class="bookmark-entry">
                        <a
                            class="bookmark-entry-main"
                            href="${escapeHTML(item.url)}"
                        >
                            <span class="entry-icon">☆</span>

                            <span class="bookmark-entry-text">
                                <strong>
                                    ${escapeHTML(item.title || item.url)}
                                </strong>

                                <small>
                                    ${escapeHTML(item.url)}
                                </small>
                            </span>
                        </a>

                        <button
                            type="button"
                            class="bookmark-delete"
                            data-id="${escapeHTML(item.id)}"
                            aria-label="ブックマークを削除"
                        >×</button>
                    </div>
                `).join("")}
            </div>
        ` : `
            <div class="panel-empty">
                <span>☆</span>
                <h3>保存したページはありません</h3>
                <p>
                    検索結果からページを保存できます。
                </p>
            </div>
        `;

        openPanel("ブックマーク", html);

        el.panelContent
            .querySelectorAll(".bookmark-delete")
            .forEach(button => {
                button.addEventListener("click", async () => {
                    try {
                        await api(
                            `${API.bookmarks}/${encodeURIComponent(button.dataset.id)}`,
                            { method: "DELETE" }
                        );

                        showMessage("削除しました。");
                        openBookmarks();
                    } catch (error) {
                        showMessage(error.message);
                    }
                });
            });
    } catch (error) {
        openPanel(
            "ブックマーク",
            `<p class="panel-error">${escapeHTML(error.message)}</p>`
        );
    }
}

/* --------------------------------
   設定画面
-------------------------------- */

function openSettings() {
    const s = state.settings;

    openPanel("設定", `
        <div class="settings-layout">

            <aside class="settings-sidebar">
                <button class="settings-nav active" data-category="general">
                    <span>◈</span> 全般
                </button>

                <button class="settings-nav" data-category="appearance">
                    <span>◐</span> デザイン
                </button>

                <button class="settings-nav" data-category="search">
                    <span>⌕</span> 検索
                </button>

                <button class="settings-nav" data-category="privacy">
                    <span>◇</span> プライバシー
                </button>

                <button class="settings-nav" data-category="about">
                    <span>ⓘ</span> Dorrについて
                </button>
            </aside>

            <div class="settings-main">

                <div class="settings-category" data-page="general">
                    <div class="settings-page-heading">
                        <span class="settings-overline">DORR PREFERENCES</span>
                        <h3>全般</h3>
                        <p>Dorr Searchの基本設定を管理します。</p>
                    </div>

                    <div class="settings-card">
                        <div class="settings-card-heading">
                            <strong>検索エンジン</strong>
                            <small>
                                通常使用する検索先を選択します。
                            </small>
                        </div>

                        <select id="setting-engine" class="settings-select">
                            <option value="dorr">Dorr Search</option>
                            <option value="google">Google</option>
                            <option value="bing">Bing</option>
                            <option value="duckduckgo">DuckDuckGo</option>
                        </select>
                    </div>
                </div>

                <div class="settings-category hidden" data-page="appearance">
                    <div class="settings-page-heading">
                        <span class="settings-overline">PERSONALIZATION</span>
                        <h3>デザイン</h3>
                        <p>
                            画面のテーマや動作をカスタマイズします。
                        </p>
                    </div>

                    <div class="settings-card">
                        <div class="settings-card-heading">
                            <strong>カラーテーマ</strong>
                            <small>
                                Dorr Searchの表示テーマを選択します。
                            </small>
                        </div>

                        <div class="theme-options">
                            <label class="theme-option">
                                <input type="radio" name="setting-theme" value="dark">
                                <span class="theme-preview theme-preview-dark"></span>
                                <strong>ダーク</strong>
                            </label>

                            <label class="theme-option">
                                <input type="radio" name="setting-theme" value="light">
                                <span class="theme-preview theme-preview-light"></span>
                                <strong>ライト</strong>
                            </label>

                            <label class="theme-option">
                                <input type="radio" name="setting-theme" value="system">
                                <span class="theme-preview theme-preview-system"></span>
                                <strong>システム</strong>
                            </label>
                        </div>
                    </div>

                    <div class="settings-card settings-toggle-row">
                        <div class="settings-card-heading">
                            <strong>アニメーション</strong>
                            <small>
                                パネルやボタンの動きを有効にします。
                            </small>
                        </div>

                        <label class="switch">
                            <input type="checkbox" id="setting-animations">
                            <span class="switch-track"></span>
                        </label>
                    </div>
                </div>

                <div class="settings-category hidden" data-page="search">
                    <div class="settings-page-heading">
                        <span class="settings-overline">SEARCH PREFERENCES</span>
                        <h3>検索</h3>
                        <p>検索時の動作を設定します。</p>
                    </div>

                    <div class="settings-card settings-toggle-row">
                        <div class="settings-card-heading">
                            <strong>セーフサーチ</strong>
                            <small>
                                対応する検索機能で安全性を重視します。
                            </small>
                        </div>

                        <label class="switch">
                            <input type="checkbox" id="setting-safe-search">
                            <span class="switch-track"></span>
                        </label>
                    </div>

                    <div class="settings-note">
                        セーフサーチの適用範囲は、
                        選択した検索エンジンや機能によって異なります。
                    </div>
                </div>

                <div class="settings-category hidden" data-page="privacy">
                    <div class="settings-page-heading">
                        <span class="settings-overline">PRIVACY</span>
                        <h3>プライバシー</h3>
                        <p>このアプリ内のデータについて。</p>
                    </div>

                    <div class="settings-card">
                        <strong>検索履歴</strong>
                        <p>
                            検索履歴はDorr Searchの
                            ローカルデータベースに保存されます。
                        </p>

                        <button
                            type="button"
                            class="settings-secondary-button"
                            id="privacy-history"
                        >
                            検索履歴を開く
                        </button>
                    </div>

                    <div class="settings-card">
                        <strong>ブックマーク</strong>
                        <p>
                            保存したページはDorr Searchの
                            ローカルデータベースに保存されます。
                        </p>

                        <button
                            type="button"
                            class="settings-secondary-button"
                            id="privacy-bookmarks"
                        >
                            ブックマークを開く
                        </button>
                    </div>
                </div>

                <div class="settings-category hidden" data-page="about">
                    <div class="settings-page-heading">
                        <span class="settings-overline">ABOUT DORR</span>
                        <h3>Dorrについて</h3>
                        <p>Dorr Searchのアプリ情報です。</p>
                    </div>

                    <div class="settings-card about-card">
                        <div class="about-logo">D</div>
                        <h4>Dorr Search</h4>
                        <p>必要な情報を、シンプルに。</p>

                        <div class="about-version">
                            バージョン <strong>{{APP_VERSION}}</strong>
                        </div>
                    </div>
                </div>

                <div class="settings-footer">
                    <span id="settings-status">
                        変更内容を保存できます。
                    </span>

                    <button id="save-settings" type="button">
                        変更を保存
                    </button>
                </div>
            </div>
        </div>
    `);

    $("#setting-engine").value =
        s.search_engine || "dorr";

    const themeInput = el.panelContent.querySelector(
        `input[name="setting-theme"][value="${s.theme || "dark"}"]`
    );

    if (themeInput) {
        themeInput.checked = true;
    }

    $("#setting-animations").checked =
        asBoolean(s.animations, true);

    $("#setting-safe-search").checked =
        asBoolean(s.safe_search, true);

    bindSettingsNavigation();

    $("#save-settings").addEventListener(
        "click",
        saveSettings
    );

    $("#privacy-history").addEventListener(
        "click",
        openHistory
    );

    $("#privacy-bookmarks").addEventListener(
        "click",
        openBookmarks
    );
}

function bindSettingsNavigation() {
    const navButtons =
        el.panelContent.querySelectorAll(".settings-nav");

    const pages =
        el.panelContent.querySelectorAll(".settings-category");

    navButtons.forEach(button => {
        button.addEventListener("click", () => {
            const category = button.dataset.category;

            navButtons.forEach(item => {
                item.classList.remove("active");
            });

            button.classList.add("active");

            pages.forEach(page => {
                const selected =
                    page.dataset.page === category;

                page.classList.toggle(
                    "hidden",
                    !selected
                );

                if (selected) {
                    page.classList.remove("page-enter");

                    void page.offsetWidth;

                    page.classList.add("page-enter");
                }
            });
        });
    });
}

async function saveSettings() {
    const theme =
        el.panelContent.querySelector(
            'input[name="setting-theme"]:checked'
        )?.value || "dark";

    const values = {
        theme,
        search_engine: $("#setting-engine").value,
        animations: $("#setting-animations").checked,
        safe_search: $("#setting-safe-search").checked
    };

    const button = $("#save-settings");
    const status = $("#settings-status");

    button.disabled = true;
    button.textContent = "保存中...";

    status.textContent = "設定を保存しています...";

    try {
        await api(API.settings, {
            method: "PUT",
            body: JSON.stringify({ values })
        });

        state.settings = {
            ...state.settings,
            ...values
        };

        applyTheme(values.theme);
        applyAnimations(values.animations);

        el.searchEngine.value =
            values.search_engine;

        status.textContent = "設定を保存しました。";
        status.classList.add("saved");

        showMessage("設定を保存しました。");
    } catch (error) {
        status.textContent = error.message;
        status.classList.remove("saved");
    } finally {
        button.disabled = false;
        button.textContent = "変更を保存";
    }
}

/* --------------------------------
   ショートカット
-------------------------------- */

function openShortcuts() {
    openPanel("ショートカット", `
        <div class="shortcut-list">
            <div class="shortcut-row">
                <span>検索欄に移動</span>
                <kbd>/</kbd>
            </div>

            <div class="shortcut-row">
                <span>新しいタブ（EXE版）</span>
                <kbd>Ctrl</kbd><kbd>T</kbd>
            </div>

            <div class="shortcut-row">
                <span>現在のタブを閉じる（EXE版）</span>
                <kbd>Ctrl</kbd><kbd>W</kbd>
            </div>

            <div class="shortcut-row">
                <span>ページを再読み込み（EXE版）</span>
                <kbd>Ctrl</kbd><kbd>R</kbd>
            </div>

            <div class="shortcut-row">
                <span>次のタブ（EXE版）</span>
                <kbd>Ctrl</kbd><kbd>Tab</kbd>
            </div>

            <div class="shortcut-row">
                <span>前のタブ（EXE版）</span>
                <kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>Tab</kbd>
            </div>

            <div class="shortcut-row">
                <span>前のページ（EXE版）</span>
                <kbd>Alt</kbd><kbd>←</kbd>
            </div>

            <div class="shortcut-row">
                <span>次のページ（EXE版）</span>
                <kbd>Alt</kbd><kbd>→</kbd>
            </div>

            <div class="shortcut-row">
                <span>検索欄に移動</span>
                <kbd>Ctrl</kbd><kbd>K</kbd>
            </div>

            <div class="shortcut-row">
                <span>検索履歴</span>
                <kbd>Ctrl</kbd><kbd>H</kbd>
            </div>

            <div class="shortcut-row">
                <span>ブックマーク</span>
                <kbd>Ctrl</kbd><kbd>D</kbd>
            </div>

            <div class="shortcut-row">
                <span>設定</span>
                <kbd>Ctrl</kbd><kbd>,</kbd>
            </div>

            <div class="shortcut-row">
                <span>閉じる</span>
                <kbd>Esc</kbd>
            </div>

            <div class="shortcut-row">
                <span>候補を選択</span>
                <kbd>↑</kbd><kbd>↓</kbd>
            </div>

            <div class="shortcut-row">
                <span>検索</span>
                <kbd>Enter</kbd>
            </div>
        </div>
    `);
}

/* --------------------------------
   設定・統計読み込み
-------------------------------- */

async function loadSettings() {
    try {
        const data = await api(API.settings);

        const settings =
            data.settings || data;

        state.settings = {
            ...state.settings,
            ...settings
        };

        applyTheme(state.settings.theme);

        applyAnimations(
            asBoolean(state.settings.animations, true)
        );

        if (el.searchEngine) {
            el.searchEngine.value =
                state.settings.search_engine || "dorr";
        }
    } catch (error) {
        console.warn(
            "設定を読み込めませんでした:",
            error
        );

        applyTheme("dark");
    }
}

async function loadStats() {
    try {
        const data = await api(API.stats);

        const count =
            data.indexed_pages ??
            data.page_count;

        if (count !== undefined && el.pageCount) {
            el.pageCount.textContent =
                `${Number(count).toLocaleString()} ページを登録`;
        }
    } catch (error) {
        console.warn(
            "統計情報を取得できませんでした:",
            error
        );
    }
}

/* --------------------------------
   イベント
-------------------------------- */

function bindEvents() {
    document.querySelectorAll(".standard-shortcut-icon img").forEach(image => {
        image.addEventListener("error", () => {
            image.style.display = "none";
            const fallback = image.nextElementSibling;
            if (fallback) fallback.style.display = "block";
        }, { once: true });
    });

    document.querySelectorAll(".standard-shortcut").forEach(link => {
        link.addEventListener("click", event => {
            // Keep navigation in the current tab, including the desktop wrapper.
            event.preventDefault();
            const destination = link.getAttribute("href");
            if (destination) {
                window.location.assign(destination);
            }
        });
    });

    el.searchForm.addEventListener("submit", event => {
        event.preventDefault();

        performSearch(
            el.searchInput.value
        );
    });

    el.searchInput.addEventListener("input", () => {
        clearTimeout(state.suggestionTimer);

        const query =
            el.searchInput.value.trim();

        if (!query) {
            closeSuggestions();
            return;
        }

        state.suggestionTimer = setTimeout(() => {
            fetchSuggestions(query);
        }, 180);
    });

    el.searchInput.addEventListener("keydown", event => {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            selectSuggestion(1);

        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            selectSuggestion(-1);

        } else if (
            event.key === "Enter" &&
            state.selectedSuggestion >= 0
        ) {
            event.preventDefault();

            const item =
                state.suggestionItems[
                    state.selectedSuggestion
                ];

            if (!item) return;

            const query =
                item.query ||
                item.title ||
                item.url ||
                "";

            el.searchInput.value = query;

            closeSuggestions();
            performSearch(query);

        } else if (event.key === "Escape") {
            closeSuggestions();
        }
    });

    el.historyButton.addEventListener(
        "click",
        openHistory
    );

    el.bookmarksButton.addEventListener(
        "click",
        openBookmarks
    );

    el.settingsButton.addEventListener(
        "click",
        openSettings
    );

    el.shortcutsButton.addEventListener(
        "click",
        openShortcuts
    );

    el.panelClose.addEventListener(
        "click",
        closePanel
    );

    el.panel.addEventListener("click", event => {
        if (event.target === el.panel) {
            closePanel();
        }
    });

    el.searchEngine.addEventListener("change", event => {
        state.settings.search_engine =
            event.target.value;
    });

    document.addEventListener("click", event => {
        if (!event.target.closest("#search-form")) {
            closeSuggestions();
        }
    });

    document.addEventListener("keydown", event => {
        const target = event.target;

        const typing =
            target instanceof HTMLElement &&
            (
                target.isContentEditable ||
                ["INPUT", "TEXTAREA", "SELECT"].includes(
                    target.tagName
                )
            );

        if (event.key === "Escape") {
            closeSuggestions();

            if (!el.panel.classList.contains("hidden")) {
                closePanel();
            }

            return;
        }

        if (
            event.ctrlKey &&
            event.key.toLowerCase() === "k"
        ) {
            event.preventDefault();

            el.searchInput.focus();
            el.searchInput.select();

            return;
        }

        if (
            event.ctrlKey &&
            event.key.toLowerCase() === "h"
        ) {
            event.preventDefault();
            openHistory();
            return;
        }

        if (
            event.ctrlKey &&
            event.key.toLowerCase() === "d"
        ) {
            event.preventDefault();
            openBookmarks();
            return;
        }

        if (
            event.ctrlKey &&
            event.key === ","
        ) {
            event.preventDefault();
            openSettings();
            return;
        }

        if (
            !typing &&
            event.key === "/" &&
            !event.ctrlKey &&
            !event.altKey
        ) {
            event.preventDefault();
            el.searchInput.focus();
        }
    });

    window.matchMedia(
        "(prefers-color-scheme: light)"
    ).addEventListener?.("change", () => {
        if (state.settings.theme === "system") {
            applyTheme("system");
        }
    });
}

/* --------------------------------
   起動
-------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadSettings();
    loadStats();
});
