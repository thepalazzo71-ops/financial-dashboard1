"""Merge a comments Export file from the dashboard into data/comments.json
(the repo copy), de-duplicating by comment id, then rebuild the pages.

Usage: python3 scripts/merge_comments.py path/to/shortlist-comments-YYYY-MM-DD.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "data" / "comments.json"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = json.load(open(sys.argv[1]))
    incoming = src.get("comments")
    if not isinstance(incoming, dict):
        sys.exit("not a comments export (no 'comments' object)")
    dest = json.load(open(DEST)) if DEST.exists() else {"comments": {}}
    store = dest.setdefault("comments", {})
    added = 0
    for ticker, items in incoming.items():
        if not isinstance(items, list):
            continue
        have = {x["id"] for x in store.get(ticker, [])}
        for x in items:
            atts = x.get("attachments") if isinstance(x, dict) else None
            atts = atts if isinstance(atts, list) and atts else None
            if (isinstance(x, dict) and isinstance(x.get("id"), str) and isinstance(x.get("ts"), str)
                    and isinstance(x.get("text"), str) and (x["text"].strip() or atts) and x["id"] not in have):
                item = {"id": x["id"], "ts": x["ts"], "text": x["text"]}
                if atts:  # metadata only: the file bytes stay in Cloudflare
                    item["attachments"] = atts
                store.setdefault(ticker, []).append(item)
                have.add(x["id"])
                added += 1
        if ticker in store:
            store[ticker].sort(key=lambda x: x["ts"], reverse=True)
    json.dump(dest, open(DEST, "w"), indent=1, ensure_ascii=False)
    total = sum(len(v) for v in store.values())
    print(f"merged {added} new comment(s); data/comments.json now holds {total} on {len(store)} companies")


if __name__ == "__main__":
    main()
