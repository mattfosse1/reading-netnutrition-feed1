import tempfile
import unittest
from pathlib import Path
from reader import units, menus, dishes, label, collect, save

LANDING = '<a onclick="unitsSelectUnit(12)">Park Eat</a><a onclick="unitsSelectUnit(13)">Wantage Hall</a>'
MENUS = '<div class="card-title">Monday 23 November</div><a onclick="menuListSelectMenu(40)">Lunch</a>'
ITEMS = '''<table>
<tr class="cbo_nn_itemGroupRow" onclick="toggleCourseItems(this, 51)"><td><div>Hot mains</div></td></tr>
<tr data-categoryid="51"><td><a onclick="getItemNutritionLabelOnClick(event, 223)"><img title="Contains Milk"/>Roasted Vegetable Lasagne</a></td><td></td><td>200g</td></tr>
</table>'''
LABEL = '<div id="nutritionLabel"><div class="cbo_nn_LabelIngredients">pasta, tomato</div><div class="cbo_nn_LabelAllergens">Contains milk</div>345 kcal</div>'

class MockClient:
    name = "test"
    def landing(self):
        return LANDING
    def post(self, path, data, json_response=True):
        if not json_response:
            return LABEL
        if path.startswith("Unit"):
            html = ITEMS if data["unitOid"] == "13" else MENUS
            return {"success": True, "panels": [{"id": "itemPanel" if data["unitOid"] == "13" else "menuPanel", "html": html}]}
        if path.startswith("Menu"):
            return {"success": True, "panels": [{"id": "itemPanel", "html": ITEMS}]}
        raise AssertionError(path)

class ReaderTests(unittest.TestCase):
    def test_units(self):
        self.assertEqual(len(units(LANDING)), 2)
    def test_menus(self):
        self.assertEqual(menus(MENUS)[0]["name"], "Lunch")
    def test_items(self):
        item = dishes(ITEMS)[0]["items"][0]
        self.assertEqual(item["name"], "Roasted Vegetable Lasagne")
        self.assertEqual(item["reportedIcons"], ["Contains Milk"])
    def test_label(self):
        self.assertIn("pasta", label(LABEL)["ingredients"])
    def test_collection_and_output(self):
        report = collect(MockClient(), include_labels=True)
        self.assertEqual(report["stats"]["items"], 2)
        self.assertEqual(report["stats"]["labels"], 2)
        with tempfile.TemporaryDirectory() as d:
            save(report, Path(d))
            for name in ["latest.json", "latest.csv", "latest.md"]:
                self.assertTrue((Path(d) / name).is_file())
    def test_no_blank_success(self):
        class Empty(MockClient):
            def landing(self):
                return "<p>No units</p>"
        with self.assertRaises(RuntimeError):
            collect(Empty())

if __name__ == "__main__":
    unittest.main()
