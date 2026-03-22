from datetime import date, datetime
from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import DailyLog, JournalEntry, JournalPrompt, JournalResponse

journal_bp = Blueprint("journal", __name__, url_prefix="/journal")


def get_or_create_log(log_date):
    log = DailyLog.query.filter_by(log_date=log_date).first()
    if not log:
        log = DailyLog(log_date=log_date)
        db.session.add(log)
        db.session.flush()
    return log


@journal_bp.route("/")
def index():
    return render_template("journal/index.html")


@journal_bp.route("/api/today/<entry_type>", methods=["GET"])
def get_today_entry(entry_type):
    if entry_type not in ("gratitude", "evening"):
        return jsonify({"error": "Invalid entry type"}), 400

    today = date.today()
    prompts = (JournalPrompt.query
               .filter_by(prompt_type=entry_type, is_active=True)
               .order_by(JournalPrompt.position)
               .all())

    log = DailyLog.query.filter_by(log_date=today).first()
    entry = None
    responses_map = {}

    if log:
        entry = JournalEntry.query.filter_by(daily_log_id=log.id, entry_type=entry_type).first()
        if entry:
            for r in entry.responses:
                responses_map[r.prompt_id] = r.body

    result = {
        "date": today.isoformat(),
        "entry_type": entry_type,
        "entry_id": entry.id if entry else None,
        "prompts": [
            {
                "id": p.id,
                "text": p.text,
                "response": responses_map.get(p.id, ""),
            }
            for p in prompts
        ],
    }
    return jsonify(result)


@journal_bp.route("/api/today/<entry_type>/save", methods=["POST"])
def save_today_entry(entry_type):
    if entry_type not in ("gratitude", "evening"):
        return jsonify({"error": "Invalid entry type"}), 400

    data = request.get_json()
    responses_data = data.get("responses", {})  # {prompt_id: body_text}

    today = date.today()
    log = get_or_create_log(today)

    entry = JournalEntry.query.filter_by(daily_log_id=log.id, entry_type=entry_type).first()
    if not entry:
        entry = JournalEntry(daily_log_id=log.id, entry_type=entry_type)
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
            response = JournalResponse(entry_id=entry.id, prompt_id=prompt_id, body=body)
            db.session.add(response)

    db.session.commit()
    return jsonify({"ok": True, "entry_id": entry.id})


@journal_bp.route("/api/entries", methods=["GET"])
def list_entries():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    entries = (JournalEntry.query
               .join(DailyLog)
               .order_by(DailyLog.log_date.desc())
               .paginate(page=page, per_page=per_page, error_out=False))

    result = []
    for entry in entries.items:
        first_response = entry.responses[0].body if entry.responses else ""
        snippet = (first_response[:80] + "…") if first_response and len(first_response) > 80 else first_response
        result.append({
            "id": entry.id,
            "date": entry.daily_log.log_date.isoformat(),
            "entry_type": entry.entry_type,
            "snippet": snippet,
        })

    return jsonify({
        "entries": result,
        "page": page,
        "has_more": entries.has_next,
    })


@journal_bp.route("/api/entries/<date_str>/<entry_type>", methods=["GET"])
def get_entry(date_str, entry_type):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    log = DailyLog.query.filter_by(log_date=d).first()
    if not log:
        return jsonify({"error": "No entry found"}), 404

    entry = JournalEntry.query.filter_by(daily_log_id=log.id, entry_type=entry_type).first()
    if not entry:
        return jsonify({"error": "No entry found"}), 404

    return jsonify({
        "id": entry.id,
        "date": date_str,
        "entry_type": entry_type,
        "responses": [
            {
                "prompt_id": r.prompt_id,
                "prompt_text": r.prompt.text,
                "body": r.body,
            }
            for r in sorted(entry.responses, key=lambda r: r.prompt.position)
        ],
    })


@journal_bp.route("/api/search", methods=["GET"])
def search_entries():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"entries": []})

    matching_responses = (JournalResponse.query
                          .filter(JournalResponse.body.ilike(f"%{q}%"))
                          .all())

    seen_entry_ids = set()
    result = []
    for response in matching_responses:
        entry = response.entry
        if entry.id not in seen_entry_ids:
            seen_entry_ids.add(entry.id)
            snippet = (response.body[:80] + "…") if response.body and len(response.body) > 80 else response.body
            result.append({
                "id": entry.id,
                "date": entry.daily_log.log_date.isoformat(),
                "entry_type": entry.entry_type,
                "snippet": snippet,
            })

    return jsonify({"entries": result})
