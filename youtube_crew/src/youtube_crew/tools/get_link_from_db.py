import sqlite3
import json
from typing import Type
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

class GetLinkInput(BaseModel):
    pass

class GetNextOpenLinkTool(BaseTool):
    name: str = "get_and_complete_amazon_link"
    description: str = (
        "Checks the database for an open Amazon product link. "
        "Returns the link URL and IMMEDIATELY marks it as 'completed' in the database. "
        "Returns an error message if the database is empty or no open links exist."
    )
    args_schema: Type[BaseModel] = GetLinkInput

    def cache_function(self, *args, **kwargs) -> bool:
        return False
    
    def _run(self) -> str:
        try:
            conn = sqlite3.connect("/home/mm/dev/git/hackathon_spring_2026/amazon_links_db/amazon_products.db")
            cursor = conn.cursor()
            

            cursor.execute("SELECT id, link FROM product_links WHERE tag = 'open' LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                link_id, link_url = row
                

                cursor.execute("UPDATE product_links SET tag = 'completed' WHERE id = ?", (link_id,))
                conn.commit()
                conn.close()
                
                return json.dumps({"status": "success", "link": link_url, "id": link_id})
            else:
                conn.close()
                return json.dumps({"status": "empty", "message": "No open links found in the database."})
                
        except sqlite3.OperationalError as e:
             return json.dumps({"status": "error", "message": f"Database error: {e}"})