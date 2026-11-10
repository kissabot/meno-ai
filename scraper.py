
import csv
import asyncio
from playwright.async_api import async_playwright

async def main():
    results = []

    with open("sources.csv", newline="", encoding="utf-8-sig") as file:
        sources = list(csv.DictReader(file))

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        for source in sources:
            url = source["url"]
            city = source["city"]
            venue = source["venue"]

            print(f"Luetaan: {venue}")

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                title = await page.title()
                content = await page.locator("body").inner_text(
                    timeout=10000
                )

                results.append({
                    "city": city,
                    "venue": venue,
                    "url": url,
                    "title": title,
                    "content": content[:5000]
                })

            except Exception as error:
                print(f"Virhe: {venue}: {error}")

        await browser.close()

    with open("scan_results.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["city", "venue", "url", "title", "content"]
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"Valmis! Tallennettiin {len(results)} lähdettä.")

asyncio.run(main())
