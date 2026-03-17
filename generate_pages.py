"""
Generate markdown pages for each occupation from occupations.json.

Each page provides structured context for the AI exposure scorer,
including inferred job duties based on ANZSCO title and category.

Usage:
    uv run python generate_pages.py
"""

import json
import sys
from pathlib import Path

# Inferred job duties by ANZSCO major category and common title keywords.
# These provide context for the AI scorer to make better judgments.
CATEGORY_DUTIES = {
    "Managers": "plan, organise, control, coordinate and direct the operations of an organisation or department",
    "Professionals": "apply specialist knowledge and analytical skills to solve problems, develop policies, and deliver professional services",
    "Technicians & Trades": "perform skilled technical and trade tasks requiring specialised training and practical expertise",
    "Community & Personal Service": "provide personal care, community services, and support to individuals and groups",
    "Clerical & Administrative": "organise, manage information, communicate, and carry out administrative and office tasks",
    "Sales Workers": "sell goods and services, assist customers, and manage retail and sales operations",
    "Machinery Operators & Drivers": "operate machinery, vehicles, and equipment in industrial, transport, and production settings",
    "Labourers": "perform routine manual tasks in cleaning, construction, agriculture, manufacturing, and other physical work",
}

# More specific duty descriptions for common occupation title keywords
KEYWORD_DUTIES = {
    "accountant": "prepare and examine financial records, ensure compliance with tax laws, and advise on financial planning",
    "nurse": "provide patient care, administer medications, monitor health conditions, and coordinate with medical teams",
    "teacher": "plan and deliver educational programs, assess student progress, and manage classroom environments",
    "engineer": "design, develop, and oversee engineering systems, structures, and processes using technical expertise",
    "developer": "design, write, test, and maintain software code and applications",
    "programmer": "write, test, debug, and maintain computer programs and software systems",
    "analyst": "collect, analyse, and interpret data to support decision-making and improve business processes",
    "electrician": "install, maintain, and repair electrical wiring, equipment, and systems in buildings and infrastructure",
    "plumber": "install, maintain, and repair water supply, drainage, and gas piping systems",
    "carpenter": "construct, install, and repair structures and fittings made from wood and other materials",
    "chef": "plan menus, prepare and cook food, and manage kitchen operations in hospitality settings",
    "driver": "operate vehicles to transport passengers, goods, or materials safely and efficiently",
    "mechanic": "inspect, diagnose, repair, and maintain vehicles, machinery, and mechanical equipment",
    "lawyer": "advise clients on legal matters, prepare legal documents, and represent clients in courts and tribunals",
    "solicitor": "provide legal advice, draft documents, and represent clients in legal proceedings",
    "doctor": "diagnose and treat illnesses, prescribe medications, and manage patient health",
    "dentist": "examine, diagnose, and treat diseases and conditions of the teeth, gums, and oral cavity",
    "pharmacist": "dispense medications, provide drug information, and advise on pharmaceutical care",
    "psychologist": "assess, diagnose, and treat mental health conditions using therapeutic techniques",
    "architect": "design buildings and spaces, prepare plans and specifications, and oversee construction",
    "designer": "create visual concepts, layouts, and designs for communications, products, or digital media",
    "writer": "research, write, and edit content for publications, media, marketing, or communications",
    "editor": "review, edit, and prepare written content for publication across various media",
    "farmer": "plan and manage agricultural operations including crop cultivation, livestock care, and farm maintenance",
    "miner": "extract minerals, coal, or other resources from underground or surface mines",
    "welder": "join metal parts using welding equipment and techniques in fabrication and construction",
    "cleaner": "clean and maintain buildings, premises, and facilities to hygiene standards",
    "carer": "provide personal care, support, and assistance to elderly, disabled, or unwell individuals",
    "childcare": "supervise, care for, and support the development of children in early childhood settings",
    "receptionist": "greet visitors, answer enquiries, manage appointments, and perform front-desk administrative tasks",
    "secretary": "provide administrative support, manage correspondence, organise files, and coordinate schedules",
    "clerk": "perform administrative tasks including data entry, filing, record-keeping, and processing documents",
    "sales": "sell products or services, assist customers, process transactions, and meet sales targets",
    "retail": "assist customers, manage stock, operate registers, and maintain retail store operations",
    "waiter": "take customer orders, serve food and beverages, and provide table service in hospitality venues",
    "barista": "prepare and serve coffee and other beverages in cafes and hospitality venues",
    "hairdresser": "cut, style, colour, and treat hair according to client preferences and current trends",
    "police": "maintain public order, investigate crimes, enforce laws, and protect community safety",
    "firefighter": "respond to fires and emergencies, perform rescues, and carry out fire prevention activities",
    "paramedic": "provide emergency medical care, assess patients, and transport them to medical facilities",
    "pilot": "operate aircraft to transport passengers and cargo safely, following flight plans and regulations",
    "surveyor": "measure and map land, buildings, and other features for construction, planning, and legal purposes",
    "librarian": "manage library collections, assist patrons with research, and organise information resources",
    "veterinar": "diagnose and treat diseases and injuries in animals, and advise on animal health care",
    "counsellor": "provide guidance and support to individuals dealing with personal, social, or psychological issues",
    "social worker": "support individuals and communities facing challenges through case management and advocacy",
    "economist": "analyse economic data, study trends, and provide advice on economic policy and business decisions",
    "actuary": "use mathematical and statistical methods to assess financial risk in insurance and finance",
    "auditor": "examine financial records and systems to ensure accuracy, compliance, and proper governance",
    "manager": "plan, direct, coordinate, and oversee the activities of an organisation, department, or team",
}


def infer_duties(title: str, category: str) -> str:
    """Infer a 1-2 sentence description of job duties from title and category."""
    title_lower = title.lower()

    # Check specific keywords first
    for keyword, duties in KEYWORD_DUTIES.items():
        if keyword in title_lower:
            return f"Workers in this occupation {duties}."

    # Fall back to category-level description
    cat_duties = CATEGORY_DUTIES.get(category, "perform specialised tasks in their field of work")
    return f"Workers in this occupation {cat_duties}."


def generate_page(occ: dict) -> str:
    """Generate a markdown page for one occupation."""
    lines = []
    lines.append(f"# {occ['title']}")
    lines.append("")
    lines.append(f"**ANZSCO Code:** {occ['anzsco_code']}")
    lines.append(f"**Category:** {occ['category']}")
    lines.append("")

    # Official ANZSCO description (from Table_2) or inferred fallback
    lines.append(f"## What workers do")
    lines.append("")
    if occ.get("description"):
        lines.append(occ["description"])
    else:
        duties = infer_duties(occ["title"], occ["category"])
        lines.append(duties)
    lines.append("")

    # Employment
    lines.append("## Key statistics")
    lines.append("")
    if occ.get("jobs"):
        lines.append(f"- **Employment:** {occ['jobs']:,} workers in Australia")
    else:
        lines.append("- **Employment:** Data not available")

    if occ.get("pay_aud"):
        lines.append(f"- **Median annual earnings:** A${occ['pay_aud']:,}")
    else:
        lines.append("- **Median annual earnings:** Data not available")

    if occ.get("skill_level"):
        lines.append(f"- **Skill level required:** {occ['skill_level']}")

    if occ.get("shortage_status"):
        lines.append(f"- **Labour shortage status:** {occ['shortage_status']}")

    if occ.get("growth_pct") is not None:
        sign = "+" if occ["growth_pct"] > 0 else ""
        lines.append(f"- **Employment growth:** {sign}{occ['growth_pct']}% annually (projected)")

    lines.append("")
    return "\n".join(lines)


def main():
    json_path = Path("occupations.json")
    if not json_path.exists():
        print("ERROR: occupations.json not found. Run parse_jsa.py first.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        occupations = json.load(f)

    pages_dir = Path("pages")
    pages_dir.mkdir(exist_ok=True)

    count = 0
    for occ in occupations:
        slug = occ["slug"]
        content = generate_page(occ)
        page_path = pages_dir / f"{slug}.md"
        page_path.write_text(content, encoding="utf-8")
        count += 1

    print(f"Generated {count} markdown pages in pages/")

    # Show a sample
    if occupations:
        sample = occupations[0]
        print(f"\nSample page (pages/{sample['slug']}.md):")
        print("-" * 50)
        print(generate_page(sample))


if __name__ == "__main__":
    main()
