import io
import json
import os
import time
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import engine

try:  # optional: load ANTHROPIC_API_KEY from .env (never commit .env)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="FeedbackLens")
db.init(engine.analyze)


# ------------------------------------------------------------------ models
class RubricIn(BaseModel):
    name: str
    assignment_prompt: str = ""
    min_words: int = 150
    criteria: list[dict]


class SubmissionIn(BaseModel):
    rubric_id: int
    student_name: str
    text: str


class FeedbackIn(BaseModel):
    data: dict
    status: str = "draft"  # draft | approved


def validate_rubric(r: RubricIn):
    if not r.name.strip():
        raise HTTPException(400, "Rubric needs a name")
    if not r.criteria:
        raise HTTPException(400, "Rubric needs at least one criterion")
    clean = []
    for c in r.criteria:
        try:
            mp = float(c.get("max_points", 0))
        except (TypeError, ValueError):
            mp = 0
        if not str(c.get("name", "")).strip() or mp <= 0:
            raise HTTPException(400, "Each criterion needs a name and max_points > 0")
        ctype = c.get("type", "concepts")
        if ctype not in ("concepts", "structure", "clarity", "evidence"):
            raise HTTPException(400, f"Unknown criterion type {ctype}")
        clean.append({"name": c["name"].strip(), "type": ctype, "max_points": mp,
                      "description": c.get("description", ""),
                      "concepts": [
                          {"name": k["name"], "keywords": [x for x in k.get("keywords", []) if x] or [k["name"]],
                           "hint": k.get("hint", ""), "example": k.get("example", "")}
                          for k in c.get("concepts", []) if k.get("name")]})
    return {"name": r.name.strip(), "assignment_prompt": r.assignment_prompt,
            "min_words": r.min_words, "criteria": clean}


def get_rubric(c, rid):
    row = c.execute("SELECT data FROM rubrics WHERE id=?", (rid,)).fetchone()
    if not row:
        raise HTTPException(404, "Rubric not found")
    return json.loads(row["data"])


# ------------------------------------------------------------------ API
@app.get("/api/status")
def status():
    return {"engine": "llm" if engine.llm_available() else "local",
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5") if engine.llm_available() else None}


@app.get("/api/rubrics")
def list_rubrics():
    with db.conn() as c:
        return [{"id": r["id"], **json.loads(r["data"])} for r in c.execute("SELECT * FROM rubrics ORDER BY id")]


@app.post("/api/rubrics")
def create_rubric(r: RubricIn):
    data = validate_rubric(r)
    with db.conn() as c:
        cur = c.execute("INSERT INTO rubrics(data) VALUES (?)", (json.dumps(data),))
        return {"id": cur.lastrowid, **data}


@app.put("/api/rubrics/{rid}")
def update_rubric(rid: int, r: RubricIn):
    data = validate_rubric(r)
    with db.conn() as c:
        get_rubric(c, rid)
        c.execute("UPDATE rubrics SET data=? WHERE id=?", (json.dumps(data), rid))
        return {"id": rid, **data}


@app.delete("/api/rubrics/{rid}")
def delete_rubric(rid: int):
    with db.conn() as c:
        if c.execute("SELECT COUNT(*) FROM submissions WHERE rubric_id=?", (rid,)).fetchone()[0]:
            raise HTTPException(409, "Rubric has submissions and cannot be deleted")
        c.execute("DELETE FROM rubrics WHERE id=?", (rid,))
    return {"ok": True}


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    """Turn an uploaded .txt/.md/.docx/.pdf into plain text (shown to the student before submitting)."""
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "File too large (max 2 MB)")
    name = (file.filename or "").lower()
    try:
        if name.endswith((".txt", ".md")):
            text = raw.decode("utf-8", errors="replace")
        elif name.endswith(".docx"):
            import docx
            text = "\n\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            text = "\n\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
        else:
            raise HTTPException(400, "Supported files: .txt, .md, .docx, .pdf")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read that file")
    if not text.strip():
        raise HTTPException(400, "No text found in file (scanned PDFs are not supported)")
    return {"text": text.strip()}


@app.post("/api/submissions")
def submit(s: SubmissionIn):
    text = s.text.strip()
    if len(text) < 20:
        raise HTTPException(400, "Submission is too short")
    if len(text) > 20000:
        raise HTTPException(400, "Submission is too long (max 20,000 characters)")
    if not s.student_name.strip():
        raise HTTPException(400, "Student name is required")
    with db.conn() as c:
        rubric = get_rubric(c, s.rubric_id)
        cur = c.execute("INSERT INTO submissions(rubric_id,student_name,text,created) VALUES (?,?,?,?)",
                        (s.rubric_id, s.student_name.strip(), text, time.time()))
        sid = cur.lastrowid
        fb = engine.analyze(rubric, text)
        c.execute("INSERT INTO feedback(submission_id,data,status,updated) VALUES (?,?,?,?)",
                  (sid, json.dumps(fb), "draft", time.time()))
    return {"id": sid, "status": "draft"}


@app.get("/api/submissions")
def list_submissions():
    with db.conn() as c:
        rows = c.execute("""SELECT s.id, s.student_name, s.created, s.rubric_id, f.status, f.data
                            FROM submissions s JOIN feedback f ON f.submission_id=s.id ORDER BY s.id DESC""").fetchall()
        out = []
        for r in rows:
            d = json.loads(r["data"])
            out.append({"id": r["id"], "student_name": r["student_name"], "created": r["created"],
                        "rubric_id": r["rubric_id"], "status": r["status"],
                        "points": sum(x["points"] for x in d["criteria"]),
                        "max_points": sum(x["max_points"] for x in d["criteria"])})
        return out


@app.get("/api/submissions/{sid}")
def get_submission(sid: int):
    with db.conn() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Submission not found")
        f = c.execute("SELECT * FROM feedback WHERE submission_id=?", (sid,)).fetchone()
        return {"id": sid, "student_name": s["student_name"], "text": s["text"], "rubric_id": s["rubric_id"],
                "rubric": get_rubric(c, s["rubric_id"]), "status": f["status"], "feedback": json.loads(f["data"])}


@app.put("/api/submissions/{sid}/feedback")
def save_feedback(sid: int, body: FeedbackIn):
    if body.status not in ("draft", "approved"):
        raise HTTPException(400, "Bad status")
    fb = body.data
    with db.conn() as c:
        if not c.execute("SELECT 1 FROM feedback WHERE submission_id=?", (sid,)).fetchone():
            raise HTTPException(404, "Submission not found")
        for crit in fb.get("criteria", []):  # clamp teacher-edited points
            crit["points"] = max(0, min(float(crit["max_points"]), float(crit.get("points", 0))))
        fb["teacher_edited"] = True
        c.execute("UPDATE feedback SET data=?, status=?, updated=? WHERE submission_id=?",
                  (json.dumps(fb), body.status, time.time(), sid))
    return {"ok": True, "status": body.status}


@app.post("/api/submissions/{sid}/regenerate")
def regenerate(sid: int):
    with db.conn() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s:
            raise HTTPException(404, "Submission not found")
        fb = engine.analyze(get_rubric(c, s["rubric_id"]), s["text"])
        c.execute("UPDATE feedback SET data=?, status='draft', updated=? WHERE submission_id=?",
                  (json.dumps(fb), time.time(), sid))
        return fb


@app.get("/api/student/{sid}")
def student_view(sid: int, name: str):
    """Students only see feedback after the instructor approves it."""
    with db.conn() as c:
        s = c.execute("SELECT * FROM submissions WHERE id=?", (sid,)).fetchone()
        if not s or s["student_name"].strip().lower() != name.strip().lower():
            raise HTTPException(404, "No submission found for that ID and name")
        f = c.execute("SELECT * FROM feedback WHERE submission_id=?", (sid,)).fetchone()
        if f["status"] != "approved":
            return {"status": "pending"}
        return {"status": "approved", "feedback": json.loads(f["data"])}


@app.get("/api/rubrics/{rid}/insights")
def insights(rid: int):
    """Class-level view: recurring missing concepts and average score per criterion."""
    with db.conn() as c:
        get_rubric(c, rid)
        rows = c.execute("""SELECT f.data FROM submissions s JOIN feedback f ON f.submission_id=s.id
                            WHERE s.rubric_id=?""", (rid,)).fetchall()
    n = len(rows)
    missing, sums, maxes = Counter(), defaultdict(float), {}
    for r in rows:
        for cr in json.loads(r["data"])["criteria"]:
            sums[cr["name"]] += cr["points"]
            maxes[cr["name"]] = cr["max_points"]
            for m in cr["missing_concepts"]:
                missing[m] += 1
    return {"submissions": n,
            "missing": [{"concept": k, "count": v} for k, v in missing.most_common()],
            "averages": [{"criterion": k, "avg": round(sums[k] / n, 2), "max": maxes[k]} for k in sums] if n else []}


# ------------------------------------------------------------------ static
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
