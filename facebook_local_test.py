"""Local, interactive Facebook access test. Never commit the browser profile."""
import asyncio
import csv
from pathlib import Path
from playwright.async_api import async_playwright

PROFILE = Path(".local-facebook-profile")
OUTPUT = Path("facebook_local_test.csv")

async def main():
    with open("sources.csv", encoding="utf-8-sig", newline="") as f:
        sources = [s for s in csv.DictReader(f) if "facebook.com" in s["url"]]
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, locale="fi-FI", slow_mo=150
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        print("Kirjaudu Facebookiin avautuvassa ikkunassa tarvittaessa.")
        await asyncio.to_thread(input, "Kun olet kirjautunut, paina Enter tässä ikkunassa...")
        results = []
        for source in sources:
            print("Testataan:", source["venue"], source["url"])
            try:
                response = await page.goto(source["url"], wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
                body = (await page.locator("body").inner_text(timeout=15000))[:5000]
                status = response.status if response else ""
                blocked = any(term in body.lower() for term in (
                    "log in to facebook", "kirjaudu facebookiin", "log in or sign up"
                ))
                results.append(dict(venue=source["venue"], url=source["url"],
                    http_status=status, readable_chars=len(body),
                    login_wall=blocked, sample=body[:350].replace("\n", " ")))
                print("HTTP:", status, "Tekstiä:", len(body), "Kirjautumisseinä:", blocked)
            except Exception as exc:
                results.append(dict(venue=source["venue"], url=source["url"],
                    http_status="", readable_chars=0, login_wall="",
                    sample=str(exc)[:350]))
                print("Virhe:", str(exc)[:200])
        with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["venue", "url", "http_status",
                "readable_chars", "login_wall", "sample"])
            writer.writeheader()
            writer.writerows(results)
        print("Tulokset:", OUTPUT.resolve())
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
