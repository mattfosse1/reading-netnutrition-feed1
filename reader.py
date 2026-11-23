#!/usr/bin/env python3
"""Read public University of Reading CBORD NetNutrition menus (experimental).

No authentication, private API, or bypassing access controls. Not yet
live-validated on the Reading installation; errors never overwrite the feed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

BASE = "https://netmenu.cbord.co.uk/NetNutrition/UniversityofReading"
TIMEOUT = 25
DELAY = float(os.getenv("CALL_DELAY_SECONDS", "0.3"))
UA = "Mozilla/5.0 (compatible; ReadingPublicMenuReader/1.0; read-only)"
RE_UNIT = re.compile(r"unitsSelectUnit\(\s*['\"]?(\d+)")
RE_MENU = re.compile(r"menuListSelectMenu\(\s*['\"]?(\d+)")
RE_ITEM = re.compile(r"getItemNutritionLabelOnClick\(\s*event\s*,\s*['\"]?(\d+)")
RE_CAT = re.compile(r"toggleCourseItems\(\s*this\s*,\s*(\d+)")

def clean(node: Any) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True) if node else "").strip()

def units(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found, seen = [], set()
    for el in soup.select("[onclick*='unitsSelectUnit']"):
        match = RE_UNIT.search(el.get("onclick", ""))
        if match and match[1] not in seen:
            seen.add(match[1])
            found.append({"id": match[1], "name": clean(el)})
    return found

def menus(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    found, seen = [], set()
    for el in soup.select("[onclick*='menuListSelectMenu']"):
        match = RE_MENU.search(el.get("onclick", ""))
        if match and match[1] not in seen:
            seen.add(match[1])
            heading = el.find_previous(class_="card-title") or el.find_previous("header")
            found.append({"id": match[1], "name": clean(el), "dateText": clean(heading)})
    return found

def dishes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    groups, current = [], None
    for row in soup.select("tr.cbo_nn_itemGroupRow, tr[data-categoryid]"):
        if "cbo_nn_itemGroupRow" in row.get("class", []):
            match = RE_CAT.search(row.get("onclick", ""))
            current = {"categoryId": match[1] if match else None,
                       "name": clean(row.select_one("td div")) or clean(row), "items": []}
            groups.append(current)
            continue
        link = row.select_one("a[onclick*='getItemNutritionLabelOnClick']")
        button = row.select_one("button[data-detailoid]")
        match = RE_ITEM.search(link.get("onclick", "")) if link else None
        detail = (button.get("data-detailoid") if button else None) or (match[1] if match else None)
        if not detail:
            continue
        if current is None:
            current = {"categoryId": None, "name": "Other", "items": []}
            groups.append(current)
        cells = row.find_all("td", recursive=False)
        name = clean(link) if link else (clean(cells[0]) if cells else "")
        icons = [im.get("title") for im in (link.select("img[title]") if link else []) if im.get("title")]
        current["items"].append({"id": str(detail), "name": name,
                                 "serving": clean(cells[2]) if len(cells) > 2 else "",
                                 "reportedIcons": icons})
    return groups

def label(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one("#errorPanel, .cbo_nn_PanelErrorDiv"):
        raise RuntimeError("CBORD error panel")
    root = soup.select_one("#nutritionLabel") or soup
    return {"labelText": clean(root),
            "ingredients": clean(root.select_one(".cbo_nn_LabelIngredients")),
            "contains": clean(root.select_one(".cbo_nn_LabelAllergens"))}

class Http:
    name = "http"
    def __init__(self):
        self.base = BASE
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA,
                                     "Referer": BASE,
                                     "X-Requested-With": "XMLHttpRequest"})
    def landing(self):
        response = self.session.get(BASE, timeout=TIMEOUT)
        response.raise_for_status()
        if "html" not in response.headers.get("Content-Type", "text/html").lower():
            raise RuntimeError("Landing did not return HTML")
        return response.text
    def post(self, path, data, json_response=True):
        time.sleep(DELAY)
        response = self.session.post(BASE + "/" + path, data=data,
                                     timeout=TIMEOUT,
                                     headers={"Accept": "application/json, text/javascript, */*; q=0.01"})
        response.raise_for_status()
        if not json_response:
            return response.text
        try:
            value = response.json()
        except ValueError:
            raise RuntimeError(path + ": unexpected non-JSON response: " + response.text[:120])
        if not isinstance(value, dict) or not value.get("success") or not isinstance(value.get("panels"), list):
            raise RuntimeError(path + ": not successful panels: " + str(value)[:140])
        return value
    def close(self):
        self.session.close()

class Browser:
    name = "chromium"
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self.base = BASE
        self.p = sync_playwright().start()
        self.browser = self.p.chromium.launch(headless=True)
        self.context = self.browser.new_context(user_agent=UA)
        self.page = self.context.new_page()
        self.page.set_default_timeout(TIMEOUT * 1000)
    def landing(self):
        self.page.goto(BASE, wait_until="domcontentloaded", timeout=TIMEOUT * 1000)
        self.page.wait_for_timeout(1500)
        return self.page.content()
    def post(self, path, data, json_response=True):
        time.sleep(DELAY)
        value = self.page.evaluate("""async ({path, data, jsonResponse}) => {
            const response = await fetch(location.pathname.replace(/\\/$/, '') + '/' + path, {
                method:'POST', credentials:'same-origin',
                headers: {'X-Requested-With':'XMLHttpRequest',
                          'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'},
                body:new URLSearchParams(data)
            });
            const body = await response.text();
            if (!response.ok) throw new Error('HTTP ' + response.status + ' ' + body.slice(0,120));
            if (!jsonResponse) return body;
            try {return JSON.parse(body)}
            catch {throw new Error('Non-JSON response ' + body.slice(0,120))}
        }""", {"path": path, "data": data, "jsonResponse": json_response})
        if json_response and (not isinstance(value, dict) or not value.get("success") or
                              not isinstance(value.get("panels"), list)):
            raise RuntimeError(path + ": invalid response " + str(value)[:140])
        return value
    def close(self):
        self.browser.close()
        self.p.stop()

def panel(value, name):
    return next((p.get("html", "") for p in value.get("panels", []) if p.get("id") == name), "")

def in_date_window(date_text: str, days: int) -> bool:
    if not days or not date_text:
        return True
    try:
        day = datetime.strptime(date_text.strip(), "%A, %B %d, %Y").date()
    except ValueError:
        # Unrecognised date format: do not silently drop a menu.
        return True
    today = datetime.now(ZoneInfo("Europe/London")).date()
    return today <= day < today + timedelta(days=days)

def collect(client, include_labels=False, max_labels=150, max_menus=350, days=0):
    locations = units(client.landing())
    if not locations:
        raise RuntimeError("No venues found; Reading may use a different layout than documented CBORD instances")
    report = {"source": BASE, "capturedAtUTC": datetime.now(timezone.utc).isoformat(),
              "transport": client.name, "includesLabels": include_labels,
              "note": "Not authoritative allergen guidance: confirm against Reading's official service",
              "venues": [], "errors": []}
    menu_count = item_count = label_count = label_attempts = 0
    for loc in locations:
        print("Venue:", loc["name"], flush=True)
        venue = {"id": loc["id"], "name": loc["name"], "menus": []}
        report["venues"].append(venue)
        try:
            response = client.post("Unit/SelectUnitFromUnitsList", {"unitOid": loc["id"]})
            choices = [m for m in menus(panel(response, "menuPanel")) if in_date_window(m["dateText"], days)]
            if not choices and not panel(response, "menuPanel"):
                choices = [{"id": None, "name": "Current", "dateText": ""}]
            for choice in choices:
                if menu_count >= max_menus:
                    report["errors"].append("Maximum menu limit reached")
                    break
                try:
                    if choice["id"]:
                        response2 = client.post("Menu/SelectMenu", {"menuOid": choice["id"]})
                        html = panel(response2, "itemPanel")
                    else:
                        html = panel(response, "itemPanel")
                    cats = dishes(html)
                    menu_count += 1
                    item_count += sum(len(x["items"]) for x in cats)
                    venue["menus"].append({**choice, "categories": cats})
                    if include_labels:
                        for group in cats:
                            for item in group["items"]:
                                if label_attempts >= max_labels:
                                    break
                                label_attempts += 1
                                try:
                                    detail = client.post("NutritionDetail/ShowItemNutritionLabel",
                                                         {"detailOid": item["id"]}, json_response=False)
                                    item["label"] = label(detail)
                                    label_count += 1
                                except Exception as exc:
                                    item["labelError"] = str(exc)[:160]
                except Exception as exc:
                    report["errors"].append(loc["name"] + " / " + choice["name"] + ": " + str(exc))
        except Exception as exc:
            report["errors"].append(loc["name"] + ": " + str(exc))
        if menu_count >= max_menus:
            break
    report["stats"] = {"venuesFound": len(locations), "menus": menu_count,
                       "items": item_count, "labels": label_count,
                       "labelAttempts": label_attempts, "errors": len(report["errors"])}
    if not item_count:
        raise RuntimeError("No dishes retrieved; leaving previous feed unchanged. " + "; ".join(report["errors"][:3]))
    report["status"] = "partial" if report["errors"] else "success"
    return report

def save(report, folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    headings = ["capturedAtUTC", "venue", "date", "meal", "category", "dish",
                "serving", "reportedIcons", "ingredients", "contains", "fullNutritionLabel"]
    rows = []
    for venue in report["venues"]:
        for meal in venue["menus"]:
            for group in meal["categories"]:
                for dish in group["items"]:
                    info = dish.get("label", {})
                    rows.append({"capturedAtUTC": report["capturedAtUTC"], "venue": venue["name"],
                                 "date": meal["dateText"], "meal": meal["name"],
                                 "category": group["name"], "dish": dish["name"],
                                 "serving": dish["serving"],
                                 "reportedIcons": "; ".join(dish["reportedIcons"]),
                                 "ingredients": info.get("ingredients", ""),
                                 "contains": info.get("contains", ""),
                                 "fullNutritionLabel": info.get("labelText", "")})
    with (folder / "latest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headings)
        writer.writeheader()
        writer.writerows(rows)
    def md(value):
        return str(value or "").replace("|", "\\|").replace("\n", " ").strip()
    lines = ["# University of Reading: public NetNutrition snapshot", "",
             "Captured: " + report["capturedAtUTC"],
             "Status: " + report["status"],
             "Venues: " + str(len(report["venues"])) + "; dishes: " + str(len(rows)),
             "**Not authoritative allergen information.**", "",
             "| Venue | Date | Meal | Category | Dish | Listed icons |",
             "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append("| " + " | ".join(md(row[key]) for key in
                     ["venue", "date", "meal", "category", "dish", "reportedIcons"]) + " |")
    if report["errors"]:
        lines += ["", "## Extraction warnings"] + ["- " + md(x) for x in report["errors"]]
    (folder / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Saved", len(rows), "dishes", flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["auto", "http", "browser"], default="auto")
    parser.add_argument("--output", default="data")
    parser.add_argument("--labels", action="store_true")
    parser.add_argument("--max-labels", type=int, default=150)
    parser.add_argument("--max-menus", type=int, default=350)
    parser.add_argument("--days", type=int, default=3, help="Collect today and next N-1 local dates; 0 for all")
    opts = parser.parse_args()
    errors = []
    for name in (["http", "browser"] if opts.transport == "auto" else [opts.transport]):
        client = None
        try:
            print("Trying", name, BASE, flush=True)
            client = Http() if name == "http" else Browser()
            report = collect(client, opts.labels, opts.max_labels, opts.max_menus, opts.days)
            save(report, Path(opts.output))
            print(json.dumps(report["stats"]))
            return 0
        except Exception as exc:
            msg = name + ": " + type(exc).__name__ + ": " + str(exc)
            print(msg, file=sys.stderr, flush=True)
            errors.append(msg)
        finally:
            if client:
                client.close()
    raise SystemExit("No successful export. Existing data untouched.\n" + "\n".join(errors))

if __name__ == "__main__":
    sys.exit(main())
