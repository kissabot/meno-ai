import asyncio
import csv
import re
from datetime import datetime, date, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

SOURCE_FILE = "sources.csv"
SCAN_FILE = "scan_results.csv"
EVENT_FILE = "event_candidates.csv"

DATE_PATTERNS = [
    re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?![./\d])"),
    re.compile(r"(?<!\d)(20\d{2})-(\d{1,2})-(\d{1,2})(?!\d)"),
]
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")
PRICE_RE = re.compile(
    r"(?i)(?:liput?|pääsymaksu|sisäänpääsy|entry|tickets?|"
    r"ennakko|ovelta)\s*[:=]?\s*(\d{1,3}(?:[,.]\d{1,2})?)\s*(€|eur)?"
)
EVENT_WORDS = re.compile(
    r"(?i)\b(keikka|live|konsertti|dj|karaoke|bingo|pub quiz|"
    r"visa|tietovisa|bändi|esiintyy|show|party|bileet|tapahtuma)\b"
)
DATE_WORDS = re.compile(
    r"(?i)\b(ma|ti|ke|to|pe|la|su|maanantai|tiistai|keskiviikko|"
    r"torstai|perjantai|lauantai|sunnuntai|tänään|huomenna)\b"
)


def extract_date(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            if pattern is DATE_PATTERNS[2]:
                year, month, day = map(int, match.groups())
            elif len(match.groups()) == 3:
                day, month, year = map(int, match.groups())
            else:
                day, month = map(int, match.groups())
                year = datetime.now().year
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            continue
    return ""


def date_today():
    return date.today().isoformat()


def extract_events(source, content):
    events = []
    seen = set()
    for raw_line in content.splitlines():
        line = " ".join(raw_line.split()).strip(" •-–|")
        if len(line) < 8:
            continue

        date = extract_date(line)
        time_match = TIME_RE.search(line)
        has_event_word = bool(EVENT_WORDS.search(line))
        has_date_word = bool(DATE_WORDS.search(line))

        # Keep likely event announcements, but don't invent missing details.
        if not (date and (has_event_word or time_match)):
            continue
        if date < date_today() or date > (datetime.now().date() + timedelta(days=365)).isoformat():
            continue

        price_match = PRICE_RE.search(line)
        time = f"{time_match.group(1)}:{time_match.group(2)}" if time_match else ""
        price = price_match.group(1).replace(",", ".") if price_match else ""
        key = (source["venue"].casefold(), date, time, line.casefold())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "city": source["city"],
            "venue": source["venue"],
            "date": date,
            "time": time,
            "price_eur": price,
            "event_text": line[:1000],
            "source_url": source["url"],
            "review_status": "tarkistettava",
        })
    return events


async def main():
    with open(SOURCE_FILE, newline="", encoding="utf-8-sig") as file:
        sources = list(csv.DictReader(file))

    scans = []
    events = []
    failed_facebook = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()


        for source in sources:
            print(f"Luetaan: {source['venue']}")
            title = ""
            content = ""
            error_text = ""

            context = await browser.new_context(locale="fi-FI")
            page = await context.new_page()
            try:
                response = await page.goto(
                    source["url"],
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(800)
                title = await page.title()
                content = await page.locator("body").inner_text(timeout=10000)
                if response and response.status >= 400:
                    error_text = f"HTTP {response.status}"
                if "facebook.com" in source["url"] and re.search(r"(log in|kirjaudu sisään|create new account)", content[:1500], re.I) and len(content) < 2500:
                    error_text = error_text or "Mahdollinen Facebook-kirjautumisseinä"
            except Exception as error:
                error_text = str(error)[:500]
                print(f"Virhe: {source['venue']}: {error_text}")

            finally:
                await context.close()

            if error_text and "facebook.com" in source["url"]:
                failed_facebook.append({"venue": source["venue"], "url": source["url"], "error": error_text})
            content = content[:12000]
            scans.append({
                "city": source["city"],
                "venue": source["venue"],
                "url": source["url"],
                "title": title,
                "content": content,
                "error": error_text,
            })
            events.extend(extract_events(source, content))

        await browser.close()

    with open(SCAN_FILE, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["city", "venue", "url", "title", "content", "error"],
        )
        writer.writeheader()
        writer.writerows(scans)

    with open(EVENT_FILE, "w", newline="", encoding="utf-8-sig") as file:
        fields = [
            "city", "venue", "date", "time", "price_eur",
            "event_text", "source_url", "review_status",
        ]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(events)

    with open("facebook_failures.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["venue", "url", "error"])
        writer.writeheader()
        writer.writerows(failed_facebook)

    print(f"Facebook-ongelmia: {len(failed_facebook)}. Katso facebook_failures.csv.")
    print(f"Valmis! Skannattiin {len(scans)} lähdettä.")
    print(f"Löytyi {len(events)} mahdollista tapahtumariviä (vaativat tarkistuksen).")


if __name__ == "__main__":
    asyncio.run(main())
