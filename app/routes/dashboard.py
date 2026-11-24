from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import (
    Todo, TodoStep, NutritionTarget, NutritionEntry, DailySteps,
    Workout, Goal, Reminder,
)

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
        target = NutritionTarget(
            tdee_baseline=2050,
            steps_kcal_per_1k=45,
            protein_goal=150,
            steps_goal=8000,
        )
        db.session.add(target)
        db.session.commit()
    return target


def parse_date(value, fallback=None):
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def compute_tdee_for_day(day, target=None):
    """TDEE = baseline + 45kcal/1k steps + workout calories burned."""
    target = target or get_or_create_nutrition_target()
    steps_row = DailySteps.query.filter_by(log_date=day).first()
    step_count = steps_row.count if steps_row else 0
    rate = target.steps_kcal_per_1k or 0
    from_steps = round((step_count / 1000.0) * rate) if rate else 0
    workouts = Workout.query.filter_by(log_date=day).all()
    from_workouts = sum(w.calories_burned or 0 for w in workouts)
    baseline = target.tdee_baseline or 0
    tdee = baseline + from_steps + from_workouts
    return {
        "tdee": tdee,
        "baseline": baseline,
        "from_steps": from_steps,
        "from_workouts": from_workouts,
        "steps": step_count,
        "steps_kcal_per_1k": rate,
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


@dashboard_bp.route("/api/todos", methods=["GET"])
def list_todos():
    """Open todos for the dashboard. Completed items are excluded by default
    (use /api/todos/completed or include_done=1 for history/stats)."""
    include_done = request.args.get("include_done", "0") == "1"
    bucket = request.args.get("bucket", "overall")
    if bucket not in VALID_TODO_BUCKETS:
        return jsonify({"error": "bucket must be today, overall, or idea"}), 400

    q = Todo.query.filter_by(bucket=bucket)
    if not include_done:
        q = q.filter_by(done=False)

    if bucket == "today":
        day = parse_date(request.args.get("date"), date.today())
        q = q.filter(Todo.for_date == day)

    if bucket == "idea":
        todos = q.order_by(Todo.id.desc()).all()
    else:
        todos = q.order_by(
            Todo.done.asc(), Todo.importance.desc(), Todo.effort.asc(), Todo.id.desc()
        ).all()
    return jsonify([t.to_dict() for t in todos])


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

    # Ideas stay light — default mid importance/effort unless provided
    default_imp = 3 if bucket != "idea" else 2
    default_eff = 3 if bucket != "idea" else 1

    todo = Todo(
        title=title,
        notes=data.get("notes"),
        importance=_clamp(data.get("importance", default_imp), 1, 5),
        effort=_clamp(data.get("effort", default_eff), 1, 5),
        due_date=parse_date(data.get("due_date")),
        bucket=bucket,
        for_date=for_date,
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
        todo.importance = _clamp(data["importance"], 1, 5)
    if "effort" in data:
        todo.effort = _clamp(data["effort"], 1, 5)
    if "due_date" in data:
        todo.due_date = parse_date(data["due_date"])
    if "bucket" in data:
        bucket = (data["bucket"] or "").strip()
        if bucket not in VALID_TODO_BUCKETS:
            return jsonify({"error": "Invalid bucket"}), 400
        todo.bucket = bucket
        if bucket == "today":
            todo.for_date = parse_date(data.get("for_date"), todo.for_date or date.today())
        else:
            todo.for_date = None
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
    db.session.commit()
    return jsonify(todo.to_dict())


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
    return jsonify(get_or_create_nutrition_target().to_dict())


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
        target.protein_goal = max(0, int(data["protein_goal"]))
    if "steps_goal" in data:
        target.steps_goal = max(0, int(data["steps_goal"]))
    db.session.commit()
    return jsonify(target.to_dict())


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
    deficit = tdee_info["tdee"] - calories  # positive = deficit
    return jsonify({
        "date": today.isoformat(),
        "targets": target.to_dict(),
        "totals": {"calories": calories, "protein": protein},
        "tdee": tdee_info,
        "deficit": deficit,  # + deficit, − surplus
        "entries": [e.to_dict() for e in entries],
    })


@dashboard_bp.route("/api/nutrition/week", methods=["GET"])
def nutrition_week():
    """Weekly calorie deficit/surplus vs dynamic TDEE + protein ±15% days."""
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

    days = []
    protein_hit_days = 0
    days_with_food = 0
    total_deficit = 0

    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        totals = by_day.get(d)
        tdee_info = compute_tdee_for_day(d, target)
        if not totals:
            days.append({
                "date": d.isoformat(),
                "calories": 0,
                "protein": 0,
                "tdee": tdee_info,
                "deficit": None,
                "protein_within_15": False,
                "logged": False,
            })
            continue
        days_with_food += 1
        deficit = tdee_info["tdee"] - totals["calories"]
        total_deficit += deficit
        within = False
        if target.protein_goal > 0:
            lo = target.protein_goal * (1 - PROTEIN_TOLERANCE)
            hi = target.protein_goal * (1 + PROTEIN_TOLERANCE)
            within = lo <= totals["protein"] <= hi
            if within:
                protein_hit_days += 1
        days.append({
            "date": d.isoformat(),
            "calories": totals["calories"],
            "protein": totals["protein"],
            "tdee": tdee_info,
            "deficit": deficit,
            "protein_within_15": within,
            "logged": True,
        })

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "targets": target.to_dict(),
        "total_deficit": total_deficit,  # sum of (dynamic TDEE − intake) on logged days
        "avg_deficit": round(total_deficit / days_with_food) if days_with_food else 0,
        "days_logged": days_with_food,
        "protein_hit_days": protein_hit_days,
        "protein_tolerance_pct": int(PROTEIN_TOLERANCE * 100),
        "days": days,
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


@dashboard_bp.route("/api/nutrition/entries/<int:entry_id>", methods=["DELETE"])
def delete_nutrition_entry(entry_id):
    entry = NutritionEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"ok": True})


# ── STEPS ──────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/steps/today", methods=["GET"])
def get_steps_today():
    today = date.today()
    target = get_or_create_nutrition_target()
    row = DailySteps.query.filter_by(log_date=today).first()
    count = row.count if row else 0
    goal = target.steps_goal or 0
    return jsonify({
        "date": today.isoformat(),
        "count": count,
        "steps_goal": goal,
        "pct": min(100, round(count / goal * 100)) if goal else 0,
        "logged": row is not None,
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
    goal = target.steps_goal or 0
    return jsonify({
        "date": today.isoformat(),
        "count": row.count,
        "steps_goal": goal,
        "pct": min(100, round(row.count / goal * 100)) if goal else 0,
        "logged": True,
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

    days = []
    total = 0
    logged = 0
    hit = 0
    goal = target.steps_goal or 0
    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        if d in by_date:
            count = by_date[d]
            logged += 1
            total += count
            if goal and count >= goal:
                hit += 1
            days.append({"date": d.isoformat(), "count": count, "logged": True, "hit_goal": bool(goal and count >= goal)})
        else:
            days.append({"date": d.isoformat(), "count": 0, "logged": False, "hit_goal": False})

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "steps_goal": goal,
        "total": total,
        "avg": round(total / logged) if logged else 0,
        "days_logged": logged,
        "goal_hit_days": hit,
        "days": days,
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
    """Week: upper/lower counts (full counts for both) + overall Zone 2."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    workouts = (Workout.query
                .filter(Workout.log_date >= week_start, Workout.log_date <= week_end)
                .all())

    zone2 = [w for w in workouts if w.kind == "zone2"]
    upper_count = sum(1 for w in workouts if w.kind in ("upper", "full"))
    lower_count = sum(1 for w in workouts if w.kind in ("lower", "full"))
    full_count = sum(1 for w in workouts if w.kind == "full")

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "upper": {
            "count": upper_count,
            "today": any(w.log_date == today and w.kind in ("upper", "full") for w in workouts),
        },
        "lower": {
            "count": lower_count,
            "today": any(w.log_date == today and w.kind in ("lower", "full") for w in workouts),
        },
        "full": {"count": full_count},
        "zone2": {
            "count": len(zone2),
            "minutes": sum(w.duration_minutes or 0 for w in zone2),
            "today": any(w.log_date == today for w in zone2),
        },
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

@dashboard_bp.route("/api/goals", methods=["GET"])
def list_goals():
    status = request.args.get("status", "active")
    q = Goal.query
    if status != "all":
        q = q.filter_by(status=status)
    goals = q.order_by(Goal.target_date.asc(), Goal.created_at.desc()).all()
    return jsonify([g.to_dict() for g in goals])


@dashboard_bp.route("/api/goals", methods=["POST"])
def create_goal():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    goal = Goal(
        title=title,
        description=data.get("description"),
        target_date=parse_date(data.get("target_date")),
        status="active",
    )
    db.session.add(goal)
    db.session.commit()
    return jsonify(goal.to_dict()), 201


@dashboard_bp.route("/api/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    data = request.get_json() or {}
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            return jsonify({"error": "Title is required"}), 400
        goal.title = title
    if "description" in data:
        goal.description = data["description"]
    if "target_date" in data:
        goal.target_date = parse_date(data["target_date"])
    if "status" in data:
        status = data["status"]
        if status not in ("active", "done", "dropped"):
            return jsonify({"error": "Invalid status"}), 400
        goal.status = status
        goal.completed_at = datetime.utcnow() if status == "done" else None
    db.session.commit()
    return jsonify(goal.to_dict())


@dashboard_bp.route("/api/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    db.session.delete(goal)
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
