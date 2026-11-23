# University of Reading NetNutrition feed

An independent **read-only experimental extractor** for the public University of Reading [CBORD NetNutrition menus](https://netmenu.cbord.co.uk/NetNutrition/UniversityofReading). It retrieves menu names, dishes and any displayed dietary/allergen icon tooltips. Optional nutrition-label parsing is included but is **off by default**.

**Status:** Code deployed. Live data extraction from Reading is not yet proven. Until `data/latest.json` exists and contains real dishes, there is no working feed.

## Where the menu feed will appear

After the first successful scheduled or manual run:
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
- Reading's UK site has **not** yet been live-validated. The endpoint and parsing patterns are based on other CBORD installations and may need adjustment.
- This is not an approved operational allergen source. Always check official Reading/CBORD records before using allergen information for safety decisions.
- Requests are throttled, with a maximum of 160 menus per collection.
- Only enable routine collection where compatible with institutional and CBORD policies.

**Background:** [Publicly documented CBORD NetNutrition extraction patterns](https://github.com/RW290/Duke-Net-Nutrition).
