#!/usr/bin/env python3
"""
Syncs CPI/PPI/FOMC/NFP-tagged days from the INDICES LOG Notion database
and computes direction bias + RTH-profile stats for each event category.

Requires env var:
  NOTION_TOKEN - Notion integration token (must have access to INDICES LOG,
                 the DIRECTION lookup table, and the RTH PROFILES lookup table)
"""
import os
import sys
import json
import re
import datetime as dt
from collections import Counter, defaultdict
import urllib.request
import urllib.error

NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or None
INDICES_LOG_ID = "28cf7bb7-7d6d-80d1-94ef-000b834cefb7"
NOTION_VERSION = "2025-09-03"
API_URL = f"https://api.notion.com/v1/data_sources/{INDICES_LOG_ID}/query"

# Lookup tables (hardcoded — small fixed sets, avoids extra API calls per page)
DIRECTION_NAMES = {
    "33af7bb7-7d6d-802a-ad19-d8d882d8fadc": "DOWNCLOSE",
    "33af7bb7-7d6d-8062-a4bc-df0dd5c1ec97": "UPCLOSE",
    "33af7bb7-7d6d-80b5-b9bf-e985fb27de01": "BOTHWAYS",
    "33bf7bb7-7d6d-8016-bf4f-d1719a470710": "SIDEWAYS",
}

# RTH RANGE page id -> display name (from the actual RTH RANGE relation
# property on INDICES LOG — distinct from RTH PROFILES).
RTH_RANGE_NAMES = {
    "2c2f7bb7-7d6d-8002-8c2c-c2926ebb2b7b": "AM DR-[2:50-3:10]",
    "2c2f7bb7-7d6d-8033-97be-cc9a19f6a033": "11AM-1PM-[3:30-4PM]",
    "2c2f7bb7-7d6d-804f-ae83-eac27c9ae297": "AM DR-[3:30-4PM]",
    "2c2f7bb7-7d6d-805c-af2c-c05ef8351291": "AM DR-[11AM-1PM]",
    "2c2f7bb7-7d6d-8075-93f9-ca871f7074a8": "11AM-1PM-[2:50-3:10]",
    "2c2f7bb7-7d6d-80da-99e6-cea24324f125": "AM DR-[1-2PM]",
    "2c2f7bb7-7d6d-80ec-8fb9-da0f27c9dfda": "11AM-1PM-[11AM-1PM]",
    "33af7bb7-7d6d-8058-a259-e66f8e00f9b6": "1-2PM-[3:30-4PM]",
    "33af7bb7-7d6d-80f7-9446-d412719b312f": "AM DR [Low-High]",
    "34cf7bb7-7d6d-80b4-9193-eae53b5d6f90": "11AM-1PM-[1-2PM]",
    "3adf7bb7-7d6d-8038-af75-cb12a879bf82": "PM [LOD-HOD]",
}

RTH_PROFILE_NAMES = {
    "2a2f7bb7-7d6d-805c-83bd-e0aa4ab66f53": "AM DR Low LOD - 3:30-4PM HOD",
    "2a2f7bb7-7d6d-808f-b08b-df211236bba1": "AM DR Low LOD - 1-2PM HOD",
    "2a2f7bb7-7d6d-80e4-b3d4-ef1d317f380e": "AM DR High HOD - 11AM-1PM LOD",
    "303f7bb7-7d6d-8076-92ef-cb57d0a10e16": "AM DR Low LOD - 2:50-3:10 HOD",
    "339f7bb7-7d6d-8005-a190-efdf6a9e4fb8": "AM DR High HOD - 3:30-4PM LOD",
    "339f7bb7-7d6d-8014-b10f-c4db97570c0d": "AM DR Low LOD - 11AM-1PM HOD",
    "339f7bb7-7d6d-8017-b1e6-ef2c1c1b9e42": "AM DR High HOD - 1-2PM LOD",
    "339f7bb7-7d6d-8051-a990-cbf4451c80af": "AM ADR High HOD - AM ADR Low LOD",
    "339f7bb7-7d6d-806e-b59d-cc71859f8018": "11AM-1PM HOD - 3:30-4PM LOD",
    "339f7bb7-7d6d-8097-b7a8-e0a89f67ad7d": "1-2PM LOD - 3:30-4PM HOD",
    "339f7bb7-7d6d-80a0-849c-c9e959a66894": "11AM-1PM LOD - 3:30-4PM HOD",
    "339f7bb7-7d6d-80bb-8a5c-d37fba209ae0": "11AM-1PM HOD - 11AM-1PM LOD",
    "33af7bb7-7d6d-808a-be8e-f87aa014db8d": "AM DR High HOD - 2:50-3:10 LOD",
    "34cf7bb7-7d6d-8072-b982-e4ed843b7d7e": "11AM-1PM HOD - 1-2PM LOD",
    "3adf7bb7-7d6d-808f-8fe0-f4011e2d2a28": "2:30-4PM - HOD/LOD",
}

# RTH profile page id -> whether the AM opening range (AM DR / AM ADR)
# captured one of the day's extremes (HOD or LOD)
RTH_AM_CAPTURE = {
    "2a2f7bb7-7d6d-805c-83bd-e0aa4ab66f53": True,   # AM DR Low LOD - 3:30-4PM HOD
    "2a2f7bb7-7d6d-808f-b08b-df211236bba1": True,   # AM DR Low LOD - 1-2PM HOD
    "2a2f7bb7-7d6d-80e4-b3d4-ef1d317f380e": True,   # AM DR High HOD - 11AM-1PM LOD
    "303f7bb7-7d6d-8076-92ef-cb57d0a10e16": True,   # AM DR Low LOD - 2:50-3:10 HOD
    "339f7bb7-7d6d-8005-a190-efdf6a9e4fb8": True,   # AM DR High HOD - 3:30-4PM LOD
    "339f7bb7-7d6d-8014-b10f-c4db97570c0d": True,   # AM DR Low LOD - 11AM-1PM HOD
    "339f7bb7-7d6d-8017-b1e6-ef2c1c1b9e42": True,   # AM DR High HOD - 1-2PM LOD
    "339f7bb7-7d6d-8051-a990-cbf4451c80af": True,   # AM ADR High HOD - AM ADR Low LOD
    "339f7bb7-7d6d-806e-b59d-cc71859f8018": False,  # 11AM-1PM HOD - 3:30-4PM LOD
    "339f7bb7-7d6d-8097-b7a8-e0a89f67ad7d": False,  # 1-2PM LOD - 3:30-4PM HOD
    "339f7bb7-7d6d-80a0-849c-c9e959a66894": False,  # 11AM-1PM LOD - 3:30-4PM HOD
    "339f7bb7-7d6d-80bb-8a5c-d37fba209ae0": False,  # 11AM-1PM HOD - 11AM-1PM LOD
    "33af7bb7-7d6d-808a-be8e-f87aa014db8d": True,   # AM DR High HOD - 2:50-3:10 LOD
    "34cf7bb7-7d6d-8072-b982-e4ed843b7d7e": False,  # 11AM-1PM HOD - 1-2PM LOD
    "3adf7bb7-7d6d-808f-8fe0-f4011e2d2a28": False,  # 2:30-4PM - HOD LOD
}


def notion_request(payload, cursor=None):
    body = dict(payload)
    if cursor:
        body["start_cursor"] = cursor
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_event_pages():
    """Fetch all INDICES LOG pages whose Name contains a macro-event tag."""
    results = []
    cursor = None
    filt = {
        "or": [
            {"property": "Name", "title": {"contains": kw}}
            for kw in ["CPI", "PPI", "FOMC", "NFP"]
        ]
    }
    while True:
        data = notion_request({"page_size": 100, "filter": filt}, cursor)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return results


def relation_id(prop):
    rel = (prop or {}).get("relation") or []
    return rel[0]["id"] if rel else None


def categorize(name):
    """Return list of (category, is_pre) tuples this page's Name belongs to."""
    cats = []
    for event in ["CPI", "PPI", "FOMC", "NFP"]:
        if event in name:
            is_pre = bool(re.search(r"pre[\s-]*" + event, name, re.IGNORECASE))
            cats.append((event, is_pre))
    return cats


def build_stats(pages):
    # per-category counters
    direction_counts = defaultdict(Counter)
    am_capture = defaultdict(lambda: [0, 0])  # [captured, total]
    rth_range_counts = defaultdict(Counter)
    day_list = defaultdict(list)

    for p in pages:
        props = p.get("properties", {})
        name = "".join(t.get("plain_text", "") for t in props.get("Name", {}).get("title", []))
        start = (props.get("Date", {}).get("date") or {}).get("start")

        dir_id = relation_id(props.get("DIRECTION"))
        rth_profile_id = relation_id(props.get("RTH PROFILES"))
        rth_range_id = relation_id(props.get("RTH RANGE"))
        direction = DIRECTION_NAMES.get(dir_id)
        am_hit = RTH_AM_CAPTURE.get(rth_profile_id)
        rth_range = RTH_RANGE_NAMES.get(rth_range_id)

        cats = categorize(name)
        for event, is_pre in cats:
            key = f"Pre-{event}" if is_pre else event
            if direction:
                direction_counts[key][direction] += 1
            if am_hit is not None:
                am_capture[key][1] += 1
                if am_hit:
                    am_capture[key][0] += 1
            if rth_range:
                rth_range_counts[key][rth_range] += 1
            day_list[key].append({"name": name, "date": start, "direction": direction})

    order = ["Pre-NFP", "NFP", "Pre-CPI", "CPI", "Pre-FOMC", "FOMC", "Pre-PPI", "PPI"]
    direction_labels = ["DOWNCLOSE", "UPCLOSE", "BOTHWAYS", "SIDEWAYS"]

    categories = {}
    for key in order:
        total_dir = sum(direction_counts[key].values())
        categories[key] = {
            "n_direction": total_dir,
            "direction_count": {lbl: direction_counts[key][lbl] for lbl in direction_labels},
            "direction_pct": {
                lbl: round(100 * direction_counts[key][lbl] / total_dir, 1) if total_dir else 0
                for lbl in direction_labels
            },
            "am_capture_pct": round(100 * am_capture[key][0] / am_capture[key][1], 1) if am_capture[key][1] else None,
            "am_capture_count": am_capture[key][0],
            "am_capture_n": am_capture[key][1],
            "rth_range": dict(rth_range_counts[key]),
            "days": sorted(day_list[key], key=lambda d: d["date"] or ""),
        }

    return {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "category_order": order,
        "categories": categories,
    }


def main():
    if not NOTION_TOKEN:
        print("NOTION_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    try:
        pages = fetch_event_pages()
    except urllib.error.HTTPError as e:
        print(f"Notion API error: {e.code} {e.read()}", file=sys.stderr)
        sys.exit(1)

    stats = build_stats(pages)
    os.makedirs("data", exist_ok=True)

    # TEMPORARY DIAGNOSTIC: query the DIRECTION table directly (not through
    # INDICES LOG) to see if ITS relation back to INDICES LOG resolves —
    # isolates whether this is a one-directional visibility issue.
    try:
        dir_url = "https://api.notion.com/v1/data_sources/33af7bb7-7d6d-80b1-bd2e-000bf31c2649/query"
        req = urllib.request.Request(
            dir_url, data=json.dumps({"page_size": 5}).encode(),
            headers={"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": NOTION_VERSION, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            dir_data = json.loads(resp.read())
        rows = []
        for r in dir_data.get("results", []):
            name = "".join(t.get("plain_text", "") for t in r.get("properties", {}).get("Name", {}).get("title", []))
            rows.append({"name": name, "properties": list(r.get("properties", {}).keys()), "raw": r.get("properties", {})})
        with open("data/debug.log", "w") as f:
            f.write(json.dumps(rows, indent=2, default=str))
    except Exception as e:
        with open("data/debug.log", "w") as f:
            f.write(f"Direct DIRECTION query failed: {e}")

    with open("data/macro_events.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Synced {len(pages)} tagged pages -> data/macro_events.json")


if __name__ == "__main__":
    main()
