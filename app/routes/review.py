from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import (
    DailyLog, Todo, RoutineStep, RoutineCompletion,
    JournalPrompt, JournalEntry, JournalResponse,
    Workout, AppSettings,
)

review_bp = Blueprint("review", __name__, url_prefix="/review")

VALID_DISPOSITIONS = ("done", "roll", "overall", "delete", "skip")


def get_or_create_log(log_date):
    log = DailyLog.query.filter_by(log_date=log_date).first()
    if not log:
        log = DailyLog(log_date=log_date)
        db.session.add(log)
        db.session.flush()
    return log


def get_settings():
    row = AppSettings.query.first()
    if not row:
        row = AppSettings()
        db.session.add(row)
        db.session.commit()
    return row


def sort_todos(todos):
    manual = [t for t in todos if t.manual_sort]
    auto = [t for t in todos if not t.manual_sort]
    manual.sort(key=lambda t: (t.manual_position is None, t.manual_position or 0, t.id))
    auto.sort(key=lambda t: (-(t.importance or 0), t.effort or 0, -(t.id or 0)))
    return manual + auto


@review_bp.route("/")
def index():
    return render_template("review/index.html")


@review_bp.route("/evening")
def evening():
    return render_template("review/evening.html")


@review_bp.route("/api/shutdown", methods=["GET"])
def shutdown_state():
    today = parse_date(request.args.get("date")) or date.today()
    tomorrow = today + timedelta(days=1)
    settings = get_settings()
    log = get_or_create_log(today)
    db.session.commit()

    open_today = sort_todos(
        Todo.query.filter_by(bucket="today", done=False, for_date=today).all()
    )
    overall = sort_todos(
        Todo.query.filter_by(bucket="overall", done=False).all()
    )
    tomorrow_todos = sort_todos(
        Todo.query.filter_by(bucket="today", done=False, for_date=tomorrow).all()
    )

    # Evening routine completions
    active_evening = (RoutineStep.query
                      .filter_by(routine="evening", is_active=True)
                      .order_by(RoutineStep.position)
                      .all())
    existing = {c.step_id: c for c in log.completions}
    for step in active_evening:
        if step.id not in existing:
            c = RoutineCompletion(daily_log_id=log.id, step_id=step.id)
            db.session.add(c)
    db.session.commit()
    # Re-query so newly created completions are included
    evening_completions = []
    for c in (RoutineCompletion.query
              .filter_by(daily_log_id=log.id)
              .all()):
        if c.step and c.step.routine == "evening" and c.step.is_active:
            evening_completions.append(c.to_dict())
    evening_completions.sort(
        key=lambda d: next(
            (s.position for s in active_evening if s.id == d["step_id"]), 0
        )
    )

    prompts = (JournalPrompt.query
               .filter_by(prompt_type="evening", is_active=True)
               .order_by(JournalPrompt.position)
               .all())
    entry = JournalEntry.query.filter_by(daily_log_id=log.id, entry_type="evening").first()
    responses_map = {}
    if entry:
        for r in entry.responses:
            responses_map[r.prompt_id] = r.body

    tmr_log = DailyLog.query.filter_by(log_date=tomorrow).first()
    tmr_hours = (
        tmr_log.available_hours
        if tmr_log and tmr_log.available_hours is not None
        else settings.default_available_hours
    )

    return jsonify({
        "date": today.isoformat(),
        "tomorrow": tomorrow.isoformat(),
        "is_complete": bool(log.is_complete),
        "shutdown_step": log.shutdown_step,
        "todo_cap": settings.todo_cap or 3,
        "open_todos": [t.to_dict() for t in open_today],
        "overall_todos": [t.to_dict(include_steps=False) for t in overall],
        "tomorrow_todos": [t.to_dict(include_steps=False) for t in tomorrow_todos],
        "evening_completions": evening_completions,
        "reflection": {
            "prompts": [
                {"id": p.id, "text": p.text, "response": responses_map.get(p.id, "")}
                for p in prompts
            ],
            "entry_id": entry.id if entry else None,
        },
        "tomorrow_available_hours": tmr_hours,
        "default_available_hours": settings.default_available_hours,
    })


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@review_bp.route("/api/shutdown/step", methods=["POST"])
def shutdown_save_step():
    data = request.get_json() or {}
    today = parse_date(data.get("date")) or date.today()
    log = get_or_create_log(today)
    step = data.get("shutdown_step")
    if step is not None:
        try:
            log.shutdown_step = max(0, min(4, int(step)))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid shutdown_step"}), 400
    db.session.commit()
    return jsonify({"ok": True, "shutdown_step": log.shutdown_step})


@review_bp.route("/api/shutdown/tasks", methods=["POST"])
def shutdown_tasks():
    """Apply dispositions to today's open tasks.
    dispositions: {todo_id: 'done'|'roll'|'overall'|'delete'|'skip'}
    """
    data = request.get_json() or {}
    today = parse_date(data.get("date")) or date.today()
    tomorrow = today + timedelta(days=1)
    dispositions = data.get("dispositions") or {}
    log = get_or_create_log(today)

    for tid_str, action in dispositions.items():
        try:
            tid = int(tid_str)
        except (TypeError, ValueError):
            continue
        action = (action or "skip").strip()
        if action not in VALID_DISPOSITIONS:
            continue
        todo = Todo.query.get(tid)
        if not todo or todo.bucket != "today" or todo.for_date != today:
            continue
        if action == "skip":
            continue
        if action == "done":
            todo.done = True
            todo.completed_at = datetime.utcnow()
            for step in todo.steps:
                step.done = True
                if not step.completed_at:
                    step.completed_at = datetime.utcnow()
        elif action == "roll":
            todo.for_date = tomorrow
            todo.rollover_count = (todo.rollover_count or 0) + 1
            todo.manual_sort = False
            todo.manual_position = None
        elif action == "overall":
            todo.bucket = "overall"
            todo.for_date = None
            todo.manual_sort = False
            todo.manual_position = None
        elif action == "delete":
            db.session.delete(todo)

    log.shutdown_step = max(log.shutdown_step or 0, 1)
    db.session.commit()
    return jsonify({"ok": True})


@review_bp.route("/api/shutdown/reflection", methods=["POST"])
def shutdown_reflection():
    data = request.get_json() or {}
    today = parse_date(data.get("date")) or date.today()
    responses_data = data.get("responses") or {}
    log = get_or_create_log(today)

    entry = JournalEntry.query.filter_by(daily_log_id=log.id, entry_type="evening").first()
    if not entry:
        entry = JournalEntry(daily_log_id=log.id, entry_type="evening")
        db.session.add(entry)
        db.session.flush()
    else:
        entry.updated_at = datetime.utcnow()

    for prompt_id_str, body in responses_data.items():
        prompt_id = int(prompt_id_str)
        response = JournalResponse.query.filter_by(entry_id=entry.id, prompt_id=prompt_id).first()
        if response:
            response.body = body
        else:
            db.session.add(JournalResponse(entry_id=entry.id, prompt_id=prompt_id, body=body))

    log.shutdown_step = max(log.shutdown_step or 0, 3)
    db.session.commit()
    return jsonify({"ok": True, "entry_id": entry.id})


@review_bp.route("/api/shutdown/plan", methods=["POST"])
def shutdown_plan():
    """Set tomorrow's top tasks (up to cap) and available hours."""
    data = request.get_json() or {}
    today = parse_date(data.get("date")) or date.today()
    tomorrow = today + timedelta(days=1)
    settings = get_settings()
    cap = settings.todo_cap or 3
    todo_ids = data.get("todo_ids") or []
    if not isinstance(todo_ids, list):
        return jsonify({"error": "todo_ids must be a list"}), 400
    if len(todo_ids) > cap:
        return jsonify({"error": f"Pick at most {cap} tasks for tomorrow"}), 400

    # Clear other today-bucket items already assigned to tomorrow that aren't selected
    selected = set()
    for tid in todo_ids:
        try:
            selected.add(int(tid))
        except (TypeError, ValueError):
            continue

    existing_tmr = Todo.query.filter_by(bucket="today", for_date=tomorrow, done=False).all()
    for t in existing_tmr:
        if t.id not in selected:
            # send extras back to overall rather than deleting
            t.bucket = "overall"
            t.for_date = None

    for i, tid in enumerate(todo_ids):
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            continue
        todo = Todo.query.get(tid)
        if not todo or todo.done:
            continue
        todo.bucket = "today"
        todo.for_date = tomorrow
        todo.manual_sort = True
        todo.manual_position = i

    tmr_log = get_or_create_log(tomorrow)
    if "available_hours" in data:
        raw = data.get("available_hours")
        if raw in ("", None):
            tmr_log.available_hours = None
        else:
            try:
                tmr_log.available_hours = max(0.5, min(24, float(raw)))
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid available_hours"}), 400

    log = get_or_create_log(today)
    log.shutdown_step = max(log.shutdown_step or 0, 4)
    db.session.commit()
    return jsonify({"ok": True, "tomorrow": tomorrow.isoformat()})


@review_bp.route("/api/shutdown/complete", methods=["POST"])
def shutdown_complete():
    data = request.get_json() or {}
    today = parse_date(data.get("date")) or date.today()
    log = get_or_create_log(today)
    log.is_complete = True
    log.completed_at = datetime.utcnow()
    log.shutdown_step = 4
    db.session.commit()
    return jsonify({
        "ok": True,
        "date": today.isoformat(),
        "is_complete": True,
        "completed_at": log.completed_at.isoformat(),
    })


@review_bp.route("/api/morning-brief", methods=["GET"])
def morning_brief():
    today = date.today()
    settings = get_settings()
    log = get_or_create_log(today)
    db.session.commit()

    todos = sort_todos(
        Todo.query.filter_by(bucket="today", done=False, for_date=today).all()
    )
    planned = sum(t.estimate_minutes or 0 for t in todos)
    available = (
        log.available_hours
        if log.available_hours is not None
        else settings.default_available_hours
    )

    # Suggest workout kind: least-trained among upper/lower this week, else zone2
    week_start = today - timedelta(days=today.weekday())
    workouts = Workout.query.filter(
        Workout.log_date >= week_start, Workout.log_date <= today
    ).all()
    upper = sum(1 for w in workouts if w.kind in ("upper", "full"))
    lower = sum(1 for w in workouts if w.kind in ("lower", "full"))
    zone2 = sum(1 for w in workouts if w.kind == "zone2")
    if upper <= lower and upper <= zone2:
        suggest = "Upper"
    elif lower <= zone2:
        suggest = "Lower"
    else:
        suggest = "Zone 2"

    show_banner = not log.morning_seen and not log.is_complete

    return jsonify({
        "date": today.isoformat(),
        "show_banner": show_banner,
        "morning_seen": bool(log.morning_seen),
        "is_complete": bool(log.is_complete),
        "priorities": [
            {"id": t.id, "title": t.title, "estimate_minutes": t.estimate_minutes}
            for t in todos[: settings.todo_cap or 3]
        ],
        "planned_minutes": planned,
        "available_hours": available,
        "workout_suggestion": suggest,
        "evening_from": settings.evening_from or "18:00",
        "morning_until": settings.morning_until or "12:00",
    })


@review_bp.route("/api/morning-brief/dismiss", methods=["POST"])
def morning_brief_dismiss():
    today = date.today()
    log = get_or_create_log(today)
    log.morning_seen = True
    db.session.commit()
    return jsonify({"ok": True})
