"""
Ecosystem Database Updater
==========================
Searches the web for recent news on each organisation in your Notion
Ecosystem database, summarises updates using Claude, and writes them
back to the "Latest Updates" property.

Run manually:  python update_ecosystem.py
Run on a schedule: see README / setup guide
"""

import os
import json
import time
import anthropic
from notion_client import Client
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────

NOTION_TOKEN      = os.environ["NOTION_TOKEN"]        # your Notion integration token
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]   # your Anthropic API key
DATABASE_ID       = os.environ["NOTION_DATABASE_ID"]  # your Ecosystem database ID

# How many months back to search for news (keep at 1–3 for relevance)
MONTHS_BACK = 1

# Which Notion property to write updates into
UPDATES_PROPERTY = "Latest Updates"

# Delay between API calls (seconds) — avoids hitting rate limits
DELAY_SECONDS = 3

# ── Clients ──────────────────────────────────────────────────────────────────

notion    = Client(auth=NOTION_TOKEN)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_all_organisations():
    """Fetch every row from the Notion database."""
    results = []
    has_more = True
    start_cursor = None

    while has_more:
        kwargs = {"database_id": DATABASE_ID, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = notion.databases.query(**kwargs)
        results.extend(response["results"])
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    return results


def extract_org_name(page):
    """Pull the organisation name out of a Notion page's title property."""
    for prop_name, prop_value in page["properties"].items():
        if prop_value["type"] == "title":
            rich_text = prop_value["title"]
            if rich_text:
                return rich_text[0]["plain_text"]
    return None


def search_and_summarise(org_name):
    """
    Use Claude with web search to find and summarise recent news
    about the given organisation. Returns a short text summary.
    """
    today = datetime.today().strftime("%B %Y")

    prompt = f"""Search the web for recent news and updates about "{org_name}" 
from the past {MONTHS_BACK} month(s). Focus on:
- New products, tools or data releases
- Key publications or reports
- Policy announcements or partnerships
- Funding rounds or major organisational changes

Today's date is {today}.

Write a concise 2–4 sentence summary of the most relevant recent updates. 
If there is nothing noteworthy, say "No significant updates found."
Do not include bullet points — write in plain prose."""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract the text response from the content blocks
    summary = ""
    for block in response.content:
        if block.type == "text":
            summary += block.text

    return summary.strip() if summary else "No significant updates found."


def write_update_to_notion(page_id, summary):
    """Write the summary string into the Latest Updates property."""
    notion.pages.update(
        page_id=page_id,
        properties={
            UPDATES_PROPERTY: {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": summary[:2000]}  # Notion rich_text limit
                    }
                ]
            }
        }
    )


# ── Main loop ────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  Ecosystem Updater — {datetime.today().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}\n")

    pages = get_all_organisations()
    print(f"Found {len(pages)} organisations in database.\n")

    for i, page in enumerate(pages, start=1):
        org_name = extract_org_name(page)
        if not org_name:
            print(f"  [{i}] Skipping row with no name.")
            continue

        print(f"  [{i}/{len(pages)}] Searching for: {org_name} ...", end=" ", flush=True)

        try:
            summary = search_and_summarise(org_name)
            write_update_to_notion(page["id"], summary)
            print("✓")
            print(f"        → {summary[:120]}{'...' if len(summary) > 120 else ''}\n")
        except Exception as e:
            print(f"✗ ERROR: {e}\n")

        time.sleep(DELAY_SECONDS)

    print(f"\n{'='*60}")
    print("  Done! All organisations updated in Notion.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
