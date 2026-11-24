from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.models import RoutineStep, Technique, JournalPrompt

design_bp = Blueprint("design", __name__, url_prefix="/design")


@design_bp.route("/")
def index():
    return render_template("design/index.html")


# ── ROUTINE STEPS ──────────────────────────────────────────────────────────────

VALID_ROUTINES = ("morning", "evening", "daily")


@design_bp.route("/api/routine/<routine_type>", methods=["GET"])
def get_routine(routine_type):
    if routine_type not in VALID_ROUTINES:
        return jsonify({"error": "Invalid routine type"}), 400
    steps = (RoutineStep.query
             .filter_by(routine=routine_type, is_active=True)
             .order_by(RoutineStep.position)
             .all())
    return jsonify([s.to_dict() for s in steps])


@design_bp.route("/api/routine/<routine_type>/step", methods=["POST"])
def create_step(routine_type):
    if routine_type not in VALID_ROUTINES:
        return jsonify({"error": "Invalid routine type"}), 400
    data = request.get_json()
    max_pos = db.session.query(db.func.max(RoutineStep.position)).filter_by(routine=routine_type).scalar() or 0
    step = RoutineStep(
        routine=routine_type,
        title=data["title"],
        description=data.get("description"),
        duration_minutes=data.get("duration_minutes"),
        position=max_pos + 1,
    )
    db.session.add(step)
    db.session.commit()
    return jsonify(step.to_dict()), 201


@design_bp.route("/api/routine/step/<int:step_id>", methods=["PUT"])
def update_step(step_id):
    step = RoutineStep.query.get_or_404(step_id)
    data = request.get_json()
    if "title" in data:
        step.title = data["title"]
    if "description" in data:
        step.description = data["description"]
    if "duration_minutes" in data:
        step.duration_minutes = data["duration_minutes"]
    db.session.commit()
    return jsonify(step.to_dict())


@design_bp.route("/api/routine/step/<int:step_id>", methods=["DELETE"])
def delete_step(step_id):
    step = RoutineStep.query.get_or_404(step_id)
    db.session.delete(step)
    db.session.commit()
    return jsonify({"ok": True})


@design_bp.route("/api/routine/<routine_type>/reorder", methods=["POST"])
def reorder_steps(routine_type):
    data = request.get_json()
    order = data.get("order", [])
    for position, step_id in enumerate(order):
        RoutineStep.query.filter_by(id=step_id).update({"position": position})
    db.session.commit()
    return jsonify({"ok": True})


# ── TECHNIQUES ─────────────────────────────────────────────────────────────────

@design_bp.route("/api/techniques", methods=["GET"])
def get_techniques():
    techniques = Technique.query.order_by(Technique.category, Technique.name).all()
    return jsonify([t.to_dict() for t in techniques])


@design_bp.route("/api/techniques", methods=["POST"])
def create_technique():
    data = request.get_json()
    technique = Technique(
        name=data["name"],
        description=data["description"],
        category=data.get("category"),
    )
    db.session.add(technique)
    db.session.commit()
    return jsonify(technique.to_dict()), 201


@design_bp.route("/api/techniques/<int:tech_id>", methods=["PUT"])
def update_technique(tech_id):
    technique = Technique.query.get_or_404(tech_id)
    data = request.get_json()
    if "name" in data:
        technique.name = data["name"]
    if "description" in data:
        technique.description = data["description"]
    if "category" in data:
        technique.category = data["category"]
    db.session.commit()
    return jsonify(technique.to_dict())


@design_bp.route("/api/techniques/<int:tech_id>", methods=["DELETE"])
def delete_technique(tech_id):
    technique = Technique.query.get_or_404(tech_id)
    db.session.delete(technique)
    db.session.commit()
    return jsonify({"ok": True})


# ── JOURNAL PROMPTS ────────────────────────────────────────────────────────────

@design_bp.route("/api/prompts/<prompt_type>", methods=["GET"])
def get_prompts(prompt_type):
    if prompt_type not in ("gratitude", "evening"):
        return jsonify({"error": "Invalid prompt type"}), 400
    prompts = (JournalPrompt.query
               .filter_by(prompt_type=prompt_type)
               .order_by(JournalPrompt.position)
               .all())
    return jsonify([p.to_dict() for p in prompts])


@design_bp.route("/api/prompts/<prompt_type>", methods=["POST"])
def create_prompt(prompt_type):
    if prompt_type not in ("gratitude", "evening"):
        return jsonify({"error": "Invalid prompt type"}), 400
    data = request.get_json()
    max_pos = db.session.query(db.func.max(JournalPrompt.position)).filter_by(prompt_type=prompt_type).scalar() or 0
    prompt = JournalPrompt(
        prompt_type=prompt_type,
        text=data["text"],
        position=max_pos + 1,
    )
    db.session.add(prompt)
    db.session.commit()
    return jsonify(prompt.to_dict()), 201


@design_bp.route("/api/prompts/<int:prompt_id>", methods=["PUT"])
def update_prompt(prompt_id):
    prompt = JournalPrompt.query.get_or_404(prompt_id)
    data = request.get_json()
    if "text" in data:
        prompt.text = data["text"]
    if "is_active" in data:
        prompt.is_active = data["is_active"]
    db.session.commit()
    return jsonify(prompt.to_dict())


@design_bp.route("/api/prompts/<int:prompt_id>", methods=["DELETE"])
def delete_prompt(prompt_id):
    prompt = JournalPrompt.query.get_or_404(prompt_id)
    db.session.delete(prompt)
    db.session.commit()
    return jsonify({"ok": True})


@design_bp.route("/api/prompts/<prompt_type>/reorder", methods=["POST"])
def reorder_prompts(prompt_type):
    data = request.get_json()
    order = data.get("order", [])
    for position, prompt_id in enumerate(order):
        JournalPrompt.query.filter_by(id=prompt_id).update({"position": position})
    db.session.commit()
    return jsonify({"ok": True})
