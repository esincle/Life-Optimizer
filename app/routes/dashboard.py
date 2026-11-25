from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import (
    Todo, TodoStep, NutritionTarget, NutritionEntry, DailySteps,
    Workout, Goal, GoalCommitment, Reminder, DailyLog, AppSettings,
    WeightLog, VALID_GOAL_TYPES, VALID_METRIC_KEYS,
)

KG_PER_LB = 0.45359237

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/today")

PROTEIN_TOLERANCE = 0.15  # within 15% of daily protein goal


@dashboard_bp.route("/")
def index():
    return render_template("dashboard/index.html")


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _clamp(n, lo, hi):
    try:
        return max(lo, min(hi, int(n)))
    except (TypeError, ValueError):
        return lo


def get_or_create_nutrition_target():
    target = NutritionTarget.query.first()
    if not target:
        # Protein/steps goals stay unset until saved in Design
        target = NutritionTarget(
            tdee_baseline=2050,
            steps_kcal_per_1k=45,
            protein_goal=None,
            steps_goal=None,
        )
        db.session.add(target)
        db.session.commit()
    return target


def _parse_optional_goal(value):
    """Empty / null → None (unset). Otherwise non-negative int."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def _day_is_complete(day):
    log = DailyLog.query.filter_by(log_date=day).first()
    return bool(log and log.is_complete)


def parse_date(value, fallback=None):
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def weight_to_kg(weight, unit):
    unit = (unit or "kg").lower()
    return float(weight) if unit == "kg" else float(weight) * KG_PER_LB


def kg_to_unit(kg, unit):
    unit = (unit or "kg").lower()
    return round(kg, 2) if unit == "kg" else round(kg / KG_PER_LB, 2)


def get_display_weight_unit():
    settings = get_or_create_app_settings()
    return (settings.weight_unit or "kg").lower()


def latest_weight_kg(as_of=None):
    """Most recent weight on or before as_of, in kg."""
    as_of = as_of or date.today()
    row = (WeightLog.query
           .filter(WeightLog.log_date <= as_of)
           .order_by(WeightLog.log_date.desc())
           .first())
    if not row:
        return None, None
    return weight_to_kg(row.weight, row.unit), row


def mifflin_st_jeor_bmr(weight_kg, height_cm, age_years, sex="male"):
    """Mifflin–St Jeor BMR.

    Male (user formula): 10×kg + 6.25×cm − 5×age + 5
    Female: same with −161 instead of +5
    """
    sex = (sex or "male").lower()
    constant = 5 if sex != "female" else -161
    return 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age_years + constant


def compute_bmr_baseline(target=None, as_of=None):
    """BMR from latest weight + Design height/age/sex when all inputs exist."""
    target = target or get_or_create_nutrition_target()
    settings = get_or_create_app_settings()
    as_of = as_of or date.today()
    weight_kg, weight_row = latest_weight_kg(as_of)
    height = settings.height_cm
    age = settings.age_years
    sex = settings.sex or "male"

    missing = []
    if weight_kg is None:
        missing.append("weight")
    if height is None or height <= 0:
        missing.append("height")
    if age is None or age <= 0:
        missing.append("age")

    payload = {
        "ready": False,
        "bmr": None,
        "adaptive_baseline": None,  # alias kept for older UI keys
        "manual_baseline": target.tdee_baseline or 0,
        "formula": "10×weight_kg + 6.25×height_cm − 5×age + (5 male / −161 female)",
        "weight_kg": round(weight_kg, 2) if weight_kg is not None else None,
        "weight_date": weight_row.log_date.isoformat() if weight_row else None,
        "height_cm": height,
        "age_years": age,
        "sex": sex,
        "missing": missing,
    }
    if missing:
        return payload

    bmr = round(mifflin_st_jeor_bmr(weight_kg, float(height), int(age), sex))
    bmr = max(800, min(5000, bmr))
    payload["ready"] = True
    payload["bmr"] = bmr
    payload["adaptive_baseline"] = bmr
    return payload


def compute_adaptive_tdee(target=None):
    """Back-compat name → Mifflin–St Jeor BMR baseline."""
    return compute_bmr_baseline(target)


def compute_tdee_for_day(day, target=None):
    """TDEE = baseline + kcal/1k steps + workout calories burned.

    Baseline is Mifflin–St Jeor BMR when enabled and ready; else manual Design value.
    """
    target = target or get_or_create_nutrition_target()
    steps_row = DailySteps.query.filter_by(log_date=day).first()
    step_count = steps_row.count if steps_row else 0
    rate = target.steps_kcal_per_1k or 0
    from_steps = round((step_count / 1000.0) * rate) if rate else 0
    workouts = Workout.query.filter_by(log_date=day).all()
    from_workouts = sum(w.calories_burned or 0 for w in workouts)

    bmr_info = compute_bmr_baseline(target, as_of=day)
    using_bmr = bool(target.use_adaptive_tdee) and bmr_info["ready"]
    baseline = bmr_info["bmr"] if using_bmr else (target.tdee_baseline or 0)
    tdee = baseline + from_steps + from_workouts
    return {
        "tdee": tdee,
        "baseline": baseline,
        "manual_baseline": target.tdee_baseline or 0,
        "from_steps": from_steps,
        "from_workouts": from_workouts,
        "steps": step_count,
        "steps_kcal_per_1k": rate,
        "bmr": bmr_info,
        "adaptive": bmr_info,  # back-compat
        "using_bmr": using_bmr,
        "using_adaptive": using_bmr,
    }


def weight_summary(as_of=None):
    """Today's weight + 7-day MA + change vs prior week average."""
    as_of = as_of or date.today()
    unit = get_display_weight_unit()
    today_row = WeightLog.query.filter_by(log_date=as_of).first()

    def avg_for_range(start, end):
        rows = (WeightLog.query
                .filter(WeightLog.log_date >= start, WeightLog.log_date <= end)
                .all())
        if not rows:
            return None, 0
        kgs = [weight_to_kg(r.weight, r.unit) for r in rows]
        return sum(kgs) / len(kgs), len(rows)

    week_start = as_of - timedelta(days=6)
    prev_end = week_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    ma7_kg, ma7_n = avg_for_range(week_start, as_of)
    prev_kg, prev_n = avg_for_range(prev_start, prev_end)

    today_display = None
    if today_row:
        today_display = kg_to_unit(weight_to_kg(today_row.weight, today_row.unit), unit)

    ma7 = kg_to_unit(ma7_kg, unit) if ma7_kg is not None else None
    prev = kg_to_unit(prev_kg, unit) if prev_kg is not None else None
    delta = round(ma7 - prev, 2) if ma7 is not None and prev is not None else None

    return {
        "date": as_of.isoformat(),
        "unit": unit,
        "today": today_display,
        "today_logged": today_row is not None,
        "avg_7d": ma7,
        "avg_7d_n": ma7_n,
        "prev_week_avg": prev,
        "prev_week_n": prev_n,
        "vs_prev_week": delta,
    }


def sync_todo_completion(todo):
    """If a todo has steps, mark it done when all steps are done."""
    if not todo.steps:
        return
    all_done = all(s.done for s in todo.steps)
    if all_done and not todo.done:
        todo.done = True
        todo.completed_at = datetime.utcnow()
    elif not all_done and todo.done:
        todo.done = False
        todo.completed_at = None


# ── TODOS ──────────────────────────────────────────────────────────────────────

VALID_TODO_BUCKETS = ("today", "overall", "idea")
VALID_ESTIMATES = (15, 30, 60, 120, 240)


def get_or_create_app_settings():
    row = AppSettings.query.first()
    if not row:
        row = AppSettings(
            morning_until="12:00",
            evening_from="18:00",
            todo_cap=3,
            default_available_hours=4.0,
        )
        db.session.add(row)
        db.session.commit()
    return row


def get_or_create_daily_log(day):
    log = DailyLog.query.filter_by(log_date=day).first()
    if not log:
        log = DailyLog(log_date=day)
        db.session.add(log)
        db.session.flush()
    return log


def roll_forward_today_todos(day):
    """Unfinished today-bucket tasks from earlier dates roll to `day`."""
    stale = (Todo.query
             .filter(
                 Todo.bucket == "today",
                 Todo.done.is_(False),
                 Todo.for_date.isnot(None),
                 Todo.for_date < day,
             )
             .all())
    for t in stale:
        t.for_date = day
        t.rollover_count = (t.rollover_count or 0) + 1
        t.manual_sort = False
        t.manual_position = None
    if stale:
        db.session.commit()
    return len(stale)


def sort_todos(todos):
    """Manual order first (if flagged), else importance desc → effort asc."""
    manual = [t for t in todos if t.manual_sort]
    auto = [t for t in todos if not t.manual_sort]
    manual.sort(key=lambda t: (t.manual_position is None, t.manual_position or 0, t.id))
    auto.sort(key=lambda t: (-(t.importance or 0), t.effort or 0, -(t.id or 0)))
    return manual + auto


def count_open_today(day):
    return Todo.query.filter_by(bucket="today", done=False, for_date=day).count()


@dashboard_bp.route("/api/todos", methods=["GET"])
def list_todos():
    """Open todos for the dashboard. Completed items are excluded by default
    (use /api/todos/completed or include_done=1 for history/stats)."""
    include_done = request.args.get("include_done", "0") == "1"
    bucket = request.args.get("bucket", "overall")
    if bucket not in VALID_TODO_BUCKETS:
        return jsonify({"error": "bucket must be today, overall, or idea"}), 400

    settings = get_or_create_app_settings()
    day = parse_date(request.args.get("date"), date.today())
    rolled = 0
    if bucket == "today":
        rolled = roll_forward_today_todos(day)

    q = Todo.query.filter_by(bucket=bucket)
    if not include_done:
        q = q.filter_by(done=False)

    if bucket == "today":
        q = q.filter(Todo.for_date == day)

    todos = q.all()
    if bucket == "idea":
        todos.sort(key=lambda t: -(t.id or 0))
    else:
        todos = sort_todos(todos)

    log = DailyLog.query.filter_by(log_date=day).first()
    available = (
        log.available_hours
        if log and log.available_hours is not None
        else settings.default_available_hours
    )
    planned_minutes = sum(t.estimate_minutes or 0 for t in todos if not t.done)

    return jsonify({
        "todos": [t.to_dict() for t in todos],
        "meta": {
            "bucket": bucket,
            "date": day.isoformat(),
            "todo_cap": settings.todo_cap,
            "open_today_count": count_open_today(day),
            "available_hours": available,
            "default_available_hours": settings.default_available_hours,
            "planned_minutes": planned_minutes,
            "rolled_forward": rolled,
        },
    })


@dashboard_bp.route("/api/todos/completed", methods=["GET"])
def list_completed_todos():
    """Completed todos kept for statistics — not shown on the dashboard UI."""
    bucket = request.args.get("bucket")  # optional filter
    days = request.args.get("days")
    since_date = parse_date(request.args.get("since"))
    until_date = parse_date(request.args.get("until"))

    q = Todo.query.filter_by(done=True)
    if bucket:
        if bucket not in VALID_TODO_BUCKETS:
            return jsonify({"error": "Invalid bucket"}), 400
        q = q.filter_by(bucket=bucket)

    if days is not None:
        try:
            n = max(1, int(days))
        except (TypeError, ValueError):
            return jsonify({"error": "days must be an integer"}), 400
        cutoff = datetime.utcnow() - timedelta(days=n)
        q = q.filter(Todo.completed_at >= cutoff)
    if since_date:
        q = q.filter(Todo.completed_at >= datetime.combine(since_date, datetime.min.time()))
    if until_date:
        q = q.filter(Todo.completed_at < datetime.combine(until_date + timedelta(days=1), datetime.min.time()))

    todos = q.order_by(Todo.completed_at.desc(), Todo.id.desc()).all()
    return jsonify([t.to_dict() for t in todos])


@dashboard_bp.route("/api/todos/stats", methods=["GET"])
def todo_stats():
    """Aggregate completion counts for later dashboards/charts."""
    try:
        days = max(1, int(request.args.get("days", 30)))
    except (TypeError, ValueError):
        return jsonify({"error": "days must be an integer"}), 400

    cutoff = datetime.utcnow() - timedelta(days=days)
    completed = (Todo.query
                 .filter(Todo.done.is_(True), Todo.completed_at.isnot(None),
                         Todo.completed_at >= cutoff)
                 .all())
    open_counts = {
        b: Todo.query.filter_by(bucket=b, done=False).count()
        for b in VALID_TODO_BUCKETS
    }

    by_day = {}
    by_bucket = {b: 0 for b in VALID_TODO_BUCKETS}
    for t in completed:
        by_bucket[t.bucket] = by_bucket.get(t.bucket, 0) + 1
        day_key = (t.completed_at.date() if t.completed_at else date.today()).isoformat()
        cell = by_day.setdefault(day_key, {b: 0 for b in VALID_TODO_BUCKETS})
        cell[t.bucket] = cell.get(t.bucket, 0) + 1
        cell["total"] = cell.get("total", 0) + 1

    day_rows = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        cell = by_day.get(d, {})
        day_rows.append({
            "date": d,
            "total": cell.get("total", 0),
            "today": cell.get("today", 0),
            "overall": cell.get("overall", 0),
            "idea": cell.get("idea", 0),
        })

    return jsonify({
        "days": days,
        "completed_total": len(completed),
        "completed_by_bucket": by_bucket,
        "open_by_bucket": open_counts,
        "by_day": day_rows,
    })


@dashboard_bp.route("/api/todos", methods=["POST"])
def create_todo():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    bucket = (data.get("bucket") or "overall").strip()
    if bucket not in VALID_TODO_BUCKETS:
        return jsonify({"error": "bucket must be today, overall, or idea"}), 400

    for_date = parse_date(data.get("for_date"))
    if bucket == "today":
        for_date = for_date or date.today()
    else:
        for_date = None

    settings = get_or_create_app_settings()
    force = bool(data.get("force"))
    swap_out_id = data.get("swap_out_id")

    if bucket == "today" and not force:
        open_count = count_open_today(for_date)
        if open_count >= settings.todo_cap:
            if swap_out_id:
                victim = Todo.query.get(swap_out_id)
                if not victim or victim.bucket != "today" or victim.for_date != for_date:
                    return jsonify({"error": "swap_out_id must be an open Today task"}), 400
                victim.bucket = "overall"
                victim.for_date = None
                victim.manual_sort = False
                victim.manual_position = None
            else:
                open_todos = (Todo.query
                              .filter_by(bucket="today", done=False, for_date=for_date)
                              .all())
                return jsonify({
                    "error": f"Today is capped at {settings.todo_cap} tasks",
                    "code": "cap_exceeded",
                    "todo_cap": settings.todo_cap,
                    "open_todos": [t.to_dict(include_steps=False) for t in sort_todos(open_todos)],
                }), 409

    estimate = data.get("estimate_minutes")
    if estimate in ("", None):
        estimate = None
    else:
        try:
            estimate = int(estimate)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid estimate_minutes"}), 400
        if estimate not in VALID_ESTIMATES:
            return jsonify({"error": "estimate_minutes must be 15, 30, 60, 120, or 240"}), 400

    # Default Med/Med (2/2) on the 1–3 scale
    default_imp = 2
    default_eff = 2

    goal_id = data.get("goal_id")
    if goal_id in ("", None):
        goal_id = None
    else:
        try:
            goal_id = int(goal_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid goal_id"}), 400
        if not Goal.query.get(goal_id):
            return jsonify({"error": "Goal not found"}), 400

    todo = Todo(
        title=title,
        notes=data.get("notes"),
        importance=_clamp(data.get("importance", default_imp), 1, 3),
        effort=_clamp(data.get("effort", default_eff), 1, 3),
        estimate_minutes=estimate,
        due_date=parse_date(data.get("due_date")),
        bucket=bucket,
        for_date=for_date,
        goal_id=goal_id,
    )
    db.session.add(todo)
    db.session.flush()
    if bucket != "idea":
        for i, step_title in enumerate(data.get("steps") or []):
            st = (step_title or "").strip()
            if st:
                db.session.add(TodoStep(todo_id=todo.id, title=st, position=i))
    db.session.commit()
    return jsonify(todo.to_dict()), 201


@dashboard_bp.route("/api/todos/<int:todo_id>", methods=["PUT"])
def update_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    data = request.get_json() or {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "Title is required"}), 400
        todo.title = title
    if "notes" in data:
        todo.notes = data["notes"]
    if "importance" in data:
        todo.importance = _clamp(data["importance"], 1, 3)
    if "effort" in data:
        todo.effort = _clamp(data["effort"], 1, 3)
    if "estimate_minutes" in data:
        estimate = data.get("estimate_minutes")
        if estimate in ("", None):
            todo.estimate_minutes = None
        else:
            try:
                estimate = int(estimate)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid estimate_minutes"}), 400
            if estimate not in VALID_ESTIMATES:
                return jsonify({"error": "estimate_minutes must be 15, 30, 60, 120, or 240"}), 400
            todo.estimate_minutes = estimate
    if "due_date" in data:
        todo.due_date = parse_date(data["due_date"])
    if "bucket" in data:
        bucket = (data["bucket"] or "").strip()
        if bucket not in VALID_TODO_BUCKETS:
            return jsonify({"error": "Invalid bucket"}), 400
        if bucket == "today" and todo.bucket != "today":
            settings = get_or_create_app_settings()
            day = parse_date(data.get("for_date"), date.today())
            if count_open_today(day) >= settings.todo_cap and not data.get("force"):
                return jsonify({
                    "error": f"Today is capped at {settings.todo_cap} tasks",
                    "code": "cap_exceeded",
                    "todo_cap": settings.todo_cap,
                }), 409
        todo.bucket = bucket
        if bucket == "today":
            todo.for_date = parse_date(data.get("for_date"), todo.for_date or date.today())
        else:
            todo.for_date = None
            todo.manual_sort = False
            todo.manual_position = None
    elif "for_date" in data and todo.bucket == "today":
        todo.for_date = parse_date(data["for_date"], date.today())
    if "done" in data:
        todo.done = bool(data["done"])
        todo.completed_at = datetime.utcnow() if todo.done else None
        if todo.done:
            for step in todo.steps:
                step.done = True
                if not step.completed_at:
                    step.completed_at = datetime.utcnow()
        else:
            for step in todo.steps:
                step.done = False
                step.completed_at = None
    if "goal_id" in data:
        raw = data.get("goal_id")
        if raw in ("", None):
            todo.goal_id = None
        else:
            try:
                gid = int(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid goal_id"}), 400
            if not Goal.query.get(gid):
                return jsonify({"error": "Goal not found"}), 400
            todo.goal_id = gid
    db.session.commit()
    return jsonify(todo.to_dict())


@dashboard_bp.route("/api/todos/reorder", methods=["POST"])
def reorder_todos():
    """Persist manual drag order for Today or Overall."""
    data = request.get_json() or {}
    bucket = (data.get("bucket") or "today").strip()
    if bucket not in ("today", "overall"):
        return jsonify({"error": "bucket must be today or overall"}), 400
    ids = data.get("ordered_ids") or []
    if not isinstance(ids, list) or not ids:
        return jsonify({"error": "ordered_ids required"}), 400
    day = parse_date(data.get("date"), date.today())
    for i, tid in enumerate(ids):
        todo = Todo.query.get(tid)
        if not todo or todo.bucket != bucket:
            continue
        if bucket == "today" and todo.for_date != day:
            continue
        todo.manual_sort = True
        todo.manual_position = i
    db.session.commit()
    return jsonify({"ok": True})


@dashboard_bp.route("/api/day-plan", methods=["GET"])
def get_day_plan():
    day = parse_date(request.args.get("date"), date.today())
    settings = get_or_create_app_settings()
    log = DailyLog.query.filter_by(log_date=day).first()
    available = (
        log.available_hours
        if log and log.available_hours is not None
        else settings.default_available_hours
    )
    todos = Todo.query.filter_by(bucket="today", done=False, for_date=day).all()
    planned = sum(t.estimate_minutes or 0 for t in todos)
    return jsonify({
        "date": day.isoformat(),
        "available_hours": available,
        "default_available_hours": settings.default_available_hours,
        "planned_minutes": planned,
        "todo_cap": settings.todo_cap,
        "open_count": len(todos),
    })


@dashboard_bp.route("/api/day-plan", methods=["PUT"])
def put_day_plan():
    data = request.get_json() or {}
    day = parse_date(data.get("date"), date.today())
    log = get_or_create_daily_log(day)
    if "available_hours" in data:
        raw = data.get("available_hours")
        if raw in ("", None):
            log.available_hours = None
        else:
            try:
                log.available_hours = max(0.5, min(24, float(raw)))
            except (TypeError, ValueError):
                return jsonify({"error": "available_hours must be a number"}), 400
    db.session.commit()
    settings = get_or_create_app_settings()
    available = (
        log.available_hours
        if log.available_hours is not None
        else settings.default_available_hours
    )
    return jsonify({
        "date": day.isoformat(),
        "available_hours": available,
        "default_available_hours": settings.default_available_hours,
    })


@dashboard_bp.route("/api/todos/<int:todo_id>/toggle", methods=["POST"])
def toggle_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    todo.done = not todo.done
    todo.completed_at = datetime.utcnow() if todo.done else None
    if todo.done:
        for step in todo.steps:
            step.done = True
            if not step.completed_at:
                step.completed_at = datetime.utcnow()
    else:
        for step in todo.steps:
            step.done = False
            step.completed_at = None
    db.session.commit()
    return jsonify(todo.to_dict())


@dashboard_bp.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    """Permanently remove a todo. Prefer marking done (toggle) to keep history for stats."""
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({"ok": True})


@dashboard_bp.route("/api/todos/<int:todo_id>/steps", methods=["POST"])
def create_todo_step(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    max_pos = db.session.query(db.func.max(TodoStep.position)).filter_by(todo_id=todo.id).scalar() or 0
    step = TodoStep(todo_id=todo.id, title=title, position=max_pos + 1)
    db.session.add(step)
    # Opening a new step un-completes the parent
    if todo.done:
        todo.done = False
        todo.completed_at = None
    db.session.commit()
    return jsonify(todo.to_dict()), 201


@dashboard_bp.route("/api/todo-steps/<int:step_id>/toggle", methods=["POST"])
def toggle_todo_step(step_id):
    step = TodoStep.query.get_or_404(step_id)
    step.done = not step.done
    step.completed_at = datetime.utcnow() if step.done else None
    sync_todo_completion(step.todo)
    db.session.commit()
    return jsonify(step.todo.to_dict())


@dashboard_bp.route("/api/todo-steps/<int:step_id>", methods=["DELETE"])
def delete_todo_step(step_id):
    step = TodoStep.query.get_or_404(step_id)
    todo = step.todo
    db.session.delete(step)
    db.session.flush()
    sync_todo_completion(todo)
    db.session.commit()
    return jsonify(todo.to_dict())


# ── NUTRITION ──────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/nutrition/targets", methods=["GET"])
def get_nutrition_targets():
    target = get_or_create_nutrition_target()
    payload = target.to_dict()
    bmr = compute_bmr_baseline(target)
    payload["bmr"] = bmr
    payload["adaptive"] = bmr  # back-compat
    return jsonify(payload)


@dashboard_bp.route("/api/nutrition/targets", methods=["PUT"])
def update_nutrition_targets():
    data = request.get_json() or {}
    target = get_or_create_nutrition_target()
    # Prefer tdee_baseline; accept legacy keys
    if "tdee_baseline" in data:
        target.tdee_baseline = max(0, int(data["tdee_baseline"]))
    elif "maintenance_calories" in data:
        target.tdee_baseline = max(0, int(data["maintenance_calories"]))
    elif "calorie_goal" in data:
        target.tdee_baseline = max(0, int(data["calorie_goal"]))
    if "steps_kcal_per_1k" in data:
        target.steps_kcal_per_1k = max(0, int(data["steps_kcal_per_1k"]))
    if "protein_goal" in data:
        target.protein_goal = _parse_optional_goal(data.get("protein_goal"))
    if "steps_goal" in data:
        target.steps_goal = _parse_optional_goal(data.get("steps_goal"))
    if "use_adaptive_tdee" in data or "use_bmr_baseline" in data:
        flag = data.get("use_bmr_baseline", data.get("use_adaptive_tdee"))
        target.use_adaptive_tdee = bool(flag)
    db.session.commit()
    payload = target.to_dict()
    bmr = compute_bmr_baseline(target)
    payload["bmr"] = bmr
    payload["adaptive"] = bmr
    return jsonify(payload)


@dashboard_bp.route("/api/nutrition/today", methods=["GET"])
def nutrition_today():
    today = date.today()
    target = get_or_create_nutrition_target()
    entries = (NutritionEntry.query
               .filter_by(log_date=today)
               .order_by(NutritionEntry.created_at.desc())
               .all())
    calories = sum(e.calories for e in entries)
    protein = sum(e.protein for e in entries)
    tdee_info = compute_tdee_for_day(today, target)
    food_logged = len(entries) > 0
    # No calorie deficit unless food was tracked today
    deficit = (tdee_info["tdee"] - calories) if food_logged else None
    return jsonify({
        "date": today.isoformat(),
        "targets": {**target.to_dict(), "adaptive": tdee_info.get("adaptive")},
        "totals": {"calories": calories, "protein": protein},
        "tdee": tdee_info,
        "food_logged": food_logged,
        "deficit": deficit,  # None if calories not tracked; else + deficit / − surplus
        "entries": [e.to_dict() for e in entries],
        "weight": weight_summary(today),
    })


def _nutrition_day_payload(d, totals, target, tdee_info, *, is_complete, is_today):
    food_logged = totals is not None
    protein_goal = target.protein_goal
    deficit = None
    within = False
    if food_logged:
        deficit = tdee_info["tdee"] - totals["calories"]
        if protein_goal:
            lo = protein_goal * (1 - PROTEIN_TOLERANCE)
            hi = protein_goal * (1 + PROTEIN_TOLERANCE)
            within = lo <= totals["protein"] <= hi
    return {
        "date": d.isoformat(),
        "calories": totals["calories"] if food_logged else 0,
        "protein": totals["protein"] if food_logged else 0,
        "tdee": tdee_info,
        "deficit": deficit,
        "protein_within_15": within,
        "logged": food_logged,
        "is_complete": is_complete,
        "is_today": is_today,
    }


@dashboard_bp.route("/api/nutrition/week", methods=["GET"])
def nutrition_week():
    """Week deficit/protein on complete days only; today returned separately."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    target = get_or_create_nutrition_target()
    entries = (NutritionEntry.query
               .filter(NutritionEntry.log_date >= week_start,
                       NutritionEntry.log_date <= week_end)
               .all())

    by_day = {}
    for e in entries:
        bucket = by_day.setdefault(e.log_date, {"calories": 0, "protein": 0})
        bucket["calories"] += e.calories
        bucket["protein"] += e.protein

    complete_dates = {
        row.log_date
        for row in DailyLog.query.filter(
            DailyLog.log_date >= week_start,
            DailyLog.log_date <= week_end,
            DailyLog.is_complete.is_(True),
        ).all()
    }

    days = []
    protein_hit_days = 0
    days_complete = 0
    total_deficit = 0
    today_payload = None

    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        totals = by_day.get(d)
        tdee_info = compute_tdee_for_day(d, target)
        is_today = d == today
        is_complete = d in complete_dates
        payload = _nutrition_day_payload(
            d, totals, target, tdee_info,
            is_complete=is_complete, is_today=is_today,
        )
        days.append(payload)
        if is_today:
            today_payload = payload
            continue
        # Week rollups: complete days only (never the in-progress today)
        if not is_complete or not payload["logged"]:
            continue
        days_complete += 1
        if payload["deficit"] is not None:
            total_deficit += payload["deficit"]
        if payload["protein_within_15"]:
            protein_hit_days += 1

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "targets": target.to_dict(),
        "total_deficit": total_deficit,
        "avg_deficit": round(total_deficit / days_complete) if days_complete else 0,
        "days_logged": days_complete,
        "days_complete": days_complete,
        "protein_hit_days": protein_hit_days,
        "protein_tolerance_pct": int(PROTEIN_TOLERANCE * 100),
        "days": days,
        "today": today_payload,
    })


@dashboard_bp.route("/api/nutrition/entries", methods=["POST"])
def create_nutrition_entry():
    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "Label is required"}), 400
    entry = NutritionEntry(
        log_date=parse_date(data.get("log_date"), date.today()),
        label=label,
        calories=max(0, int(data.get("calories") or 0)),
        protein=max(0, int(data.get("protein") or 0)),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify(entry.to_dict()), 201


@dashboard_bp.route("/api/nutrition/entries/<int:entry_id>", methods=["PUT"])
def update_nutrition_entry(entry_id):
    entry = NutritionEntry.query.get_or_404(entry_id)
    data = request.get_json() or {}
    if "label" in data:
        label = (data["label"] or "").strip()
        if not label:
            return jsonify({"error": "Label is required"}), 400
        entry.label = label
    if "calories" in data:
        entry.calories = max(0, int(data["calories"] or 0))
    if "protein" in data:
        entry.protein = max(0, int(data["protein"] or 0))
    if "log_date" in data:
        entry.log_date = parse_date(data["log_date"], entry.log_date)
    db.session.commit()
    return jsonify(entry.to_dict())


@dashboard_bp.route("/api/nutrition/entries/<int:entry_id>", methods=["DELETE"])
def delete_nutrition_entry(entry_id):
    entry = NutritionEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"ok": True})


# ── DAY HISTORY ────────────────────────────────────────────────────────────────

def _day_bounds(d):
    start = datetime.combine(d, datetime.min.time())
    end = datetime.combine(d + timedelta(days=1), datetime.min.time())
    return start, end


def build_day_overview(d, target=None):
    """Compact day snapshot for history list + detail."""
    target = target or get_or_create_nutrition_target()
    entries = NutritionEntry.query.filter_by(log_date=d).all()
    calories = sum(e.calories for e in entries)
    protein = sum(e.protein for e in entries)
    tdee_info = compute_tdee_for_day(d, target)
    food_logged = len(entries) > 0
    # Calorie deficit only when food/calories were tracked that day
    deficit = (tdee_info["tdee"] - calories) if food_logged else None

    protein_hit = False
    if food_logged and target.protein_goal > 0:
        lo = target.protein_goal * (1 - PROTEIN_TOLERANCE)
        hi = target.protein_goal * (1 + PROTEIN_TOLERANCE)
        protein_hit = lo <= protein <= hi

    workouts = Workout.query.filter_by(log_date=d).all()
    steps_logged = DailySteps.query.filter_by(log_date=d).first() is not None
    start, end = _day_bounds(d)
    todos_completed = Todo.query.filter(
        Todo.done.is_(True),
        Todo.completed_at.isnot(None),
        Todo.completed_at >= start,
        Todo.completed_at < end,
    ).count()
    today_todos_open = Todo.query.filter_by(bucket="today", for_date=d, done=False).count()
    today_todos_done = Todo.query.filter_by(bucket="today", for_date=d, done=True).count()
    workouts_logged = len(workouts) > 0
    todos_tracked = todos_completed > 0 or today_todos_open > 0 or today_todos_done > 0

    has_activity = (
        food_logged
        or steps_logged
        or workouts_logged
        or todos_tracked
    )

    return {
        "date": d.isoformat(),
        "has_activity": has_activity,
        "tracked": {
            "calories": food_logged,
            "protein": food_logged,
            "steps": steps_logged,
            "workouts": workouts_logged,
            "todos": todos_tracked,
        },
        "intake_calories": calories if food_logged else None,
        "protein": protein if food_logged else None,
        "protein_goal": target.protein_goal,
        "protein_hit": protein_hit if food_logged else None,
        "tdee": tdee_info,
        "deficit": deficit,
        "steps": tdee_info["steps"] if steps_logged else None,
        "steps_goal": target.steps_goal,
        "steps_hit": bool(target.steps_goal and steps_logged and tdee_info["steps"] >= target.steps_goal),
        "workouts_count": len(workouts) if workouts_logged else None,
        "workout_kcal": sum(w.calories_burned or 0 for w in workouts) if workouts_logged else None,
        "todos_completed": todos_completed if todos_tracked else None,
        "today_todos_open": today_todos_open,
        "today_todos_done": today_todos_done,
        "food_entries": len(entries),
    }


@dashboard_bp.route("/api/history", methods=["GET"])
def history_list():
    """Past days overview for the History tab."""
    try:
        days = max(1, min(90, int(request.args.get("days", 21))))
    except (TypeError, ValueError):
        return jsonify({"error": "days must be an integer"}), 400

    only_active = request.args.get("active", "0") == "1"
    today = date.today()
    target = get_or_create_nutrition_target()
    rows = []
    for i in range(days):
        d = today - timedelta(days=i)
        row = build_day_overview(d, target)
        if only_active and not row["has_activity"]:
            continue
        rows.append(row)

    return jsonify({
        "days": days,
        "targets": target.to_dict(),
        "days_list": rows,
    })


@dashboard_bp.route("/api/history/<date_str>", methods=["GET"])
def history_day(date_str):
    """Full day detail for viewing/editing."""
    d = parse_date(date_str)
    if not d:
        return jsonify({"error": "Invalid date"}), 400
    if d > date.today():
        return jsonify({"error": "Cannot open future dates"}), 400

    target = get_or_create_nutrition_target()
    overview = build_day_overview(d, target)
    entries = (NutritionEntry.query
               .filter_by(log_date=d)
               .order_by(NutritionEntry.created_at.desc())
               .all())
    workouts = (Workout.query
                .filter_by(log_date=d)
                .order_by(Workout.created_at.desc())
                .all())
    start, end = _day_bounds(d)
    completed_todos = (Todo.query
                       .filter(
                           Todo.done.is_(True),
                           Todo.completed_at.isnot(None),
                           Todo.completed_at >= start,
                           Todo.completed_at < end,
                       )
                       .order_by(Todo.completed_at.desc())
                       .all())
    day_todos = (Todo.query
                 .filter_by(bucket="today", for_date=d)
                 .order_by(Todo.done.asc(), Todo.importance.desc())
                 .all())

    return jsonify({
        "overview": overview,
        "targets": target.to_dict(),
        "entries": [e.to_dict() for e in entries],
        "workouts": [w.to_dict() for w in workouts],
        "completed_todos": [t.to_dict() for t in completed_todos],
        "day_todos": [t.to_dict() for t in day_todos],
    })


# ── DAILY CHECK-IN (Phase 6) ───────────────────────────────────────────────────

def _clamp_checkin(n):
    try:
        return max(1, min(5, int(n)))
    except (TypeError, ValueError):
        return None


@dashboard_bp.route("/api/checkin", methods=["GET"])
def get_checkin():
    day = parse_date(request.args.get("date"), date.today())
    log = get_or_create_daily_log(day)
    db.session.commit()
    # Last 7 days for a tiny sparkline strip
    week_start = day - timedelta(days=6)
    logs = (DailyLog.query
            .filter(DailyLog.log_date >= week_start, DailyLog.log_date <= day)
            .order_by(DailyLog.log_date.asc())
            .all())
    by_date = {l.log_date: l for l in logs}
    week = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        row = by_date.get(d)
        week.append({
            "date": d.isoformat(),
            "mood": row.checkin_mood if row else None,
            "energy": row.checkin_energy if row else None,
            "is_today": d == day,
        })
    return jsonify({
        "date": day.isoformat(),
        **log.checkin_to_dict(),
        "week": week,
    })


@dashboard_bp.route("/api/checkin", methods=["PUT"])
def put_checkin():
    data = request.get_json() or {}
    day = parse_date(data.get("date"), date.today())
    log = get_or_create_daily_log(day)

    if "mood" in data:
        raw = data.get("mood")
        log.checkin_mood = None if raw in ("", None) else _clamp_checkin(raw)
        if raw not in ("", None) and log.checkin_mood is None:
            return jsonify({"error": "mood must be 1–5"}), 400
    if "energy" in data:
        raw = data.get("energy")
        log.checkin_energy = None if raw in ("", None) else _clamp_checkin(raw)
        if raw not in ("", None) and log.checkin_energy is None:
            return jsonify({"error": "energy must be 1–5"}), 400
    if "note" in data:
        note = data.get("note")
        log.checkin_note = (note or "").strip() or None

    if log.checkin_mood is not None or log.checkin_energy is not None or log.checkin_note:
        log.checkin_at = datetime.utcnow()
    else:
        log.checkin_at = None

    db.session.commit()
    return jsonify({"date": day.isoformat(), **log.checkin_to_dict()})


# ── WEIGHT ─────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/weight", methods=["GET"])
def get_weight():
    day = parse_date(request.args.get("date"), date.today())
    return jsonify(weight_summary(day))


@dashboard_bp.route("/api/weight", methods=["PUT"])
def put_weight():
    data = request.get_json() or {}
    day = parse_date(data.get("log_date"), date.today())
    unit = (data.get("unit") or get_display_weight_unit() or "kg").lower()
    if unit not in ("kg", "lb"):
        return jsonify({"error": "unit must be kg or lb"}), 400
    try:
        weight = float(data.get("weight"))
    except (TypeError, ValueError):
        return jsonify({"error": "weight must be a number"}), 400
    if weight <= 0 or weight > 1000:
        return jsonify({"error": "weight out of range"}), 400

    row = WeightLog.query.filter_by(log_date=day).first()
    if not row:
        row = WeightLog(log_date=day, weight=weight, unit=unit)
        db.session.add(row)
    else:
        row.weight = weight
        row.unit = unit
    db.session.commit()
    return jsonify(weight_summary(day))


@dashboard_bp.route("/api/weight", methods=["DELETE"])
def delete_weight():
    data = request.get_json() or {}
    day = parse_date(data.get("log_date") or request.args.get("date"), date.today())
    row = WeightLog.query.filter_by(log_date=day).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    return jsonify(weight_summary(day))


# ── STEPS ──────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/steps/today", methods=["GET"])
def get_steps_today():
    today = date.today()
    target = get_or_create_nutrition_target()
    row = DailySteps.query.filter_by(log_date=today).first()
    count = row.count if row else 0
    goal = target.steps_goal  # None if unset
    return jsonify({
        "date": today.isoformat(),
        "count": count,
        "steps_goal": goal,
        "pct": min(100, round(count / goal * 100)) if goal else 0,
        "logged": row is not None,
        "goal_set": goal is not None,
    })


@dashboard_bp.route("/api/steps/today", methods=["PUT"])
def put_steps_today():
    data = request.get_json() or {}
    today = parse_date(data.get("log_date"), date.today())
    try:
        count = max(0, int(data.get("count", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "count must be an integer"}), 400

    row = DailySteps.query.filter_by(log_date=today).first()
    if not row:
        row = DailySteps(log_date=today, count=count)
        db.session.add(row)
    else:
        row.count = count
    db.session.commit()

    target = get_or_create_nutrition_target()
    goal = target.steps_goal
    return jsonify({
        "date": today.isoformat(),
        "count": row.count,
        "steps_goal": goal,
        "pct": min(100, round(row.count / goal * 100)) if goal else 0,
        "logged": True,
        "goal_set": goal is not None,
    })


@dashboard_bp.route("/api/steps/week", methods=["GET"])
def steps_week():
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    target = get_or_create_nutrition_target()
    rows = (DailySteps.query
            .filter(DailySteps.log_date >= week_start, DailySteps.log_date <= week_end)
            .all())
    by_date = {r.log_date: r.count for r in rows}
    complete_dates = {
        row.log_date
        for row in DailyLog.query.filter(
            DailyLog.log_date >= week_start,
            DailyLog.log_date <= week_end,
            DailyLog.is_complete.is_(True),
        ).all()
    }

    days = []
    total = 0
    logged = 0
    hit = 0
    goal = target.steps_goal
    today_payload = None

    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        is_today = d == today
        is_complete = d in complete_dates
        if d in by_date:
            count = by_date[d]
            payload = {
                "date": d.isoformat(),
                "count": count,
                "logged": True,
                "hit_goal": bool(goal and count >= goal),
                "is_complete": is_complete,
                "is_today": is_today,
            }
        else:
            payload = {
                "date": d.isoformat(),
                "count": 0,
                "logged": False,
                "hit_goal": False,
                "is_complete": is_complete,
                "is_today": is_today,
            }
        days.append(payload)
        if is_today:
            today_payload = payload
            continue
        # Week goal-days: only complete days that actually have a steps log
        if not is_complete or not payload["logged"]:
            continue
        logged += 1
        total += payload["count"]
        if payload["hit_goal"]:
            hit += 1

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "steps_goal": goal,
        "total": total,
        "avg": round(total / logged) if logged else 0,
        "days_logged": logged,
        "goal_hit_days": hit,
        "days": days,
        "today": today_payload,
        "goal_set": goal is not None,
    })


# ── WORKOUTS ───────────────────────────────────────────────────────────────────

VALID_WORKOUT_KINDS = ("zone2", "full", "upper", "lower")


@dashboard_bp.route("/api/workouts", methods=["GET"])
def list_workouts():
    days = int(request.args.get("days", 14))
    since = date.today() - timedelta(days=days - 1)
    workouts = (Workout.query
                .filter(Workout.log_date >= since)
                .order_by(Workout.log_date.desc(), Workout.created_at.desc())
                .all())
    return jsonify([w.to_dict() for w in workouts])


@dashboard_bp.route("/api/workouts/overview", methods=["GET"])
def workouts_overview():
    """Week overview counts + today's sessions for the day input panel."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    workouts = (Workout.query
                .filter(Workout.log_date >= week_start, Workout.log_date <= week_end)
                .all())

    zone2 = [w for w in workouts if w.kind == "zone2"]
    today_workouts = [w for w in workouts if w.log_date == today]
    upper_count = sum(1 for w in workouts if w.kind in ("upper", "full"))
    lower_count = sum(1 for w in workouts if w.kind in ("lower", "full"))
    full_count = sum(1 for w in workouts if w.kind == "full")

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "upper": {
            "count": upper_count,
            "today": any(w.kind in ("upper", "full") for w in today_workouts),
        },
        "lower": {
            "count": lower_count,
            "today": any(w.kind in ("lower", "full") for w in today_workouts),
        },
        "full": {"count": full_count},
        "zone2": {
            "count": len(zone2),
            "minutes": sum(w.duration_minutes or 0 for w in zone2),
            "today": any(w.kind == "zone2" for w in today_workouts),
        },
        "week_workouts": [w.to_dict() for w in sorted(workouts, key=lambda w: (w.log_date, w.id), reverse=True)],
        "today_workouts": [w.to_dict() for w in sorted(today_workouts, key=lambda w: w.id, reverse=True)],
        # Back-compat for older clients
        "workouts": [w.to_dict() for w in sorted(workouts, key=lambda w: (w.log_date, w.id), reverse=True)],
    })


@dashboard_bp.route("/api/workouts", methods=["POST"])
def create_workout():
    data = request.get_json() or {}
    kind = data.get("kind")
    if kind not in VALID_WORKOUT_KINDS:
        return jsonify({"error": "kind must be zone2, full, upper, or lower"}), 400
    duration = data.get("duration_minutes")
    burned = data.get("calories_burned")
    workout = Workout(
        log_date=parse_date(data.get("log_date"), date.today()),
        kind=kind,
        title=(data.get("title") or "").strip() or None,
        duration_minutes=int(duration) if duration not in (None, "") else None,
        calories_burned=max(0, int(burned)) if burned not in (None, "") else None,
        notes=data.get("notes"),
    )
    db.session.add(workout)
    db.session.commit()
    return jsonify(workout.to_dict()), 201


@dashboard_bp.route("/api/workouts/<int:workout_id>", methods=["DELETE"])
def delete_workout(workout_id):
    workout = Workout.query.get_or_404(workout_id)
    db.session.delete(workout)
    db.session.commit()
    return jsonify({"ok": True})


# ── GOALS ──────────────────────────────────────────────────────────────────────

METRIC_LABELS = {
    "weight": "Weight",
    "protein_days": "Protein days / week",
    "steps_days": "Steps days / week",
    "workouts_week": "Workouts / week",
    "routine_pct": "Routine completion %",
}


def iso_week_start(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def _metric_current(metric_key, week_start=None):
    """Return (current_value, meta_dict) for a metric key this ISO week."""
    today = date.today()
    week_start = week_start or iso_week_start(today)
    week_end = week_start + timedelta(days=6)
    target = get_or_create_nutrition_target()

    if metric_key == "weight":
        unit = get_display_weight_unit()
        latest = WeightLog.query.order_by(WeightLog.log_date.desc()).first()
        if not latest:
            return None, {
                "available": False,
                "unit": unit,
                "note": "No weight logged yet",
            }
        current = kg_to_unit(weight_to_kg(latest.weight, latest.unit), unit)
        return current, {"available": True, "unit": unit}

    if metric_key == "protein_days":
        goal = target.protein_goal
        if goal is None:
            return 0, {"available": False, "unit": "days", "note": "Set a protein goal in Design"}
        complete = {
            row.log_date
            for row in DailyLog.query.filter(
                DailyLog.log_date >= week_start,
                DailyLog.log_date <= min(week_end, today),
                DailyLog.is_complete.is_(True),
            ).all()
        }
        # Include today as in-progress for a live feel
        days = set(complete)
        days.add(today)
        hit = 0
        for d in days:
            if d > today:
                continue
            entries = NutritionEntry.query.filter_by(log_date=d).all()
            protein = sum(e.protein or 0 for e in entries)
            lo = goal * (1 - PROTEIN_TOLERANCE)
            hi = goal * (1 + PROTEIN_TOLERANCE)
            if lo <= protein <= hi:
                hit += 1
        return hit, {"available": True, "unit": "days"}

    if metric_key == "steps_days":
        goal = target.steps_goal
        if goal is None:
            return 0, {"available": False, "unit": "days", "note": "Set a steps goal in Design"}
        complete = {
            row.log_date
            for row in DailyLog.query.filter(
                DailyLog.log_date >= week_start,
                DailyLog.log_date <= min(week_end, today),
                DailyLog.is_complete.is_(True),
            ).all()
        }
        days = set(complete)
        days.add(today)
        hit = 0
        for d in days:
            if d > today:
                continue
            row = DailySteps.query.filter_by(log_date=d).first()
            if row and row.count >= goal:
                hit += 1
        return hit, {"available": True, "unit": "days"}

    if metric_key == "workouts_week":
        n = Workout.query.filter(
            Workout.log_date >= week_start,
            Workout.log_date <= min(week_end, today),
        ).count()
        return n, {"available": True, "unit": "sessions"}

    if metric_key == "routine_pct":
        logs = DailyLog.query.filter(
            DailyLog.log_date >= week_start,
            DailyLog.log_date <= min(week_end, today),
        ).all()
        pcts = []
        for log in logs:
            comps = [
                c for c in log.completions
                if c.step and c.step.is_active
            ]
            if not comps:
                continue
            pcts.append(sum(1 for c in comps if c.completed) / len(comps) * 100)
        if not pcts:
            return 0, {"available": True, "unit": "%", "note": "No routines logged this week yet"}
        return round(sum(pcts) / len(pcts)), {"available": True, "unit": "%"}

    return None, {"available": False, "note": "Unknown metric"}


def _goal_last_activity(goal):
    """Latest datetime of meaningful activity on this goal."""
    stamps = []
    if goal.updated_at:
        stamps.append(goal.updated_at)
    if goal.created_at:
        stamps.append(goal.created_at)
    for c in goal.commitments:
        if c.updated_at:
            stamps.append(c.updated_at)
        elif c.created_at:
            stamps.append(c.created_at)
    for t in goal.todos:
        if t.completed_at:
            stamps.append(t.completed_at)
        if t.created_at:
            stamps.append(t.created_at)
    return max(stamps) if stamps else goal.created_at


def enrich_goal(goal, week_start=None):
    week_start = week_start or iso_week_start()
    data = goal.to_dict()
    week_commitments = [
        c for c in goal.commitments if c.week_start == week_start
    ]
    data["week_start"] = week_start.isoformat()
    data["commitments"] = [c.to_dict() for c in week_commitments]
    data["commitments_done"] = sum(1 for c in week_commitments if c.done)
    data["commitments_total"] = len(week_commitments)

    linked = list(goal.todos)
    linked_open = [t for t in linked if not t.done]
    linked_done = [t for t in linked if t.done]
    data["linked_todos"] = len(linked)
    data["linked_open"] = len(linked_open)
    data["linked_done"] = len(linked_done)

    last = _goal_last_activity(goal)
    data["last_activity_at"] = last.isoformat() if last else None
    if last:
        days_ago = (date.today() - last.date()).days
    else:
        days_ago = 999
    data["last_activity_days"] = days_ago
    data["stalled"] = goal.status == "active" and days_ago >= 7

    if (goal.goal_type or "project") == "metric":
        current, meta = _metric_current(goal.metric_key, week_start)
        target_val = goal.metric_target
        data["metric"] = {
            "key": goal.metric_key,
            "label": METRIC_LABELS.get(goal.metric_key, goal.metric_key),
            "current": current,
            "target": target_val,
            **meta,
        }
        if current is not None and target_val and target_val > 0:
            data["progress_pct"] = min(100, round(current / target_val * 100))
        else:
            data["progress_pct"] = 0
    else:
        # Project: prefer this week's commitments; else linked todos
        if week_commitments:
            data["progress_pct"] = round(
                sum(1 for c in week_commitments if c.done) / len(week_commitments) * 100
            )
        elif linked:
            data["progress_pct"] = round(len(linked_done) / len(linked) * 100)
        else:
            data["progress_pct"] = 0
        data["metric"] = None

    return data


@dashboard_bp.route("/api/goals", methods=["GET"])
def list_goals():
    status = request.args.get("status", "active")
    q = Goal.query
    if status != "all":
        q = q.filter_by(status=status)
    goals = q.order_by(Goal.target_date.asc(), Goal.created_at.desc()).all()
    week_start = iso_week_start()
    return jsonify([enrich_goal(g, week_start) for g in goals])


@dashboard_bp.route("/api/goals/metrics", methods=["GET"])
def list_goal_metrics():
    """Catalog of linkable metrics for metric-type goals."""
    items = []
    for key in VALID_METRIC_KEYS:
        current, meta = _metric_current(key)
        items.append({
            "key": key,
            "label": METRIC_LABELS.get(key, key),
            "current": current,
            **meta,
        })
    return jsonify({"metrics": items, "week_start": iso_week_start().isoformat()})


@dashboard_bp.route("/api/goals", methods=["POST"])
def create_goal():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    goal_type = (data.get("goal_type") or "project").strip()
    if goal_type not in VALID_GOAL_TYPES:
        return jsonify({"error": "goal_type must be project or metric"}), 400
    why = data.get("why")
    if why is None:
        why = data.get("description")
    why = (why or "").strip() or None
    metric_key = data.get("metric_key")
    metric_target = data.get("metric_target")
    if goal_type == "metric":
        if metric_key not in VALID_METRIC_KEYS:
            return jsonify({"error": "Invalid metric_key"}), 400
        try:
            metric_target = float(metric_target)
        except (TypeError, ValueError):
            return jsonify({"error": "metric_target required for metric goals"}), 400
        if metric_target <= 0:
            return jsonify({"error": "metric_target must be > 0"}), 400
    else:
        metric_key = None
        metric_target = None

    goal = Goal(
        title=title,
        description=why,
        why=why,
        target_date=parse_date(data.get("target_date")),
        status="active",
        goal_type=goal_type,
        metric_key=metric_key,
        metric_target=metric_target,
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(enrich_goal(goal)), 201


@dashboard_bp.route("/api/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    data = request.get_json() or {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "Title is required"}), 400
        goal.title = title
    if "why" in data or "description" in data:
        why = data.get("why") if "why" in data else data.get("description")
        why = (why or "").strip() or None
        goal.why = why
        goal.description = why
    if "target_date" in data:
        goal.target_date = parse_date(data["target_date"])
    if "goal_type" in data:
        goal_type = (data["goal_type"] or "").strip()
        if goal_type not in VALID_GOAL_TYPES:
            return jsonify({"error": "goal_type must be project or metric"}), 400
        goal.goal_type = goal_type
        if goal_type == "project":
            goal.metric_key = None
            goal.metric_target = None
    if "metric_key" in data or "metric_target" in data:
        if (goal.goal_type or "project") != "metric":
            return jsonify({"error": "Only metric goals use metric_key/target"}), 400
        if "metric_key" in data:
            key = data.get("metric_key")
            if key not in VALID_METRIC_KEYS:
                return jsonify({"error": "Invalid metric_key"}), 400
            goal.metric_key = key
        if "metric_target" in data:
            try:
                goal.metric_target = float(data.get("metric_target"))
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid metric_target"}), 400
            if goal.metric_target <= 0:
                return jsonify({"error": "metric_target must be > 0"}), 400
    if "status" in data:
        status = data["status"]
        if status not in ("active", "done", "dropped"):
            return jsonify({"error": "Invalid status"}), 400
        goal.status = status
        goal.completed_at = datetime.utcnow() if status == "done" else None
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(enrich_goal(goal))


@dashboard_bp.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    for t in Todo.query.filter_by(goal_id=goal.id).all():
        t.goal_id = None
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"ok": True})


@dashboard_bp.route("/api/goals/<int:goal_id>/commitments", methods=["GET"])
def list_commitments(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    week = parse_date(request.args.get("week_start")) or iso_week_start()
    rows = (GoalCommitment.query
            .filter_by(goal_id=goal.id, week_start=week)
            .order_by(GoalCommitment.id)
            .all())
    return jsonify({
        "goal_id": goal.id,
        "week_start": week.isoformat(),
        "commitments": [c.to_dict() for c in rows],
    })


@dashboard_bp.route("/api/goals/<int:goal_id>/commitments", methods=["POST"])
def create_commitment(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    week = parse_date(data.get("week_start")) or iso_week_start()
    # Normalize to Monday
    week = week - timedelta(days=week.weekday())
    row = GoalCommitment(goal_id=goal.id, week_start=week, text=text, done=False)
    db.session.add(row)
    goal.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(row.to_dict()), 201


@dashboard_bp.route("/api/commitments/<int:commitment_id>", methods=["PUT"])
def update_commitment(commitment_id):
    row = GoalCommitment.query.get_or_404(commitment_id)
    data = request.get_json() or {}
    if "text" in data:
        text = (data["text"] or "").strip()
        if not text:
            return jsonify({"error": "text is required"}), 400
        row.text = text
    if "done" in data:
        row.done = bool(data["done"])
    row.updated_at = datetime.utcnow()
    if row.goal:
        row.goal.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(row.to_dict())


@dashboard_bp.route("/api/commitments/<int:commitment_id>", methods=["DELETE"])
def delete_commitment(commitment_id):
    row = GoalCommitment.query.get_or_404(commitment_id)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


# ── REMINDERS ──────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/reminders", methods=["GET"])
def list_reminders():
    reminders = Reminder.query.order_by(Reminder.time_of_day).all()
    return jsonify([r.to_dict() for r in reminders])


@dashboard_bp.route("/api/reminders", methods=["POST"])
def create_reminder():
    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    time_of_day = (data.get("time_of_day") or "").strip()
    if not label or not time_of_day:
        return jsonify({"error": "label and time_of_day are required"}), 400
    if len(time_of_day) != 5 or time_of_day[2] != ":":
        return jsonify({"error": "time_of_day must be HH:MM"}), 400
    reminder = Reminder(
        label=label,
        kind=(data.get("kind") or "custom").strip() or "custom",
        time_of_day=time_of_day,
        enabled=bool(data.get("enabled", True)),
    )
    db.session.add(reminder)
    db.session.commit()
    return jsonify(reminder.to_dict()), 201


@dashboard_bp.route("/api/reminders/<int:reminder_id>", methods=["PUT"])
def update_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    data = request.get_json() or {}
    if "label" in data:
        reminder.label = (data["label"] or "").strip() or reminder.label
    if "kind" in data:
        reminder.kind = data["kind"]
    if "time_of_day" in data:
        tod = (data["time_of_day"] or "").strip()
        if len(tod) != 5 or tod[2] != ":":
            return jsonify({"error": "time_of_day must be HH:MM"}), 400
        reminder.time_of_day = tod
    if "enabled" in data:
        reminder.enabled = bool(data["enabled"])
    db.session.commit()
    return jsonify(reminder.to_dict())


@dashboard_bp.route("/api/reminders/<int:reminder_id>", methods=["DELETE"])
def delete_reminder(reminder_id):
    reminder = Reminder.query.get_or_404(reminder_id)
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"ok": True})


@dashboard_bp.route("/api/reminders/seed", methods=["POST"])
def seed_reminders():
    if Reminder.query.count() > 0:
        return jsonify([r.to_dict() for r in Reminder.query.order_by(Reminder.time_of_day).all()])
    defaults = [
        Reminder(label="Morning routine", kind="morning", time_of_day="07:30", enabled=True),
        Reminder(label="Daily checklist", kind="daily", time_of_day="12:00", enabled=True),
        Reminder(label="Log protein & calories", kind="nutrition", time_of_day="13:00", enabled=True),
        Reminder(label="Workout check-in", kind="workout", time_of_day="17:00", enabled=True),
        Reminder(label="Evening routine", kind="evening", time_of_day="21:00", enabled=True),
    ]
    for r in defaults:
        db.session.add(r)
    db.session.commit()
    return jsonify([r.to_dict() for r in Reminder.query.order_by(Reminder.time_of_day).all()]), 201
