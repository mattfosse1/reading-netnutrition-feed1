#!/usr/bin/env python3
"""Incremental, rate-limited nutrition-label collection from public Reading menus.

Read-only use of public CBORD endpoints. Keep each label tied to its exact
detailOid; do not merge same-named dishes. JSON sharded by venue.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reader import Http, Browser, label

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def valid_cached(record, *, max_age_days=7):
    if not isinstance(record, dict) or not record.get("labelText"):
        return False
    try:
        observed = datetime.fromisoformat(record["fetchedAtUTC"])
        return observed.tzinfo is not None and datetime.now(timezone.utc) - observed < timedelta(days=max_age_days)
    except (KeyError, ValueError, TypeError):
        return False

def load_cache(folder):
    cache = {}
    for path in Path(folder).glob("venue-*.json"):
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(values, dict):
                cache[path.stem.removeprefix("venue-")] = values
        except (ValueError, OSError) as exc:
            raise RuntimeError(f"Invalid existing nutrition cache {path}: {exc}") from exc
    return cache

def feed_entries(snapshot):
    # Oldest scheduled date first, across every venue. Where date is unknown,
    # retain it at the end. Never use a dish name as its cache key.
    result = []
    for vi, venue in enumerate(snapshot["venues"]):
        for mi, menu in enumerate(venue["menus"]):
            for category in menu["categories"]:
                for item in category["items"]:
                    if item.get("id"):
                        result.append((menu.get("dateText") or "9999", vi, mi, str(item["id"])))
    def sort_key(record):
        dt, vi, mi, _ = record
        try:
            parsed = datetime.strptime(dt, "%A, %B %d, %Y").date().isoformat()
        except ValueError:
            parsed = "9999"
        return parsed, vi, mi
    result.sort(key=sort_key)
    return result

def coverage(snapshot, cache):
    by_venue = []
    total = 0
    available = 0
    ingredients_available = 0
    for venue in snapshot["venues"]:
        vid = str(venue["id"])
        ids = {str(item["id"]) for menu in venue["menus"]
               for category in menu["categories"] for item in category["items"] if item.get("id")}
        ready = [cache.get(vid, {}).get(oid) for oid in ids
                 if valid_cached(cache.get(vid, {}).get(oid))]
        by_venue.append({"venue": venue["name"], "venueId": vid,
                         "total": len(ids), "withLabels": len(ready)})
        total += len(ids)
        available += len(ready)
        ingredients_available += sum(bool(x.get("ingredients")) for x in ready)
    return {"totalDishEntries": total, "withRecentLabels": available,
            "withIngredientsField": ingredients_available,
            "labelCoveragePercent": round(available / total * 100, 2) if total else 0,
            "byVenue": by_venue}

def collect_batch(client, snapshot, cache, limit=350, max_errors=12):
    candidates = feed_entries(snapshot)
    selected_venue = selected_menu = None
    attempted = saved = 0
    errors = []
    seen = set()
    for date_text, vi, mi, oid in candidates:
        venue, menu = snapshot["venues"][vi], snapshot["venues"][vi]["menus"][mi]
        vid = str(venue["id"])
        key = vid, oid
        if key in seen:
            continue
        seen.add(key)
        if valid_cached(cache.get(vid, {}).get(oid)):
            continue
        if attempted >= limit or len(errors) >= max_errors:
            break
        try:
            if selected_venue != vid:
                client.post("Unit/SelectUnitFromUnitsList", {"unitOid": vid})
                selected_venue, selected_menu = vid, None
            mid = str(menu.get("id") or "")
            if mid and selected_menu != mid:
                client.post("Menu/SelectMenu", {"menuOid": mid})
                selected_menu = mid
            attempted += 1
            raw = client.post("NutritionDetail/ShowItemNutritionLabel",
                              {"detailOid": oid}, json_response=False)
            parsed = label(raw)
            full = parsed.get("labelText", "")
            if not full or not ("Nutrition" in full or "Ingredients:" in full):
                raise RuntimeError("Empty or unrecognised nutrition label")
            record = {"id": oid, "venueId": vid, "dish": next(
                      (item.get("name", "") for cat in menu["categories"]
                       for item in cat["items"] if str(item.get("id")) == oid), ""),
                      "dateText": date_text, "meal": menu.get("name", ""),
                      "fetchedAtUTC": utc_now(), **parsed}
            cache.setdefault(vid, {})[oid] = record
            saved += 1
        except Exception as exc:
            errors.append(f"{venue['name']} / {oid}: {type(exc).__name__}: {str(exc)[:120]}")
    return {"attempted": attempted, "newLabels": saved, "errors": errors}

def save_cache(folder, snapshot, cache, batch):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    valid_ids = defaultdict(set)
    for venue in snapshot["venues"]:
        for menu in venue["menus"]:
            for category in menu["categories"]:
                for item in category["items"]:
                    if item.get("id"):
                        valid_ids[str(venue["id"])].add(str(item["id"]))
    # Prune no-longer-published detailOids and expired labels.
    for vid in list(cache):
        cache[vid] = {oid: value for oid, value in cache[vid].items()
                      if oid in valid_ids.get(vid, set()) and valid_cached(value)}
    for vid in valid_ids:
        path = folder / f"venue-{vid}.json"
        new_text = json.dumps(cache.get(vid, {}), indent=2, ensure_ascii=False)
        if not path.exists() or path.read_text(encoding="utf-8") != new_text:
            path.write_text(new_text + "\n", encoding="utf-8")
    status = {"menuCapturedAtUTC": snapshot.get("capturedAtUTC"),
              "lastCheckedUTC": utc_now(), **coverage(snapshot, cache),
              "lastBatch": batch,
              "note": ("Labels are public CBORD snapshots. Ingredient and allergen "
                       "fields are not authoritative for food safety; verify with Dining.")}
    (folder / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "byVenue"}, indent=2), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=Path("data/latest.json"))
    parser.add_argument("--output", type=Path, default=Path("data/labels"))
    parser.add_argument("--max-labels", type=int, default=350)
    parser.add_argument("--transport", choices=("http", "browser"), default="http")
    args = parser.parse_args()
    if not 1 <= args.max_labels <= 750:
        parser.error("--max-labels must be 1–750")
    snapshot = json.loads(args.feed.read_text(encoding="utf-8"))
    if not snapshot.get("venues") or not snapshot.get("stats", {}).get("items"):
        raise SystemExit("No valid menu snapshot")
    cache = load_cache(args.output)
    client = Http() if args.transport == "http" else Browser()
    try:
        client.landing()
        batch = collect_batch(client, snapshot, cache, args.max_labels)
    finally:
        client.close()
    # Never poison current caches with failures, but commit successful partial batches.
    if batch["attempted"] and batch["newLabels"] == 0:
        raise SystemExit("No new labels retrieved; existing cache untouched. " + repr(batch["errors"][:3]))
    save_cache(args.output, snapshot, cache, batch)
    if batch["errors"]:
        print("Some labels could not be read:", *batch["errors"], sep="\n- ", file=sys.stderr)

if __name__ == "__main__":
    main()
