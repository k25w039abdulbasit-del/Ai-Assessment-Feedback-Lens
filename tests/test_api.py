import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from fastapi.testclient import TestClient
import main

c = TestClient(main.app)

def test_flow():
    rubrics = c.get("/api/rubrics").json()
    assert rubrics and rubrics[0]["criteria"]
    rid = rubrics[0]["id"]
    # weak vs strong sample submissions seeded
    subs = c.get("/api/submissions").json()
    assert len(subs) >= 2
    by = {s["student_name"]: s for s in subs}
    assert by["Ayesha Khan"]["points"] > by["Bilal Ahmed"]["points"]
    # new submission -> draft, hidden from student
    r = c.post("/api/submissions", json={"rubric_id": rid, "student_name": "Test", "text": "Hash tables use a hash function and chaining to handle a collision. " * 5})
    sid = r.json()["id"]
    assert c.get(f"/api/student/{sid}", params={"name": "test"}).json()["status"] == "pending"
    # teacher edits + approves
    d = c.get(f"/api/submissions/{sid}").json()["feedback"]
    d["criteria"][0]["points"] = 99  # must be clamped
    assert c.put(f"/api/submissions/{sid}/feedback", json={"data": d, "status": "approved"}).status_code == 200
    v = c.get(f"/api/student/{sid}", params={"name": "Test"}).json()
    assert v["status"] == "approved"
    assert v["feedback"]["criteria"][0]["points"] == v["feedback"]["criteria"][0]["max_points"]
    assert c.get(f"/api/student/{sid}", params={"name": "wrong"}).status_code == 404
    ins = c.get(f"/api/rubrics/{rid}/insights").json()
    assert ins["submissions"] >= 3 and ins["missing"]

def test_validation_and_upload():
    assert c.post("/api/submissions", json={"rubric_id": 1, "student_name": "x", "text": "short"}).status_code == 400
    assert c.post("/api/rubrics", json={"name": "r", "criteria": []}).status_code == 400
    assert c.post("/api/extract", files={"file": ("a.txt", b"hello world text")}).json()["text"] == "hello world text"
    assert c.post("/api/extract", files={"file": ("a.exe", b"x")}).status_code == 400
