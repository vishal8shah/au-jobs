"""
Score each occupation's Digital AI Exposure using the Google Gemini API.

Uses the new google-genai SDK with structured JSON output.
Reads occupation markdown from pages/{slug}.md, scores via Gemini,
and saves results incrementally to scores.json.

Usage:
    uv run python score.py                    # Score all occupations
    uv run python score.py --dry-run          # Print prompt for first occupation
    uv run python score.py --start 0 --end 50 # Score a batch
    uv run python score.py --force            # Re-score cached occupations
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

SYSTEM_PROMPT = """
You are an expert analyst evaluating how exposed different occupations are to AI in the Australian context.
You will be given a description of an occupation from the Australian ANZSCO classification.
Rate the occupation's overall Digital AI Exposure on a scale from 0 to 10.

AI Exposure measures: how much will AI reshape this occupation in Australia over the next 5 years?
Consider both direct effects (AI automating tasks) and indirect effects (AI making workers so productive
that fewer are needed). Weight the score toward current digital AI capabilities (language, code, image,
analysis) — not hypothetical future robotics.

Key signal: if the job can be done entirely from a home computer — writing, coding, analyzing,
communicating — then AI exposure is inherently high (7+). Physical presence, manual skill, and
real-world unpredictability are natural barriers.

Australian-specific context: FIFO mining, aged care, construction trades, childcare, and hospitality
are major Australian employment categories with lower AI exposure. Knowledge work in finance, law,
tech, and government administration has high exposure.

Calibration anchors:
- 0–1: Minimal. Almost entirely physical or unpredictable environments.
  Examples: underground miner, roof tiler, commercial diver, cane harvester.
- 2–3: Low. Mostly physical/interpersonal. AI helps only with minor admin.
  Examples: electrician, plumber, childcare worker, aged care worker.
- 4–5: Moderate. Mix of physical and knowledge work.
  Examples: registered nurse, police officer, secondary teacher, vet.
- 6–7: High. Predominantly knowledge work.
  Examples: accountant, solicitor, HR manager, financial adviser, architect.
- 8–9: Very high. Almost entirely computer-based.
  Examples: software developer, data analyst, graphic designer, copywriter, paralegal, web developer.
- 10: Maximum. Routine digital processing.
  Examples: data entry clerk, call centre operator, payroll administrator.

Respond with ONLY a JSON object, no other text:
{"exposure": <0-10>, "rationale": "<2-3 sentences about the key factors in the Australian context>"}
""".strip()


def load_scores(scores_path: Path) -> dict:
    """Load existing scores from scores.json."""
    if scores_path.exists():
        with open(scores_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_scores(scores: dict, scores_path: Path):
    """Save scores to scores.json."""
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)


METHODOLOGY_VERSION = "1.0"

RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "exposure": types.Schema(type=types.Type.INTEGER),
        "rationale": types.Schema(type=types.Type.STRING),
    },
    required=["exposure", "rationale"],
)


def extract_json(text: str) -> dict:
    """Extract JSON from response text, handling markdown code fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return json.loads(text)


def prompt_version() -> str:
    """Return a short SHA-256 hash of SYSTEM_PROMPT for comparison safety."""
    return hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:12]


def call_with_retry(client, model, content, config, max_retries=3):
    """Call Gemini API with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(
                model=model, contents=content, config=config,
            )
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"    Retry {attempt + 1}/{max_retries - 1} after {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def archive_previous_scores(scores_path: Path):
    """Archive existing scores.json to runs/ before a new scoring run."""
    if not scores_path.exists():
        return
    existing = load_scores(scores_path)
    meta = existing.get("_meta")
    if not meta:
        return
    runs_dir = scores_path.parent / "runs"
    runs_dir.mkdir(exist_ok=True)
    run_date = meta.get("run_date", "unknown")
    archive_path = runs_dir / f"{run_date}_scores.json"
    # Don't overwrite existing archives
    if archive_path.exists():
        return
    shutil.copy2(scores_path, archive_path)
    print(f"Archived previous scores to {archive_path}")


def main():
    parser = argparse.ArgumentParser(description="Score occupations for AI exposure using Gemini")
    parser.add_argument("--model", default="gemini-3.1-pro-preview", help="Gemini model name")
    parser.add_argument("--start", type=int, default=0, help="Start index for batch processing")
    parser.add_argument("--end", type=int, default=None, help="End index for batch processing")
    parser.add_argument("--force", action="store_true", help="Re-score already cached occupations")
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds between API calls")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt for first occupation only")
    parser.add_argument("--thinking-budget", type=int, default=2048, help="Thinking token budget (0 to disable)")
    args = parser.parse_args()

    # Load occupations
    occ_path = Path("occupations.json")
    if not occ_path.exists():
        print("ERROR: occupations.json not found. Run parse_jsa.py first.")
        sys.exit(1)

    with open(occ_path, "r", encoding="utf-8") as f:
        occupations = json.load(f)

    pages_dir = Path("pages")
    if not pages_dir.exists():
        print("ERROR: pages/ directory not found. Run generate_pages.py first.")
        sys.exit(1)

    # Apply batch range
    end = args.end if args.end is not None else len(occupations)
    batch = occupations[args.start:end]
    print(f"Processing {len(batch)} occupations (index {args.start} to {end})")

    # Dry run: just show the prompt
    if args.dry_run:
        if not batch:
            print("No occupations in range.")
            return
        slug = batch[0]["slug"]
        page_path = pages_dir / f"{slug}.md"
        if page_path.exists():
            content = page_path.read_text(encoding="utf-8")
            print("=" * 60)
            print("SYSTEM PROMPT:")
            print("=" * 60)
            print(SYSTEM_PROMPT)
            print()
            print("=" * 60)
            print(f"USER MESSAGE (pages/{slug}.md):")
            print("=" * 60)
            print(content)
        else:
            print(f"Page not found: {page_path}")
        return

    # Configure Gemini (new google-genai SDK)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_google_ai_studio_key_here":
        print("ERROR: Set GEMINI_API_KEY in .env file.")
        print("Get a key from: https://aistudio.google.com/apikey")
        sys.exit(1)

    api_key_2 = os.environ.get("GEMINI_API_KEY_2")
    clients = [genai.Client(api_key=api_key)]
    if api_key_2:
        clients.append(genai.Client(api_key=api_key_2))
        print(f"Loaded {len(clients)} API keys (will rotate on quota exhaustion)")
    client = clients[0]
    client_index = 0

    scores_path = Path("scores.json")

    # Archive previous run before starting new one
    if args.force:
        archive_previous_scores(scores_path)

    scores = load_scores(scores_path)
    # Filter out _meta when counting existing occupation scores
    occ_score_count = sum(1 for k in scores if k != "_meta")
    print(f"Existing scores: {occ_score_count}")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        max_output_tokens=1024,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        thinking_config=types.ThinkingConfig(thinking_budget=args.thinking_budget),
    )

    scored = 0
    skipped = 0
    errors = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_thinking_tokens = 0

    for i, occ in enumerate(batch):
        slug = occ["slug"]

        # Skip if already scored (unless --force)
        if slug in scores and slug != "_meta" and not args.force:
            skipped += 1
            continue

        page_path = pages_dir / f"{slug}.md"
        if not page_path.exists():
            print(f"  [{args.start + i}] SKIP {slug} (no page)")
            skipped += 1
            continue

        content = page_path.read_text(encoding="utf-8")

        last_error = None
        for parse_attempt in range(3):
            try:
                response = call_with_retry(client, args.model, content, config)

                # Track token usage
                if response.usage_metadata:
                    total_input_tokens += response.usage_metadata.prompt_token_count or 0
                    total_output_tokens += response.usage_metadata.candidates_token_count or 0
                    total_thinking_tokens += response.usage_metadata.thoughts_token_count or 0

                result = extract_json(response.text)

                exposure = result.get("exposure")
                rationale = result.get("rationale", "")

                if exposure is not None:
                    exposure = max(0, min(10, int(round(float(exposure)))))

                scores[slug] = {
                    "exposure": exposure,
                    "rationale": rationale,
                }

                # Save incrementally
                save_scores(scores, scores_path)
                scored += 1

                print(f"  [{args.start + i}] {slug}: {exposure}/10 - {rationale[:80]}...")
                last_error = None
                break

            except json.JSONDecodeError as e:
                last_error = e
                wait = 2 ** (parse_attempt + 1)
                print(f"    Parse retry {parse_attempt + 1}/3 after {wait}s: {e}")
                time.sleep(wait)

            except Exception as e:
                # On quota exhaustion, rotate to next API key
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    next_index = (client_index + 1) % len(clients)
                    if next_index != client_index:
                        client_index = next_index
                        client = clients[client_index]
                        print(f"    Rotated to API key {client_index + 1}, retrying...")
                        continue
                last_error = e
                break

        if last_error is not None:
            print(f"  [{args.start + i}] ERROR {slug}: {last_error}")
            errors += 1

        # Rate limiting
        if args.delay > 0:
            time.sleep(args.delay)

    # Update run metadata
    now = datetime.now(timezone.utc)
    scores["_meta"] = {
        "run_id": now.isoformat(timespec="seconds"),
        "run_date": now.strftime("%Y-%m-%d"),
        "model": args.model,
        "prompt_version": prompt_version(),
        "methodology_version": METHODOLOGY_VERSION,
        "thinking_budget": args.thinking_budget,
        "occupations_scored": scored,
    }
    save_scores(scores, scores_path)

    occ_score_count = sum(1 for k in scores if k != "_meta")
    print(f"\nDone: {scored} scored, {skipped} skipped, {errors} errors")
    print(f"Total scores in scores.json: {occ_score_count}")
    if total_input_tokens or total_output_tokens:
        print(f"Tokens used: {total_input_tokens:,} input, {total_output_tokens:,} output, {total_thinking_tokens:,} thinking")


if __name__ == "__main__":
    main()
