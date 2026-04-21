"""
Ecosystem Database Updater
"""

import os
import time
import requests
import anthropic
from datetime import datetime

# ── Configuration ────────────────────────────────────────────────────────────

NOTION_TOKEN      = os.environ["NOTION_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DATABASE_ID       = os.environ["NOTION_DATABASE_ID"]

MONTHS_BACK       = 1
UPDATES_PROPERTY  = "Latest Updates"
DELAY_SECONDS     = 3

NOTION_VERSION    = "2022-06-28"
NOTION_HEADERS    = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Notion helpers ────────────────────────────────────────────────────────────

def get_all_organisations():
    """Fetch every row from the Notion database using the REST API directly."""
    results = []

    # Strip any accidental whitespace from the database ID
    db_id = DATABASE_ID.strip()
    print(f"  Database ID being used: '{db_id}' (length: {len(db_id)})")

    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {"page_size": 100}

    while True:
        response = requests.post(url, headers=NOTION_HEADERS, json=payload)

        # Print full error detail if something goes wrong
        if not response.ok:
            print(f"  Notion API error {response.status_code}: {response.text}")
            response.raise_for_status()

        data = response.json()
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]

    return results


def extract_org_name(page):
    """Pull the organisation name from the title property."""
    for prop_value in page["properties"].values():
        if prop_value["type"] == "title":
            rich_text = prop_value["title"]
            if rich_text:
                return rich_text[0]["plain_text"]
    return None


def write_update_to_notion(page_id, summary):
    """Write the summary into the Latest Updates property."""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            UPDATES_PROPERTY: {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": summary[:2000]}
                    }
                ]
            }
        }
    }
    response = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    if not response.ok:
        print(f"  Notion write error {response.status_code}: {response.text}")
        response.raise_for_status()


# ── Claude search + summarise ─────────────────────────────────────────────────

def search_and_summarise(org_name):
    """Use Claude with web search to summarise recent news about the org."""
    today = datetime.today().strftime("%B %Y")

prompt = f"""Search the web for recent news about "{org_name}" from the past {MONTHS_BACK} month(s).

Only report on these four topics:
1. New products or tools launched
2. New policy changes or regulatory announcements
3. New technology partnerships
4. New nature finance announcements

Today's date is {today}.

If you find relevant updates, write exactly 2 sentences summarising the most important one. Each sentence must include a markdown hyperlink to the source, formatted like this: [anchor text](URL).

Example format:
{org_name} launched a new biodiversity monitoring tool in partnership with the EU ([read more](https://example.com)). The tool integrates eDNA data with satellite imagery to provide real-time ecosystem assessments ([source](https://example.com)).

If none of the four topics above have any updates, write only: "No relevant updates found."

Do not include bullet points, headers, or any other formatting."""

    response = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    summary = ""
    for block in response.content:
        if block.type == "text":
            summary += block.text

    return summary.strip() if summary else "No significant updates found."


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  Ecosystem Updater -- {datetime.today().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*60}\n")

    pages = get_all_organisations()
    print(f"Found {len(pages)} organisations in database.\n")

    for i, page in enumerate(pages, start=1):
        org_name = extract_org_name(page)
        if not org_name:
            print(f"  [{i}] Skipping row with no name.")
            continue

        print(f"  [{i}/{len(pages)}] {org_name} ...", flush=True)

        try:
            summary = search_and_summarise(org_name)
            write_update_to_notion(page["id"], summary)
            print(f"  -> Done: {summary[:120]}{'...' if len(summary) > 120 else ''}\n")
        except Exception as e:
            print(f"  -> ERROR: {e}\n")

        time.sleep(DELAY_SECONDS)

    print(f"\n{'='*60}")
    print("  Done! All organisations updated in Notion.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
