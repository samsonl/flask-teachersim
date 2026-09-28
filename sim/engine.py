"""
Teacher Simulator ΓÇö simulation engine.

One term = 12 weeks x 5 days x 5 periods. You teach one subject to five classes.
Each day you choose how to teach every lesson and what to do in each free period,
at lunch and after school. The day then runs: students learn (or don't), issues
come up, marking and admin pile up. Midterms happen at the end of week 6, finals
at the end of week 11, and reports are due by the end of week 12.
"""
from __future__ import annotations

import itertools
import math
import random
import statistics
from dataclasses import dataclass, field

from . import content

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
PERIOD_TIMES = ["8:50", "9:50", "11:10", "12:10", "14:00"]
LUNCH_AFTER = 3            # lunch happens after period index 3
TERM_WEEKS = 12
MIDTERM_WEEK = 6
FINAL_WEEK = 11
PARENTS_EVENING = (8, 3)   # week 8, Thursday
STAFF_MEETING_DAY = 2      # Wednesdays
TOTAL_DAYS = TERM_WEEKS * 5
TOPICS = 20
MIDTERM_TOPICS = 10
MARK_WEIGHT = {"quiz": 1, "midterm": 3, "final": 3}

GRADES = [(85, "A*"), (75, "A"), (65, "B"), (55, "C"), (45, "D"), (35, "E"), (0, "U")]

APPROACHES = {
    "lecture":   dict(label="Direct instruction", new=True,  gain=0.72, energy=6,  engage=-0.8, disrupt=1.0, plans=1),
    "group":     dict(label="Group work",         new=True,  gain=0.74, energy=9,  engage=1.4,  disrupt=1.6, plans=1),
    "practical": dict(label="Hands-on practical", new=True,  gain=0.85, energy=12, engage=2.4,  disrupt=1.3, plans=2),
    "revision":  dict(label="Revision",           new=False, gain=0.40, energy=6,  engage=-0.4, disrupt=1.0, plans=1),
    "quiz":      dict(label="Quiz",               new=False, gain=0.10, energy=4,  engage=-0.6, disrupt=0.6, plans=0),
    "film":      dict(label="Film / free lesson", new=False, gain=0.00, energy=1,  engage=2.0,  disrupt=0.8, plans=0),
}

FREE_TASKS = {
    "plan":    "Plan lessons",
    "mark":    "Mark work",
    "admin":   "Admin and emails",
    "reports": "Write reports",
    "rest":    "Staffroom break",
}
LUNCH_TASKS = {
    "eat":       "Eat lunch",
    "club":      "Run a lunch club",
    "catchup":   "Catch-up session",
    "detention": "Supervise detentions",
    "mark":      "Working lunch (mark)",
}
AFTER_TASKS = {
    "home":  "Go home on time",
    "late":  "Stay late to catch up",
    "plan":  "Plan next week",
    "gym":   "Look after yourself",
    "club":  "After-school club",
}


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def grade_for(score):
    if score is None:
        return "-"
    for cut, g in GRADES:
        if score >= cut:
            return g
    return "U"


# --------------------------------------------------------------------------- models

@dataclass
class Task:
    id: int
    title: str
    cost: int
    kind: str = "admin"
    due: int | None = None  # absolute day index


@dataclass
class MarkBatch:
    id: int
    cid: str
    label: str
    kind: str
    remaining: int
    total: int
    topics: list


@dataclass
class Student:
    id: str
    name: str
    cid: str
    seed: int
    aptitude: float
    motivation: float
    behaviour: float
    wellbeing: float
    attendance: float
    traits: list
    understanding: list
    target: int
    tests: list = field(default_factory=list)
    detention_due: bool = False
    detentions: int = 0
    notes: list = field(default_factory=list)
    present: bool = True
    report_written: bool = False
    report_comment: str = ""

    def has(self, t):
        return t in self.traits


@dataclass
class SchoolClass:
    id: str
    year: int
    students: list
    coverage: int = 0
    plans: int = 3
    climate: float = 60.0
    tutor: bool = False
    lessons: int = 0
    lost_lessons: int = 0


@dataclass
class Teacher:
    name: str
    subject: str
    seed: int
    energy: float = 85.0
    stress: float = 20.0
    xp: int = 0
    rep: dict = field(default_factory=lambda: {"students": 50.0, "parents": 50.0, "leadership": 50.0})
    admin: list = field(default_factory=list)
    marking: list = field(default_factory=list)
    sick_days: int = 0

    @property
    def level(self):
        return min(5, 1 + self.xp // 45)


@dataclass
class Staff:
    name: str
    subject: str
    role: str
    seed: int


# --------------------------------------------------------------------------- game

class Game:
    def __init__(self, teacher_name="You", subject="Maths", difficulty="standard", seed=None):
        self.seed = seed if seed is not None else random.randrange(10**9)
        self.rng = random.Random(self.seed)
        self.difficulty = difficulty
        self.diff = {"relaxed": 0.7, "standard": 1.0, "inspection": 1.35}[difficulty]
        self.day = 0
        self.phase = "term"
        self._ids = itertools.count(1)
        self.teacher = Teacher(teacher_name, subject, self.rng.randrange(10**6))
        self.topics = content.TOPICS[subject]
        self.students: dict[str, Student] = {}
        self.classes: dict[str, SchoolClass] = {}
        self.staff: list[Staff] = []
        self.pending: list[dict] = []
        self.scheduled: list[dict] = []
        self.log: list[dict] = []
        self.history: list[dict] = []
        self.cover_slots: set = set()
        self.observations: set = set()
        self.last_day_summary: dict | None = None
        self.default_plan: dict = {}
        self.final_report: dict | None = None
        self._build_school()
        self._say("term", f"Welcome to Hillcrest Academy, {teacher_name}. Term starts today.")
        self._daily_admin_arrivals(first=True)

    # ------------------------------------------------------------------ setup
    def _uid(self):
        return next(self._ids)

    def _build_school(self):
        rng = self.rng
        used = set()

        def fresh_name():
            while True:
                n = f"{rng.choice(content.FIRST_NAMES)} {rng.choice(content.SURNAMES)}"
                if n not in used:
                    used.add(n)
                    return n

        class_ids = ["7A", "8C", "9B", "10A", "11D"]
        tutor = rng.choice(class_ids)
        for cid in class_ids:
            year = int(cid[:-1])
            c = SchoolClass(id=cid, year=year, students=[], tutor=(cid == tutor),
                            climate=rng.uniform(48, 72))
            for i in range(rng.randint(18, 24)):
                sid = f"{cid}-{i + 1:02d}"
                traits = rng.sample(list(content.TRAITS), k=rng.choice([1, 1, 2]))
                apt = clamp(rng.gauss(0.95, 0.2), 0.5, 1.45)
                if "Gifted" in traits:
                    apt = clamp(apt + 0.3, 0.5, 1.6)
                base = content.TRAITS
                mot = clamp(rng.gauss(58, 14) + sum(base[t].get("motivation", 0) for t in traits))
                beh = clamp(rng.gauss(65, 14) + sum(base[t].get("behaviour", 0) for t in traits))
                wb = clamp(rng.gauss(66, 12) + sum(base[t].get("wellbeing", 0) for t in traits))
                att = clamp(rng.gauss(0.95, 0.03) + sum(base[t].get("attendance", 0) for t in traits), 0.7, 0.995)
                prior = [clamp(rng.uniform(0.0, 0.12) * apt, 0, 0.3) for _ in range(TOPICS)]
                target = int(clamp(30 + 38 * (apt - 0.5) + (mot - 55) * 0.2 + rng.gauss(0, 4), 20, 95))
                s = Student(sid, fresh_name(), cid, rng.randrange(10**6), round(apt, 2),
                            mot, beh, wb, att, traits, prior, target)
                self.students[sid] = s
                c.students.append(sid)
            self.classes[cid] = c

        # staff
        others = [s for s in content.ALL_SUBJECTS if s != self.teacher.subject]
        self.staff.append(Staff(fresh_name(), self.teacher.subject, "Head of Department", rng.randrange(10**6)))
        self.staff.append(Staff(fresh_name(), "Leadership", "Deputy Head", rng.randrange(10**6)))
        self.staff.append(Staff(fresh_name(), "Pastoral", "Safeguarding Lead", rng.randrange(10**6)))
        for subj in others:
            self.staff.append(Staff(fresh_name(), subj, f"{subj} teacher", rng.randrange(10**6)))

        # timetable: each class gets 3 of your lessons on different days, no clashes
        for _ in range(200):
            taken, grid, ok = set(), [[None] * 5 for _ in range(5)], True
            for cid in class_ids:
                slots = [(d, p) for d in range(5) for p in range(5) if (d, p) not in taken]
                rng.shuffle(slots)
                chosen, days = [], set()
                for d, p in slots:
                    if d not in days:
                        chosen.append((d, p)); days.add(d)
                    if len(chosen) == 3:
                        break
                if len(chosen) < 3:
                    ok = False
                    break
                for d, p in chosen:
                    taken.add((d, p)); grid[d][p] = cid
            if ok:
                break
        self.my_tt = grid
        self.duty_days = sorted(rng.sample(range(5), 2))
        subj_teacher = {s.subject: s for s in self.staff}
        self.class_tt = {}
        for cid in class_ids:
            g = []
            for d in range(5):
                row = []
                for p in range(5):
                    if grid[d][p] == cid:
                        row.append({"subject": self.teacher.subject, "teacher": self.teacher.name, "mine": True})
                    else:
                        subj = rng.choice(others)
                        row.append({"subject": subj, "teacher": subj_teacher[subj].name, "mine": False})
                g.append(row)
            self.class_tt[cid] = g
        for cid in class_ids:
            self.default_plan[cid] = "lecture"

    # ------------------------------------------------------------------ helpers
    @property
    def week(self):
        return min(TERM_WEEKS, self.day // 5 + 1)

    @property
    def weekday(self):
        return self.day % 5

    def _say(self, kind, text, tone="info"):
        self.log.append({"day": self.day, "week": self.week, "weekday": DAYS[self.weekday] if self.day < TOTAL_DAYS else "",
                         "kind": kind, "text": text, "tone": tone})
        self.log = self.log[-400:]

    def _add_task(self, title, cost, kind="admin", due_in=None):
        t = Task(self._uid(), title, cost, kind, None if due_in is None else self.day + due_in)
        self.teacher.admin.append(t)
        return t

    def expected_coverage(self, day=None):
        d = self.day if day is None else day
        lessons_so_far = (d // 5) * 3 + 1.5
        return min(TOPICS, round(lessons_so_far * TOPICS / (FINAL_WEEK * 3 - 6)))

    def marking_papers(self):
        return sum(b.remaining * MARK_WEIGHT[b.kind] for b in self.teacher.marking)

    def admin_points(self):
        return sum(t.cost for t in self.teacher.admin)

    def mood(self, s: Student):
        if not s.present:
            return "sleepy"
        if s.wellbeing < 35:
            return "sad"
        if s.behaviour < 38 and s.motivation < 50:
            return "angry"
        if s.wellbeing < 52 and (s.has("Anxious") or s.has("Perfectionist")):
            return "stressed"
        if s.has("Night owl") and s.motivation < 55:
            return "sleepy"
        if s.motivation > 64 and s.wellbeing > 58:
            return "happy"
        return "neutral"

    def teacher_mood(self):
        t = self.teacher
        if t.stress > 75:
            return "stressed"
        if t.energy < 25:
            return "sleepy"
        if t.stress > 55:
            return "sad"
        if t.energy > 60 and t.stress < 40:
            return "happy"
        return "neutral"

    def current_score(self, s: Student, topics=None):
        topics = topics if topics is not None else range(max(1, self.classes[s.cid].coverage))
        vals = [s.understanding[t] for t in topics]
        return 100 * statistics.mean(vals) if vals else 0.0

    def predicted_final(self, s: Student):
        c = self.classes[s.cid]
        covered = max(1, c.coverage)
        now = self.current_score(s, range(covered))
        # project the rest of the syllabus from current form, then lean on the
        # target grade while there's still little evidence
        projected = (now * covered + now * 0.95 * (TOPICS - covered)) / TOPICS
        evidence = min(1.0, covered / 8)
        return round(evidence * projected + (1 - evidence) * s.target)

    # ------------------------------------------------------------------ day
    def day_info(self, d=None):
        d = self.day if d is None else d
        wk, wd = d // 5 + 1, d % 5
        periods = []
        for p in range(5):
            cid = self.my_tt[wd][p]
            periods.append({
                "period": p + 1, "time": PERIOD_TIMES[p], "class": cid,
                "cover": (d, p) in self.cover_slots,
                "observed": bool(cid and (d, cid) in self.observations),
            })
        fixed = []
        if wd in self.duty_days:
            fixed.append("Lunch duty (playground)")
        if wd == STAFF_MEETING_DAY:
            fixed.append("Staff meeting after school")
        if (wk, wd) == PARENTS_EVENING:
            fixed.append("Parents' evening after school")
        if wk == MIDTERM_WEEK and wd == 4:
            fixed.append("Midterm exams sat at the end of the day")
        if wk == FINAL_WEEK and wd == 4:
            fixed.append("Final exams sat at the end of the day")
        return {"day": d, "week": wk, "weekday": DAYS[wd] if d < TOTAL_DAYS else "", "periods": periods,
                "fixed": fixed, "duty": wd in self.duty_days,
                "staff_meeting": wd == STAFF_MEETING_DAY,
                "parents_evening": (wk, wd) == PARENTS_EVENING}

    def run_day(self, plan: dict):
        if self.phase != "term":
            raise ValueError("The term is over. Start a new game to play again.")
        if self.pending:
            raise ValueError("Deal with the open issues before starting the next day.")
        rng, t = self.rng, self.teacher
        info = self.day_info()
        wk, wd = info["week"], self.weekday
        summary = {"day": self.day, "week": wk, "weekday": DAYS[wd], "lessons": [], "tasks": [], "notes": []}
        start = {"energy": t.energy, "stress": t.stress, **{k: v for k, v in t.rep.items()}}

        for s in self.students.values():
            chance = s.attendance * (0.85 + 0.15 * s.wellbeing / 100)
            s.present = rng.random() < chance

        sick = t.stress >= 95 or t.energy <= 3
        if sick:
            self._sick_day(summary)
        else:
            periods = plan.get("periods", [{}] * 5)
            fire_drill = rng.random() < 0.012
            drill_period = rng.randrange(5)
            for p in range(5):
                cid = self.my_tt[wd][p]
                choice = periods[p] if p < len(periods) else {}
                if (self.day, p) in self.cover_slots:
                    t.energy -= 7
                    t.rep["leadership"] = clamp(t.rep["leadership"] + 1.5)
                    summary["tasks"].append({"period": p + 1, "label": "Covered a colleague's lesson", "detail": "Free period used for cover."})
                elif cid:
                    approach = choice.get("approach") or self.default_plan.get(cid, "lecture")
                    self.default_plan[cid] = approach
                    res = self._run_lesson(cid, approach, interrupted=(fire_drill and p == drill_period))
                    res["period"] = p + 1
                    summary["lessons"].append(res)
                else:
                    task = choice.get("task") or "mark"
                    summary["tasks"].append({"period": p + 1, **self._do_task(task)})
                if p == LUNCH_AFTER:
                    summary["tasks"].append({"period": "Lunch", **self._do_lunch(plan.get("lunch", "eat"), wd in self.duty_days)})
            if fire_drill:
                summary["notes"].append(f"Fire drill during period {drill_period + 1}. That lesson was cut short.")
            summary["tasks"].append({"period": "After school", **self._after_school(plan.get("after", "home"), info)})

        # exams at the end of Friday
        if wd == 4 and wk == MIDTERM_WEEK:
            self._sit_exams("midterm", range(MIDTERM_TOPICS))
            summary["notes"].append("Midterm exams sat. Papers added to your marking pile.")
        if wd == 4 and wk == FINAL_WEEK:
            self._sit_exams("final", range(TOPICS))
            summary["notes"].append("Final exams sat. Papers added to your marking pile ΓÇö results are needed for reports.")

        self._end_of_day(summary)
        summary["delta"] = {
            "energy": round(t.energy - start["energy"]), "stress": round(t.stress - start["stress"]),
            **{k: round(t.rep[k] - start[k], 1) for k in t.rep},
        }
        self.last_day_summary = summary
        return summary

    def _sick_day(self, summary):
        t = self.teacher
        t.sick_days += 1
        wd = self.weekday
        for p in range(5):
            cid = self.my_tt[wd][p]
            if cid:
                c = self.classes[cid]
                c.lost_lessons += 1
                c.climate = clamp(c.climate - 3)
                summary["lessons"].append({"period": p + 1, "class": cid, "approach": "Supply teacher",
                                           "summary": "A supply teacher ran a worksheet lesson. Little was learned.",
                                           "gain": 0, "present": sum(self.students[s].present for s in c.students),
                                           "size": len(c.students)})
        t.energy = clamp(t.energy + 40)
        t.stress = clamp(t.stress - 30)
        t.rep["leadership"] = clamp(t.rep["leadership"] - 4)
        summary["notes"].append("You were signed off sick today ΓÇö burnout caught up with you.")
        self._say("teacher", "Off sick. Stress and exhaustion forced a day at home.", "bad")

    # ------------------------------------------------------------------ lessons
    def _run_lesson(self, cid, approach, interrupted=False):
        rng, t = self.rng, self.teacher
        c = self.classes[cid]
        a = APPROACHES.get(approach, APPROACHES["lecture"])
        need = a["plans"]
        planned = c.plans >= need
        if planned:
            c.plans -= need
        elif need:
            c.plans = 0
        quality = (0.85 + 0.05 * t.level) * (1.0 if planned else 0.68) * (0.6 + 0.4 * t.energy / 100)
        issues = []
        if rng.random() < 0.03 and approach != "film":
            quality *= 0.75
            issues.append("The projector died halfway through.")
        if interrupted:
            quality *= 0.5
        present = [self.students[s] for s in c.students if self.students[s].present]
        topic = None
        gains = []
        if a["new"] and c.coverage < TOPICS:
            topic = c.coverage
            c.coverage += 1
        elif a["new"]:
            issues.append("Syllabus finished, so the lesson became consolidation.")
        covered = list(range(c.coverage))
        for s in present:
            focus = clamp(0.45 + 0.35 * s.motivation / 100 + 0.1 * s.behaviour / 100 + 0.1 * c.climate / 100, 0.1, 1.1)
            mod = 1.0
            if s.has("EAL") and approach == "lecture":
                mod *= 0.75
            if s.has("Hands-on"):
                mod *= 1.3 if approach == "practical" else (0.85 if approach == "lecture" else 1.0)
            if s.has("Chatterbox") and approach == "group":
                mod *= 0.85
            if s.has("Quiet") and approach == "group":
                mod *= 0.9
            g = a["gain"] * s.aptitude * focus * quality * mod
            before = self.current_score(s, covered) if covered else 0
            if topic is not None:
                s.understanding[topic] = clamp(s.understanding[topic] + g * (1 - s.understanding[topic]), 0, 1)
                if topic > 0:
                    s.understanding[topic - 1] = clamp(s.understanding[topic - 1] + 0.1 * g * (1 - s.understanding[topic - 1]), 0, 1)
            elif covered and a["gain"] > 0:
                weakest = sorted(covered, key=lambda i: s.understanding[i])[:3]
                for i in weakest:
                    s.understanding[i] = clamp(s.understanding[i] + g * (1 - s.understanding[i]), 0, 1)
            after = self.current_score(s, covered) if covered else 0
            gains.append(after - before)
            s.motivation = clamp(s.motivation + a["engage"] * rng.uniform(0.4, 1.4) + (0.4 if planned else -0.5))
            if approach == "revision" and self.week in (MIDTERM_WEEK, FINAL_WEEK, MIDTERM_WEEK - 1, FINAL_WEEK - 1):
                s.wellbeing = clamp(s.wellbeing + 1.5)
        c.climate = clamp(c.climate + a["engage"] * 0.6 + (0.6 if planned else -1.2)
                          + (statistics.mean(self.students[x].behaviour for x in c.students) - c.climate) * 0.04)
        c.lessons += 1
        t.energy = clamp(t.energy - a["energy"] * (1.15 if c.climate < 40 else 1.0))
        t.stress = clamp(t.stress + (1.0 if planned else 2.5) + (1.5 if c.climate < 40 else 0))
        t.xp += 1

        if approach == "quiz" and covered:
            recent = covered[-5:]
            bid = self._uid()
            for s in present:
                score = self._paper_score(s, recent, exam=False)
                s.tests.append({"label": f"Quiz wk{self.week}", "kind": "quiz", "score": score, "week": self.week,
                                "marked": False, "batch": bid})
            t.marking.append(MarkBatch(bid, cid, f"{cid} quiz (week {self.week})", "quiz", len(present), len(present), recent))
            if rng.random() < 0.18 * self.diff and present:
                cheat = rng.choice(present)
                self._queue_event("cheating", student=cheat.id, cid=cid, batch=bid)

        # observation
        if (self.day, cid) in self.observations:
            self.observations.discard((self.day, cid))
            score = quality * 60 + c.climate * 0.3 + (15 if a["new"] or approach == "revision" else 0)
            score -= 30 if approach == "film" else 0
            verdict = "Outstanding" if score > 85 else "Good" if score > 68 else "Requires improvement" if score > 50 else "Inadequate"
            delta = {"Outstanding": 8, "Good": 4, "Requires improvement": -3, "Inadequate": -9}[verdict]
            t.rep["leadership"] = clamp(t.rep["leadership"] + delta)
            t.stress = clamp(t.stress + 4)
            issues.append(f"Observed by your Head of Department: {verdict}.")
            self._say("observation", f"Lesson observation with {cid}: {verdict}.", "good" if delta > 0 else "bad")

        # disruption risk
        risk = 0.13 * a["disrupt"] * (1.45 - c.climate / 100) * (1.35 if not planned else 1) \
            * (1.25 if t.energy < 30 else 1) * self.diff
        if present and rng.random() < risk:
            weights = [(100 - s.behaviour + 5) * math.prod(content.TRAITS[x].get("disrupt", 1.0) for x in s.traits)
                       for s in present]
            culprit = rng.choices(present, weights=weights)[0]
            c.climate = clamp(c.climate - 3)
            self._queue_event(rng.choice(["disruption", "disruption", "phone", "defiance"]), student=culprit.id, cid=cid)
        if present and rng.random() < 0.035:
            self._queue_event("sick_student", student=rng.choice(present).id, cid=cid)

        avg_gain = statistics.mean(gains) if gains else 0.0
        topic_name = self.topics[topic] if topic is not None else None
        text = {
            "lecture": f"Taught {topic_name}." if topic_name else "Went over earlier material.",
            "group": f"Groups explored {topic_name}." if topic_name else "Group consolidation tasks.",
            "practical": f"Hands-on lesson on {topic_name}." if topic_name else "Practical consolidation.",
            "revision": "Revised the class's weakest topics.",
            "quiz": "Ran a quiz on recent topics. Scripts added to marking.",
            "film": "Put a film on. The class enjoyed it; nobody learned much.",
        }[approach]
        if not planned and need:
            text += " You winged it without a plan."
        return {"class": cid, "approach": a["label"], "summary": text, "issues": issues,
                "gain": round(avg_gain, 1), "present": len(present), "size": len(c.students),
                "topic": topic_name, "planned": planned}

    def _paper_score(self, s: Student, topics, exam=True):
        vals = [s.understanding[t] for t in topics] or [0]
        base = 100 * statistics.mean(vals)
        penalty = 0
        if exam and (s.has("Anxious") or s.has("Perfectionist")):
            penalty += 10 * (1 - s.wellbeing / 100)
        if exam and s.wellbeing < 40:
            penalty += 4
        return int(clamp(base + self.rng.gauss(0, 5 if exam else 7) - penalty + (3 if exam else 0)))

    def _sit_exams(self, kind, topics):
        topics = list(topics)
        for cid, c in self.classes.items():
            bid = self._uid()
            sitting = 0
            for sid in c.students:
                s = self.students[sid]
                score = self._paper_score(s, topics, exam=True)
                s.tests.append({"label": kind.capitalize(), "kind": kind, "score": score, "week": self.week,
                                "marked": False, "batch": bid})
                sitting += 1
            self.teacher.marking.append(MarkBatch(bid, cid, f"{cid} {kind} exam", kind, sitting, sitting, topics))
        self._say("exam", f"{kind.capitalize()} exams sat by all classes.", "info")

    # ------------------------------------------------------------------ non-teaching work
    def _mark(self, capacity):
        t = self.teacher
        done = 0
        released = []
        cap = capacity * (0.6 + 0.4 * t.energy / 100)
        while t.marking and cap > 0:
            b = t.marking[0]
            w = MARK_WEIGHT[b.kind]
            n = min(b.remaining, int(cap // w) or (1 if cap >= w * 0.5 else 0))
            if n == 0:
                break
            b.remaining -= n
            cap -= n * w
            done += n
            if b.remaining <= 0:
                t.marking.pop(0)
                released.append(b.label)
                self._release(b)
        return done, released

    def _release(self, b: MarkBatch):
        for sid in self.classes[b.cid].students:
            s = self.students[sid]
            for test in s.tests:
                if test["batch"] == b.id and not test["marked"]:
                    test["marked"] = True
                    for i in b.topics:
                        s.understanding[i] = clamp(s.understanding[i] + 0.09 * (1 - s.understanding[i]), 0, 1)
        self._say("marking", f"Marked and returned: {b.label}. Feedback helps students fix mistakes.", "good")

    def _do_admin(self, points):
        t = self.teacher
        t.admin.sort(key=lambda x: (x.due if x.due is not None else 10**6, x.id))
        cleared = []
        while t.admin and points > 0:
            task = t.admin[0]
            if task.cost <= points:
                points -= task.cost
                cleared.append(task.title)
                t.admin.pop(0)
                if task.kind == "parent":
                    t.rep["parents"] = clamp(t.rep["parents"] + 0.6)
                elif task.kind == "data":
                    t.rep["leadership"] = clamp(t.rep["leadership"] + 0.8)
            else:
                task.cost -= points
                points = 0
        return cleared

    def _plan(self, credits, cid=None):
        given = []
        for _ in range(credits):
            c = self.classes[cid] if cid in self.classes else min(self.classes.values(), key=lambda k: k.plans)
            c.plans += 1
            given.append(c.id)
        return given

    def _write_reports(self, n):
        pending = [s for s in self.students.values() if not s.report_written]
        written = 0
        for s in pending[:n]:
            s.report_comment = self._report_comment(s)
            s.report_written = True
            written += 1
        return written, len(pending) - written

    def _do_task(self, task):
        t = self.teacher
        if task.startswith("plan"):
            cid = task.split(":", 1)[1] if ":" in task else None
            given = self._plan(2, cid)
            t.energy = clamp(t.energy - 3)
            return {"label": "Planned lessons", "detail": f"+2 lesson plans ({', '.join(sorted(set(given)))})."}
        if task == "mark":
            done, released = self._mark(24)
            t.energy = clamp(t.energy - 4)
            if not done:
                t.stress = clamp(t.stress - 3)
                return {"label": "Marked work", "detail": "Nothing to mark ΓÇö you tidied your classroom instead."}
            return {"label": "Marked work", "detail": f"Marked {done} scripts." + (f" Returned: {', '.join(released)}." if released else "")}
        if task == "admin":
            cleared = self._do_admin(4)
            t.energy = clamp(t.energy - 3)
            return {"label": "Admin and emails", "detail": f"Cleared {len(cleared)} task(s)." if cleared else "Chipped away at a long task."}
        if task == "reports":
            if self.week < FINAL_WEEK:
                t.stress = clamp(t.stress - 1)
                return {"label": "Write reports", "detail": "Too early ΓÇö reports open in week 11. You drafted some notes."}
            w, left = self._write_reports(14)
            t.energy = clamp(t.energy - 5)
            return {"label": "Wrote reports", "detail": f"Wrote {w} reports. {left} still to write."}
        # rest
        t.energy = clamp(t.energy + 10)
        t.stress = clamp(t.stress - 7)
        return {"label": "Staffroom break", "detail": "Coffee, biscuits and a moan with colleagues."}

    def _do_lunch(self, task, duty):
        t, rng = self.teacher, self.rng
        if duty:
            t.energy = clamp(t.energy - 6)
            if rng.random() < 0.3 * self.diff:
                s = rng.choice(list(self.students.values()))
                self._queue_event("corridor_fight", student=s.id, cid=s.cid)
            return {"label": "Lunch duty", "detail": "Patrolled the playground. Ate a sandwich standing up."}
        if task == "club":
            t.energy = clamp(t.energy - 4)
            t.rep["students"] = clamp(t.rep["students"] + 2)
            members = rng.sample(list(self.students.values()), 8)
            for s in members:
                s.motivation = clamp(s.motivation + 4)
                s.wellbeing = clamp(s.wellbeing + 3)
            return {"label": "Lunch club", "detail": "Eight students came along. They seem happier for it."}
        if task == "catchup":
            t.energy = clamp(t.energy - 5)
            pool = sorted(self.students.values(), key=lambda s: self.current_score(s) - s.target / 2)[:6]
            for s in pool:
                c = self.classes[s.cid]
                if c.coverage:
                    i = min(range(c.coverage), key=lambda k: s.understanding[k])
                    s.understanding[i] = clamp(s.understanding[i] + 0.25 * (1 - s.understanding[i]), 0, 1)
                s.motivation = clamp(s.motivation + 2)
            return {"label": "Catch-up session", "detail": f"Helped {len(pool)} struggling students with their weakest topics."}
        if task == "detention":
            due = [s for s in self.students.values() if s.detention_due]
            for s in due:
                s.detention_due = False
                s.detentions += 1
                s.behaviour = clamp(s.behaviour + 6)
                s.motivation = clamp(s.motivation - 2)
            t.energy = clamp(t.energy - 3)
            return {"label": "Detentions", "detail": f"{len(due)} student(s) served detention." if due else "Nobody was due. You ate in peace."}
        if task == "mark":
            done, _ = self._mark(10)
            t.energy = clamp(t.energy - 1)
            return {"label": "Working lunch", "detail": f"Marked {done} scripts between bites."}
        t.energy = clamp(t.energy + 9)
        t.stress = clamp(t.stress - 3)
        return {"label": "Lunch", "detail": "An actual lunch break."}

    def _after_school(self, task, info):
        t, rng = self.teacher, self.rng
        extra = []
        if info["staff_meeting"]:
            t.energy = clamp(t.energy - 5)
            self._add_task("Action points from staff meeting", 2, "data", due_in=5)
            extra.append("Sat through the staff meeting (new action points added).")
        if info["parents_evening"]:
            t.energy = clamp(t.energy - 15)
            progress = statistics.mean(self.current_score(s) - s.target * 0.8 for s in self.students.values())
            delta = clamp(progress / 3, -8, 8)
            t.rep["parents"] = clamp(t.rep["parents"] + delta + (t.rep["students"] - 50) / 20)
            for s in self.students.values():
                s.motivation = clamp(s.motivation + rng.uniform(-1, 3))
            extra.append("Parents' evening: " + ("parents were impressed with progress." if delta > 0 else "some difficult conversations about progress."))
            return {"label": "Parents' evening", "detail": " ".join(extra)}
        if task == "late":
            done, _ = self._mark(20)
            cleared = self._do_admin(3)
            t.energy = clamp(t.energy - 10)
            t.stress = clamp(t.stress + 1)
            extra.append(f"Stayed until 7pm: marked {done}, cleared {len(cleared)} admin task(s).")
        elif task == "plan":
            given = self._plan(3)
            t.energy = clamp(t.energy - 7)
            extra.append(f"Planned ahead: +3 plans ({', '.join(sorted(set(given)))}).")
        elif task == "gym":
            t.stress = clamp(t.stress - 10)
            t.energy = clamp(t.energy + 4)
            extra.append("Went for a run and switched your phone off.")
        elif task == "club":
            t.energy = clamp(t.energy - 8)
            t.rep["students"] = clamp(t.rep["students"] + 2.5)
            t.rep["parents"] = clamp(t.rep["parents"] + 1)
            extra.append("Ran an after-school club.")
        else:
            t.stress = clamp(t.stress - 4)
            extra.append("Home on time. Dinner, then a little admin on the sofa.")
        return {"label": AFTER_TASKS.get(task, "After school"), "detail": " ".join(extra)}

    # ------------------------------------------------------------------ end of day
    def _daily_admin_arrivals(self, first=False):
        rng = self.rng
        n = 3 if first else rng.choices([0, 1, 2, 3], weights=[2, 5, 3, 1])[0]
        for _ in range(int(round(n * self.diff))):
            title, cost, kind = rng.choice(content.ADMIN_TASKS)
            if "{cls}" in title:
                title = title.format(cls=rng.choice(list(self.classes)))
            if "{student}" in title:
                title = title.format(student=rng.choice(list(self.students.values())).name)
            self._add_task(title, cost, kind, due_in=rng.choice([3, 5, 7, None]))

    def _end_of_day(self, summary):
        rng, t = self.rng, self.teacher
        wk, wd = self.week, self.weekday

        # overdue admin
        overdue = [x for x in t.admin if x.due is not None and x.due < self.day]
        if overdue:
            t.rep["leadership"] = clamp(t.rep["leadership"] - 0.6 * len(overdue))
            t.rep["parents"] = clamp(t.rep["parents"] - 0.4 * sum(1 for x in overdue if x.kind == "parent"))
            for x in overdue:
                x.due = None
            summary["notes"].append(f"{len(overdue)} admin task(s) went past their deadline.")

        # student drift
        for s in self.students.values():
            s.wellbeing = clamp(s.wellbeing + (64 - s.wellbeing) * 0.03 + rng.uniform(-1.5, 1.5)
                                - (1.5 if wk in (MIDTERM_WEEK, FINAL_WEEK) else 0))
            s.motivation = clamp(s.motivation + (58 - s.motivation) * 0.02 + rng.uniform(-1, 1))
            s.behaviour = clamp(s.behaviour + (62 - s.behaviour) * 0.015 + rng.uniform(-0.8, 0.8))
            if s.detention_due and rng.random() < 0.15:
                s.detention_due = False
                s.behaviour = clamp(s.behaviour - 5)
                s.notes.append(f"Wk{wk}: skipped detention.")

        # random daily issues
        self._roll_daily_events()
        # scheduled follow-ups
        for sch in [x for x in self.scheduled if x["day"] <= self.day]:
            self.scheduled.remove(sch)
            self._queue_event(sch["kind"], student=sch.get("student"), cid=sch.get("cid"))

        # weekly
        if wd == 4:
            for s in self.students.values():
                s.understanding = [u * 0.985 for u in s.understanding]
            for c in self.classes.values():
                gap = self.expected_coverage(self.day) - c.coverage
                if gap > 2:
                    t.rep["leadership"] = clamp(t.rep["leadership"] - min(4, gap * 0.5))
                    t.rep["parents"] = clamp(t.rep["parents"] - min(3, gap * 0.3))
            # parents and students react to how their children are actually doing
            prog = statistics.mean(self.current_score(s) - s.target * 0.9 for s in self.students.values()) \
                if all(c.coverage for c in self.classes.values()) else -10
            t.rep["parents"] = clamp(t.rep["parents"] + clamp(prog / 6, -2.5, 2.0) + (50 - t.rep["parents"]) * 0.03)
            self._say("week", f"End of week {wk}. " + self._week_line(), "info")
        if wd == 4 and wk == FINAL_WEEK:
            self._add_task("Enter final grades into the system", 3, "data", due_in=6)

        # workload pressure and overnight recovery
        papers, points = self.marking_papers(), self.admin_points()
        t.stress = clamp(t.stress + papers / 42 + points / 11 - 1.9 + (2 if t.energy < 20 else 0))
        recovery = 27 if wd < 4 else 50  # weekends help
        t.energy = clamp(t.energy + recovery * (1 - t.stress / 180))
        t.energy = min(t.energy, 100 - t.stress * 0.25)
        self._daily_admin_arrivals()

        self.history.append({"day": self.day, "energy": round(t.energy), "stress": round(t.stress),
                             **{k: round(v) for k, v in t.rep.items()},
                             "avg": round(statistics.mean(self.current_score(s) for s in self.students.values()), 1)})
        for n in summary["notes"]:
            self._say("day", n)
        for les in summary["lessons"]:
            for i in les.get("issues", []):
                self._say("lesson", f"{les['class']}: {i}")

        self.day += 1
        if self.day >= TOTAL_DAYS:
            self._end_term()

    def _week_line(self):
        behind = [c.id for c in self.classes.values() if c.coverage < self.expected_coverage(self.day) - 1]
        if behind:
            return f"Behind on the syllabus with {', '.join(behind)}."
        return "All classes on track with the syllabus."

    # ------------------------------------------------------------------ events
    def _queue_event(self, kind, student=None, cid=None, **extra):
        d = content.EVENTS[kind]
        s = self.students.get(student) if student else None
        if cid is None and s:
            cid = s.cid
        fmt = {"name": s.name if s else "", "first": s.name.split()[0] if s else "",
               "cls": cid or "", "hod": self.staff[0].name, "deputy": self.staff[1].name,
               "dsl": self.staff[2].name, "colleague": self.rng.choice(self.staff[3:]).name}
        if any(e["kind"] == kind and e.get("student") == student and e.get("cid") == cid for e in self.pending):
            return
        ev = {"id": self._uid(), "kind": kind, "title": d["title"].format(**fmt), "text": d["text"].format(**fmt),
              "student": student, "cid": cid, "priority": d.get("priority", 1),
              "choices": [{"key": k, "label": v["label"].format(**fmt), "hint": v.get("hint", "")} for k, v in d["choices"].items()],
              "sprite": ({"role": "student", "seed": s.seed, "mood": self.mood(s)} if s else
                         {"role": "teacher", "seed": self.staff[d.get("staff", 0)].seed, "mood": d.get("mood", "neutral")}),
              **extra}
        self.pending.append(ev)

    def _roll_daily_events(self):
        rng, t, wk = self.rng, self.teacher, self.week
        studs = list(self.students.values())
        D = self.diff
        rolls = [
            ("parent_complaint", 0.10 * D * (1.5 - t.rep["parents"] / 100)),
            ("safeguarding", 0.045 * D),
            ("homework", 0.10 * D),
            ("extra_help", 0.08),
            ("bored_gifted", 0.05),
            ("thank_you", 0.03 + 0.05 * t.rep["students"] / 100),
            ("data_deadline", 0.05 * D),
            ("cover_request", 0.10 * D),
            ("observation", 0.06 if wk not in (3, 9) else 0.35),
            ("anxious_exam", 0.25 if wk in (MIDTERM_WEEK - 1, MIDTERM_WEEK, FINAL_WEEK - 1, FINAL_WEEK) else 0.0),
            ("colleague_favour", 0.04),
            ("trip_request", 0.03),
        ]
        added = 0
        for kind, p in rolls:
            if added >= 3:
                break
            if self.day + 1 >= TOTAL_DAYS and kind in ("cover_request", "observation"):
                continue
            if rng.random() >= p:
                continue
            student = None
            if kind == "safeguarding":
                student = min(rng.sample(studs, 12), key=lambda s: s.wellbeing).id
            elif kind == "bored_gifted":
                g = [s for s in studs if s.has("Gifted")]
                if not g:
                    continue
                student = rng.choice(g).id
            elif kind == "anxious_exam":
                a = [s for s in studs if s.has("Anxious") or s.has("Perfectionist")] or studs
                student = rng.choice(a).id
            elif kind in ("parent_complaint", "extra_help", "thank_you"):
                student = rng.choice(studs).id
            elif kind == "homework":
                student = min(rng.sample(studs, 8), key=lambda s: s.motivation).id
            cid = self.students[student].cid if student else None
            if kind == "observation":
                nd = self.day + 1
                lessons = [x for x in self.my_tt[nd % 5] if x]
                if not lessons:
                    continue
                cid = rng.choice(lessons)
            if kind == "cover_request":
                nd = self.day + 1
                frees = [p for p in range(5) if not self.my_tt[nd % 5][p] and (nd, p) not in self.cover_slots]
                if not frees:
                    continue
                self._queue_event(kind, cid=None, slot=[nd, rng.choice(frees)])
                added += 1
                continue
            self._queue_event(kind, student=student, cid=cid)
            added += 1

    def resolve_event(self, eid, choice):
        ev = next((e for e in self.pending if e["id"] == eid), None)
        if not ev:
            raise ValueError("That issue has already been dealt with.")
        d = content.EVENTS[ev["kind"]]
        if choice not in d["choices"]:
            raise ValueError("Pick one of the listed options.")
        opt = d["choices"][choice]
        outcomes = opt["outcomes"]
        # teacher state can tip the odds on skill-based choices
        weights = [o[0] for o in outcomes]
        if opt.get("skill") and len(weights) > 1:
            boost = (self.teacher.energy - 50) / 100 + (self.teacher.level - 1) * 0.05
            weights[0] = max(0.05, weights[0] + boost)
        p, effects, msg = self.rng.choices(outcomes, weights=weights)[0]
        s = self.students.get(ev.get("student")) if ev.get("student") else None
        c = self.classes.get(ev.get("cid")) if ev.get("cid") else None
        self._apply(effects, ev, s, c)
        self.pending.remove(ev)
        fmt = {"name": s.name if s else "", "first": s.name.split()[0] if s else "", "cls": ev.get("cid") or ""}
        text = msg.format(**fmt)
        if s:
            s.notes.append(f"Wk{self.week}: {ev['title']} ΓÇö {opt['label'].format(**fmt, hod='', deputy='', dsl='', colleague='')}.")
        tone = "good" if effects.get("tone", 0) > 0 else "bad" if effects.get("tone", 0) < 0 else "info"
        self._say("issue", text, tone)
        return {"text": text, "tone": tone}

    def _apply(self, fx, ev, s, c):
        t = self.teacher
        for k, v in fx.items():
            if k == "energy":
                t.energy = clamp(t.energy + v)
            elif k == "stress":
                t.stress = clamp(t.stress + v)
            elif k.startswith("rep_"):
                t.rep[k[4:]] = clamp(t.rep[k[4:]] + v)
            elif k == "admin":
                self._add_task(fx.get("admin_title", "Follow-up paperwork"), v, fx.get("admin_kind", "admin"), due_in=4)
            elif k == "plans" and c:
                c.plans = max(0, c.plans + v)
            elif k.startswith("s_") and s:
                attr = k[2:]
                if attr == "gain":
                    cc = self.classes[s.cid]
                    for i in sorted(range(max(1, cc.coverage)), key=lambda i: s.understanding[i])[:3]:
                        s.understanding[i] = clamp(s.understanding[i] + v * (1 - s.understanding[i]), 0, 1)
                else:
                    setattr(s, attr, clamp(getattr(s, attr) + v))
            elif k == "c_climate" and c:
                c.climate = clamp(c.climate + v)
            elif k == "c_motivation" and c:
                for sid in c.students:
                    st = self.students[sid]
                    st.motivation = clamp(st.motivation + v)
            elif k == "detention" and s:
                s.detention_due = True
            elif k == "followup":
                self.scheduled.append({"day": self.day + fx.get("followup_in", 2), "kind": v,
                                       "student": ev.get("student"), "cid": ev.get("cid")})
            elif k == "cover" and ev.get("slot"):
                self.cover_slots.add(tuple(ev["slot"]))
            elif k == "observe" and c:
                self.observations.add((self.day, c.id))
            elif k == "zero_test" and s and ev.get("batch"):
                for test in s.tests:
                    if test["batch"] == ev["batch"]:
                        test["score"] = 0
                        test["label"] += " (voided)"

    # ------------------------------------------------------------------ reports
    def _report_comment(self, s: Student):
        final = next((x for x in reversed(s.tests) if x["kind"] == "final" and x["marked"]), None)
        score = final["score"] if final else self.predicted_final(s)
        c = self.classes[s.cid]
        covered = range(max(1, c.coverage))
        best = max(covered, key=lambda i: s.understanding[i])
        worst = min(covered, key=lambda i: s.understanding[i])
        first = s.name.split()[0]
        g = grade_for(score)
        parts = []
        verb = "finishing on" if final else "working at"
        if score >= s.target + 5:
            parts.append(f"{first} has exceeded expectations this term, {verb} grade {g}.")
        elif score >= s.target - 5:
            parts.append(f"{first} has worked steadily and is on track, {verb} grade {g}.")
        else:
            parts.append(f"{first} has found this term challenging and is {verb} grade {g}, below target.")
        if best != worst:
            parts.append(f"A particular strength is {self.topics[best].lower()}; the next step is to revisit {self.topics[worst].lower()}.")
        if s.motivation > 68:
            parts.append("Effort in lessons has been excellent.")
        elif s.motivation < 42:
            parts.append(f"More consistent effort in class would help {first} make faster progress.")
        if s.behaviour < 40 or s.detentions >= 2:
            parts.append("Behaviour has at times got in the way of learning.")
        elif s.behaviour > 78:
            parts.append(f"{first} is a positive presence in the classroom.")
        if s.attendance < 0.9:
            parts.append("Improved attendance would make a real difference.")
        return " ".join(parts)

    def _end_term(self):
        self.phase = "ended"
        t = self.teacher
        auto = [s for s in self.students.values() if not s.report_written]
        for s in auto:
            s.report_comment = f"{s.name.split()[0]} has completed the term. (Generic comment ΓÇö report written in a rush.)"
            s.report_written = True
        unmarked_finals = [b for b in t.marking if b.kind == "final"]
        if auto:
            t.rep["leadership"] = clamp(t.rep["leadership"] - min(15, len(auto) / 6))
            t.rep["parents"] = clamp(t.rep["parents"] - min(10, len(auto) / 10))
        if unmarked_finals:
            t.rep["leadership"] = clamp(t.rep["leadership"] - 5 * len(unmarked_finals))
        self.final_report = self.build_report(final=True, auto_reports=len(auto), unmarked=len(unmarked_finals))
        self._say("term", "The term is over. Your end-of-term review is ready.", "info")

    def build_report(self, final=False, auto_reports=0, unmarked=0):
        t = self.teacher
        classes = []
        va_all, scores_all = [], []
        for cid, c in self.classes.items():
            rows = []
            for sid in c.students:
                s = self.students[sid]
                fin = next((x for x in reversed(s.tests) if x["kind"] == "final"), None)
                mid = next((x for x in reversed(s.tests) if x["kind"] == "midterm"), None)
                score = fin["score"] if fin else self.predicted_final(s)
                scores_all.append(score)
                va_all.append(score - s.target)
                quizzes = [x["score"] for x in s.tests if x["kind"] == "quiz" and x["marked"]]
                rows.append({
                    "id": s.id, "name": s.name, "seed": s.seed, "mood": self.mood(s),
                    "target": s.target, "target_grade": grade_for(s.target),
                    "midterm": mid["score"] if mid and mid["marked"] else None,
                    "final": score, "final_grade": grade_for(score), "final_is_prediction": fin is None,
                    "quiz_avg": round(statistics.mean(quizzes)) if quizzes else None,
                    "effort": "High" if s.motivation > 68 else "Low" if s.motivation < 42 else "Steady",
                    "behaviour": "Excellent" if s.behaviour > 78 else "Concern" if s.behaviour < 40 else "Good",
                    "attendance": round(s.attendance * 100),
                    "comment": s.report_comment or (self._report_comment(s) if not final else ""),
                    "written": s.report_written,
                })
            classes.append({"id": cid, "rows": rows,
                            "avg": round(statistics.mean(r["final"] for r in rows), 1),
                            "va": round(statistics.mean(r["final"] - r["target"] for r in rows), 1),
                            "coverage": c.coverage})
        va = statistics.mean(va_all)
        wellbeing = 100 - t.stress * 0.6 - max(0, 40 - t.energy) * 0.5
        overall = clamp(50 + va * 2.2 + (t.rep["leadership"] - 50) * 0.25 + (t.rep["parents"] - 50) * 0.15
                        + (t.rep["students"] - 50) * 0.15 + (wellbeing - 60) * 0.2 - t.sick_days * 3)
        titles = [(85, "Legendary sensei", "Students will remember you for years. So will leadership."),
                  (70, "Outstanding teacher", "Great results and a job you can keep doing."),
                  (55, "Solid professional", "A good term. A few things to sharpen next time."),
                  (40, "Surviving, just", "The term got the better of you in places."),
                  (0, "Burnt-out martyr", "Something has to change before next term.")]
        title, blurb = next((n, b) for cut, n, b in titles if overall >= cut)
        return {
            "final": final, "overall": round(overall), "title": title, "blurb": blurb,
            "value_added": round(va, 1), "avg_score": round(statistics.mean(scores_all), 1),
            "avg_grade": grade_for(statistics.mean(scores_all)),
            "wellbeing": round(wellbeing), "rep": {k: round(v) for k, v in t.rep.items()},
            "sick_days": t.sick_days, "auto_reports": auto_reports, "unmarked_finals": unmarked,
            "classes": classes,
        }
