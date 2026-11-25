from datetime import date, timedelta
from flask import Blueprint, redirect, url_for, request, jsonify
from app.extensions import db
from app.models import DailyLog, RoutineCompletion, RoutineStep, JournalEntry

tracker_bp = Blueprint("tracker", __name__, url_prefix="/tracker")


def get_or_create_log(log_date):
    log = DailyLog.query.filter_by(log_date=log_date).first()
    if not log:
        log = DailyLog(log_date=log_date)
        db.session.add(log)
        db.session.flush()
    return log


@tracker_bp.route("/")
def index():
    # Phase 1: Tracker merged into Today
    return redirect(url_for("dashboard.index"))


@tracker_bp.route("/api/today", methods=["GET"])
def get_today():
    today = date.today()
    log = DailyLog.query.filter_by(log_date=today).first()
    if not log:
        return jsonify({"date": today.isoformat(), "completions": []})
    completions = [c.to_dict() for c in log.completions]
    return jsonify({"date": today.isoformat(), "log_id": log.id, "completions": completions})


@tracker_bp.route("/api/today/init", methods=["POST"])
def init_today():
    today = date.today()
    log = get_or_create_log(today)
    active_steps = RoutineStep.query.filter_by(is_active=True).all()
    existing_step_ids = {c.step_id for c in log.completions}
    for step in active_steps:
        if step.id not in existing_step_ids:
            completion = RoutineCompletion(daily_log_id=log.id, step_id=step.id)
            db.session.add(completion)
    db.session.commit()
    completions = [c.to_dict() for c in log.completions]
    return jsonify({"date": today.isoformat(), "log_id": log.id, "completions": completions})


@tracker_bp.route("/api/completion/<int:completion_id>/toggle", methods=["POST"])
def toggle_completion(completion_id):
    from datetime import datetime
    completion = RoutineCompletion.query.get_or_404(completion_id)
    completion.completed = not completion.completed
    completion.completed_at = datetime.utcnow() if completion.completed else None
    db.session.commit()
    return jsonify(completion.to_dict())


@tracker_bp.route("/api/streaks", methods=["GET"])
def get_streaks():
    active_steps = RoutineStep.query.filter_by(is_active=True).all()
    streaks = {}
    today = date.today()

    for step in active_steps:
        streak = 0
        check_date = today
        while True:
            log = DailyLog.query.filter_by(log_date=check_date).first()
            if not log:
                break
            completion = RoutineCompletion.query.filter_by(
                daily_log_id=log.id, step_id=step.id, completed=True
            ).first()
            if completion:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break
        streaks[step.id] = {
            "step_id": step.id,
            "title": step.title,
            "routine": step.routine,
            "streak": streak,
        }

    return jsonify(list(streaks.values()))


@tracker_bp.route("/api/history", methods=["GET"])
def get_history():
    days = int(request.args.get("days", 30))
    today = date.today()
    result = []

    for i in range(days):
        d = today - timedelta(days=i)
        log = DailyLog.query.filter_by(log_date=d).first()
        has_journal = False
        morning_pct = 0
        evening_pct = 0
        daily_pct = 0

        if log:
            morning = [c for c in log.completions if c.step.routine == "morning"]
            evening = [c for c in log.completions if c.step.routine == "evening"]
            daily = [c for c in log.completions if c.step.routine == "daily"]
            morning_pct = (sum(1 for c in morning if c.completed) / len(morning) * 100) if morning else 0
            evening_pct = (sum(1 for c in evening if c.completed) / len(evening) * 100) if evening else 0
            daily_pct = (sum(1 for c in daily if c.completed) / len(daily) * 100) if daily else 0
            has_journal = any(e.entry_type == "evening" for e in log.journal_entries)

        result.append({
            "date": d.isoformat(),
            "morning_pct": round(morning_pct),
            "evening_pct": round(evening_pct),
            "daily_pct": round(daily_pct),
            "has_journal": has_journal,
        })

    return jsonify(result)


@tracker_bp.route("/api/history/<date_str>", methods=["GET"])
def get_history_day(date_str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    log = DailyLog.query.filter_by(log_date=d).first()
    if not log:
        return jsonify({"date": date_str, "completions": []})

    return jsonify({
        "date": date_str,
        "completions": [c.to_dict() for c in log.completions],
    })
