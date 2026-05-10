import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LINKS_FILE = BASE_DIR / "metadata" / "links.csv"
RAW_HTML_DIR = BASE_DIR / "raw_html"
RAW_PDF_DIR = BASE_DIR / "raw_pdfs"
SCRAPE_LOG = BASE_DIR / "logs" / "scraper.log"
SCRAPE_META = BASE_DIR / "metadata" / "scrape_results.jsonl"


def setup_logging() -> None:
    SCRAPE_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(SCRAPE_LOG, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "untitled"


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(options=options)


def fetch_pdf(pdf_url: str, output_path: Path, timeout: int = 30) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    try:
        resp = requests.get(pdf_url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(resp.content)
        return True
    except Exception as exc:
        logging.warning("Failed to download PDF %s (%s)", pdf_url, exc)
        return False


def save_html(domain: str, title_slug: str, html: str) -> Path:
    output_dir = RAW_HTML_DIR / slugify(domain)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{title_slug}.html"
    output_file.write_text(html, encoding="utf-8", errors="ignore")
    return output_file


def discover_pdf_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    pdf_links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if ".pdf" in href.lower():
            if href.startswith(("http://", "https://")):
                pdf_links.append(href)
            elif href.startswith("/"):
                from urllib.parse import urljoin

                pdf_links.append(urljoin(page_url, href))
    return sorted(set(pdf_links))


def scrape_one(
    driver: webdriver.Chrome,
    row: pd.Series,
    wait_seconds: int,
    max_pdf_links: int,
    retries: int,
) -> dict:
    domain = row.get("domain", "unclassified")
    title = row.get("title", "untitled")
    url = row.get("url", "")
    expected_type = str(row.get("expected_type", "auto")).lower()

    title_slug = slugify(title)
    result = {
        "domain": domain,
        "title": title,
        "url": url,
        "status": "failed",
        "html_path": None,
        "pdf_paths": [],
        "error": None,
    }

    for attempt in range(1, retries + 1):
        try:
            logging.info("Scraping [%s/%s]: %s", attempt, retries, url)
            driver.get(url)
            WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            current_url = driver.current_url
            html = driver.page_source

            if expected_type != "pdf":
                html_path = save_html(domain, title_slug, html)
                result["html_path"] = str(html_path)

            pdf_urls = discover_pdf_links(html, current_url)
            if expected_type == "pdf" and current_url.lower().endswith(".pdf"):
                pdf_urls = [current_url] + pdf_urls

            for idx, pdf_url in enumerate(pdf_urls[:max_pdf_links], start=1):
                pdf_name = f"{title_slug}_{idx}.pdf" if len(pdf_urls) > 1 else f"{title_slug}.pdf"
                pdf_path = RAW_PDF_DIR / slugify(domain) / pdf_name
                if fetch_pdf(pdf_url, pdf_path):
                    result["pdf_paths"].append(str(pdf_path))

            result["status"] = "success"
            return result
        except Exception as exc:
            result["error"] = str(exc)
            logging.warning("Attempt failed for %s (%s)", url, exc)
            time.sleep(1)

    return result


def append_result(result: dict) -> None:
    SCRAPE_META.parent.mkdir(parents=True, exist_ok=True)
    with SCRAPE_META.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk scrape legal pages and PDFs.")
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS_FILE)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait", type=int, default=15)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-pdfs", type=int, default=2)
    parser.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Optional domain filter: cybersecurity or property_rights",
    )
    args = parser.parse_args()

    setup_logging()
    df = pd.read_csv(args.links)

    if args.domain:
        df = df[df["domain"].str.lower() == args.domain.lower()]

    if df.empty:
        logging.warning("No rows to scrape. Check links CSV and domain filter.")
        return

    driver = build_driver(headless=args.headless)
    try:
        for _, row in df.iterrows():
            result = scrape_one(
                driver=driver,
                row=row,
                wait_seconds=args.wait,
                max_pdf_links=args.max_pdfs,
                retries=args.retries,
            )
            append_result(result)
            logging.info("Result: %s -> %s", row.get("title", "untitled"), result["status"])
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
