"""
Teacher Simulator ΓÇö Flask web app.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""
import os
import pickle
import secrets
import statistics
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, session

from sim import sprites
from sim.engine import (AFTER_TASKS, APPROACHES, DAYS, FINAL_WEEK, FREE_TASKS, LUNCH_TASKS, MIDTERM_WEEK,
                        PARENTS_EVENING, PERIOD_TIMES, TERM_WEEKS, TOPICS, Game, grade_for)
from sim.content import TOPICS as SUBJECT_TOPICS, TRAITS

app = Flask(__name__)
SAVE_DIR = Path(__file__).parent / "saves"
SAVE_DIR.mkdir(exist_ok=True)
_secret_file = SAVE_DIR / ".secret"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_hex(24))
# a stable secret keeps your session (and your save) across server restarts
app.secret_key = os.environ.get("TEACHER_SIM_SECRET") or _secret_file.read_text().strip()
GAMES: dict[str, Game] = {}


# ---------------------------------------------------------------- persistence
def _path(gid):
    return SAVE_DIR / f"{gid}.pkl"


def save(gid, game):
    with open(_path(gid), "wb") as f:
        pickle.dump(game, f)


def current_game():
    gid = session.get("gid")
    if not gid:
        return None, None
    if gid not in GAMES and _path(gid).exists():
        with open(_path(gid), "rb") as f:
            GAMES[gid] = pickle.load(f)
    return gid, GAMES.get(gid)


def err(msg, code=400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------- serialisers
def student_brief(g: Game, s):
    c = g.classes[s.cid]
    now = g.current_score(s)
    return {
        "id": s.id, "name": s.name, "seed": s.seed, "mood": g.mood(s), "present": s.present,
        "traits": s.traits, "motivation": round(s.motivation), "behaviour": round(s.behaviour),
        "wellbeing": round(s.wellbeing), "attendance": round(s.attendance * 100),
        "target": s.target, "target_grade": grade_for(s.target),
        "current": round(now), "predicted": g.predicted_final(s) if c.coverage else None,
        "predicted_grade": grade_for(g.predicted_final(s)) if c.coverage else "-",
        "detention_due": s.detention_due,
    }


def class_brief(g: Game, c):
    studs = [g.students[x] for x in c.students]
    return {
        "id": c.id, "year": c.year, "size": len(studs), "coverage": c.coverage,
        "expected": g.expected_coverage(), "plans": c.plans, "climate": round(c.climate),
        "tutor": c.tutor, "lost": c.lost_lessons,
        "avg": round(statistics.mean(g.current_score(s) for s in studs)) if c.coverage else None,
        "moods": [g.mood(s) for s in studs],
        "default": g.default_plan.get(c.id, "lecture"),
    }


def state(g: Game):
    t = g.teacher
    free_opts = [{"key": k, "label": v} for k, v in FREE_TASKS.items() if k != "plan"]
    free_opts[0:0] = [{"key": "plan", "label": "Plan lessons (neediest class)"}] + \
        [{"key": f"plan:{cid}", "label": f"Plan lessons for {cid}"} for cid in g.classes]
    calendar = []
    for w in range(1, TERM_WEEKS + 1):
        marks = []
        if w == MIDTERM_WEEK:
            marks.append("Midterms")
        if w == FINAL_WEEK:
            marks.append("Finals")
        if w == PARENTS_EVENING[0]:
            marks.append("Parents' evening")
        if w == TERM_WEEKS:
            marks.append("Reports due")
        calendar.append({"week": w, "marks": marks})
    return {
        "phase": g.phase, "day": g.day, "week": g.week, "weekday": DAYS[g.weekday] if g.phase == "term" else "",
        "difficulty": g.difficulty, "term_weeks": TERM_WEEKS, "calendar": calendar,
        "teacher": {
            "name": t.name, "subject": t.subject, "seed": t.seed, "mood": g.teacher_mood(),
            "energy": round(t.energy), "stress": round(t.stress), "level": t.level, "xp": t.xp,
            "rep": {k: round(v) for k, v in t.rep.items()}, "sick_days": t.sick_days,
            "marking_papers": g.marking_papers(), "admin_points": g.admin_points(),
            "marking": [{"label": b.label, "remaining": b.remaining, "total": b.total, "kind": b.kind} for b in t.marking],
            "admin": [{"title": a.title, "cost": a.cost, "kind": a.kind,
                       "due_in": None if a.due is None else a.due - g.day} for a in t.admin],
            "reports_left": sum(1 for s in g.students.values() if not s.report_written),
        },
        "today": g.day_info() if g.phase == "term" else None,
        "classes": [class_brief(g, c) for c in g.classes.values()],
        "options": {
            "approaches": [{"key": k, "label": v["label"], "new": v["new"], "plans": v["plans"],
                            "energy": v["energy"]} for k, v in APPROACHES.items()],
            "free": free_opts,
            "lunch": [{"key": k, "label": v} for k, v in LUNCH_TASKS.items()],
            "after": [{"key": k, "label": v} for k, v in AFTER_TASKS.items()],
        },
        "pending": sorted(g.pending, key=lambda e: -e["priority"]),
        "log": list(reversed(g.log[-80:])),
        "last_day": g.last_day_summary,
        "history": g.history,
        "timetable": {"mine": g.my_tt, "duty_days": g.duty_days, "times": PERIOD_TIMES, "days": DAYS,
                      "classes": g.class_tt},
        "staff": [{"name": s.name, "subject": s.subject, "role": s.role, "seed": s.seed} for s in g.staff],
        "topics": g.topics,
        "report_ready": g.final_report is not None,
    }


# ---------------------------------------------------------------- routes
@app.get("/")
def index():
    return render_template("index.html", subjects=list(SUBJECT_TOPICS))


@app.get("/sprite/<role>/<int:seed>/<mood>.svg")
def sprite(role, seed, mood):
    if role not in ("student", "teacher") or mood not in ("happy", "neutral", "sad", "angry", "stressed", "sleepy"):
        return err("Unknown sprite", 404)
    svg = sprites.render(seed, role, mood)
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.post("/api/new")
def new_game():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()[:30] or "Ms. Sensei"
    subject = data.get("subject") if data.get("subject") in SUBJECT_TOPICS else "Maths"
    difficulty = data.get("difficulty") if data.get("difficulty") in ("relaxed", "standard", "inspection") else "standard"
    gid = secrets.token_hex(8)
    g = Game(name, subject, difficulty)
    GAMES[gid] = g
    session["gid"] = gid
    save(gid, g)
    return jsonify(state(g))


@app.get("/api/state")
def get_state():
    gid, g = current_game()
    if not g:
        return jsonify({"phase": "none"})
    return jsonify(state(g))


@app.post("/api/day")
def run_day():
    gid, g = current_game()
    if not g:
        return err("Start a new game first.")
    try:
        g.run_day(request.get_json(force=True, silent=True) or {})
    except ValueError as e:
        return err(str(e))
    save(gid, g)
    return jsonify(state(g))


@app.post("/api/event/<int:eid>")
def resolve(eid):
    gid, g = current_game()
    if not g:
        return err("Start a new game first.")
    choice = (request.get_json(force=True, silent=True) or {}).get("choice")
    try:
        result = g.resolve_event(eid, choice)
    except ValueError as e:
        return err(str(e))
    save(gid, g)
    out = state(g)
    out["result"] = result
    return jsonify(out)


@app.get("/api/class/<cid>")
def class_detail(cid):
    gid, g = current_game()
    if not g or cid not in g.classes:
        return err("Class not found.", 404)
    c = g.classes[cid]
    def with_tests(s):
        return {**student_brief(g, s), "tests": [{"label": x["label"], "kind": x["kind"],
                                                  "score": x["score"] if x["marked"] else None} for x in s.tests]}
    return jsonify({**class_brief(g, c), "students": [with_tests(g.students[s]) for s in c.students],
                    "next_topic": g.topics[c.coverage] if c.coverage < TOPICS else None,
                    "timetable": g.class_tt[cid]})


@app.get("/api/student/<sid>")
def student_detail(sid):
    gid, g = current_game()
    if not g or sid not in g.students:
        return err("Student not found.", 404)
    s = g.students[sid]
    c = g.classes[s.cid]
    topics = [{"name": g.topics[i], "value": round(s.understanding[i] * 100), "covered": i < c.coverage}
              for i in range(TOPICS)]
    return jsonify({**student_brief(g, s), "cid": s.cid, "aptitude": s.aptitude,
                    "trait_info": {t: TRAITS[t]["desc"] for t in s.traits},
                    "topics": topics,
                    "tests": [{"label": x["label"], "score": x["score"] if x["marked"] else None, "week": x["week"],
                               "kind": x["kind"], "grade": grade_for(x["score"]) if x["marked"] else "-"} for x in s.tests],
                    "notes": s.notes[-12:], "detentions": s.detentions,
                    "report": s.report_comment})


@app.get("/api/report")
def report():
    gid, g = current_game()
    if not g:
        return err("Start a new game first.")
    return jsonify(g.final_report or g.build_report(final=False))


if __name__ == "__main__":
    import argparse
    import socket

    ap = argparse.ArgumentParser(description="Run the Teacher Simulator server.")
    ap.add_argument("--lan", action="store_true", help="listen on all interfaces so other devices on your network can play")
    ap.add_argument("--host", default=os.environ.get("HOST"), help="address to bind (overrides --lan)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    ap.add_argument("--debug", action="store_true", help="auto-reload and debugger (local use only)")
    args = ap.parse_args()

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    exposed = host not in ("127.0.0.1", "localhost")
    if exposed and args.debug:
        # the Werkzeug debugger lets anyone who can reach it run code on this machine
        print("Refusing to enable --debug on a network address. Running without it.")
        args.debug = False
    if exposed:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            lan_ip = s.getsockname()[0]
            s.close()
        except OSError:
            lan_ip = "<your-ip>"
        print(f"Other devices on your network can play at http://{lan_ip}:{args.port}")
    app.run(host=host, port=args.port, debug=args.debug)
