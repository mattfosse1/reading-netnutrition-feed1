import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from labels import valid_cached, feed_entries, coverage, collect_batch, load_cache, save_cache

NOW = datetime.now(timezone.utc).isoformat()
SNAPSHOT = {
    "capturedAtUTC": NOW,
    "stats": {"items": 3},
    "venues": [
        {"id": "11", "name": "Square", "menus": [
            {"id": "40", "name": "Lunch", "dateText": "Monday, November 23, 2026",
             "categories": [{"name": "Mains", "items": [
                 {"id": "123", "name": "Pizza"}, {"id": "124", "name": "Soup"}]}]},
            {"id": "41", "name": "Dinner", "dateText": "Tuesday, November 24, 2026",
             "categories": [{"name": "Mains", "items": [{"id": "125", "name": "Pizza"}]}]}]}
    ]
}

class MockClient:
    def __init__(self):
        self.calls = []
    def post(self, path, data, json_response=True):
        self.calls.append((path, data))
        if path == "NutritionDetail/ShowItemNutritionLabel":
            return '<div id="nutritionLabel">Pizza Nutrition 280 kcal Ingredients: flour</div>'
        return {"success": True, "panels": []}

class LabelTests(unittest.TestCase):
    def test_cache_freshness(self):
        self.assertFalse(valid_cached(None))
        self.assertFalse(valid_cached({"labelText": "Nutrition"}))
        self.assertTrue(valid_cached({"labelText": "Nutrition", "fetchedAtUTC": NOW}))
        stale = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        self.assertFalse(valid_cached({"labelText": "Nutrition", "fetchedAtUTC": stale}))
    def test_order(self):
        self.assertEqual([x[-1] for x in feed_entries(SNAPSHOT)], ["123", "124", "125"])
    def test_batched_cache(self):
        client = MockClient()
        cache = {}
        result = collect_batch(client, SNAPSHOT, cache, limit=2)
        self.assertEqual(result["newLabels"], 2)
        self.assertEqual(coverage(SNAPSHOT, cache)["withRecentLabels"], 2)
        self.assertEqual(len([c for c in client.calls if c[0].startswith("NutritionDetail")]), 2)
        second = collect_batch(client, SNAPSHOT, cache, limit=2)
        self.assertEqual(second["newLabels"], 1)
        self.assertEqual(coverage(SNAPSHOT, cache)["withRecentLabels"], 3)
        with tempfile.TemporaryDirectory() as tmp:
            save_cache(Path(tmp), SNAPSHOT, cache, second)
            self.assertTrue((Path(tmp) / "venue-11.json").exists())
            self.assertEqual(coverage(SNAPSHOT, load_cache(Path(tmp)))["withRecentLabels"], 3)
            self.assertEqual(json.loads((Path(tmp) / "status.json").read_text())["labelCoveragePercent"], 100.0)
    def test_do_not_reuse_name(self):
        # The two Pizzas have different detail IDs and are collected independently.
        client = MockClient()
        cache = {}
        collect_batch(client, SNAPSHOT, cache, limit=3)
        self.assertIn("123", cache["11"])
        self.assertIn("125", cache["11"])

if __name__ == "__main__":
    unittest.main()
