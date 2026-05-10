import argparse
import json
import logging
import re
from collections import deque
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config" / "seeds.json"
DEFAULT_OUTPUT = BASE_DIR / "metadata" / "links_collected.csv"
LOG_FILE = BASE_DIR / "logs" / "link_collector.log"


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    return webdriver.Chrome(options=options)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    cleaned = parsed._replace(fragment="")
    return cleaned.geturl()


def same_host(url_a: str, url_b: str) -> bool:
    return urlparse(url_a).netloc == urlparse(url_b).netloc


def tag_domain(text: str, keyword_map: Dict[str, List[str]]) -> str:
    lower_text = text.lower()
    for domain, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword.lower() in lower_text:
                return domain
    return "unclassified"


def looks_like_download(url: str) -> bool:
    return bool(re.search(r"\.(pdf|doc|docx|zip)$", url.lower()))


def collect_links(
    driver: webdriver.Chrome,
    seeds: List[str],
    keyword_map: Dict[str, List[str]],
    max_pages: int,
    timeout: int,
) -> pd.DataFrame:
    visited: Set[str] = set()
    queue = deque(normalize_url(seed) for seed in seeds)
    records = []

    while queue and len(visited) < max_pages:
        current_url = queue.popleft()
        if current_url in visited:
            continue

        logging.info("Visiting: %s", current_url)
        visited.add(current_url)

        try:
            driver.get(current_url)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            page_title = driver.title.strip() or "untitled"
            anchors = driver.find_elements(By.TAG_NAME, "a")

            for anchor in anchors:
                href = anchor.get_attribute("href")
                text = (anchor.text or "").strip()

                if not href or not href.startswith(("http://", "https://")):
                    continue

                absolute = normalize_url(urljoin(current_url, href))
                domain_guess = tag_domain(
                    f"{absolute} {text} {page_title}",
                    keyword_map,
                )

                records.append(
                    {
                        "source_page": current_url,
                        "source_title": page_title,
                        "url": absolute,
                        "anchor_text": text,
                        "domain": domain_guess,
                        "is_download": looks_like_download(absolute),
                    }
                )

                if same_host(current_url, absolute) and absolute not in visited:
                    queue.append(absolute)

        except Exception as exc:
            logging.exception("Failed to collect links from %s: %s", current_url, exc)

    df = pd.DataFrame(records)
    if df.empty:
        return df

    df = df.drop_duplicates(subset=["url"]).sort_values(by=["domain", "url"])
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect legal links for domain scraping.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    setup_logging()

    with args.config.open("r", encoding="utf-8") as f:
        config = json.load(f)

    seeds = config.get("seeds", [])
    keywords = config.get("domain_keywords", {})

    if not seeds:
        raise ValueError("No seeds found in config file.")

    driver = build_driver(headless=args.headless)
    try:
        df = collect_links(
            driver=driver,
            seeds=seeds,
            keyword_map=keywords,
            max_pages=args.max_pages,
            timeout=args.timeout,
        )
    finally:
        driver.quit()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False, encoding="utf-8")

    logging.info("Saved %s links to %s", len(df), args.output)


if __name__ == "__main__":
    main()
