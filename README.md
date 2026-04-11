# AU Job Market Visualizer

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Data: Jobs & Skills Australia](https://img.shields.io/badge/Data-Jobs_%26_Skills_AU-green)](https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles)
[![AI: Gemini 3.1 Pro](https://img.shields.io/badge/AI-Gemini%203.1%20Pro-purple)](https://ai.google.dev)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)

An interactive **treemap of 358 Australian occupations and 14.4M workers**, inspired by [karpathy/jobs](https://karpathy.ai/jobs). Built to answer: **which jobs does AI disrupt first?**

Explore four data layers: **shortage status**, **median pay**, **skill level**, and **Digital AI Exposure** (scored by Google Gemini). Features a **scorecard panel** with LinkedIn sharing, **occupation search**, and an **Exposure vs Growth scatter plot** showing which roles are transforming vs. at risk.

---

## Data Sources & Credits

- **[Jobs and Skills Australia](https://www.jobsandskills.gov.au/data/occupation-and-industry-profiles)** — occupation profiles, employment, earnings, and education data (ANZSCO 4-digit level)
- **[Occupation Shortage Data (OSD)](https://www.jobsandskills.gov.au/work/skills-shortages)** — labour shortage assessments
- **[Google Gemini](https://ai.google.dev/)** — AI exposure scoring via `gemini-3.1-pro-preview`
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

Scores each occupation's Digital AI Exposure (0-10) using Google Gemini with extended thinking for higher-quality reasoning. Results are saved incrementally to `scores.json` with run metadata. Previous scores are archived to `runs/` when re-scoring with `--force`.

Options:
- `--model MODEL` — Gemini model (default: `gemini-3.1-pro-preview`)
- `--thinking-budget N` — thinking token budget for reasoning (default: 2048, 0 to disable)
- `--start N --end M` — score a batch range
- `--force` — re-score already cached occupations (archives previous run first)
- `--delay SECONDS` — delay between API calls (default: 0.2)

### 4. Build site data

```bash
uv run python build_site_data.py
```

Merges `occupations.csv` and `scores.json` into `docs/data.json`. If previous scores exist in `runs/`, computes comparison fields (delta, safety check) for the "compare to last refresh" mode.

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

## Compare to Last Refresh

When you re-score occupations (using `--force`), the previous `scores.json` is automatically archived to `runs/`. The build step then computes score deltas and adds a **"vs. Last Refresh"** toggle to the AI Exposure layer. This shows:

- Tile colors by score change (blue = rising exposure, amber = falling)
- Biggest upward and downward movers
- Workforce share with rising/falling exposure

**Comparison safety:** Comparisons are only shown as reliable when the scoring prompt, methodology version, and model family match across runs. If they differ, a warning is displayed and delta coloring is flagged.

## Cost Estimate

Scoring all ~358 occupations with Gemini 2.5 Flash costs roughly A$0.50-2.00. With extended thinking enabled (default), costs may be slightly higher due to thinking tokens.

## Caveats

- **AI exposure scores are LLM estimates**, not rigorous economic research. A high score does not predict the job will disappear.
- Scores reflect current digital AI capabilities (language, code, image, analysis) — not hypothetical future robotics.
- Many high-exposure jobs will be reshaped, not replaced. The score does not account for demand elasticity, latent demand, or regulatory barriers.

## Customising the Scoring Prompt

Edit the `SYSTEM_PROMPT` in `score.py` to score occupations by different criteria. Note: changing the prompt will cause the comparison safety check to flag run-to-run comparisons as unsafe (prompt version is auto-detected via hash). You could write prompts for:
- Exposure to humanoid robotics
- Offshoring risk
- Climate impact on occupation
- Remote work suitability

Re-run `score.py` and `build_site_data.py` after changing the prompt.

## License

MIT — see [LICENSE](LICENSE).
