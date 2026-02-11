# Hospital Directories OCR → CSV

A tiny, zero-dependency helper to turn the OCR’d Markdown tables from the hospital directory PDFs into usable CSVs.

## Quick start
```bash
python3 convert_to_csv.py
```

That’s it. Requires only Python 3.9+; no external packages.

## What it does
- Parses the `<table>` blocks in `output/markdown/AHA_1966_sample.md` (or any similar file).
- Handles `colspan`/`rowspan`, cleans headers, drops empty section rows.
- Writes per-table CSVs (`output/hospital_table_0..4.csv`) and a merged dataset (`output/hospital_data_merged.csv`).

## Using your own OCR output
1) Place your Markdown with `<table>` tags in `output/markdown/` (or anywhere).
2) If you use a different path, edit `MARKDOWN_FILE` and optionally `OUTPUT_DIR` at the top of `convert_to_csv.py`.
3) Run `python3 convert_to_csv.py`.

## Repo layout
- `convert_to_csv.py` — stdlib-only converter script.
- `output/markdown/AHA_1966_sample.md` — sample OCR’d tables for a test run.
- `output/` — generated CSVs are written here.

## Troubleshooting
- If you see “Markdown file not found”, adjust `MARKDOWN_FILE` in `convert_to_csv.py`.
- Script is pure stdlib; no pip installs needed.

## License
Choose your preferred license before publishing. (MIT is a common default.)
