# AU Job Market Visualizer

An interactive treemap visualization of the Australian labour market, inspired by [karpathy/jobs](https://karpathy.ai/jobs). Covers **358 occupations** and **14.4M workers** using official ANZSCO data from Jobs and Skills Australia.

Explore four data layers: **shortage status**, **median pay**, **skill level**, and **Digital AI Exposure** (scored by Google Gemini).

## Data Sources & Credits

- **[Jobs and Skills Australia](https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles)** — occupation profiles, employment, earnings, and education data (ANZSCO 4-digit level)
- **[Occupation Shortage Data (OSD)](https://www.jobsandskills.gov.au/work/skills-shortages)** — labour shortage assessments
- **[Google Gemini](https://ai.google.dev/)** — AI exposure scoring via `gemini-2.5-flash`
- **[karpathy/jobs](https://github.com/karpathy/jobs)** — original inspiration and treemap algorithm

## Setup

```bash
# Install dependencies
uv sync

# Configure your Gemini API key
cp .env.example .env
# Edit .env and add your key from https://aistudio.google.com/apikey
```

You need a **Google Gemini API key** (free tier available). Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

## Pipeline

Run each step in order:

### 1. Parse JSA Excel data

```bash
uv run python parse_jsa.py
```

Auto-downloads the JSA occupation profiles Excel file and OSD shortage data (cached in `data/`), extracts ANZSCO 4-digit occupation data from multiple sheets, and outputs `occupations.csv` and `occupations.json`.

### 2. Generate occupation markdown pages

```bash
uv run python generate_pages.py
```

Creates a markdown file per occupation in `pages/` with structured descriptions for the AI scorer.

### 3. Score AI exposure

```bash
# Test the prompt first
uv run python score.py --dry-run

# Run the full scoring
uv run python score.py
```

Scores each occupation's Digital AI Exposure (0-10) using Google Gemini. Results are saved incrementally to `scores.json`.

Options:
- `--model MODEL` — Gemini model (default: `gemini-2.5-flash`)
- `--start N --end M` — score a batch range
- `--force` — re-score already cached occupations
- `--delay SECONDS` — delay between API calls (default: 0.2)

### 4. Build site data

```bash
uv run python build_site_data.py
```

Merges `occupations.csv` and `scores.json` into `docs/data.json`.

### 5. View the visualization

```bash
cd docs && python -m http.server 8000
```

Open http://localhost:8000 in your browser.

## Deploying to GitHub Pages

The site lives in the `docs/` folder (`index.html` + `data.json`). To deploy:

1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` / Folder: `/docs`
4. Click Save — your site is live at `https://yourusername.github.io/repo-name/`

## Cost Estimate

Scoring all ~358 occupations with Gemini 2.5 Flash costs roughly A$0.50-2.00.

## Caveats

- **AI exposure scores are LLM estimates**, not rigorous economic research. A high score does not predict the job will disappear.
- Scores reflect current digital AI capabilities (language, code, image, analysis) — not hypothetical future robotics.
- Many high-exposure jobs will be reshaped, not replaced. The score does not account for demand elasticity, latent demand, or regulatory barriers.

## Customising the Scoring Prompt

Edit the `SYSTEM_PROMPT` in `score.py` to score occupations by different criteria. For example, you could write prompts for:
- Exposure to humanoid robotics
- Offshoring risk
- Climate impact on occupation
- Remote work suitability

Re-run `score.py` and `build_site_data.py` after changing the prompt.

## License

MIT — see [LICENSE](LICENSE).
