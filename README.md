# DorrBrowser

<p align="center">
  <strong>Version 1.0.0</strong>
</p>

DorrBrowser is a lightweight search application built with Python, FastAPI, SQLite, and a web-based interface.

---

## Features

- Local indexed-page search
- Real-time search suggestions
- Search history
- Bookmarks
- Theme settings
- Public website crawler
- SQLite database storage
- Desktop application support through PySide6

## Requirements

- Windows 10 / Windows 11
- Python 3.10 or later
- Internet connection for installing dependencies

## Installation

Open PowerShell in the project directory.

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

Install the dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Usage

Start DorrBrowser:

```powershell
python run.py
```

Open the following address in your browser:

```text
http://127.0.0.1:8000
```

## Database

The SQLite database is stored at:

```text
data/dorr_search.db
```

The application automatically creates missing database tables during initialization.

Existing page records are preserved during initialization.

It is recommended to back up the database before making manual changes.

## Web Crawler

The built-in crawler is designed for publicly accessible HTTP/HTTPS websites.

Crawler features:

- Checks `robots.txt`
- Limits the number of indexed pages
- Stays on the starting hostname
- Does not automatically follow redirects
- Skips non-HTML responses
- Applies delays between requests

Please use the crawler responsibly. Do not access private systems, restricted content, or websites without permission.

## Desktop Application

The desktop interface is provided by:

```text
app/desktop.py
```

It uses PySide6 and can be launched after installing the required dependencies.

## Project Structure

```text
DorrBrowser/
├── app/
│   ├── __init__.py
│   ├── database.py
│   ├── desktop.py
│   ├── main.py
│   └── search.py
├── crawler/
│   ├── __init__.py
│   ├── engine.py
│   └── parser.py
├── data/
│   └── dorr_search.db
├── static/
│   ├── app.js
│   └── style.css
├── templates/
│   └── index.html
├── config.py
├── requirements.txt
└── run.py
```

## Live Demo

[Open DorrBrowser](https://1c078ecf4dfe99.lhr.life/)

*The demo may be unavailable when the hosting computer is offline.*

---

## Developer

Created independently by a Japanese junior high school student.

DorrBrowser is a personal development project built with passion and curiosity. I am continuously working to improve its features and user experience.

**Thank you for visiting DorrBrowser!**

© 2026 DorrBrowser Project
