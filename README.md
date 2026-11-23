# University of Reading NetNutrition feed

An independent **read-only experimental extractor** for the public University of Reading [CBORD NetNutrition menus](https://netmenu.cbord.co.uk/NetNutrition/UniversityofReading). It retrieves menu names, dishes and any displayed dietary/allergen icon tooltips. Optional nutrition-label parsing is included but is **off by default**.

**Status: live extraction verified (23 November 2026).** The three-day snapshot captured all **17/17 public venues**, **103 menus** and **6,519 dish entries** with **zero collection errors**. Two public dish nutrition labels were also retrieved successfully in a separate [diagnostic run](https://github.com/mattfosse1/reading-netnutrition-feed1/actions/runs/45266714744), demonstrating per-serving nutrition data and ingredients. **Not yet proven:** bulk collection of every label and all future dates.

## Where the menu feed will appear

Latest successfully retrieved menu snapshots:
- [Menu table](data/latest.md)
- [Full JSON](data/latest.json)
- [CSV](data/latest.csv)

The exported fields include venue, meal, displayed date, category, dish name, serving and displayed icons. There are no fabricated sample dishes in the feed. Failed runs do **not** replace an existing successful snapshot.

## Automatic updates

[GitHub Actions → Refresh Reading public dining menus](actions/workflows/refresh-netnutrition.yml) is configured to try **06:17, 12:17 and 18:17 UTC** every day. GitHub's cron jobs can start late.

For a manual run, select **Actions → Refresh Reading public dining menus → Run workflow**. The first run also checks the parser against simulated CBORD responses. The runner then attempts normal HTTP requests and, if necessary, a full Chromium browser.

If collection succeeds but the final commit fails with a GitHub permission error, go to **Settings → Actions → General → Workflow permissions** and allow read/write permissions, if available. The workflow file requests `contents: write`.

## Local run

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m unittest discover -s tests -v
python reader.py --transport auto --output data
```

To request individual public labels as well: `python reader.py --labels --max-labels 150`.

## Important limitations

- Only public pages are requested. No CBORD credentials, privileged APIs or bypasses of access controls.
- Reading's UK public menu endpoints **have been live-validated** for menus and two individual nutritional labels. Large-scale label retrieval and completeness over all published dates have not yet been validated.
- This is not an approved operational allergen source. Always check official Reading/CBORD records before using allergen information for safety decisions.
- Requests are throttled, with a maximum of 160 menus per collection.
- Only enable routine collection where compatible with institutional and CBORD policies.

**Background:** [Publicly documented CBORD NetNutrition extraction patterns](https://github.com/RW290/Duke-Net-Nutrition).
