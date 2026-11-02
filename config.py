from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "dorr_search.db"

APP_NAME = "Dorr Search"
APP_VERSION = "1.0.0"

MAX_RESULTS = 20
MIN_QUERY_LENGTH = 1

CRAWLER_USER_AGENT = "DorrSearchBot/1.0"
CRAWLER_TIMEOUT = 15

CRAWLER_MAX_CONTENT_LENGTH = 100_000
CRAWLER_MAX_PAGES = 10
CRAWLER_DELAY = 1.5

DATA_DIR.mkdir(parents=True, exist_ok=True)