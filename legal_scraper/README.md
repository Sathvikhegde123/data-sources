# Legal Scraper (Cybersecurity + Property Rights)

This project gives you a scalable pipeline:

1. Collect legal links from seed websites
2. Scrape HTML + linked PDFs for many URLs
3. Parse raw files into structured JSON

## Folder Layout

```text
legal_scraper/
├── config/
│   └── seeds.json
├── logs/
├── metadata/
│   ├── links.csv
│   ├── links_collected.csv
│   └── scrape_results.jsonl
├── parsed_json/
├── raw_html/
├── raw_pdfs/
├── link_collector.py
├── scraper.py
├── parser.py
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
```

`selenium` uses Selenium Manager, so you do not need to download ChromeDriver manually.

## 1) Collect Candidate Links

Use this to discover many links from seed websites and auto-tag by domain keywords.

```bash
python link_collector.py --headless --max-pages 80
```

Output file: `metadata/links_collected.csv`

Review it and move good URLs into `metadata/links.csv`.

## 2) Bulk Scrape URLs (HTML + PDF)

Scrape all links:

```bash
python scraper.py --headless --wait 20 --retries 3 --max-pdfs 3
```

Scrape only cyber domain:

```bash
python scraper.py --headless --domain cybersecurity
```

Scrape only property domain:

```bash
python scraper.py --headless --domain property_rights
```

Outputs:
- HTML files in `raw_html/<domain>/`
- PDF files in `raw_pdfs/<domain>/`
- Status log in `metadata/scrape_results.jsonl`

## 3) Parse Raw Data into JSON

```bash
python parser.py --max-pdf-pages 25
```

Output JSON files are saved under `parsed_json/` mirroring source folders.

## URL Dataset Schema

`metadata/links.csv` columns:

- `domain`: `cybersecurity` or `property_rights`
- `category`: `act`, `case_law`, `policy`, `manual`, etc.
- `title`: friendly title used for filenames
- `url`: page URL
- `source`: source website name
- `expected_type`: `auto`, `html`, or `pdf`
- `tags`: semicolon-separated keywords

## Notes for Dynamic Pages

- Use explicit waits already included in `scraper.py`
- Avoid `time.sleep` unless absolutely necessary
- If a page needs button clicks before content appears, add site-specific Selenium actions in `scraper.py` before reading `page_source`

## Professional Workflow

- Keep fetch and parse separate
- Never parse directly from live site in the same script
- Store raw corpus (`raw_html`, `raw_pdfs`) so parser improvements are easy without re-scraping

