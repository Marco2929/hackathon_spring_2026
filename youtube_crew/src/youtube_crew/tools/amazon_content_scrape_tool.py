from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from playwright.sync_api import Page, sync_playwright
from pydantic import BaseModel, Field


class AmazonContentScrapeInput(BaseModel):
	url: str = Field(..., description="Amazon product URL (must include /dp/<ASIN>).")


class AmazonContentScrapeTool(BaseTool):
	name: str = "amazon_content_scrape"
	description: str = (
		"Scrape one Amazon product page and extract title, product description, AI summary, "
		"reviews dump, and image URLs. Optionally downloads images and saves a data.json dump."
	)
	args_schema: Type[BaseModel] = AmazonContentScrapeInput
	OUTPUT_ROOT: str = "output/product_data"
	HEADLESS: bool = True
	LOCALE: str = "de-DE"
	SAVE_IMAGES: bool = True

	@staticmethod
	def _extract_asin(url: str) -> str:
		match = re.search(r"/dp/([A-Z0-9]{10})", url)
		return match.group(1) if match else "unknown_product"

	@staticmethod
	def _get_high_res_image_url(url: str | None) -> str | None:
		if not url:
			return None
		return re.sub(r"\._.*_\.", ".", url)

	@staticmethod
	def _clean_visible_text(text: str | None) -> str | None:
		if not text:
			return None
		normalized = re.sub(r"\s+", " ", text).strip()
		return normalized if normalized else None

	@classmethod
	def _extract_ai_summary_text(cls, page: Page) -> str | None:
		try:
			page.wait_for_selector(
				"span[data-testid='aspect-summary'], div[data-testid='overall-summary'], p[data-hook='cr-summarization-excerpt']",
				timeout=12000,
			)
		except Exception:
			pass

		summary_text = page.evaluate(
			"""() => {
				const candidates = [
					"span[data-testid='aspect-summary']",
					"div[data-testid='overall-summary'] [data-testid='aspect-summary']",
					"p[data-hook='cr-summarization-excerpt']",
					".cr-summarization-content p",
					"[data-hook='cr-insights-widget-summary']",
					"div[data-testid='overall-summary']",
					"#cr-insights-widget-aspects",
					"#cr-product-insights-widget",
					"#cr-insights-widget",
				];

				for (const selector of candidates) {
					const node = document.querySelector(selector);
					if (!node) {
						continue;
					}

					const raw = (node.textContent || node.innerText || "")
						.replace(/KI-generiert aus dem Text von Kundenrezensionen/gi, " ")
						.replace(/\s+/g, " ")
						.trim();

					if (raw.length >= 10) {
						return raw;
					}
				}

				return null;
			}"""
		)
		return cls._clean_visible_text(summary_text)

	@classmethod
	def _download_images(cls, image_urls: list[str], image_dir: Path) -> list[dict[str, str]]:
		image_dir.mkdir(parents=True, exist_ok=True)
		opener = urllib.request.build_opener()
		opener.addheaders = [("User-Agent", "Mozilla/5.0")]
		urllib.request.install_opener(opener)

		image_mapping: list[dict[str, str]] = []
		for idx, img_url in enumerate(image_urls):
			ext = ".jpg"
			file_name = f"product_image_{idx + 1:02d}{ext}"
			img_path = image_dir / file_name

			try:
				urllib.request.urlretrieve(img_url, str(img_path))
				image_mapping.append(
					{
						"id": f"img_{idx + 1}",
						"file_name": file_name,
						"local_path": f"images/{file_name}",
					}
				)
			except Exception:
				continue

		return image_mapping

	def _run(
		self,
		url: str,
	) -> str:
		asin = self._extract_asin(url)
		result: dict[str, object] = {
			"title": None,
			"asin": asin,
			"product_description": None,
			"ai_summary": None,
			"reviews_dump": [],
			"raw_image_urls": [],
			"error": None,
		}

		output_dir = Path(self.OUTPUT_ROOT).expanduser()
		image_dir = output_dir / "images"

		try:
			with sync_playwright() as p:
				browser = p.chromium.launch(
					headless=self.HEADLESS,
					args=["--disable-blink-features=AutomationControlled"],
				)
				context = browser.new_context(viewport={"width": 1920, "height": 1080}, locale=self.LOCALE)
				page = context.new_page()
				page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

				page.goto(url, wait_until="domcontentloaded", timeout=60000)

				if page.locator("input#sp-cc-accept").count() > 0:
					page.locator("input#sp-cc-accept").first.click()

				title_el = page.locator("span#productTitle").first
				if title_el.count() > 0:
					result["title"] = self._clean_visible_text(title_el.text_content())

				bullet_texts = [
					self._clean_visible_text(t)
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
						desc_text = self._clean_visible_text(desc_el.inner_text())
						if desc_text:
							result["product_description"] = desc_text
							break

				image_elements = page.locator("#altImages img, #landingImage").all()
				raw_urls = [
					self._get_high_res_image_url(img.get_attribute("src"))
					for img in image_elements
					if img.get_attribute("src")
				]
				deduped_urls = list(dict.fromkeys([u for u in raw_urls if u]))
				result["raw_image_urls"] = deduped_urls

				for i in range(1, 6):
					page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i / 5});")
					time.sleep(1)

				result["ai_summary"] = self._extract_ai_summary_text(page)

				expanders = page.locator("[data-hook='review-body-expander']").all()
				for btn in expanders:
					try:
						if btn.is_visible():
							btn.click()
							time.sleep(0.3)
					except Exception:
						continue

				review_elements = page.locator("[data-hook='review']").all()
				reviews_dump: list[str] = []
				for rev in review_elements:
					raw_dump = rev.inner_text().strip()
					clean_dump = raw_dump.replace("Weiterlesen", "").replace("Weniger anzeigen", "").strip()
					if clean_dump:
						reviews_dump.append(clean_dump)
				result["reviews_dump"] = reviews_dump

				browser.close()

			output_dir.mkdir(parents=True, exist_ok=True)
			if self.SAVE_IMAGES:
				result["images"] = self._download_images(deduped_urls, image_dir)
			else:
				result["images"] = []

			result.pop("raw_image_urls", None)
			data_path = output_dir / "data.json"
			data_path.write_text(json.dumps(result, indent=4, ensure_ascii=False), encoding="utf-8")

			return json.dumps(
				{
					"status": "success",
					"asin": asin,
					"output_dir": str(output_dir),
					"data_path": str(data_path),
					"title": result.get("title"),
					"ai_summary_found": bool(result.get("ai_summary")),
					"review_count": len(reviews_dump),
					"image_count": len(result.get("images", [])),
				},
				ensure_ascii=False,
			)
		except Exception as exc:
			return json.dumps(
				{
					"status": "error",
					"asin": asin,
					"message": f"Scraping error: {exc}",
				},
				ensure_ascii=False,
			)
