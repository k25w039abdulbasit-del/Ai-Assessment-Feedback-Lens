// FeedbackLens frontend (vanilla JS). All user text is escaped before insertion.
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const wc = t => (t.trim().match(/[A-Za-z0-9']+/g) || []).length;

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.body); }
  const r = await fetch("/api" + path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

let rubrics = [];
let currentSub = null;

// ---------------------------------------------------------------- tabs
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {
  document.querySelectorAll("nav button").forEach(x => x.classList.toggle("active", x === b));
  ["student", "teacher", "rubrics", "insights"].forEach(t => $("#tab-" + t).hidden = t !== b.dataset.tab);
  if (b.dataset.tab === "teacher") loadSubs();
  if (b.dataset.tab === "rubrics") renderRubricList();
  if (b.dataset.tab === "insights") loadInsights();
});

async function loadRubrics() {
  rubrics = await api("/rubrics");
  const opts = rubrics.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
  $("#s-rubric").innerHTML = opts;
  $("#i-rubric").innerHTML = opts;
  showPrompt();
}
function showPrompt() {
  const r = rubrics.find(x => x.id == $("#s-rubric").value);
  $("#s-prompt").textContent = r ? r.assignment_prompt : "";
}
$("#s-rubric").onchange = showPrompt;
$("#i-rubric").onchange = loadInsights;

// ---------------------------------------------------------------- student
$("#s-text").oninput = () => $("#s-count").textContent = wc($("#s-text").value) + " words";
$("#s-file").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  const fd = new FormData(); fd.append("file", f);
  try { $("#s-text").value = (await api("/extract", { method: "POST", body: fd })).text; $("#s-text").oninput(); $("#s-msg").innerHTML = ""; }
  catch (err) { $("#s-msg").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
};
$("#s-submit").onclick = async () => {
  const btn = $("#s-submit"); btn.disabled = true; btn.textContent = "Analysing...";
  try {
    const r = await api("/submissions", { method: "POST", body: { rubric_id: +$("#s-rubric").value, student_name: $("#s-name").value, text: $("#s-text").value } });
    $("#s-msg").innerHTML = `<p class="okmsg">Submitted! Your submission ID is <b>${r.id}</b>. Your instructor will review the AI suggestions first. Use your ID and name below to see approved feedback.</p>`;
    $("#c-id").value = r.id; $("#c-name").value = $("#s-name").value;
  } catch (err) { $("#s-msg").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  btn.disabled = false; btn.textContent = "Submit";
};
$("#c-go").onclick = async () => {
  try {
    const r = await api(`/student/${+$("#c-id").value}?name=${encodeURIComponent($("#c-name").value)}`);
    $("#c-out").innerHTML = r.status === "pending"
      ? `<p class="muted">Your instructor hasn't released the feedback yet. Check back soon.</p>` : renderReadOnly(r.feedback);
  } catch (err) { $("#c-out").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
};

function suggestionsHtml(list) {
  return list.map(s => `<li>${esc(s.text)}${s.example ? `<div class="ex">${esc(s.example)}</div>` : ""}</li>`).join("");
}
function renderReadOnly(fb) {
  const tot = fb.criteria.reduce((a, c) => a + c.points, 0), mx = fb.criteria.reduce((a, c) => a + c.max_points, 0);
  return `<h3>Instructor-reviewed feedback: ${tot}/${mx}</h3><p>${esc(fb.summary)}</p>` + fb.criteria.map(c => `
    <div class="crit"><div class="crit-h"><span>${esc(c.name)}</span><span>${c.points}/${c.max_points}</span></div>
    ${c.comment ? `<p>${esc(c.comment)}</p>` : ""}
    ${c.strengths.length ? `<b class="good">Strengths</b><ul>${c.strengths.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
    ${c.missing_concepts.length ? `<b class="miss">Missing</b><ul>${c.missing_concepts.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
    ${c.suggestions.length ? `<b>How to improve</b><ul>${suggestionsHtml(c.suggestions)}</ul>` : ""}</div>`).join("");
}

// ---------------------------------------------------------------- teacher review
async function loadSubs() {
  const subs = await api("/submissions");
  $("#t-list").innerHTML = subs.length ? subs.map(s => `
    <div class="item ${currentSub && currentSub.id === s.id ? "sel" : ""}" data-id="${s.id}">
      <b>#${s.id} ${esc(s.student_name)}</b><br>
      <span class="pill ${s.status}">${s.status}</span> <span class="muted">${s.points}/${s.max_points}</span></div>`).join("")
    : `<p class="muted">No submissions yet.</p>`;
  document.querySelectorAll("#t-list .item").forEach(el => el.onclick = () => openSub(+el.dataset.id));
}

async function openSub(id) {
  currentSub = await api("/submissions/" + id);
  drawReview();
  loadSubs();
}

function drawReview() {
  const s = currentSub, fb = s.feedback;
  $("#t-detail").innerHTML = `
    <div class="row"><h2>#${s.id} ${esc(s.student_name)} <span class="pill ${s.status}">${s.status}</span></h2>
      <span class="badge ${fb.engine === "llm" ? "llm" : ""}">${fb.engine === "llm" ? "Claude LLM" : "Rule-based engine"}</span></div>
    ${fb.engine_note ? `<p class="muted">${esc(fb.engine_note)}</p>` : ""}
    <div class="disc">${esc(fb.disclaimer)}</div>
    <h3>Submission</h3><div class="essay">${esc(s.text)}</div>
    <h3>Overall comment</h3><textarea id="e-summary" rows="2">${esc(fb.summary)}</textarea>
    <div id="e-crits">${fb.criteria.map((c, i) => critEditor(c, i)).join("")}</div>
    <div class="row"><b id="e-total"></b>
      <span><button id="e-regen">Re-analyse</button> <button id="e-save">Save draft</button> <button id="e-approve" class="ok">Approve &amp; release to student</button></span></div>
    <div id="e-msg"></div>`;
  updateTotal();
  document.querySelectorAll(".e-pts").forEach(i => i.oninput = updateTotal);
  document.querySelectorAll(".e-rm").forEach(b => b.onclick = () => b.closest("li").remove());
  $("#e-save").onclick = () => saveFb("draft");
  $("#e-approve").onclick = () => saveFb("approved");
  $("#e-regen").onclick = async () => {
    if (!confirm("Replace current feedback and edits with a new analysis?")) return;
    currentSub.feedback = await api(`/submissions/${s.id}/regenerate`, { method: "POST" }); currentSub.status = "draft"; drawReview(); loadSubs();
  };
}

function critEditor(c, i) {
  return `<div class="crit" data-i="${i}">
    <div class="crit-h"><span>${esc(c.name)} <span class="lvl ${esc(c.level)}">${esc(c.level)}</span></span>
      <span>Points <input type="number" class="e-pts" min="0" max="${c.max_points}" step="0.5" value="${c.points}"> / ${c.max_points}
      <span class="muted">(AI suggested ${c.suggested_points})</span></span></div>
    <p class="muted">Basis: ${esc(c.evidence_basis || "")}</p>
    <label>Comment <textarea class="e-comment" rows="2">${esc(c.comment)}</textarea></label>
    ${c.strengths.length ? `<b class="good">Strengths</b><ul>${c.strengths.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${c.missing_concepts.length ? `<b class="miss">Missing concepts</b><ul>${c.missing_concepts.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <b>Suggestions (edit or remove)</b>
    <ul class="e-sugs">${c.suggestions.map(sg => `<li><textarea class="sg-t" rows="2">${esc(sg.text)}</textarea>
      <textarea class="sg-e" rows="1" placeholder="Example">${esc(sg.example)}</textarea> <button class="e-rm danger">Remove</button></li>`).join("")}</ul>
  </div>`;
}

function updateTotal() {
  let tot = 0, mx = 0;
  currentSub.feedback.criteria.forEach((c, i) => { mx += c.max_points; tot += +document.querySelectorAll(".e-pts")[i].value || 0; });
  $("#e-total").textContent = `Total: ${tot}/${mx}`;
}

async function saveFb(status) {
  const fb = JSON.parse(JSON.stringify(currentSub.feedback));
  fb.summary = $("#e-summary").value;
  document.querySelectorAll("#e-crits .crit").forEach(el => {
    const c = fb.criteria[+el.dataset.i];
    c.points = Math.max(0, Math.min(c.max_points, +el.querySelector(".e-pts").value || 0));
    c.comment = el.querySelector(".e-comment").value;
    c.suggestions = [...el.querySelectorAll(".e-sugs li")].map(li => ({ text: li.querySelector(".sg-t").value, example: li.querySelector(".sg-e").value }));
  });
  try {
    await api(`/submissions/${currentSub.id}/feedback`, { method: "PUT", body: { data: fb, status } });
    currentSub.feedback = fb; currentSub.status = status;
    $("#e-msg").innerHTML = `<p class="okmsg">${status === "approved" ? "Approved - the student can now see this feedback." : "Draft saved."}</p>`;
    loadSubs();
  } catch (err) { $("#e-msg").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
}

// ---------------------------------------------------------------- rubrics
function renderRubricList() {
  $("#r-list").innerHTML = rubrics.map(r => `<div class="item" data-id="${r.id}"><b>${esc(r.name)}</b><br><span class="muted">${r.criteria.length} criteria</span></div>`).join("");
  document.querySelectorAll("#r-list .item").forEach(el => el.onclick = () => editRubric(rubrics.find(r => r.id == el.dataset.id)));
}
$("#r-new").onclick = () => editRubric(null);

const conceptsToText = cs => (cs || []).map(c => [c.name, (c.keywords || []).join(", "), c.hint || "", c.example || ""].join(" | ")).join("\n");
function textToConcepts(t) {
  return t.split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const [name, kws = "", hint = "", example = ""] = l.split("|").map(x => x.trim());
    return { name, keywords: kws.split(",").map(x => x.trim()).filter(Boolean), hint, example };
  });
}

function critRow(c = { name: "", type: "concepts", max_points: 5, concepts: [] }) {
  const types = ["concepts", "evidence", "structure", "clarity"];
  return `<div class="crit rc">
    <div class="cgrid"><input class="rc-name" placeholder="Criterion name" value="${esc(c.name)}">
      <select class="rc-type">${types.map(t => `<option ${t === c.type ? "selected" : ""}>${t}</option>`).join("")}</select>
      <input class="rc-max" type="number" min="1" value="${c.max_points}"></div>
    <textarea class="rc-concepts" rows="4" placeholder="(concepts type only) one per line:  Name | keyword1, keyword2 | hint | example sentence">${esc(conceptsToText(c.concepts))}</textarea>
    <button class="rc-del danger">Remove criterion</button></div>`;
}

function editRubric(r) {
  const d = r || { name: "", assignment_prompt: "", min_words: 150, criteria: [] };
  $("#r-edit").innerHTML = `<h2>${r ? "Edit" : "New"} rubric</h2>
    <label>Name <input id="r-name" value="${esc(d.name)}"></label>
    <label>Assignment prompt <textarea id="r-prompt" rows="2">${esc(d.assignment_prompt)}</textarea></label>
    <label>Expected minimum words <input id="r-min" type="number" value="${d.min_words}"></label>
    <p class="muted">Criterion types: <b>concepts</b> (checks for expected ideas/keywords), <b>evidence</b> (examples), <b>structure</b> (intro/body/conclusion), <b>clarity</b> (readability). When an API key is configured, Claude also uses your concept list and descriptions.</p>
    <div id="r-crits">${d.criteria.map(c => critRow(c)).join("")}</div>
    <div class="row"><button id="r-add">+ Add criterion</button><span><button id="r-del" class="danger">Delete</button> <button id="r-save" class="primary">Save rubric</button></span></div>
    <div id="r-msg"></div>`;
  const wire = () => document.querySelectorAll(".rc-del").forEach(b => b.onclick = () => b.closest(".rc").remove());
  wire();
  $("#r-add").onclick = () => { $("#r-crits").insertAdjacentHTML("beforeend", critRow()); wire(); };
  $("#r-del").onclick = async () => {
    if (!r) return;
    try { await api("/rubrics/" + r.id, { method: "DELETE" }); await loadRubrics(); renderRubricList(); $("#r-edit").innerHTML = `<p class="muted">Deleted.</p>`; }
    catch (err) { $("#r-msg").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
  $("#r-save").onclick = async () => {
    const body = {
      name: $("#r-name").value, assignment_prompt: $("#r-prompt").value, min_words: +$("#r-min").value || 150,
      criteria: [...document.querySelectorAll(".rc")].map(el => ({
        name: el.querySelector(".rc-name").value, type: el.querySelector(".rc-type").value,
        max_points: +el.querySelector(".rc-max").value, concepts: textToConcepts(el.querySelector(".rc-concepts").value)
      }))
    };
    try {
      await api(r ? "/rubrics/" + r.id : "/rubrics", { method: r ? "PUT" : "POST", body });
      await loadRubrics(); renderRubricList(); $("#r-msg").innerHTML = `<p class="okmsg">Saved.</p>`;
    } catch (err) { $("#r-msg").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  };
}

// ---------------------------------------------------------------- insights
async function loadInsights() {
  const id = $("#i-rubric").value; if (!id) return;
  const d = await api(`/rubrics/${id}/insights`);
  if (!d.submissions) { $("#i-out").innerHTML = `<p class="muted">No submissions for this rubric yet.</p>`; return; }
  const maxCount = Math.max(1, ...d.missing.map(m => m.count));
  $("#i-out").innerHTML = `<p class="muted">${d.submissions} submissions analysed.</p>
    <h3>Most commonly missing concepts</h3>
    ${d.missing.length ? d.missing.map(m => `<div class="irow"><span>${esc(m.concept)}</span><div class="bar"><div style="width:${m.count / maxCount * 100}%"></div></div><span>${m.count} of ${d.submissions}</span></div>`).join("") : "<p>None - great!</p>"}
    <h3>Average score by criterion</h3>
    ${d.averages.map(a => `<div class="irow"><span>${esc(a.criterion)}</span><div class="bar"><div style="width:${a.avg / a.max * 100}%"></div></div><span>${a.avg}/${a.max}</span></div>`).join("")}`;
}

// ---------------------------------------------------------------- init
(async () => {
  const st = await api("/status");
  const b = $("#engine"); b.textContent = st.engine === "llm" ? `Claude LLM (${st.model})` : "Rule-based engine (no API key)";
  b.className = "badge " + (st.engine === "llm" ? "llm" : "");
  await loadRubrics();
})();
