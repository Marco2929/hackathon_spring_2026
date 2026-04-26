import sqlite3
import os

DB_NAME = "amazon_products.db"

def init_db():
    """Erstellt die Datenbank und die Tabelle für die Links."""
    if os.path.exists(DB_NAME):
        print(f"Hinweis: Die Datenbank '{DB_NAME}' existiert bereits.")
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabelle enthält nur id, den Link (einzigartig) und den Tag
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE,
            tag TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Tabelle 'product_links' ist bereit in '{DB_NAME}'.")

if __name__ == "__main__":
    init_db()