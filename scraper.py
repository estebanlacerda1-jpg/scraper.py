# =========================================================
# ABC GAMING - SCRAPER FINAL
# Versión: merge completo + corrección de monedas
# =========================================================

import re
import asyncio
import requests
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# =========================================================
# CONFIG GLOBAL
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    )
}

PAGINAS = 2
USD_TO_UYU = 40
ARS_TO_UYU = 0.035

print("Script recuperado desde PDF correctamente.")
