#!/usr/bin/env python3
"""
Convert OCR'd markdown tables to CSV without external dependencies.

Why this should align better
----------------------------
- Parses HTML tables directly and applies colspan/rowspan while building rows,
  keeping cells in their intended columns.
- Drops rows/columns that are entirely empty to prevent header drift.

Usage: python3 convert_to_csv.py
Outputs: output/hospital_table_0.csv, output/hospital_table_1.csv, ...
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
import csv
from typing import List, Optional, Tuple

MARKDOWN_FILE = Path("output/markdown/AHA_1966_sample.md")
OUTPUT_DIR = Path("output")


@dataclass
class Cell:
    text: str
    colspan: int = 1
    rowspan: int = 1


class TableParser(HTMLParser):
    """Minimal HTML table parser with colspan/rowspan support (no external deps)."""

    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._in_table = False
        self._in_tr = False
        self._in_cell = False
        self._current_tables_rows: List[List[str]] = []
        self._current_row_cells: List[Cell] = []
        self._pending_spans: List[int] = []
        self._cell_buffer: List[str] = []
        self._current_colspan = 1
        self._current_rowspan = 1

    # --- Helpers --------------------------------------------------------- #
    def _flush_row(self):
        if not self._in_tr:
            return

        row_out: List[str] = []
        col_idx = 0

        # Ensure pending spans list is long enough
        if self._pending_spans and len(self._pending_spans) < len(row_out):
            self._pending_spans += [0] * (len(row_out) - len(self._pending_spans))

        # process spans from previous rows
        while self._pending_spans and col_idx < len(self._pending_spans):
            if self._pending_spans[col_idx] > 0:
                row_out.append("")
                self._pending_spans[col_idx] -= 1
            else:
                row_out.append(None)  # placeholder to be replaced by next cell
            col_idx += 1

        # place current cells
        col_idx = 0
        for cell in self._current_row_cells:
            # advance past filled placeholders
            while col_idx < len(row_out) and row_out[col_idx] is not None:
                col_idx += 1
            # ensure length
            if col_idx >= len(row_out):
                row_out.extend([None] * (col_idx - len(row_out) + 1))

            # set text for colspan positions
            for _ in range(cell.colspan):
                if col_idx >= len(row_out):
                    row_out.append(cell.text)
                else:
                    row_out[col_idx] = cell.text
                # handle rowspan bookkeeping
                if cell.rowspan > 1:
                    if col_idx >= len(self._pending_spans):
                        self._pending_spans.extend([0] * (col_idx - len(self._pending_spans) + 1))
                    self._pending_spans[col_idx] = cell.rowspan - 1
                col_idx += 1

        # replace remaining None with ""
        row_out = [c if c is not None else "" for c in row_out]

        if row_out:
            self._current_tables_rows.append(row_out)

        self._current_row_cells = []
        self._in_tr = False

    def _finish_table(self):
        if self._current_tables_rows:
            self.tables.append(self._current_tables_rows)
        self._current_tables_rows = []
        self._pending_spans = []

    # --- HTMLParser overrides ------------------------------------------- #
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_tr = True
            self._current_row_cells = []
        elif tag in ("td", "th") and self._in_tr:
            self._in_cell = True
            self._cell_buffer = []
            self._current_colspan = int(attrs_dict.get("colspan", "1") or "1")
            self._current_rowspan = int(attrs_dict.get("rowspan", "1") or "1")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            text = " ".join(self._cell_buffer).strip()
            self._current_row_cells.append(Cell(text, self._current_colspan, self._current_rowspan))
            self._cell_buffer = []
            self._in_cell = False
        elif tag == "tr" and self._in_tr:
            self._flush_row()
        elif tag == "table" and self._in_table:
            self._finish_table()
            self._in_table = False

    def handle_data(self, data):
        if self._in_cell:
            self._cell_buffer.append(data)


def drop_empty(table: List[List[str]]) -> List[List[str]]:
    """Remove all-empty rows and columns."""
    if not table:
        return table

    # Drop empty rows
    table = [row for row in table if any(cell.strip() for cell in row)]
    if not table:
        return table

    # Transpose-like check for empty columns
    col_count = max(len(row) for row in table)
    non_empty_cols = []
    for col_idx in range(col_count):
        if any((row[col_idx].strip() if col_idx < len(row) else "").strip() for row in table):
            non_empty_cols.append(col_idx)

    cleaned = []
    for row in table:
        cleaned.append([row[c] if c < len(row) else "" for c in non_empty_cols])
    return cleaned


def normalize_header(name: str) -> str:
    """Fix common OCR/header issues and align to a consistent schema."""
    name = name.strip()
    replacements = {
        "Classification Codes | Control": "Classification Control",
        "Classification Codes | Service": "Classification Service",
        "Classification Codes | Control Service Stay": "Classification Control Service Stay",
        "Classification Codes | Central Service Stay": "Classification Control Service Stay",
        "Classification Codes": "Classification Codes",
        "Inpatient Data | Stay": "Stay",
        "Inpatient Data | Beds": "Beds",
        "Inpatient Data | Admissions": "Admissions",
        "Inpatient Data | Beds Admissions Census": "Beds Admissions Census",
        "Inpatient Data | Beds Admissions Census Bassinets Births Newborn Census": "Beds Admissions Census Bassinets Births Newborn Census",
        "Newborn Data | Consus": "Newborn Census",
        "Newborn Data | Newborn Consus": "Newborn Census",
        "Newborn Data | Basinats Births Newborn Census": "Bassinets Births Newborn Census",
        "Newborn Data | Bassins": "Bassinets",
        "Newborn Data | Admissions": "Newborn Admissions",
        "Expense (thousands of dollars) | Births": "Expense Births",
        "Expense (thousands of dollars) | Newborn Consus": "Expense Newborn Census",
        "Expense (thousands of dollars) | Census": "Expense Census",
        "Expense (thousands of dollars) | Total Payroll Personnel": "Expense Total Payroll Personnel",
        "Expense (thousands of dollars)": "Expense",
        "Hospital, Address, Telephone, Administrator, Approval and Facility Codes": "Hospital Detail",
        "Total": "Expense Total",
        "Payroll": "Expense Payroll",
        "Newborn Data | Total Payroll Personnel": "Newborn Total Payroll Personnel",
        "col_11": "Misc",
        "Personnel": "Personnel",
        "Bassinets": "Bassinets",
        "Births": "Births",
        "Newborn Census": "Newborn Census",
    }
    return replacements.get(name, name or "col")


def build_headers(rows: List[List[str]]) -> Tuple[List[str], List[List[str]]]:
    """
    Derive a single header row from the first one or two rows, then return (headers, data_rows).
    """
    if not rows:
        return [], []

    first = rows[0]
    second = rows[1] if len(rows) > 1 else []

    headers: List[str] = []
    max_len = max(len(first), len(second))
    for i in range(max_len):
        top = first[i].strip() if i < len(first) else ""
        bottom = second[i].strip() if i < len(second) else ""
        if bottom:
            name = f"{top} | {bottom}" if top else bottom
        else:
            name = top
        name = name or f"col_{i}"
        headers.append(normalize_header(name))

    # Remove duplicate empty header rows from data
    data_start = 2 if len(second) else 1
    data_rows = rows[data_start:]
    return headers, data_rows


def drop_section_rows(data_rows: List[List[str]]) -> List[List[str]]:
    """
    Remove rows that are purely section headings (first cell filled, others empty).
    """
    cleaned = []
    for row in data_rows:
        if len(row) == 0:
            continue
        rest_empty = all(not cell.strip() for cell in row[1:])
        if rest_empty:
            continue
        cleaned.append(row)
    return cleaned


def dedupe_headers(headers: List[str]) -> List[str]:
    """Ensure headers are unique by appending numeric suffixes where needed."""
    seen = {}
    unique = []
    for h in headers:
        if h not in seen:
            seen[h] = 1
            unique.append(h)
        else:
            seen[h] += 1
            unique.append(f"{h}_{seen[h]}")
    return unique


def rows_to_dicts(headers: List[str], rows: List[List[str]]) -> List[dict]:
    out = []
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        out.append({h: padded[i].strip() for i, h in enumerate(headers)})
    return out


def write_csv(table: List[List[str]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(table)


def main():
    if not MARKDOWN_FILE.exists():
        raise FileNotFoundError(f"Markdown file not found: {MARKDOWN_FILE}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    html_text = MARKDOWN_FILE.read_text(encoding="utf-8")

    parser = TableParser()
    parser.feed(html_text)

    if not parser.tables:
        raise RuntimeError("No tables found in markdown file.")

    merged_records: List[dict] = []
    merged_headers: List[str] = []

    for idx, raw_table in enumerate(parser.tables):
        cleaned = drop_empty(raw_table)
        headers, data_rows = build_headers(cleaned)
        headers = dedupe_headers(headers)
        data_rows = drop_section_rows(data_rows)

        # Save per-table CSV
        out_path = OUTPUT_DIR / f"hospital_table_{idx}.csv"
        write_csv([headers] + data_rows, out_path)
        print(f"✓ Saved table {idx} -> {out_path} | rows={len(data_rows)}, cols={len(headers)}")

        # Prepare for merge
        # Expand merged header set preserving order of first appearance
        for h in headers:
            if h not in merged_headers:
                merged_headers.append(h)

        merged_records.extend(rows_to_dicts(headers, data_rows))

    if merged_records:
        merged_path = OUTPUT_DIR / "hospital_data_merged.csv"
        with merged_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=merged_headers)
            writer.writeheader()
            writer.writerows(merged_records)
        print(f"✓ Merged CSV -> {merged_path} | rows={len(merged_records)}, cols={len(merged_headers)}")


if __name__ == "__main__":
    main()
