/* Hillcrest Academy ΓÇö Teacher Simulator front end (vanilla JS, no build step) */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const spr = (role, seed, mood = "neutral") => `/sprite/${role}/${seed}/${mood}.svg`;
const img = (role, seed, mood, alt = "") => `<img class="px" src="${spr(role, seed, mood)}" alt="${esc(alt)}">`;

let S = null;             // latest game state from the server
let tab = "today";
let classSel = null;      // class id shown on Classes / Gradebook / Report
let draft = null;         // today's plan being edited
let classCache = {};

// ------------------------------------------------------------------ api
async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) { toast(data.error || "Something went wrong.", "bad"); throw new Error(data.error); }
  return data;
}

function toast(msg, tone = "") {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = document.createElement("div");
  t.className = `toast ${tone}`;
  t.setAttribute("role", "status");
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

// ------------------------------------------------------------------ helpers
function meter(label, value, { invert = false, suffix = "" } = {}) {
  const v = Math.max(0, Math.min(100, value));
  const good = invert ? 100 - v : v;
  const cls = good < 30 ? "bad" : good < 55 ? "mid" : "";
  return `<div class="meter"><div class="meter-top"><span>${label}</span><span>${Math.round(value)}${suffix}</span></div>
    <div class="bar ${cls}" role="meter" aria-valuenow="${Math.round(v)}" aria-valuemin="0" aria-valuemax="100" aria-label="${esc(label)}"><i style="width:${v}%"></i></div></div>`;
}
const gradeCls = (g) => (["A*", "A", "B"].includes(g) ? "hi" : ["E", "U"].includes(g) ? "lo" : "");
const gradeOf = (n) => (n == null ? "-" : n >= 85 ? "A*" : n >= 75 ? "A" : n >= 65 ? "B" : n >= 55 ? "C" : n >= 45 ? "D" : n >= 35 ? "E" : "U");
const signed = (n) => (n > 0 ? `+${n}` : `${n}`);

function freshDraft() {
  if (!S || !S.today) return null;
  const t = S.today;
  const defaults = Object.fromEntries(S.classes.map((c) => [c.id, c.default]));
  const hasMarking = S.teacher.marking_papers > 0;
  const hasAdmin = S.teacher.admin_points > 4;
  let rot = 0;
  return {
    day: S.day,
    periods: t.periods.map((p) => {
      if (p.class) return { approach: defaults[p.class] || "lecture" };
      const opts = [hasMarking ? "mark" : "plan", hasAdmin ? "admin" : "plan", "plan"];
      if (S.week >= 11 && S.teacher.reports_left > 0) opts.unshift("reports");
      return { task: opts[rot++ % opts.length] };
    }),
    lunch: "eat",
    after: "home",
  };
}

// ------------------------------------------------------------------ top-level render
function render() {
  if (!S || S.phase === "none") return renderEmpty();
  if (!draft || draft.day !== S.day) draft = freshDraft();
  renderTop();
  renderSide();
  renderTabs();
  const views = { today: viewToday, classes: viewClasses, timetable: viewTimetable, work: viewWork, grades: viewGrades, staff: viewStaff, report: viewReport };
  views[tab]();
}

function renderEmpty() {
  $("#sidebar").innerHTML = `<p>No term in progress.</p><button class="primary" onclick="openNewGame()">Start a new term</button>`;
  $("#ribbon").innerHTML = "";
  const seeds = Array.from({ length: 5 }, () => Math.floor(Math.random() * 1e6));
  $("#view").innerHTML = `<div class="empty"><div class="sprites">${seeds.map((s, i) => img("student", s, ["happy", "neutral", "sleepy", "happy", "stressed"][i])).join("")}</div>
    <h2>They're waiting for you</h2><p style="margin:0.6rem auto 1.2rem">Start a term to meet your classes.</p>
    <button class="primary" onclick="openNewGame()">Start a new term</button></div>`;
  openNewGame();
}

function renderTop() {
  $("#today-line").textContent = S.phase === "term" ? `Week ${S.week}, ${S.weekday}` : "Term finished";
  $("#ribbon").innerHTML = S.calendar.map((w) => {
    const cls = [w.week < S.week || S.phase !== "term" ? "done" : "", w.week === S.week && S.phase === "term" ? "now" : "", w.marks.length ? "mark" : ""].join(" ");
    const title = `Week ${w.week}${w.marks.length ? ": " + w.marks.join(", ") : ""}`;
    return `<li class="${cls}" title="${esc(title)}" aria-label="${esc(title)}">${w.week}</li>`;
  }).join("");
}

function renderSide() {
  const t = S.teacher;
  const heavyMark = t.marking_papers > 60, heavyAdmin = t.admin_points > 12;
  $("#sidebar").innerHTML = `
    <div class="me">${img("teacher", t.seed, t.mood, t.name)}
      <div><h3>${esc(t.name)}</h3><p>${esc(t.subject)} teacher</p><p class="muted">Level ${t.level} teacher</p></div></div>
    ${meter("Energy", t.energy)}
    ${meter("Stress", t.stress, { invert: true })}
    <div class="side-sec"><h4>Reputation</h4>
      ${meter("Students", t.rep.students)}${meter("Parents", t.rep.parents)}${meter("Leadership", t.rep.leadership)}</div>
    <div class="side-sec"><h4>On your desk</h4>
      <div class="pile ${heavyMark ? "heavy" : ""}"><span>Scripts to mark</span><b>${t.marking_papers}</b></div>
      <div class="pile ${heavyAdmin ? "heavy" : ""}"><span>Admin to do</span><b>${t.admin.length}</b></div>
      ${S.week >= 11 ? `<div class="pile ${t.reports_left ? "heavy" : ""}"><span>Reports to write</span><b>${t.reports_left}</b></div>` : ""}
      ${t.sick_days ? `<div class="pile heavy"><span>Sick days</span><b>${t.sick_days}</b></div>` : ""}
    </div>
    <div class="side-sec"><button class="ghost" onclick="openNewGame()">New game</button></div>`;
}

function renderTabs() {
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.setAttribute("aria-selected", b.dataset.tab === tab);
    if (b.dataset.tab === "today") b.innerHTML = `Today${S.pending.length ? `<span class="count">${S.pending.length}</span>` : ""}`;
  });
}

// ------------------------------------------------------------------ TODAY
function viewToday() {
  const v = $("#view");
  if (S.phase !== "term") {
    v.innerHTML = `<div class="empty"><h2>The term is over</h2><p style="margin:0.6rem auto 1.2rem">Your end-of-term review is ready.</p>
      <button class="primary" onclick="go('report')">Read your review</button></div>`;
    return;
  }
  const t = S.today;
  const cls = Object.fromEntries(S.classes.map((c) => [c.id, c]));
  const optList = (list, sel) => list.map((o) => `<option value="${o.key}" ${o.key === sel ? "selected" : ""}>${esc(o.label)}</option>`).join("");
  const approachOpts = (sel) => S.options.approaches.map((a) =>
    `<option value="${a.key}" ${a.key === sel ? "selected" : ""}>${esc(a.label)}${a.plans ? ` (${a.plans} plan${a.plans > 1 ? "s" : ""})` : ""}</option>`).join("");

  const rows = [];
  t.periods.forEach((p, i) => {
    if (p.cover) {
      rows.push(`<li class="bell cover"><div class="time">P${p.period}<small>${p.time}</small></div>
        <div class="slot"><div class="who"><b>Cover</b></div><div>You're covering a colleague's class. No choice to make.</div></div></li>`);
    } else if (p.class) {
      const c = cls[p.class];
      const behind = c.coverage < c.expected - 1;
      rows.push(`<li class="bell teach"><div class="time">P${p.period}<small>${p.time}</small></div>
        <div class="slot"><div class="who"><div><b>${p.class}</b>
          <small>${c.plans} plan${c.plans === 1 ? "" : "s"} ready<br>${behind ? `<span class="observed">Behind: topic ${c.coverage}/${c.expected}</span>` : `Topic ${c.coverage}/${c.expected} expected`}</small>
          ${p.observed ? `<small class="observed">Being observed</small>` : ""}</div></div>
          <label><span class="sr-only" hidden>Approach for ${p.class}</span>
          <select data-p="${i}" data-kind="approach" aria-label="How to teach ${p.class}">${approachOpts(draft.periods[i].approach)}</select></label></div></li>`);
    } else {
      rows.push(`<li class="bell"><div class="time">P${p.period}<small>${p.time}</small></div>
        <div class="slot"><div class="who"><b>Free</b></div>
        <select data-p="${i}" data-kind="task" aria-label="Free period ${p.period}">${optList(S.options.free, draft.periods[i].task)}</select></div></li>`);
    }
    if (i === 3) {
      rows.push(t.duty
        ? `<li class="bell break"><div class="time">Lunch<small>13:10</small></div><div class="slot"><div class="who"><b>Duty</b></div><div>Playground duty today.</div></div></li>`
        : `<li class="bell break"><div class="time">Lunch<small>13:10</small></div><div class="slot"><div class="who"><b>Lunch</b></div>
           <select data-kind="lunch" aria-label="Lunchtime">${optList(S.options.lunch, draft.lunch)}</select></div></li>`);
    }
  });
  const afterFixed = t.parents_evening ? "Parents' evening. Everything else waits." : "";
  rows.push(`<li class="bell break"><div class="time">After<small>15:15</small></div><div class="slot"><div class="who"><b>After school</b></div>
    ${afterFixed ? `<div>${afterFixed}</div>` : `<select data-kind="after" aria-label="After school">${optList(S.options.after, draft.after)}</select>`}</div></li>`);

  const blocked = S.pending.length > 0;
  v.innerHTML = `
    <div class="today-grid">
      <div>
        <div class="day-head"><h2><span>Week ${S.week} of ${S.term_weeks}</span>${S.weekday}</h2></div>
        ${t.fixed.length ? `<ul class="notices">${t.fixed.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
        <ol class="bells">${rows.join("")}</ol>
        <div class="start-row">
          <button class="primary" id="run" ${blocked ? "disabled" : ""}>Start the day</button>
          <span class="hint">${blocked ? `Deal with ${S.pending.length} open issue${S.pending.length > 1 ? "s" : ""} first.` : "Lessons, lunch and after school all run in one go."}</span>
        </div>
      </div>
      <div>
        ${S.pending.length ? `<div class="issues"><h3>Needs your decision</h3>${S.pending.map(slip).join("")}</div>` : ""}
        ${S.last_day ? daySummary(S.last_day) : `<div class="summary"><h4>First day</h4><p>Pick how to teach each lesson and what to do in your free periods. Plans make lessons land better; practical lessons need two.</p></div>`}
        <h4>Staffroom noticeboard</h4>
        <ul class="log">${S.log.slice(0, 25).map((l) => `<li class="${l.tone}"><small>W${l.week}</small>${esc(l.text)}</li>`).join("")}</ul>
      </div>
    </div>`;

  v.querySelectorAll("select[data-kind]").forEach((sel) => sel.addEventListener("change", () => {
    const k = sel.dataset.kind;
    if (k === "approach" || k === "task") draft.periods[+sel.dataset.p] = { [k]: sel.value };
    else draft[k] = sel.value;
  }));
  $("#run").addEventListener("click", runDay);
  v.querySelectorAll("[data-ev]").forEach((b) => b.addEventListener("click", () => resolve(+b.dataset.ev, b.dataset.choice)));
}

function slip(e) {
  return `<article class="slip p${e.priority}">
    ${img(e.sprite.role, e.sprite.seed, e.sprite.mood)}
    <div><h4>${esc(e.title)}</h4><p>${esc(e.text)}</p>
      ${e.student ? `<p><button class="linkish" onclick="openStudent('${e.student}')">View student record</button></p>` : ""}
      <div class="choices">${e.choices.map((c) => `<button class="choice" data-ev="${e.id}" data-choice="${c.key}">${esc(c.label)}${c.hint ? `<small>${esc(c.hint)}</small>` : ""}</button>`).join("")}</div>
    </div></article>`;
}

function daySummary(d) {
  const deltas = Object.entries(d.delta || {}).filter(([, n]) => Math.round(n) !== 0).map(([k, n]) => {
    const bad = k === "stress" ? n > 0 : n < 0;
    return `<span class="chip ${bad ? "bad" : "good"}">${k} ${signed(Math.round(n))}</span>`;
  }).join("");
  return `<div class="summary"><h4>How ${d.weekday} went</h4>
    <ul>${d.lessons.map((l) => `<li><b>P${l.period} ${l.class}</b>, ${esc(l.approach)}: ${esc(l.summary)} ${l.gain ? `<span class="chip ${l.gain > 0 ? "good" : ""}">avg ${signed(l.gain)}%</span>` : ""} <small>${l.present}/${l.size} in</small>${(l.issues || []).map((i) => ` <span class="chip warn">${esc(i)}</span>`).join("")}</li>`).join("")}
    ${d.tasks.map((t) => `<li><b>${typeof t.period === "number" ? "P" + t.period : esc(t.period)}</b>, ${esc(t.label)}: ${esc(t.detail)}</li>`).join("")}
    ${d.notes.map((n) => `<li><b>Note:</b> ${esc(n)}</li>`).join("")}</ul>
    ${deltas ? `<div class="deltas">${deltas}</div>` : ""}</div>`;
}

async function runDay() {
  const btn = $("#run");
  btn.disabled = true;
  try {
    S = await api("/api/day", draft);
    classCache = {};
    draft = null;
    if (S.phase === "ended") { tab = "report"; toast("The term is over. Here's your review."); }
    else if (S.pending.length) toast(`${S.pending.length} issue${S.pending.length > 1 ? "s" : ""} came up today.`);
    render();
    $("#view").focus();
  } catch { btn.disabled = false; }
}

async function resolve(id, choice) {
  try {
    S = await api(`/api/event/${id}`, { choice });
    classCache = {};
    toast(S.result.text, S.result.tone);
    draft = draft && draft.day === S.day ? draft : null;
    render();
  } catch {}
}

// ------------------------------------------------------------------ CLASSES (seating plan)
async function getClass(cid) {
  if (!classCache[cid]) classCache[cid] = await api(`/api/class/${cid}`);
  return classCache[cid];
}
function classPicker(onPick) {
  classSel = classSel || S.classes[0].id;
  return `<div class="class-picker" role="group" aria-label="Choose a class">${S.classes.map((c) =>
    `<button aria-pressed="${c.id === classSel}" data-cid="${c.id}">${c.id}${c.tutor ? " Γÿà" : ""}</button>`).join("")}</div>`;
}
function bindPicker(fn) {
  document.querySelectorAll(".class-picker button").forEach((b) => b.addEventListener("click", () => { classSel = b.dataset.cid; fn(); }));
}

async function viewClasses() {
  const v = $("#view");
  v.innerHTML = classPicker() + `<p class="muted">Loading classΓÇª</p>`;
  bindPicker(viewClasses);
  const c = await getClass(classSel);
  const present = c.students.filter((s) => s.present).length;
  v.innerHTML = classPicker() + `
    <div class="class-stats">
      <div><b>${c.size}</b>students</div>
      <div><b>${c.coverage}/20</b>topics taught (${c.expected} expected)</div>
      <div><b>${c.plans}</b>lesson plans ready</div>
      <div><b>${c.climate}</b>class climate</div>
      <div><b>${c.avg ?? "-"}${c.avg != null ? "%" : ""}</b>average understanding</div>
    </div>
    ${c.tutor ? `<p><span class="chip warn">Γÿà Your tutor group</span></p>` : ""}
    <div class="room">
      <div class="board">${c.next_topic ? `Next topic: ${esc(c.next_topic)}` : "Syllabus complete ΓÇö time to revise"}<small>${present} of ${c.size} in today</small></div>
      <div class="desks">${c.students.map((s) => `
        <button class="desk ${s.present ? "" : "absent"}" data-sid="${s.id}" aria-label="${esc(s.name)}, predicted ${s.predicted_grade}">
          ${img("student", s.seed, s.mood)}
          <span class="top"><b>${esc(s.name.split(" ")[0])}</b>${s.predicted_grade !== "-" ? `Predicted ${s.predicted_grade}` : `Target ${s.target_grade}`}
          ${s.detention_due ? `<br><span class="flag">Detention</span>` : ""}</span>
        </button>`).join("")}</div>
      <div class="teacher-desk"><span>Your desk</span></div>
    </div>`;
  bindPicker(viewClasses);
  v.querySelectorAll(".desk").forEach((d) => d.addEventListener("click", () => openStudent(d.dataset.sid)));
}

async function openStudent(sid) {
  const s = await api(`/api/student/${sid}`);
  const tests = s.tests.length ? `<div class="table-wrap"><table><thead><tr><th>Assessment</th><th class="num">Week</th><th class="num">Score</th><th>Grade</th></tr></thead><tbody>
    ${s.tests.map((x) => `<tr><td>${esc(x.label)}</td><td class="num">${x.week}</td><td class="num">${x.score == null ? "Unmarked" : x.score + "%"}</td><td class="grade ${gradeCls(x.grade)}">${x.grade}</td></tr>`).join("")}
    </tbody></table></div>` : `<p class="muted">No assessments yet.</p>`;
  $("#modal-body").innerHTML = `
    <div class="stu-head">${img("student", s.seed, s.mood, s.name)}
      <div><h2>${esc(s.name)}</h2><p>${s.cid}${s.present ? "" : ", absent today"}</p>
        <p>${s.traits.map((t) => `<span class="chip" title="${esc(s.trait_info[t])}">${esc(t)}</span>`).join("")}</p>
        <p class="muted">${s.traits.map((t) => esc(s.trait_info[t])).join(" ")}</p>
        <p>Target <b class="grade">${s.target_grade}</b>, predicted <b class="grade ${gradeCls(s.predicted_grade)}">${s.predicted_grade}</b>${s.detentions ? `, ${s.detentions} detention${s.detentions > 1 ? "s" : ""} served` : ""}</p></div></div>
    <div class="two"><div>${meter("Motivation", s.motivation)}${meter("Behaviour", s.behaviour)}</div>
      <div>${meter("Wellbeing", s.wellbeing)}${meter("Attendance", s.attendance, { suffix: "%" })}</div></div>
    <h4 style="margin-top:1rem">Understanding by topic</h4>
    <div class="topics">${s.topics.map((t) => `<div class="${t.covered ? "" : "uncovered"}"><div class="meter-top"><span>${esc(t.name)}</span><span>${t.covered ? t.value : "ΓÇô"}</span></div>
      <div class="bar ${t.value < 35 ? "bad" : t.value < 60 ? "mid" : ""}"><i style="width:${t.value}%"></i></div></div>`).join("")}</div>
    <h4 style="margin-top:1rem">Assessments</h4>${tests}
    ${s.notes.length ? `<h4 style="margin-top:1rem">Notes</h4><ul class="log">${s.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
    ${s.report ? `<h4 style="margin-top:1rem">Report comment</h4><p>${esc(s.report)}</p>` : ""}
    <div class="row-end"><button class="primary" onclick="$('#modal').close()">Close</button></div>`;
  $("#modal").showModal();
}

// ------------------------------------------------------------------ TIMETABLE
function viewTimetable() {
  const tt = S.timetable;
  const myGrid = `<div class="table-wrap"><table class="tt"><thead><tr><th>Period</th>${tt.days.map((d, i) => `<th>${d}${tt.duty_days.includes(i) ? " <span class='chip warn'>duty</span>" : ""}</th>`).join("")}</tr></thead><tbody>
    ${[0, 1, 2, 3, 4].map((p) => `<tr><th>P${p + 1}<br><small>${tt.times[p]}</small></th>${tt.days.map((_, d) => {
      const cid = tt.mine[d][p];
      return cid ? `<td class="mine">${cid}</td>` : `<td class="free">Free</td>`;
    }).join("")}</tr>${p === 3 ? `<tr><th>Lunch</th>${tt.days.map((_, d) => `<td class="lunch">${tt.duty_days.includes(d) ? "Duty" : ""}</td>`).join("")}</tr>` : ""}`).join("")}
    </tbody></table></div>`;
  classSel = classSel || S.classes[0].id;
  const ct = tt.classes[classSel];
  const classGrid = `<div class="table-wrap"><table class="tt"><thead><tr><th>Period</th>${tt.days.map((d) => `<th>${d}</th>`).join("")}</tr></thead><tbody>
    ${[0, 1, 2, 3, 4].map((p) => `<tr><th>P${p + 1}</th>${tt.days.map((_, d) => {
      const c = ct[d][p];
      return `<td class="${c.mine ? "mine" : ""}">${esc(c.subject)}<br><small>${esc(c.teacher)}</small></td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`;
  $("#view").innerHTML = `<h2>Your week</h2><p class="muted">The same timetable repeats every week. Wednesdays end with a staff meeting.</p>${myGrid}
    <h3 style="margin-top:1.6rem">Class timetables</h3>${classPicker()}${classGrid}`;
  bindPicker(viewTimetable);
}

// ------------------------------------------------------------------ MARKING & ADMIN
function viewWork() {
  const t = S.teacher;
  const batches = t.marking.length ? t.marking.map((b) => `<div class="batch"><div class="meter-top"><b>${esc(b.label)}</b><span>${b.remaining} of ${b.total} left</span></div>
      <div class="bar ${b.kind === "quiz" ? "" : "mid"}"><i style="width:${100 - (b.remaining / b.total) * 100}%"></i></div></div>`).join("")
    : `<p class="muted">Nothing to mark. Set a quiz to find out what your classes actually know.</p>`;
  const admin = t.admin.length ? t.admin.map((a) => {
    const due = a.due_in == null ? "" : a.due_in < 0 ? `<span class="chip bad">overdue</span>` : a.due_in <= 1 ? `<span class="chip warn">due ${a.due_in === 0 ? "today" : "tomorrow"}</span>` : `<span class="chip">due in ${a.due_in} days</span>`;
    return `<div class="task"><span>${esc(a.title)}</span><span>${due}<span class="chip">${a.cost} pt</span></span></div>`;
  }).join("") : `<p class="muted">Inbox zero. Enjoy it while it lasts.</p>`;
  $("#view").innerHTML = `<div class="two">
    <div class="stack"><h2>Marking</h2><p class="muted">Scores stay hidden until you mark them. Returning marked work gives students feedback that improves their understanding. Exam scripts take three times as long.</p>${batches}</div>
    <div class="stack"><h2>Admin</h2><p class="muted">Each admin free period clears about 4 points. Overdue tasks cost you reputation with leadership and parents.</p>${admin}
      ${S.week >= 11 ? `<h3>Reports</h3><p>${t.reports_left} reports left to write. Anything unwritten at the end of week 12 goes out as a generic comment.</p>` : `<h3>Reports</h3><p class="muted">Report writing opens in week 11.</p>`}
    </div></div>`;
}

// ------------------------------------------------------------------ GRADEBOOK
async function viewGrades() {
  const v = $("#view");
  v.innerHTML = `<h2>Gradebook</h2>` + classPicker() + `<p class="muted">LoadingΓÇª</p>`;
  bindPicker(viewGrades);
  const c = await getClass(classSel);
  const quizCount = Math.max(0, ...c.students.map((s) => s.tests.filter((x) => x.kind === "quiz").length));
  const q = Math.min(quizCount, 6);
  v.innerHTML = `<h2>Gradebook</h2>` + classPicker() + `
    <div class="table-wrap"><table><thead><tr><th>Student</th><th>Target</th>${Array.from({ length: q }, (_, i) => `<th class="num">Q${quizCount - q + i + 1}</th>`).join("")}
      <th class="num">Midterm</th><th class="num">Final</th><th class="num">Now</th><th>Predicted</th></tr></thead><tbody>
    ${c.students.map((s) => {
      const quizzes = s.tests.filter((x) => x.kind === "quiz");
      const cells = Array.from({ length: q }, (_, i) => {
        const x = quizzes[quizzes.length - q + i];
        return `<td class="num">${x ? (x.score == null ? "ΓÇª" : x.score) : ""}</td>`;
      }).join("");
      const mid = s.tests.find((x) => x.kind === "midterm"), fin = s.tests.find((x) => x.kind === "final");
      const show = (x) => (x ? (x.score == null ? "Unmarked" : `${x.score} <span class="grade ${gradeCls(gradeOf(x.score))}">${gradeOf(x.score)}</span>`) : "");
      return `<tr><td><div class="namecell">${img("student", s.seed, s.mood)}<button class="linkish" onclick="openStudent('${s.id}')">${esc(s.name)}</button></div></td>
        <td class="grade">${s.target_grade}</td>${cells}<td class="num">${show(mid)}</td><td class="num">${show(fin)}</td>
        <td class="num">${s.current}%</td><td class="grade ${gradeCls(s.predicted_grade)}">${s.predicted_grade}</td></tr>`;
    }).join("")}</tbody></table></div>
    <p class="muted" style="margin-top:0.8rem">"Now" is understanding of topics taught so far. Unmarked scripts show as "ΓÇª".</p>`;
  bindPicker(viewGrades);
}

// ------------------------------------------------------------------ STAFFROOM
function chart(history) {
  if (history.length < 2) return `<p class="muted">Your term chart appears after a couple of days.</p>`;
  const W = 640, H = 200, P = 28;
  const series = [["energy", "#2F6B4F"], ["stress", "#D7263D"], ["leadership", "#3D5A99"], ["parents", "#E9A23B"], ["avg", "#1E2A4A"]];
  const x = (i) => P + (i / (history.length - 1)) * (W - P * 2);
  const y = (v) => H - P - (v / 100) * (H - P * 2);
  const lines = series.map(([k, col]) => `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${history.map((h, i) => `${x(i).toFixed(1)},${y(h[k]).toFixed(1)}`).join(" ")}"/>`).join("");
  const grid = [0, 50, 100].map((v) => `<line x1="${P}" x2="${W - P}" y1="${y(v)}" y2="${y(v)}" stroke="#D8E3EC"/><text x="4" y="${y(v) + 4}" font-size="10" fill="#55607A">${v}</text>`).join("");
  const legend = series.map(([k, col]) => `<span class="chip" style="border-color:${col};color:${col}">${k === "avg" ? "student understanding" : k}</span>`).join("");
  return `<div class="table-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Your stats over the term" style="width:100%;min-width:480px">${grid}${lines}</svg></div><div>${legend}</div>`;
}
function viewStaff() {
  $("#view").innerHTML = `<h2>Staffroom</h2><p class="muted">Your colleagues. The kettle is always on.</p>
    <div class="staff-grid">${S.staff.map((s, i) => `<div class="staff-card">${img("teacher", s.seed, i === 1 ? "neutral" : ["happy", "neutral", "sleepy", "stressed"][i % 4], s.name)}<div><b>${esc(s.name)}</b><p>${esc(s.role)}</p></div></div>`).join("")}</div>
    <h3 style="margin-top:1.6rem">Your term so far</h3>${chart(S.history)}`;
}

// ------------------------------------------------------------------ REPORT
async function viewReport() {
  const v = $("#view");
  v.innerHTML = `<p class="muted">Compiling reportsΓÇª</p>`;
  const r = await api("/api/report");
  classSel = classSel || r.classes[0].id;
  const c = r.classes.find((x) => x.id === classSel);
  v.innerHTML = `
    <div class="verdict">${img("teacher", S.teacher.seed, r.overall >= 55 ? "happy" : r.overall >= 40 ? "neutral" : "sad", "You")}
      <div>${r.final ? "" : `<p class="chip warn">Preview. Grades are predictions until the term ends.</p>`}
        <div class="score">${r.overall}</div><h2>${esc(r.title)}</h2><p>${esc(r.blurb)}</p>
        <p><span class="chip">Average ${r.avg_score}% (${r.avg_grade})</span><span class="chip ${r.value_added >= 0 ? "good" : "bad"}">Value added ${signed(r.value_added)}</span>
        <span class="chip">Wellbeing ${r.wellbeing}</span><span class="chip">Leadership ${r.rep.leadership}</span><span class="chip">Parents ${r.rep.parents}</span><span class="chip">Students ${r.rep.students}</span>
        ${r.sick_days ? `<span class="chip bad">${r.sick_days} sick days</span>` : ""}${r.auto_reports ? `<span class="chip bad">${r.auto_reports} rushed reports</span>` : ""}${r.unmarked_finals ? `<span class="chip bad">${r.unmarked_finals} classes' finals unmarked</span>` : ""}</p>
        ${r.final ? `<button class="primary" onclick="openNewGame()">Play another term</button>` : ""}</div></div>
    <div class="class-picker" role="group" aria-label="Choose a class">${r.classes.map((x) => `<button aria-pressed="${x.id === classSel}" data-cid="${x.id}">${x.id}</button>`).join("")}</div>
    <p><span class="chip">Class average ${c.avg}%</span><span class="chip ${c.va >= 0 ? "good" : "bad"}">Value added ${signed(c.va)}</span><span class="chip">${c.coverage}/20 topics taught</span></p>
    ${c.rows.map((s) => `<article class="report-card">${img("student", s.seed, s.mood)}
      <div><b>${esc(s.name)}</b> <small class="muted">Target ${s.target_grade}, effort ${s.effort.toLowerCase()}, behaviour ${s.behaviour.toLowerCase()}, attendance ${s.attendance}%</small>
        <p>${esc(s.comment)}</p></div>
      <div class="gbox" title="${s.final_is_prediction ? "Predicted" : "Final exam"}: ${s.final}%">${s.final_grade}</div></article>`).join("")}`;
  bindPicker(viewReport);
}

// ------------------------------------------------------------------ navigation + new game
function go(t) { tab = t; render(); }
document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => { if (S && S.phase !== "none") go(b.dataset.tab); }));

function openNewGame() {
  const seeds = Array.from({ length: 12 }, () => Math.floor(Math.random() * 1e6));
  $("#ng-sprites").innerHTML = seeds.map((s, i) => img("student", s, ["happy", "neutral", "sleepy", "stressed", "angry", "happy"][i % 6])).join("");
  $("#ng-cancel").hidden = !S || S.phase === "none";
  const d = $("#newgame");
  if (!d.open) d.showModal();
}
$("#ng-cancel").addEventListener("click", () => $("#newgame").close());
$("#newgame-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  S = await api("/api/new", { name: f.get("name"), subject: f.get("subject"), difficulty: f.get("difficulty") });
  $("#newgame").close();
  tab = "today"; draft = null; classSel = null; classCache = {};
  render();
  toast(`Welcome to Hillcrest, ${S.teacher.name}. Your first lesson starts at 8:50.`, "good");
});
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") e.target.close(); });

(async () => { S = await api("/api/state"); render(); })();
