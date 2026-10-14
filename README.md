# FeedbackLens - AI Assignment Feedback Assistant (OpenHack'26, ED-02)

Teachers define a rubric; students submit text (paste or .txt/.md/.docx/.pdf); the system generates
**criterion-based feedback, missing concepts and concrete improvement suggestions with examples**.
The teacher reviews and edits everything before it is released to the student. Scores are always
labelled as *AI suggestions*, never as an unquestionable grade.

## Problem and impact
Students wait days for feedback; teachers spend hours repeating the same comments. FeedbackLens gives
instant draft feedback to the teacher, keeps the teacher in control, and shows **class-wide recurring
mistakes** so the next lesson can target them.

## Features (mapped to the MVP)
| MVP item | Where |
|---|---|
| Accept text assignment or document | Student tab: paste, or upload .txt/.md/.docx/.pdf |
| Teacher defines/selects rubric | Rubrics tab (4 criterion types, editable concept lists); sample rubric pre-loaded |
| Criterion-based feedback + missing concepts | Per-criterion level, strengths, missing concepts |
| Improvements with supporting examples | Each suggestion has an example sentence |
| Instructor review & edit interface | Teacher review tab: edit points, comments, suggestions; save draft / approve |
| Not an unquestionable grade | Disclaimer everywhere; student sees feedback only after approval; AI score kept next to teacher score |
| Extra | Class insights (recurring missing concepts), prompt-injection-aware LLM prompt, re-analyse |

## Run it (Python 3.10+)
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd backend
uvicorn main:app --reload --port 8000
```
Open http://localhost:8000. Sample rubric and two sample submissions are seeded on first run.

### Optional: Claude LLM mode
Copy `.env.example` to `.env` (git-ignored) and set `ANTHROPIC_API_KEY`. The badge in the header switches to
"Claude LLM". If the API fails, the app silently falls back to the local engine. **Never commit `.env`.**

## How it works (for judges)
- `backend/engine.py`
  - **Local engine** (default, deterministic, explainable): concept coverage via keyword matching with word
    stems; structure (paragraphs, linking words, conclusion cue); clarity (sentence length, length vs expected);
    evidence (example cues, numbers). Points = coverage ratio x max points, rounded to 0.5.
  - **LLM engine**: sends rubric + submission to Claude with a system prompt that treats the submission as data
    (not instructions), requests strict JSON, clamps scores to rubric limits, validates every criterion is present.
  - Both return the same JSON shape, so the UI does not care which produced it.
- `backend/main.py`: FastAPI REST API (rubrics CRUD, submissions, feedback save/approve, insights, file extraction).
  Teacher points are clamped server-side. Students must give ID + name and only see **approved** feedback.
- `backend/db.py`: SQLite, seeded with a sample rubric.
- `static/`: dependency-free JS UI; all dynamic text is HTML-escaped.

## Tests
```bash
pip install pytest && python -m pytest -q tests
```

## Demo script (3-4 min)
1. Teacher tab: open Bilal's weak submission - show low suggested score, missing concepts, example sentences.
2. Edit a comment, adjust points, **Approve**.
3. Student tab: enter ID + name -> feedback visible only now (before approval: "pending").
4. Student tab: paste a stronger answer -> compare scores; show the AI score vs teacher score kept side by side.
5. Class insights: recurring missing concepts across the class.
6. Rubrics tab: add a concept ("Load factor") live and re-analyse.
7. Explain limits honestly: keyword matching can miss paraphrases (LLM mode addresses this); AI never finalises grades.

## Limitations / next steps
Scanned-PDF OCR, semantic (embedding) concept matching in local mode, authentication/roles, LMS integration,
multiple assignment types.

## AI & Open-Source Disclosure
AI Tools / Models:
- Claude (Anthropic) - used to help write the code and documentation; optional Claude API for feedback generation at runtime

Open-Source Technologies:
- FastAPI, Uvicorn, Pydantic, python-multipart, python-dotenv (BSD/MIT)
- python-docx (MIT), pypdf (BSD)
- Anthropic Python SDK (MIT)
- SQLite (public domain), pytest (MIT)

License: MIT (see LICENSE).
