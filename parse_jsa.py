"""
Parse Jobs and Skills Australia (JSA) occupation data Excel file.

Auto-downloads the latest JSA occupation profiles Excel file and the
Occupation Shortage Data file if not cached. Extracts ANZSCO 4-digit
occupation data from multiple sheets and outputs occupations.csv and
occupations.json.

Usage:
    uv run python parse_jsa.py
"""

import json
import re
import sys
from pathlib import Path

import httpx
import pandas as pd

# ── Auto-download JSA data ──────────────────────────────────────────────

JSA_URL = "https://www.jobsandskills.gov.au/sites/default/files/2026-01/occupation_profiles_data_-_november_2025.xlsx"
LOCAL_PATH = Path("data/occupation_profiles_nov2025.xlsx")

OSD_URL = "https://www.jobsandskills.gov.au/sites/default/files/2025-10/2025%20OSD%20downloadable%20Tables%20and%20Figures.xlsx"
OSD_PATH = Path("data/osd_2025.xlsx")


def download_file(url: str, path: Path):
    """Download a file if not already cached."""
    path.parent.mkdir(exist_ok=True)
    if path.exists():
        print(f"Using cached file: {path}")
        return
    print(f"Downloading {path.name} from {url}...")
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        r = client.get(url)
        r.raise_for_status()
        path.write_bytes(r.content)
    print(f"Saved to {path} ({path.stat().st_size / 1024:.0f} KB)")


# ── Constants ───────────────────────────────────────────────────────────

MAJOR_GROUPS = {
    1: "Managers",
    2: "Professionals",
    3: "Technicians & Trades",
    4: "Community & Personal Service",
    5: "Clerical & Administrative",
    6: "Sales Workers",
    7: "Machinery Operators & Drivers",
    8: "Labourers",
}

SKILL_LEVEL_DESC = {
    1: "Bachelor's degree or higher",
    2: "Diploma or higher",
    3: "Certificate III/IV",
    4: "Certificate I/II or secondary",
    5: "Secondary education",
}


# ── Helpers ─────────────────────────────────────────────────────────────

def read_sheet(excel_file: Path, sheet_name: str, header_row: int = 6) -> pd.DataFrame:
    """Read a specific sheet with a given header row."""
    return pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row)


def normalize_code(val) -> str | None:
    """Normalize an ANZSCO code to a 4-digit string, or None."""
    if pd.isna(val):
        return None
    try:
        code = str(int(float(val)))
    except (ValueError, TypeError):
        code = str(val).strip()
    return code if re.match(r"^\d{4}$", code) else None


def make_slug(title: str) -> str:
    """Convert occupation title to URL-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def parse_numeric(val) -> float | None:
    """Parse a numeric value, handling commas and special characters."""
    if pd.isna(val):
        return None
    val_str = str(val).strip().replace(",", "").replace("$", "").replace("%", "")
    val_str = re.sub(r"[^\d.\-]", "", val_str)
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return None


def infer_skill_level(edu_row: dict) -> int | None:
    """Infer ANZSCO skill level from Table_8 education attainment percentages.

    Logic: find the dominant education band.
    - If postgrad+bachelor >= 50% → Skill Level 1 (Bachelor's+)
    - If diploma share is dominant non-degree → Skill Level 2 (Diploma+)
    - If cert III/IV is dominant → Skill Level 3 (Cert III/IV)
    - If cert I/II or secondary → Skill Level 4/5
    """
    postgrad = edu_row.get("postgrad", 0) or 0
    bachelor = edu_row.get("bachelor", 0) or 0
    diploma = edu_row.get("diploma", 0) or 0
    cert3 = edu_row.get("cert3", 0) or 0
    secondary = edu_row.get("secondary", 0) or 0

    degree_pct = postgrad + bachelor
    if degree_pct >= 45:
        return 1
    if diploma >= 20 or (diploma + degree_pct) >= 50:
        return 2
    if cert3 >= 25:
        return 3
    if secondary >= 30:
        return 5
    # Default: moderate
    return 4


# ── Main ────────────────────────────────────────────────────────────────

def main():
    # Download data files
    download_file(JSA_URL, LOCAL_PATH)
    download_file(OSD_URL, OSD_PATH)

    print(f"\nReading: {LOCAL_PATH.name}")

    # ── Table_1: Overview (employment, earnings, growth) ────────────────
    df1 = read_sheet(LOCAL_PATH, "Table_1")
    print(f"Table_1 columns: {list(df1.columns)}")
    print(f"Table_1 shape: {df1.shape}")

    # ── Table_2: Descriptions ───────────────────────────────────────────
    df2 = read_sheet(LOCAL_PATH, "Table_2")
    desc_map = {}
    for _, row in df2.iterrows():
        code = normalize_code(row.get("ANZSCO Code"))
        desc = row.get("Description")
        if code and not pd.isna(desc):
            desc_map[code] = str(desc).strip()
    print(f"Loaded {len(desc_map)} descriptions from Table_2")

    # ── Table_8: Education attainment ───────────────────────────────────
    df8 = read_sheet(LOCAL_PATH, "Table_8")
    edu_map = {}
    for _, row in df8.iterrows():
        code = normalize_code(row.iloc[0])
        if not code:
            continue
        # Columns vary but the order is: Code, Occupation, PostGrad%, Bachelor%, Diploma%, CertIII%, Secondary%, ...
        vals = row.iloc[2:].values
        edu_map[code] = {
            "postgrad": parse_numeric(vals[0]) if len(vals) > 0 else 0,
            "bachelor": parse_numeric(vals[1]) if len(vals) > 1 else 0,
            "diploma": parse_numeric(vals[2]) if len(vals) > 2 else 0,
            "cert3": parse_numeric(vals[3]) if len(vals) > 3 else 0,
            "secondary": parse_numeric(vals[4]) if len(vals) > 4 else 0,
        }
    print(f"Loaded {len(edu_map)} education profiles from Table_8")

    # ── OSD: Shortage data from Figure C1 (name-based matching) ─────────
    shortage_name_map = {}  # title (lowered) → shortage driver
    try:
        osd_c1 = pd.read_excel(OSD_PATH, sheet_name="Figure C1", header=6)
        for _, row in osd_c1.iterrows():
            ug = row.get("Unit group")
            sd = row.get("Shortage Driver")
            if pd.notna(ug) and pd.notna(sd):
                shortage_name_map[str(ug).strip().lower()] = str(sd).strip()
        print(f"Loaded {len(shortage_name_map)} shortage entries from OSD Figure C1")
    except Exception as e:
        print(f"WARNING: Could not parse OSD Figure C1: {e}")

    # Build a lookup: normalize Table_1 titles for fuzzy matching to OSD names
    # OSD uses unit group names which may differ slightly from Table_1
    def match_shortage(title: str) -> str:
        """Match an occupation title to OSD shortage status."""
        t = title.strip().lower()
        # Exact match
        if t in shortage_name_map:
            return "Shortage"
        # Check if OSD name is contained in or contains the title
        for osd_name in shortage_name_map:
            if osd_name in t or t in osd_name:
                return "Shortage"
            # Match on key words (at least 2 significant words overlap)
            osd_words = set(osd_name.split()) - {"and", "the", "of", "or", "in", "for", "a"}
            title_words = set(t.split()) - {"and", "the", "of", "or", "in", "for", "a"}
            if len(osd_words & title_words) >= 2 and len(osd_words & title_words) / max(len(osd_words), 1) >= 0.5:
                return "Shortage"
        return "Not assessed"

    # ── Build occupation records from Table_1 ───────────────────────────
    occupations = []
    for _, row in df1.iterrows():
        code = normalize_code(row.get("ANZSCO Code"))
        if not code:
            continue

        title = str(row.get("Occupation", "")).strip()
        if not title or title.lower() == "nan":
            continue

        major = int(code[0])
        category = MAJOR_GROUPS.get(major, "Other")

        # Employment
        jobs = parse_numeric(row.get("Employed"))
        if jobs is not None:
            jobs = int(jobs)

        # Earnings (weekly → annual)
        pay_aud = None
        for col in df1.columns:
            if "weekly" in str(col).lower() and "earn" in str(col).lower():
                pay_aud = parse_numeric(row.get(col))
                if pay_aud is not None:
                    pay_aud = int(pay_aud * 52)
                break

        # Growth (absolute annual change → percentage)
        growth_pct = None
        for col in df1.columns:
            if "growth" in str(col).lower():
                growth_abs = parse_numeric(row.get(col))
                if growth_abs is not None and jobs and jobs > 0:
                    growth_pct = round((growth_abs / jobs) * 100, 1)
                break

        # Description from Table_2
        description = desc_map.get(code)

        # Skill level from Table_8 education data
        edu = edu_map.get(code)
        skill_level = None
        skill_desc = None
        if edu:
            skill_level = infer_skill_level(edu)
            skill_desc = SKILL_LEVEL_DESC.get(skill_level)

        # Shortage status from OSD (name-based matching)
        shortage_status = match_shortage(title)

        slug = make_slug(title)
        url = f"https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles/occupations/{slug}"

        occupations.append({
            "slug": slug,
            "title": title,
            "category": category,
            "anzsco_code": code,
            "jobs": jobs,
            "pay_aud": pay_aud,
            "growth_pct": growth_pct,
            "skill_level": skill_desc,
            "shortage_status": shortage_status,
            "description": description,
            "url": url,
        })

    print(f"\nExtracted {len(occupations)} occupations at ANZSCO 4-digit level")

    if not occupations:
        print("ERROR: No occupations found. Check the Excel file format.")
        sys.exit(1)

    # Stats
    has_pay = sum(1 for o in occupations if o["pay_aud"])
    has_skill = sum(1 for o in occupations if o["skill_level"])
    has_shortage = sum(1 for o in occupations if o["shortage_status"] != "Not assessed")
    has_desc = sum(1 for o in occupations if o["description"])
    has_growth = sum(1 for o in occupations if o["growth_pct"] is not None)

    print(f"\nData completeness:")
    print(f"  Pay:       {has_pay}/{len(occupations)}")
    print(f"  Growth:    {has_growth}/{len(occupations)}")
    print(f"  Skill:     {has_skill}/{len(occupations)}")
    print(f"  Shortage:  {has_shortage}/{len(occupations)}")
    print(f"  Desc:      {has_desc}/{len(occupations)}")

    # Sample
    print("\nSample entries:")
    for occ in occupations[:3]:
        print(f"  {occ['anzsco_code']} - {occ['title']} ({occ['category']})")
        print(f"    Jobs: {occ['jobs']}, Pay: A${occ['pay_aud']}, Growth: {occ['growth_pct']}%")
        print(f"    Skill: {occ['skill_level']}, Shortage: {occ['shortage_status']}")
        if occ["description"]:
            print(f"    Desc: {occ['description'][:80]}...")

    # Category breakdown
    print("\nBy category:")
    cats = {}
    for occ in occupations:
        cats[occ["category"]] = cats.get(occ["category"], 0) + 1
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")

    # Save CSV
    csv_df = pd.DataFrame(occupations)
    csv_df.to_csv("occupations.csv", index=False)
    print(f"\nSaved occupations.csv ({len(occupations)} rows)")

    # Save JSON
    with open("occupations.json", "w", encoding="utf-8") as f:
        json.dump(occupations, f, indent=2, ensure_ascii=False)
    print(f"Saved occupations.json ({len(occupations)} entries)")


if __name__ == "__main__":
    main()
