# University of Reading public NetNutrition feed

An independent **read-only** collector for the [University of Reading's public NetNutrition menus](https://netmenu.cbord.co.uk/NetNutrition/UniversityofReading). Live collection of all 17 locations and individual nutrition labels has been verified.

## Menu snapshots

- [Browse the menu table](data/latest.md)
- [Download structured menu data (JSON)](data/latest.json)
- [Download the menu spreadsheet (CSV)](data/latest.csv)

The regular feed is configured to cover **today plus the next six calendar days** across all 17 public locations, subject to what CBORD has published. It refreshes at **06:17, 12:17 and 18:17 UTC**. The last captured time and extraction errors are recorded inside the JSON.

## Nutrition and ingredient details

Full labels are downloaded incrementally, not all in one burst. The reader preserves labels by the **exact CBORD detail ID and venue**, never matching records using a dish name alone.

- [Live coverage and progress](data/labels/status.json)
- Label records appear in `data/labels/venue-<venue-id>.json` as they are retrieved.
- Batches of up to **350** missing labels run **every two hours** (minute 39 UTC) and can also be started manually using [GitHub Actions](actions/workflows/enrich-netnutrition.yml).
- The labels include the full public nutrition text and, when identified in the markup, extracted ingredients and allergens.
- Cached labels expire after 7 days or when their detail IDs disappear from the menu feed. One day's menu refresh therefore can introduce many new labels.

Check `labelCoveragePercent` and `withIngredientsField` in the status file before interpreting completeness. A missing ingredient field does not mean an ingredient-free dish; consult the full label text. No data is invented to fill missing fields.

## Reliability and safety

- Public, unauthenticated endpoints only; requests are deliberately rate-limited.
- Parsing tests run on every code update; failed collection does not overwrite a successful menu snapshot.
- If CBORD changes its website, check [Actions logs](actions) for the failure.
- Some location menus might have no explicit date; those are included and identified.
- The generated feeds are **not an approved source for operational food-safety decisions**. Verify allergens and recipes with University Dining and the official CBORD system.
- Follow University and CBORD policies before increasing request volumes.

## Local use

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
python reader.py --transport auto --output data --days 7 --max-menus 600
python labels.py --max-labels 350
```

The nutrition collection's source is [labels.py](labels.py); the menu extraction source is [reader.py](reader.py). To inspect a limited sample, see the [successful two-label diagnostic](https://github.com/mattfosse1/reading-netnutrition-feed1/actions/runs/45266714744).
