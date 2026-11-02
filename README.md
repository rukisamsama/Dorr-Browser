# Dorr Search

Dorr Search is a lightweight search application built with Python,
FastAPI, SQLite, and a web-based interface.

## Features

- Local indexed-page search
- Search suggestions
- Search history
- Bookmarks
- Theme settings
- Public website crawler
- SQLite database storage
- Desktop launcher support through PySide6

## Requirements

- Windows 10 / Windows 11
- Python 3.10 or later
- Internet connection for installing packages

## Installation

Open PowerShell in the DorrSearch directory.

Create a virtual environment:

    python -m venv .venv

Activate it:

    .venv\Scripts\activate

Install dependencies:

    python -m pip install --upgrade pip
    pip install -r requirements.txt

## Start

Run:

    python run.py

Open this address in your browser:

    http://127.0.0.1:8000

## Database

The database is stored at:

    data/dorr_search.db

The application creates missing tables automatically.
Existing page records are not deleted during initialization.

Back up this file before manually editing the database.

## Crawler

The crawler is limited to public HTTP/HTTPS websites.

It:
- Checks robots.txt
- Limits the number of indexed pages
- Stays on the starting hostname
- Does not automatically follow redirects
- Skips non-HTML responses
- Applies a delay between requests

Do not use the crawler to access private systems,
restricted content, or websites without permission.

## Desktop

The desktop interface is provided by app/desktop.py.

Install PySide6 through requirements.txt before using it.

## Project structure

    DorrSearch/
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