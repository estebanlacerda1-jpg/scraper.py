import asyncio
import csv
import os
import random
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

TEST_CATEGORIES = [
    ("PS3", "Anime", "https://portalgames.com.ar/product-category/juegos-ps3/anime/"),
    ("PS3", "Aventura", "https://portalgames.com.ar/product-category/juegos-ps3/aventura/"),
]

# HEADLESS=0 -> navegador "real" (usar con: xvfb-run python portalps3.py)
HEADLESS = os.getenv("HEADLESS", "1") != "0"
USE_REAL_CHROME = os.getenv("REAL_CHROME", "0") == "1"  # requiere: playwright install chrome
WAIT_BETWEEN_CATEGORIES = (12, 25)  # segundos, aleatorio
CHALLENGE_MAX_WAIT = 40             # segundos esperando que pase "Just a moment"
RETRIES_PER_CATEGORY = 2

LOG_FILE = "portalgames_test_2categorias.log.txt"
CSV_FILE = "portalgames_test_2categorias.csv"
PRODUCTS_CSV = "portalgames_productos.csv"
STATE_FILE = "portalgames_state.json"

CF_MARKERS = ["Just a moment", "cf-mitigated", "challenge-platform", "Enable JavaScript and cookies to continue"]


def log(message):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_price(text):
