from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import (
    Todo, NutritionTarget, NutritionEntry, Workout, Goal, Reminder,
)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/today")


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
        target = NutritionTarget(calorie_goal=2200, protein_goal=150)
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


# ── TODOS ──────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/todos", methods=["GET"])
def list_todos():
    include_done = request.args.get("include_done", "0") == "1"
    q = Todo.query
    if not include_done:
        q = q.filter_by(done=False)
    # Sort: importance desc, then effort asc (quick wins among important), then due
    todos = q.order_by(Todo.done.asc(), Todo.importance.desc(), Todo.effort.asc(), Todo.id.desc()).all()
    return jsonify([t.to_dict() for t in todos])


@dashboard_bp.route("/api/todos", methods=["POST"])
def create_todo():
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    todo = Todo(
        title=title,
        notes=data.get("notes"),
        importance=_clamp(data.get("importance", 3), 1, 5),
        effort=_clamp(data.get("effort", 3), 1, 5),
        due_date=parse_date(data.get("due_date")),
    )
    db.session.add(todo)
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
    if "done" in data:
        todo.done = bool(data["done"])
        todo.completed_at = datetime.utcnow() if todo.done else None
    db.session.commit()
    return jsonify(todo.to_dict())


@dashboard_bp.route("/api/todos/<int:todo_id>/toggle", methods=["POST"])
def toggle_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    todo.done = not todo.done
    todo.completed_at = datetime.utcnow() if todo.done else None
    db.session.commit()
    return jsonify(todo.to_dict())


@dashboard_bp.route("/api/todos/<int:todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({"ok": True})


# ── NUTRITION ──────────────────────────────────────────────────────────────────

@dashboard_bp.route("/api/nutrition/targets", methods=["GET"])
def get_nutrition_targets():
    return jsonify(get_or_create_nutrition_target().to_dict())


@dashboard_bp.route("/api/nutrition/targets", methods=["PUT"])
def update_nutrition_targets():
    data = request.get_json() or {}
    target = get_or_create_nutrition_target()
    if "calorie_goal" in data:
        target.calorie_goal = max(0, int(data["calorie_goal"]))
    if "protein_goal" in data:
        target.protein_goal = max(0, int(data["protein_goal"]))
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
    return jsonify({
        "date": today.isoformat(),
        "targets": target.to_dict(),
        "totals": {"calories": calories, "protein": protein},
        "entries": [e.to_dict() for e in entries],
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


# ── WORKOUTS ───────────────────────────────────────────────────────────────────

VALID_WORKOUT_KINDS = ("zone2", "lifting")


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
    """Week strip: zone2 vs lifting counts and minutes for current week + today."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    workouts = (Workout.query
                .filter(Workout.log_date >= week_start, Workout.log_date <= week_end)
                .all())

    def summarize(kind):
        items = [w for w in workouts if w.kind == kind]
        return {
            "count": len(items),
            "minutes": sum(w.duration_minutes or 0 for w in items),
            "today": any(w.log_date == today for w in items),
        }

    return jsonify({
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "zone2": summarize("zone2"),
        "lifting": summarize("lifting"),
        "workouts": [w.to_dict() for w in sorted(workouts, key=lambda w: (w.log_date, w.id), reverse=True)],
    })


@dashboard_bp.route("/api/workouts", methods=["POST"])
def create_workout():
    data = request.get_json() or {}
    kind = data.get("kind")
    if kind not in VALID_WORKOUT_KINDS:
        return jsonify({"error": "kind must be zone2 or lifting"}), 400
    duration = data.get("duration_minutes")
    workout = Workout(
        log_date=parse_date(data.get("log_date"), date.today()),
        kind=kind,
        title=(data.get("title") or "").strip() or None,
        duration_minutes=int(duration) if duration not in (None, "") else None,
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
    """Create sensible defaults if none exist."""
    if Reminder.query.count() > 0:
        return jsonify([r.to_dict() for r in Reminder.query.order_by(Reminder.time_of_day).all()])
    defaults = [
        Reminder(label="Morning routine", kind="morning", time_of_day="07:30", enabled=True),
        Reminder(label="Log protein & calories", kind="nutrition", time_of_day="13:00", enabled=True),
        Reminder(label="Workout check-in", kind="workout", time_of_day="17:00", enabled=True),
        Reminder(label="Evening routine", kind="evening", time_of_day="21:00", enabled=True),
    ]
    for r in defaults:
        db.session.add(r)
    db.session.commit()
    return jsonify([r.to_dict() for r in Reminder.query.order_by(Reminder.time_of_day).all()]), 201
