from playwright.sync_api import sync_playwright
import json
import os
import urllib.request
import re
import time

def extract_asin(url):
    match = re.search(r"/dp/([A-Z0-9]{10})", url)
    return match.group(1) if match else "unknown_product"

def get_high_res_image_url(url):
    if not url: return None
    return re.sub(r"\._.*_\.", ".", url)

def clean_visible_text(text):
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized if normalized else None

def extract_ai_summary_text(page):
    try:
        page.wait_for_selector("div[data-testid='overall-summary']", timeout=15000)
    except Exception:
        pass

    primary_selectors = [
        "div[data-testid='overall-summary'] [data-testid='aspect-summary']",
        "span[data-testid='aspect-summary']",
    ]

    for selector in primary_selectors:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue

        summary_text = clean_visible_text(locator.first.text_content())
        if summary_text and len(summary_text) >= 10:
            return summary_text

    fallback_selectors = [
        "div[data-testid='overall-summary']",
        "p[data-hook='cr-summarization-excerpt']",
        ".cr-summarization-content p",
        "[data-hook='cr-insights-widget-summary']",
        "#cr-insights-widget-aspects",
        "#cr-product-insights-widget",
        "#cr-insights-widget",
    ]

    for selector in fallback_selectors:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue

        summary_text = clean_visible_text(locator.first.text_content())
        if summary_text and len(summary_text) >= 10:
            summary_text = summary_text.replace("KI-generiert aus dem Text von Kundenrezensionen", "").strip()
            summary_text = clean_visible_text(summary_text)
            if summary_text:
                return summary_text

    return None

def save_assets(data, asin):
    base_dir = f"output/{asin}"
    img_dir = f"{base_dir}/images"
    os.makedirs(img_dir, exist_ok=True)
    
    image_mapping = []
    for idx, img_url in enumerate(data.get("raw_image_urls", [])):
        ext = ".jpg" if ".jpg" in img_url.lower() else ".png"
        file_name = f"product_image_{idx + 1:02d}{ext}"
        img_path = os.path.join(img_dir, file_name)
        
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            urllib.request.urlretrieve(img_url, img_path)
            
            image_mapping.append({
                "id": f"img_{idx+1}",
                "file_name": file_name,
                "local_path": f"images/{file_name}"
            })
        except Exception as e:
            print(f"[!] Fehler bei Bild-Download: {e}")

    data["images"] = image_mapping
    if "raw_image_urls" in data:
        del data["raw_image_urls"]
    
    json_path = f"{base_dir}/data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"\n[*] Dump erfolgreich gespeichert in: {base_dir}")

def scrape_amazon_dump(url):
    asin = extract_asin(url)
    result = {
        "title": None,
        "asin": asin,
        "product_description": None,
        "ai_summary": None,
        "reviews_dump": [],
        "raw_image_urls": [],
        "error": None
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080}, locale="de-DE")
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            print("[*] Lade Produktseite...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            if page.locator("input#sp-cc-accept").count() > 0:
                page.locator("input#sp-cc-accept").click()

            # Titel
            title_el = page.locator("span#productTitle").first
            if title_el.count() > 0:
                result["title"] = title_el.text_content().strip()

            # Produktbeschreibung/Bullets
            print("[*] Extrahiere Produktbeschreibung...")
            bullet_texts = [
                clean_visible_text(t)
                for t in page.locator("#feature-bullets li span.a-list-item").all_inner_texts()
            ]
            bullet_texts = [t for t in bullet_texts if t]
            if bullet_texts:
                result["product_description"] = " ".join(dict.fromkeys(bullet_texts))
            else:
                description_selectors = [
                    "#productDescription",
                    "#bookDescription_feature_div",
                    "#aplus_feature_div",
                ]
                for selector in description_selectors:
                    desc_el = page.locator(selector).first
                    if desc_el.count() == 0:
                        continue
                    desc_text = clean_visible_text(desc_el.inner_text())
                    if desc_text:
                        result["product_description"] = desc_text
                        break

            # Bilder (High-Res)
            print("[*] Extrahiere Bilder...")
            image_elements = page.locator("#altImages img, #landingImage").all()
            raw_urls = [get_high_res_image_url(img.get_attribute("src")) for img in image_elements if img.get_attribute("src")]
            result["raw_image_urls"] = list(set([u for u in raw_urls if u]))

            # Scrollen
            print("[*] Scrolle zu den Texten...")
            for i in range(1, 6):
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i/5});")
                time.sleep(1)

            # KI-Zusammenfassung (falls vorhanden)
            print("[*] Suche nach KI-Zusammenfassung...")
            try:
                page.wait_for_selector("span[data-testid='aspect-summary']", timeout=10000)
            except Exception:
                pass
            result["ai_summary"] = extract_ai_summary_text(page)

            # "Weiterlesen" anklicken
            print("[*] Klappe Rezensionstexte auf...")
            expanders = page.locator("[data-hook='review-body-expander']").all()
            for btn in expanders:
                try:
                    if btn.is_visible():
                        btn.click()
                        time.sleep(0.3)
                except: pass

            # ROBUST DUMP: Holt einfach den inneren Text des gesamten Blocks
            print("[*] Erstelle Text-Dump der Rezensionen...")
            review_elements = page.locator("[data-hook='review']").all()
            for rev in review_elements:
                # inner_text() extrahiert den sichtbaren Text inkl. Zeilenumbrüchen
                raw_dump = rev.inner_text().strip()
                clean_dump = raw_dump.replace("Weiterlesen", "").replace("Weniger anzeigen", "").strip()
                if clean_dump:
                    result["reviews_dump"].append(clean_dump)

        except Exception as e:
            result["error"] = str(e)
        finally:
            browser.close()
    return result

if __name__ == "__main__":
    target_url = "https://www.amazon.de/Xiaomi-Smart-Triple-Tuner-Virtual/dp/B0F4548TCQ/ref=zg_bs_g_1197292_d_sccl_1/260-1982185-8125653?th=1"
    asin = extract_asin(target_url)
    data = scrape_amazon_dump(target_url)
    
    if not data["error"]:
        save_assets(data, asin)
    else:
        print(f"Fehler: {data['error']}")