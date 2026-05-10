import argparse
import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://indiankanoon.org"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
DEFAULT_OUTPUT = Path("metadata/links_cybercrime_indiankanoon.csv")


@dataclass
class LinkRecord:
    title: str
    url: str
    category: str = "case_law"


SEARCH_TERMS = [
    "cyber crime",
    "cyber crimes",
    "information technology act 2000",
    "section 43 information technology act",
    "section 66 information technology act",
    "section 66c information technology act",
    "section 66d information technology act",
    "section 66e information technology act",
    "section 66f information technology act",
    "section 67 information technology act",
    "section 69 information technology act",
    "section 72 information technology act",
    "phishing india kanoon",
    "hacking india kanoon",
    "ransomware india kanoon",
    "data theft information technology act",
    "cyber terrorism india",
    "digital evidence information technology act",
]


def build_search_url(term: str, page: int) -> str:
    # IndiaKanoon uses pagenum with a step of 10 for search pagination.
    page_num = max(0, page) * 10
    return f"{BASE_URL}/search/?formInput={quote_plus(term)}&pagenum={page_num}"


def load_robots(session: requests.Session) -> RobotFileParser:
    rp = RobotFileParser()
    resp = session.get(ROBOTS_URL, timeout=30)
    resp.raise_for_status()
    rp.parse(resp.text.splitlines())
    return rp


def extract_doc_links(html: str) -> Iterable[LinkRecord]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not re.match(r"^/doc/\d+/?$", href):
            continue

        url = urljoin(BASE_URL, href)
        if url in seen:
            continue
        seen.add(url)

        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not title:
            title = "Full Document"

        yield LinkRecord(title=title, url=url)


def generate_links(
    session: requests.Session,
    rp: RobotFileParser,
    terms: list[str],
    max_pages_per_term: int,
    delay_seconds: float,
    user_agent: str,
) -> list[LinkRecord]:
    collected: dict[str, LinkRecord] = {}

    for term in terms:
        for page in range(max_pages_per_term):
            search_url = build_search_url(term, page)
            if not rp.can_fetch(user_agent, search_url):
                continue

            resp = session.get(search_url, timeout=40)
            if resp.status_code != 200:
                continue

            records = list(extract_doc_links(resp.text))
            if not records:
                break

            for record in records:
                if not rp.can_fetch(user_agent, record.url):
                    continue
                if record.url not in collected:
                    collected[record.url] = record

            time.sleep(delay_seconds)

    return list(collected.values())


def write_csv(path: Path, records: list[LinkRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["domain", "category", "title", "url", "source", "expected_type", "tags"])
        for record in records:
            writer.writerow(
                [
                    "cybercrime_laws",
                    record.category,
                    record.title,
                    record.url,
                    "indiankanoon",
                    "html",
                    "cybercrime;legal",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate robots-compliant IndiaKanoon cybercrime links.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-pages-per-term", type=int, default=25)
    parser.add_argument("--delay", type=float, default=1.2)
    args = parser.parse_args()

    user_agent = "Mozilla/5.0 (compatible; legal-scraper/1.0; +https://example.invalid/bot-info)"
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})

    rp = load_robots(session)
    records = generate_links(
        session=session,
        rp=rp,
        terms=SEARCH_TERMS,
        max_pages_per_term=args.max_pages_per_term,
        delay_seconds=args.delay,
        user_agent=user_agent,
    )

    write_csv(args.output, records)
    print(f"Wrote {len(records)} robots-allowed links to {args.output}")


if __name__ == "__main__":
    main()