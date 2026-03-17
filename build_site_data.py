"""
Build docs/data.json by merging occupations.csv with scores.json.

Output format matches what the frontend expects:
  slug, title, category, anzsco_code, jobs, pay, growth, skill_level,
  shortage_status, url, exposure, exposure_rationale

Usage:
    uv run python build_docs_data.py
"""

import json
import sys
from pathlib import Path

import pandas as pd


def main():
    # Load occupations
    csv_path = Path("occupations.csv")
    if not csv_path.exists():
        print("ERROR: occupations.csv not found. Run parse_jsa.py first.")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} occupations from occupations.csv")

    # Load scores (optional — occupations without scores get null)
    scores_path = Path("scores.json")
    scores = {}
    if scores_path.exists():
        with open(scores_path, "r", encoding="utf-8") as f:
            scores = json.load(f)
        print(f"Loaded {len(scores)} scores from scores.json")
    else:
        print("WARNING: scores.json not found. All exposures will be null.")

    # Build output data
    output = []
    scored_count = 0

    for _, row in df.iterrows():
        slug = str(row.get("slug", ""))
        score_data = scores.get(slug, {})

        entry = {
            "slug": slug,
            "title": str(row.get("title", "")),
            "category": str(row.get("category", "")),
            "anzsco_code": str(row.get("anzsco_code", "")),
            "jobs": int(row["jobs"]) if pd.notna(row.get("jobs")) else None,
            "pay": int(row["pay_aud"]) if pd.notna(row.get("pay_aud")) else None,
            "growth": float(row["growth_pct"]) if pd.notna(row.get("growth_pct")) else None,
            "skill_level": str(row["skill_level"]) if pd.notna(row.get("skill_level")) else None,
            "shortage_status": str(row["shortage_status"]) if pd.notna(row.get("shortage_status")) else "Not assessed",
            "url": str(row.get("url", "")),
            "exposure": score_data.get("exposure"),
            "exposure_rationale": score_data.get("rationale"),
        }

        if entry["exposure"] is not None:
            scored_count += 1

        output.append(entry)

    # Sort by jobs descending (nulls last)
    output.sort(key=lambda x: x["jobs"] if x["jobs"] is not None else 0, reverse=True)

    # Write output
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output_path = docs_dir / "data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_jobs = sum(e["jobs"] for e in output if e["jobs"])
    print(f"\nBuilt docs/data.json:")
    print(f"  Occupations: {len(output)}")
    print(f"  With scores: {scored_count}")
    print(f"  Without scores: {len(output) - scored_count}")
    print(f"  Total jobs: {total_jobs:,}")

    # Category breakdown
    cats = {}
    for e in output:
        cat = e["category"]
        if cat not in cats:
            cats[cat] = {"count": 0, "jobs": 0}
        cats[cat]["count"] += 1
        cats[cat]["jobs"] += e["jobs"] or 0

    print(f"\nBy category:")
    for cat in sorted(cats.keys()):
        info = cats[cat]
        print(f"  {cat}: {info['count']} occupations, {info['jobs']:,} jobs")


if __name__ == "__main__":
    main()
