from __future__ import annotations
from typing import Type, ClassVar

import json
import re
import sqlite3
import time
from typing import Type

from crewai.tools import BaseTool
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field


class AmazonScraperInput(BaseModel):
    pass


class AmazonBestsellerScraperTool(BaseTool):
    name: str = "amazon_bestseller_scraper"
    description: str = (
        "Scrapes Amazon bestseller pages for electronics (monitors, tablets, headphones, cameras), "
        "extracts clean product links, and saves new unique links to an existing SQLite database. "
        "Returns a JSON summary of the execution."
    )
    args_schema: Type[BaseModel] = AmazonScraperInput

    # Statische Definition der Kategorien
    CATEGORIES: ClassVar[dict[str, str]] = {
        "monitore": "https://www.amazon.de/-/en/gp/bestsellers/computers/429874031/",
        "tablets": "https://www.amazon.de/gp/bestsellers/computers/427957031/",
        "kopfhoerer": "https://www.amazon.de/gp/bestsellers/ce-de/1197292/",
        "kameras": "https://www.amazon.de/gp/bestsellers/ce-de/3468301/"
    }

    @staticmethod
    def _link_exists(db_path: str, link: str) -> bool:
        """Prüft, ob der Link bereits in der Datenbank ist."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM product_links WHERE link = ?', (link,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    @staticmethod
    def _save_link(db_path: str, link: str, tag: str = "open") -> bool:
        """Speichert den Link mit dem definierten Tag."""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO product_links (link, tag) VALUES (?, ?)', (link, tag))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Datenbankfehler: {e} - Ist die Tabelle initialisiert?")

    def _run(
        self) -> str:
        new_links_count = 0
        already_known_count = 0
        errors = []

        db_path = "/home/mm/dev/git/hackathon_spring_2026/amazon_links_db/amazon_products.db"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                for category_name, url in self.CATEGORIES.items():
                    try:
                        page.goto(url, wait_until="domcontentloaded")
                        time.sleep(5) 
                        
                        hrefs = page.eval_on_selector_all('a.a-link-normal', 'elements => elements.map(el => el.href)')
                        
                        for href in hrefs:
                            if '/dp/' in href:
                                match = re.search(r"(/dp/[A-Z0-9]{10})", href)
                                if match:
                                    clean_link = f"https://www.amazon.de{match.group(1)}"
                                    
                                    if not self._link_exists(db_path, clean_link):
                                        if self._save_link(db_path, clean_link):
                                            new_links_count += 1
                                    else:
                                        already_known_count += 1
                        
                        time.sleep(3)
                        
                    except Exception as e:
                        errors.append(f"Error scraping category '{category_name}': {str(e)}")

                browser.close()

            result = {
                "status": "success",
                "new_links_added": new_links_count,
                "links_skipped": already_known_count,
                "db_path": db_path,
                "errors": errors if errors else None
            }
            time.sleep(2)
            return json.dumps(result, ensure_ascii=False)

        except Exception as exc:
            return json.dumps(
                {
                    "status": "error", 
                    "message": f"Execution error: {exc}"
                }, 
                ensure_ascii=False
            )