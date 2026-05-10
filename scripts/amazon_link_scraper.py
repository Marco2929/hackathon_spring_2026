import time
import re
import sqlite3
from playwright.sync_api import sync_playwright

CATEGORIES = {
    "monitore": "https://www.amazon.de/-/en/gp/bestsellers/computers/429874031/",
    "tablets": "https://www.amazon.de/gp/bestsellers/computers/427957031/",
    "kopfhoerer": "https://www.amazon.de/gp/bestsellers/ce-de/1197292/",
    "kameras": "https://www.amazon.de/gp/bestsellers/ce-de/3468301/"
}

DB_NAME = "amazon_links_db/amazon_products.db"

def link_exists(link: str) -> bool:
    """Prüft, ob der Link bereits in der Datenbank ist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM product_links WHERE link = ?', (link,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def save_link(link: str, tag: str = "open") -> bool:
    """Speichert den Link mit dem definierten Tag."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO product_links (link, tag) VALUES (?, ?)', (link, tag))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def scrape_and_store():
    """Führt das Scraping durch und speichert neue Links ohne Kategoriebezug."""
    new_links_count = 0
    already_known_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for category_name, url in CATEGORIES.items():
            print(f"--- Prüfe URL für: {category_name} ---")
            try:
                page.goto(url, wait_until="domcontentloaded")
                time.sleep(5) 
                
                hrefs = page.eval_on_selector_all('a.a-link-normal', 'elements => elements.map(el => el.href)')
                
                for href in hrefs:
                    if '/dp/' in href:
                        match = re.search(r"(/dp/[A-Z0-9]{10})", href)
                        if match:
                            clean_link = f"https://www.amazon.de{match.group(1)}"
                            
                            if not link_exists(clean_link):
                                if save_link(clean_link):
                                    print(f"  [NEU] {clean_link}")
                                    new_links_count += 1
                            else:
                                already_known_count += 1
                
                time.sleep(3)
                
            except Exception as e:
                print(f"Fehler beim Aufruf der URL {url}: {e}")

        browser.close()

    print("="*50)
    print("SCRAPING ABGESCHLOSSEN")
    print(f"Erfolgreich hinzugefügt: {new_links_count}")
    print(f"Übersprungen (bereits vorhanden): {already_known_count}")
    print("="*50)

if __name__ == "__main__":
    scrape_and_store()