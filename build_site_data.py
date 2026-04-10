"""
Build docs/data.json by merging occupations.csv with scores.json.

Includes comparison fields from the most recent archived run in runs/.
Output format: { meta: {...}, occupations: [...] }

Usage:
    uv run python build_site_data.py
"""

import json
import sys
from pathlib import Path

import pandas as pd


def load_json(path: Path) -> dict:
    """Load a JSON file, return empty dict if missing."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_previous_scores(runs_dir: Path) -> tuple[dict, dict | None]:
    """Find the most recent archived scores in runs/.

    Returns (previous_scores_dict, previous_meta_or_None).
    """
    if not runs_dir.exists():
        return {}, None
    archives = sorted(runs_dir.glob("*_scores.json"), reverse=True)
    if not archives:
        return {}, None
    prev = load_json(archives[0])
    meta = prev.get("_meta")
    print(f"Loaded previous scores from {archives[0].name}")
    return prev, meta


def check_comparison_safety(current_meta: dict | None, previous_meta: dict | None) -> tuple[bool, str]:
    """Check if comparison between two runs is methodologically safe.

    Returns (is_safe, reason_if_unsafe).
    """
    if not current_meta or not previous_meta:
        return False, "Missing run metadata"

    # Check prompt version
    if current_meta.get("prompt_version") != previous_meta.get("prompt_version"):
        return False, "Scoring prompt changed between runs"

    # Check methodology version
    if current_meta.get("methodology_version") != previous_meta.get("methodology_version"):
        return False, "Scoring methodology changed between runs"

    # Check model family (allow minor version differences, check major family)
    curr_model = current_meta.get("model", "")
    prev_model = previous_meta.get("model", "")
    # Extract model family: "gemini-2.5-flash" → "gemini-2.5"
    curr_family = "-".join(curr_model.split("-")[:2]) if curr_model else ""
    prev_family = "-".join(prev_model.split("-")[:2]) if prev_model else ""
    if curr_family != prev_family:
        return False, f"Model changed from {prev_model} to {curr_model}"

    return True, ""


def main():
    # Load occupations
    csv_path = Path("occupations.csv")
    if not csv_path.exists():
        print("ERROR: occupations.csv not found. Run parse_jsa.py first.")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} occupations from occupations.csv")

    # Load current scores (optional — occupations without scores get null)
    scores_path = Path("scores.json")
    scores = {}
    current_meta = None
    if scores_path.exists():
        scores = load_json(scores_path)
        current_meta = scores.get("_meta")
        occ_count = sum(1 for k in scores if k != "_meta")
        print(f"Loaded {occ_count} scores from scores.json")
    else:
        print("WARNING: scores.json not found. All exposures will be null.")

    # Load previous scores for comparison
    runs_dir = Path("runs")
    prev_scores, prev_meta = find_previous_scores(runs_dir)

    comparison_safe, comparison_note = check_comparison_safety(current_meta, prev_meta)
    has_previous = bool(prev_meta)

    if has_previous:
        prev_occ_count = sum(1 for k in prev_scores if k != "_meta")
        print(f"Previous run: {prev_occ_count} scores, safe={comparison_safe}")
        if not comparison_safe:
            print(f"  Comparison unsafe: {comparison_note}")

    # Build output data
    occupations = []
    scored_count = 0
    comparison_count = 0

    for _, row in df.iterrows():
        slug = str(row.get("slug", ""))
        score_data = scores.get(slug, {})
        prev_score_data = prev_scores.get(slug, {})

        current_exposure = score_data.get("exposure")
        previous_exposure = prev_score_data.get("exposure") if has_previous else None

        # Compute delta
        exposure_delta = None
        if current_exposure is not None and previous_exposure is not None:
            exposure_delta = current_exposure - previous_exposure
            comparison_count += 1

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
            "exposure": current_exposure,
            "exposure_rationale": score_data.get("rationale"),
            "previous_exposure": previous_exposure,
            "exposure_delta": exposure_delta,
        }

        if entry["exposure"] is not None:
            scored_count += 1

        occupations.append(entry)

    # Sort by jobs descending (nulls last)
    occupations.sort(key=lambda x: x["jobs"] if x["jobs"] is not None else 0, reverse=True)

    # Build meta
    meta = {
        "run_date": current_meta.get("run_date") if current_meta else None,
        "model": current_meta.get("model") if current_meta else None,
        "previous_run_date": prev_meta.get("run_date") if prev_meta else None,
        "comparison_available": has_previous and comparison_count > 0,
        "comparison_safe": comparison_safe if has_previous else False,
        "comparison_note": comparison_note if has_previous and not comparison_safe else "",
        "comparison_count": comparison_count,
    }

    # Write output — new format: { meta, occupations }
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output = {"meta": meta, "occupations": occupations}
    output_path = docs_dir / "data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    total_jobs = sum(e["jobs"] for e in occupations if e["jobs"])
    print(f"\nBuilt docs/data.json:")
    print(f"  Occupations: {len(occupations)}")
    print(f"  With scores: {scored_count}")
    print(f"  Without scores: {len(occupations) - scored_count}")
    print(f"  With comparison: {comparison_count}")
    print(f"  Total jobs: {total_jobs:,}")

    if meta["comparison_available"]:
        rising = sum(1 for o in occupations if o["exposure_delta"] is not None and o["exposure_delta"] > 0)
        falling = sum(1 for o in occupations if o["exposure_delta"] is not None and o["exposure_delta"] < 0)
        unchanged = sum(1 for o in occupations if o["exposure_delta"] is not None and o["exposure_delta"] == 0)
        print(f"\n  Comparison: {rising} rising, {falling} falling, {unchanged} unchanged")

    # Category breakdown
    cats = {}
    for e in occupations:
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
