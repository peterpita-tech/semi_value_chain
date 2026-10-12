"""
build_web.py — Export the coverage database as JSON data files for the web viewer.

Usage:
    python scripts/build_web.py

Writes to web/data/:
    index.json        — one row per ticker (metadata, valuation, wikilinks by section)
    r/sNN.json        — full report markdown, one file per sector (loaded on demand)
    themes.json       — theme pages (markdown) grouped as in themes/README.md
    graph.json        — copy of network/graph_data.json
"""

import glob
import json
import os
import re

from utils import PROJECT_ROOT, REPORTS_DIR

WEB_DATA = os.path.join(PROJECT_ROOT, "web", "data")
THEMES_DIR = os.path.join(PROJECT_ROOT, "themes")
GRAPH_FILE = os.path.join(PROJECT_ROOT, "network", "graph_data.json")

WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
# Section name -> bit in the per-link mask
SECTION_BITS = {"業務簡介": 1, "供應鏈位置": 2, "主要客戶及供應商": 4}


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_report(text):
    row = {}
    m = re.search(r"\*\*板塊:\*\*\s*(.+)", text)
    row["sec"] = m.group(1).strip() if m else ""
    m = re.search(r"\*\*產業:\*\*\s*(.+)", text)
    row["ind"] = m.group(1).strip() if m else ""
    m = re.search(r"\*\*市值:\*\*\s*([\d,\.]+)", text)
    row["mc"] = num(m.group(1)) if m else None

    m = re.search(r"股價 \$([\d,\.]+) as of (\d{4}-\d{2}-\d{2})", text)
    if m:
        row["px"] = num(m.group(1))
        row["asof"] = m.group(2)
    m = re.search(r"### 估值指標.*?\n\|.*?\n\|[-| ]+\n\|(.+?)\|\s*\n", text, re.S)
    if m:
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) >= 5:
            row["pe"], _, _, row["pb"], _ = (num(c) for c in cells[:5])
    m = re.search(r"### 年度關鍵財務數據.*?\| Gross Margin \(%\)\s*\|\s*([-\d\.]+)", text, re.S)
    if m:
        row["gm"] = num(m.group(1))
    m = re.search(r"### 年度關鍵財務數據.*?\| Revenue\s*\|\s*([-\d\.]+)", text, re.S)
    if m:
        row["rev"] = num(m.group(1))

    # Plain-text lede from the business description
    m = re.search(r"## 業務簡介\n(?:\*\*.*\n)*\s*\n(.+)", text)
    if m:
        lede = WIKILINK.sub(r"\1", m.group(1)).replace("**", "").strip()
        row["d"] = lede[:90]

    # Wikilinks per section, as [entity, mask]
    masks = {}
    for part in re.split(r"\n(?=## )", text):
        head = part.split("\n", 1)[0].lstrip("# ").strip()
        bit = next((b for k, b in SECTION_BITS.items() if head.startswith(k)), 0)
        if not bit:
            continue
        for e in WIKILINK.findall(part):
            e = e.strip()
            masks[e] = masks.get(e, 0) | bit
    row["w"] = [[e, b] for e, b in masks.items()]
    return row


def build_reports():
    sectors = sorted(os.listdir(REPORTS_DIR))
    rows, sector_list = [], []
    os.makedirs(os.path.join(WEB_DATA, "r"), exist_ok=True)
    for i, sector in enumerate(sectors):
        key = f"s{i:02d}"
        bundle = {}
        for fp in sorted(glob.glob(os.path.join(REPORTS_DIR, sector, "*.md"))):
            fn = os.path.basename(fp)
            m = re.match(r"^(\d{4})_(.+)\.md$", fn)
            if m:
                t, name = m.groups()
            else:
                # A few files are named "Name_Ticker.md"
                m = re.match(r"^(.+)_(\d{4})\.md$", fn)
                if not m:
                    continue
                name, t = m.groups()
            with open(fp, encoding="utf-8") as f:
                text = f.read()
            bundle[t] = text
            row = {"t": t, "n": name, "f": key}
            row.update(parse_report(text))
            rows.append(row)
        with open(os.path.join(WEB_DATA, "r", f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
        sector_list.append({"k": key, "name": sector, "count": len(bundle)})
    return rows, sector_list


def build_themes():
    groups, cur = [], None
    with open(os.path.join(THEMES_DIR, "README.md"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                cur = {"group": line[3:].strip(), "items": []}
                groups.append(cur)
            m = re.match(r"- \[(.+?)\]\((.+?\.md)\) — (\d+)", line)
            if m and cur is not None:
                name, fn, count = m.groups()
                with open(os.path.join(THEMES_DIR, fn), encoding="utf-8") as tf:
                    md = tf.read()
                cur["items"].append({"name": name, "count": int(count), "md": md})
    return groups


def main():
    rows, sectors = build_reports()
    asof = max((r.get("asof", "") for r in rows), default="")
    index = {"asof": asof, "sectors": sectors, "rows": rows}
    with open(os.path.join(WEB_DATA, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(WEB_DATA, "themes.json"), "w", encoding="utf-8") as f:
        json.dump(build_themes(), f, ensure_ascii=False, separators=(",", ":"))
    with open(GRAPH_FILE, encoding="utf-8") as f:
        graph = json.load(f)
    with open(os.path.join(WEB_DATA, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Exported {len(rows)} tickers in {len(sectors)} sectors to {WEB_DATA}")


if __name__ == "__main__":
    main()
