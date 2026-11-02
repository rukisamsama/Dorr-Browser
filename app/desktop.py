import os
import socket
import subprocess
import sys
import time
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import (
    QSettings,
    QUrl,
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QStandardPaths,
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QTabWidget,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QDialog,
    QLabel,
    QFrame,
    QComboBox,
    QCheckBox,
    QStackedWidget,
    QScrollArea,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


BASE_DIR = Path(__file__).resolve().parents[1]
DORR_SERVER = "http://127.0.0.1:8000"
HOME_URL = DORR_SERVER + "/"

FONT_FAMILY = (
    '"Yu Gothic UI", "Meiryo", "Noto Sans JP", '
    '"Segoe UI", sans-serif'
)

ENGINES = {
    "dorr": ("Dorr Search", None),
    "google": (
        "Google",
        "https://www.google.com/search?q={}",
    ),
    "bing": (
        "Bing",
        "https://www.bing.com/search?q={}",
    ),
    "duckduckgo": (
        "DuckDuckGo",
        "https://duckduckgo.com/?q={}",
    ),
    "brave": (
        "Brave Search",
        "https://search.brave.com/search?q={}",
    ),
    "ecosia": (
        "Ecosia",
        "https://www.ecosia.org/search?q={}",
    ),
    "startpage": (
        "Startpage",
        "https://www.startpage.com/sp/search?query={}",
    ),
    "yahoo": (
        "Yahoo",
        "https://search.yahoo.com/search?p={}",
    ),
}

COLORS = {
    "background": "#10121b",
    "surface": "#191c28",
    "surface2": "#222637",
    "border": "#303447",
    "accent": "#8b7cff",
    "accent_hover": "#a195ff",
    "text": "#f4f5fa",
    "muted": "#9298aa",
}


def server_is_ready():
    try:
        with socket.create_connection(
            ("127.0.0.1", 8000),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Welcome to Dorr")
        self.setFixedSize(460, 420)
        self.setModal(True)

        self.setStyleSheet(f"""
            QDialog {{
                background: {COLORS["background"]};
            }}

            QLabel {{
                color: {COLORS["text"]};
                font-family: {FONT_FAMILY};
            }}

            QPushButton {{
                background: {COLORS["accent"]};
                color: white;
                border: none;
                border-radius: 12px;
                padding: 13px 24px;
                font-weight: 700;
                font-size: 14px;
            }}

            QPushButton:hover {{
                background: {COLORS["accent_hover"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mascot = QLabel("🩵")
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mascot.setStyleSheet("font-size: 82px;")

        title = QLabel("Welcome to Dorr")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 28px; font-weight: 800;"
        )

        subtitle = QLabel(
            "Explore beyond the ordinary."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {COLORS['muted']}; font-size: 13px;"
        )

        button = QPushButton("Let's explore  →")
        button.clicked.connect(self.accept)

        layout.addWidget(mascot)
        layout.addSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(28)
        layout.addWidget(button)


def read_shared_settings():
    """Web版と共有するSQLite設定をAPI経由で読み込む。"""
    try:
        with urlopen(f"{DORR_SERVER}/api/settings", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("settings", {})
    except (URLError, HTTPError, TimeoutError, ValueError, OSError):
        return {}


def write_shared_settings(values):
    """設定をWeb版と同じSQLiteへ保存する。"""
    request = Request(
        f"{DORR_SERVER}/api/settings",
        data=json.dumps({"values": values}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class SettingsOverlay(QWidget):
    def __init__(self, parent, settings):
        super().__init__(parent)

        self.settings = settings
        self.shared_settings = read_shared_settings()
        self.panel_width = 490
        self.animation = None

        self.setObjectName("settingsOverlay")
        self.setStyleSheet(f"""
            QWidget#settingsOverlay {{
                background: rgba(0, 0, 0, 150);
            }}

            QFrame#settingsPanel {{
                background: #141722;
                border-left: 1px solid #34394d;
            }}

            QLabel {{
                color: {COLORS["text"]};
                font-family: {FONT_FAMILY};
            }}

            QLabel#muted {{
                color: {COLORS["muted"]};
            }}

            QLabel#pageTitle {{
                font-size: 23px;
                font-weight: 800;
            }}

            QPushButton {{
                color: {COLORS["text"]};
                background: {COLORS["surface2"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 10px;
                padding: 10px;
            }}

            QPushButton:hover {{
                background: #343951;
                border-color: {COLORS["accent"]};
            }}

            QPushButton#primaryButton {{
                background: {COLORS["accent"]};
                border: none;
                font-weight: 700;
            }}

            QPushButton#backButton {{
                background: transparent;
                border: none;
                color: #b5aaff;
                text-align: left;
            }}

            QPushButton#closeButton {{
                font-size: 20px;
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
            }}

            QLineEdit, QComboBox {{
                color: {COLORS["text"]};
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 9px;
                padding: 10px;
                min-height: 22px;
            }}

            QCheckBox {{
                color: {COLORS["text"]};
                spacing: 10px;
                padding: 7px;
            }}

            QScrollArea {{
                border: none;
                background: transparent;
            }}

            QListWidget {{
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 9px;
                color: {COLORS["text"]};
            }}
        """)

        self.hide()

        self.panel = QFrame(self)
        self.panel.setObjectName("settingsPanel")

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(15)

        header = QHBoxLayout()

        title = QLabel("Dorr Settings")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 800;"
        )

        close_button = QPushButton("×")
        close_button.setObjectName("closeButton")
        close_button.clicked.connect(self.close_panel)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_button)

        panel_layout.addLayout(header)

        self.stack = QStackedWidget()
        panel_layout.addWidget(self.stack, 1)

        self.stack.addWidget(self.create_home_page())
        self.create_detail_pages()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.isVisible():
            width = min(self.panel_width, self.width())
            self.panel.setGeometry(
                self.width() - width,
                0,
                width,
                self.height(),
            )

    def geometry_for_x(self, x):
        return self.panel.geometry().__class__(
            x,
            0,
            min(self.panel_width, self.width()),
            self.height(),
        )

    def open_panel(self):
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.stack.setCurrentIndex(0)

        width = min(self.panel_width, self.width())

        self.panel.setGeometry(
            self.width(),
            0,
            width,
            self.height(),
        )

        self.animation = QPropertyAnimation(
            self.panel,
            b"geometry",
            self,
        )
        self.animation.setDuration(320)
        self.animation.setStartValue(
            self.panel.geometry()
        )
        self.animation.setEndValue(
            self.geometry_for_x(self.width() - width)
        )
        self.animation.setEasingCurve(
            QEasingCurve.Type.OutBack
        )
        self.animation.start()

    def close_panel(self):
        self.animation = QPropertyAnimation(
            self.panel,
            b"geometry",
            self,
        )
        self.animation.setDuration(220)
        self.animation.setStartValue(
            self.panel.geometry()
        )
        self.animation.setEndValue(
            self.geometry_for_x(self.width())
        )
        self.animation.setEasingCurve(
            QEasingCurve.Type.InCubic
        )
        self.animation.finished.connect(self.hide)
        self.animation.start()

    def create_home_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        description = QLabel(
            "Customize your browsing experience."
        )
        description.setObjectName("muted")
        layout.addWidget(description)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(3, 8, 3, 8)
        grid.setSpacing(12)

        cards = [
            ("⚙", "General", "Homepage and search engine"),
            ("◈", "Appearance", "Theme and visual preferences"),
            ("◇", "Privacy", "Privacy preferences"),
            ("◉", "Dorr VPN", "Planned privacy service"),
            ("⌕", "Search", "Search preferences"),
            ("▣", "Browser", "Tabs and browsing"),
            ("⌘", "Advanced", "Local browser storage"),
            ("ⓘ", "About Dorr", "Version and information"),
        ]

        for index, (symbol, name, subtitle) in enumerate(cards):
            button = QPushButton(
                f"{symbol}\n{name}\n{subtitle}"
            )
            button.setMinimumHeight(112)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 13px;
                    background: #1b1f2d;
                    border: 1px solid #30364b;
                    border-radius: 13px;
                }
                QPushButton:hover {
                    background: #292d40;
                    border: 1px solid #8b7cff;
                }
            """)

            button.clicked.connect(
                lambda checked=False, i=index:
                    self.stack.setCurrentIndex(i + 1)
            )

            grid.addWidget(
                button,
                index // 2,
                index % 2,
            )

        scroll.setWidget(content)
        layout.addWidget(scroll)

        return page

    def add_detail_page(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(13)

        back = QPushButton("←  All settings")
        back.setObjectName("backButton")
        back.clicked.connect(
            lambda: self.stack.setCurrentIndex(0)
        )
        layout.addWidget(back)

        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        description = QLabel(subtitle)
        description.setObjectName("muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.stack.addWidget(page)

        return layout

    def create_detail_pages(self):
        # General
        layout = self.add_detail_page(
            "General",
            "Homepage and default browsing preferences.",
        )

        layout.addWidget(QLabel("Homepage URL"))

        self.homepage_input = QLineEdit()
        self.homepage_input.setPlaceholderText(HOME_URL)
        self.homepage_input.setText(
            self.shared_settings.get(
                "homepage", self.settings.value("homepage", "")
            )
        )
        layout.addWidget(self.homepage_input)

        layout.addWidget(QLabel("Default search engine"))

        self.engine_combo = QComboBox()
        self.engine_combo.addItem("DorrSearch（内部検索）", "dorr")
        self.engine_combo.setCurrentIndex(0)
        layout.addWidget(self.engine_combo)

        search_note = QLabel(
            "検索キーワードはDorrSearch内で検索します。"
            "外部検索サイトは自動で開きません。"
        )
        search_note.setObjectName("muted")
        search_note.setWordWrap(True)
        layout.addWidget(search_note)

        save = QPushButton("Save changes")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_general)
        layout.addWidget(save)
        layout.addStretch()

        # Appearance
        layout = self.add_detail_page(
            "Appearance",
            "Visual preferences for Dorr.",
        )

        layout.addWidget(QLabel("Theme"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("System", "system")
        current_theme = self.shared_settings.get("theme", "dark")
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(current_theme)))
        layout.addWidget(self.theme_combo)

        self.animations_checkbox = QCheckBox("Enable interface animations")
        self.animations_checkbox.setChecked(
            str(self.shared_settings.get("animations", "true")).lower() not in {"false", "0", "off"}
        )
        layout.addWidget(self.animations_checkbox)

        appearance_save = QPushButton("Save appearance")
        appearance_save.setObjectName("primaryButton")
        appearance_save.clicked.connect(self.save_appearance)
        layout.addWidget(appearance_save)
        accent = QLabel("Dorr Purple  ·  #8B7CFF")
        accent.setObjectName("muted")
        layout.addWidget(accent)
        layout.addStretch()

        # Privacy
        layout = self.add_detail_page(
            "Privacy",
            "Manage browser privacy preferences.",
        )

        self.tracker_checkbox = QCheckBox(
            "Enable tracker protection preference"
        )
        self.tracker_checkbox.setChecked(
            str(self.shared_settings.get("tracker_protection", "false")).lower()
            in {"true", "1", "yes", "on"}
        )
        layout.addWidget(self.tracker_checkbox)

        privacy_note = QLabel(
            "This setting stores your preference. "
            "It does not currently provide full content blocking."
        )
        privacy_note.setObjectName("muted")
        privacy_note.setWordWrap(True)
        layout.addWidget(privacy_note)

        save_privacy = QPushButton(
            "Save privacy preferences"
        )
        save_privacy.setObjectName("primaryButton")
        save_privacy.clicked.connect(self.save_privacy)
        layout.addWidget(save_privacy)
        layout.addStretch()

        # VPN
        layout = self.add_detail_page(
            "Dorr VPN",
            "A future privacy service from Dorr.",
        )

        status = QLabel("COMING SOON")
        status.setStyleSheet(
            "color:#a195ff;font-size:18px;font-weight:800;"
        )
        layout.addWidget(status)

        vpn_note = QLabel(
            "Dorr VPN is not available yet. "
            "This page is a preview only. "
            "No VPN connection is active."
        )
        vpn_note.setObjectName("muted")
        vpn_note.setWordWrap(True)
        layout.addWidget(vpn_note)
        layout.addStretch()

        # Search
        layout = self.add_detail_page(
            "Search",
            "Choose which search engine handles typed searches.",
        )

        search_note = QLabel(
            "Change your default search engine under General."
        )
        search_note.setObjectName("muted")
        search_note.setWordWrap(True)
        layout.addWidget(search_note)
        layout.addStretch()

        # Browser
        layout = self.add_detail_page(
            "Browser",
            "Basic tab and browsing preferences.",
        )

        browser_note = QLabel(
            "Ctrl+T: New tab\n"
            "Ctrl+W: Close tab\n"
            "Ctrl+Tab: Next tab\n"
            "Ctrl+Shift+Tab: Previous tab"
        )
        browser_note.setObjectName("muted")
        browser_note.setWordWrap(True)
        layout.addWidget(browser_note)
        layout.addStretch()

        # Advanced
        layout = self.add_detail_page(
            "Advanced",
            "Information about local browser storage.",
        )

        advanced_note = QLabel(
            "Dorr uses a local browser profile for cookies "
            "and cache. Clearing browser data is not enabled "
            "in this version."
        )
        advanced_note.setObjectName("muted")
        advanced_note.setWordWrap(True)
        layout.addWidget(advanced_note)
        layout.addStretch()

        # About
        layout = self.add_detail_page(
            "About Dorr",
            "Explore beyond the ordinary.",
        )

        about = QLabel(
            "Dorr Browser\n"
            "Version 1.0.0\n"
            "Made for discovery."
        )
        about.setWordWrap(True)
        layout.addWidget(about)
        layout.addStretch()

    def save_general(self):
        homepage = self.homepage_input.text().strip()

        if homepage:
            parsed = QUrl.fromUserInput(homepage)

            if (
                not parsed.isValid()
                or parsed.scheme() not in ("http", "https")
                or not parsed.host()
            ):
                QMessageBox.warning(
                    self,
                    "Invalid homepage",
                    "有効な http:// または https:// のURLを入力してください。",
                )
                return

            homepage = parsed.toString()

        try:
            write_shared_settings({
                "homepage": homepage or HOME_URL,
                "search_engine": self.engine_combo.currentData(),
            })
        except (URLError, HTTPError, TimeoutError, OSError, ValueError) as error:
            QMessageBox.warning(self, "Dorr", f"設定を保存できませんでした。\n{error}")
            return

        self.settings.setValue("homepage", homepage)
        self.settings.setValue("default_engine", self.engine_combo.currentData())
        self.settings.sync()
        self.shared_settings.update({"homepage": homepage or HOME_URL, "search_engine": "dorr"})
        QMessageBox.information(self, "Dorr", "設定を保存しました。")

    def save_appearance(self):
        values = {
            "theme": self.theme_combo.currentData(),
            "animations": self.animations_checkbox.isChecked(),
        }
        try:
            write_shared_settings(values)
        except (URLError, HTTPError, TimeoutError, OSError, ValueError) as error:
            QMessageBox.warning(self, "Dorr", f"設定を保存できませんでした。\n{error}")
            return
        self.shared_settings.update(values)
        QMessageBox.information(self, "Dorr", "外観設定を保存しました。")

    def save_privacy(self):
        try:
            write_shared_settings({"tracker_protection": self.tracker_checkbox.isChecked()})
        except (URLError, HTTPError, TimeoutError, OSError, ValueError) as error:
            QMessageBox.warning(self, "Dorr", f"設定を保存できませんでした。\n{error}")
            return
        self.settings.setValue("tracker_protection", self.tracker_checkbox.isChecked())
        self.settings.sync()
        QMessageBox.information(self, "Dorr", "設定を保存しました。")


class DorrWebPage(QWebEnginePage):
    def __init__(self, profile, browser_tab, parent=None):
        super().__init__(profile, parent)
        self.browser_tab = browser_tab

    def createWindow(self, window_type):
        new_tab = self.browser_tab.parent_window.add_tab()
        return new_tab.browser.page()


class BrowserTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()

        self.parent_window = parent_window
        self.browser = QWebEngineView()

        self.browser.setPage(
            DorrWebPage(
                parent_window.profile,
                self,
                self.browser,
            )
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)

        self.browser.urlChanged.connect(self.url_changed)
        self.browser.titleChanged.connect(self.title_changed)
        self.browser.loadFinished.connect(self.load_finished)

        self.browser.setUrl(QUrl(HOME_URL))

    def url_changed(self, url):
        if self.parent_window.current_tab() is self:
            self.parent_window.address_bar.setText(
                url.toString()
            )
            self.parent_window.update_navigation_state()

    def title_changed(self, title):
        index = self.parent_window.tabs.indexOf(self)

        if index >= 0:
            self.parent_window.tabs.setTabText(
                index,
                (title or "New Tab")[:24],
            )

    def load_finished(self, ok):
        if self.parent_window.current_tab() is self:
            self.parent_window.update_navigation_state()


class DorrBrowser(QMainWindow):
    def __init__(self, server_process=None):
        super().__init__()

        self.server_process = server_process
        self.settings = QSettings(
            "Dorr",
            "DorrBrowser",
        )

        self.setWindowTitle("Dorr Browser")
        self.resize(1320, 850)
        self.setMinimumSize(850, 560)

        self.profile = self._create_profile()

        root = QWidget()
        self.root_widget = root

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(10, 9, 10, 9)
        toolbar.setSpacing(7)

        self.back_button = self._tool_button("←", "Back")
        self.forward_button = self._tool_button("→", "Forward")
        self.reload_button = self._tool_button("↻", "Reload")
        self.home_button = self._tool_button("⌂", "Home")

        for button in (
            self.back_button,
            self.forward_button,
            self.reload_button,
            self.home_button,
        ):
            toolbar.addWidget(button)

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText(
            "Search Dorr or enter a website address…"
        )
        self.address_bar.setClearButtonEnabled(True)
        toolbar.addWidget(self.address_bar, 1)

        self.bookmark_button = self._tool_button("☆", "Bookmark")
        self.new_tab_button = self._tool_button("+", "New tab")
        self.settings_button = self._tool_button("⚙", "Settings")

        toolbar.addWidget(self.bookmark_button)
        toolbar.addWidget(self.new_tab_button)
        toolbar.addWidget(self.settings_button)

        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)

        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

        # 設定画面をショートカット登録より先に生成
        self.settings_overlay = SettingsOverlay(
            root,
            self.settings,
        )

        self.back_button.clicked.connect(
            lambda: self.current_tab()
            and self.current_tab().browser.back()
        )
        self.forward_button.clicked.connect(
            lambda: self.current_tab()
            and self.current_tab().browser.forward()
        )
        self.reload_button.clicked.connect(
            lambda: self.current_tab()
            and self.current_tab().browser.reload()
        )
        self.home_button.clicked.connect(self.go_home)
        self.new_tab_button.clicked.connect(self.add_tab)
        self.address_bar.returnPressed.connect(self.navigate)
        self.tabs.currentChanged.connect(self.update_address)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.bookmark_button.clicked.connect(self.bookmark_current)
        self.settings_button.clicked.connect(
            self.settings_overlay.open_panel
        )

        self._create_shortcuts()
        self._apply_style()
        self.add_tab()

    def _create_profile(self):
        profile_path = (
            Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.AppDataLocation
                )
            )
            / "Dorr"
            / "webprofile"
        )

        profile_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        profile = QWebEngineProfile(
            "DorrProfile",
            self,
        )

        storage = profile_path / "storage"
        cache = profile_path / "cache"

        storage.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)

        profile.setPersistentStoragePath(str(storage))
        profile.setCachePath(str(cache))

        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy
            .AllowPersistentCookies
        )

        return profile

    def _tool_button(self, text, tooltip):
        button = QPushButton(text)
        button.setToolTip(tooltip)
        button.setFixedSize(38, 36)
        return button

    def _create_shortcuts(self):
        shortcuts = [
            ("Ctrl+L", self.focus_address),
            ("Ctrl+K", self.focus_address),
            ("Ctrl+E", self.focus_address),
            ("Ctrl+T", self.add_tab),
            ("Ctrl+W", self.close_current_tab),
            ("Ctrl+R", self.reload_current),
            ("Ctrl+Shift+T", self.add_tab),
            ("Ctrl+Tab", self.next_tab),
            ("Ctrl+Shift+Tab", self.previous_tab),
            ("Alt+Left", self.go_back),
            ("Alt+Right", self.go_forward),
            ("Ctrl+,", self.settings_overlay.open_panel),
        ]

        for sequence, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(callback)
            self.addAction(action)

    def current_tab(self):
        return self.tabs.currentWidget()

    def add_tab(self):
        tab = BrowserTab(self)

        index = self.tabs.addTab(tab, "New Tab")
        self.tabs.setCurrentIndex(index)

        self.address_bar.clear()
        return tab

    def close_tab(self, index):
        if index < 0:
            return

        if self.tabs.count() <= 1:
            tab = self.current_tab()

            if tab:
                tab.browser.setUrl(QUrl(HOME_URL))

            return

        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()

    def close_current_tab(self):
        self.close_tab(self.tabs.currentIndex())

    def next_tab(self):
        if self.tabs.count():
            index = (
                self.tabs.currentIndex() + 1
            ) % self.tabs.count()

            self.tabs.setCurrentIndex(index)

    def previous_tab(self):
        if self.tabs.count():
            index = (
                self.tabs.currentIndex() - 1
            ) % self.tabs.count()

            self.tabs.setCurrentIndex(index)

    def focus_address(self):
        self.address_bar.setFocus()
        self.address_bar.selectAll()

    def reload_current(self):
        tab = self.current_tab()

        if tab:
            tab.browser.reload()

    def go_back(self):
        tab = self.current_tab()

        if tab:
            tab.browser.back()

    def go_forward(self):
        tab = self.current_tab()

        if tab:
            tab.browser.forward()

    def navigate(self):
        text = self.address_bar.text().strip()

        if not text:
            return

        tab = self.current_tab()

        if not tab:
            return

        # URLとして入力された場合
        candidate = QUrl.fromUserInput(text)

        looks_like_url = (
            " " not in text
            and "." in text
            and candidate.isValid()
            and candidate.scheme() in ("http", "https")
            and bool(candidate.host())
        )

        if looks_like_url:
            tab.browser.setUrl(candidate)
            return

        # 検索ワードは常にDorrSearch内で処理する。
        # 外部検索エンジンのWebサイトへは移動しない。
        url = f"{DORR_SERVER}/?q={quote(text)}"
        tab.browser.setUrl(QUrl(url))

    def go_home(self):
        custom = self.settings.value(
            "homepage",
            "",
        ).strip()

        if custom:
            parsed = QUrl.fromUserInput(custom)

            if (
                parsed.isValid()
                and parsed.scheme() in ("http", "https")
                and parsed.host()
            ):
                target = parsed.toString()
            else:
                target = HOME_URL
        else:
            target = HOME_URL

        tab = self.current_tab()

        if tab:
            tab.browser.setUrl(QUrl(target))

    def update_address(self, index):
        tab = self.current_tab()

        if tab:
            self.address_bar.setText(
                tab.browser.url().toString()
            )
            self.update_navigation_state()

    def update_navigation_state(self):
        tab = self.current_tab()

        if not tab:
            return

        history = tab.browser.history()

        self.back_button.setEnabled(
            history.canGoBack()
        )
        self.forward_button.setEnabled(
            history.canGoForward()
        )

    def bookmark_current(self):
        tab = self.current_tab()

        if not tab:
            return

        url = tab.browser.url().toString()

        if not url.startswith(("http://", "https://")):
            return

        title = tab.browser.title() or url

        bookmarks = self.settings.value(
            "bookmarks",
            [],
        )

        if not isinstance(bookmarks, list):
            bookmarks = []

        for item in bookmarks:
            if isinstance(item, dict) and item.get("url") == url:
                QMessageBox.information(
                    self,
                    "Dorr",
                    "このページはすでにブックマークされています。",
                )
                return

        bookmarks.append({
            "title": title,
            "url": url,
        })

        self.settings.setValue("bookmarks", bookmarks)
        self.settings.sync()

        QMessageBox.information(
            self,
            "Dorr",
            "ブックマークに追加しました。",
        )

    def show_bookmarks(self):
        bookmarks = self.settings.value(
            "bookmarks",
            [],
        )

        if not isinstance(bookmarks, list):
            bookmarks = []

        dialog = QDialog(self)
        dialog.setWindowTitle("Dorr Bookmarks")
        dialog.resize(520, 420)

        layout = QVBoxLayout(dialog)

        listing = QListWidget()

        for item in bookmarks:
            if not isinstance(item, dict):
                continue

            title = item.get("title", "Untitled")
            url = item.get("url", "")

            row = QListWidgetItem(title)
            row.setData(
                Qt.ItemDataRole.UserRole,
                url,
            )
            listing.addItem(row)

        layout.addWidget(listing)

        def open_selected():
            item = listing.currentItem()

            if not item:
                return

            url = item.data(
                Qt.ItemDataRole.UserRole
            )

            tab = self.current_tab()

            if tab and url:
                tab.browser.setUrl(QUrl(url))

            dialog.accept()

        listing.itemDoubleClicked.connect(
            lambda item: open_selected()
        )

        open_button = QPushButton("Open")
        open_button.clicked.connect(open_selected)

        layout.addWidget(open_button)
        dialog.exec()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {COLORS["background"]};
            }}

            QWidget {{
                color: {COLORS["text"]};
                font-family: {FONT_FAMILY};
            }}

            QLineEdit {{
                background: {COLORS["surface"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 9px;
                padding: 9px 13px;
                font-size: 13px;
                selection-background-color: #8175ee;
            }}

            QLineEdit:focus {{
                border: 1px solid {COLORS["accent"]};
            }}

            QPushButton {{
                background: {COLORS["surface2"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 8px;
                font-size: 17px;
            }}

            QPushButton:hover {{
                background: #343951;
            }}

            QPushButton:disabled {{
                color: #555;
            }}

            QTabWidget::pane {{
                border: 0;
            }}

            QTabBar::tab {{
                background: {COLORS["surface"]};
                padding: 11px 18px;
                min-width: 95px;
                color: {COLORS["muted"]};
            }}

            QTabBar::tab:selected {{
                background: #292d40;
                color: white;
                border-bottom: 2px solid {COLORS["accent"]};
            }}
        """)

    def closeEvent(self, event):
        if (
            self.server_process
            and self.server_process.poll() is None
        ):
            self.server_process.terminate()

            try:
                self.server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

        super().closeEvent(event)


def start_local_server():
    if server_is_ready():
        return None

    run_file = BASE_DIR / "run.py"

    if not run_file.exists():
        raise RuntimeError(
            f"run.py が見つかりません: {run_file}"
        )

    flags = (
        subprocess.CREATE_NO_WINDOW
        if os.name == "nt"
        else 0
    )

    process = subprocess.Popen(
        [sys.executable, str(run_file)],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )

    for _ in range(60):
        if server_is_ready():
            return process

        if process.poll() is not None:
            break

        time.sleep(0.25)

    if process.poll() is None:
        process.terminate()

    raise RuntimeError(
        "Dorrのローカルサーバーを起動できませんでした。\n"
        "requirements.txt のライブラリと run.py を確認してください。"
    )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Dorr")
    app.setOrganizationName("Dorr")

    try:
        server_process = start_local_server()

    except RuntimeError as error:
        QMessageBox.critical(
            None,
            "Dorr startup error",
            str(error),
        )
        sys.exit(1)

    window = DorrBrowser(server_process)

    if not window.settings.value(
        "welcome_completed",
        False,
        type=bool,
    ):
        dialog = WelcomeDialog(window)
        dialog.exec()

        window.settings.setValue(
            "welcome_completed",
            True,
        )
        window.settings.sync()

    window.show()
    sys.exit(app.exec())