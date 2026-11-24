from datetime import datetime
from app.extensions import db


# ── DESIGN / CONFIGURATION MODELS ─────────────────────────────────────────────

class RoutineStep(db.Model):
    __tablename__ = "routine_steps"

    id               = db.Column(db.Integer, primary_key=True)
    routine          = db.Column(db.String(10), nullable=False)  # "morning" | "evening" | "daily"
    title            = db.Column(db.String(200), nullable=False)
    description      = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    position         = db.Column(db.Integer, nullable=False, default=0)
    is_active        = db.Column(db.Boolean, default=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    completions = db.relationship("RoutineCompletion", back_populates="step",
                                  cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "routine": self.routine,
            "title": self.title,
            "description": self.description,
            "duration_minutes": self.duration_minutes,
            "position": self.position,
            "is_active": self.is_active,
        }


class Technique(db.Model):
    __tablename__ = "techniques"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(100), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
        }


class JournalPrompt(db.Model):
    __tablename__ = "journal_prompts"

    id          = db.Column(db.Integer, primary_key=True)
    prompt_type = db.Column(db.String(20), nullable=False)  # "gratitude" | "evening"
    text        = db.Column(db.String(500), nullable=False)
    position    = db.Column(db.Integer, nullable=False, default=0)
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    responses = db.relationship("JournalResponse", back_populates="prompt",
                                cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "prompt_type": self.prompt_type,
            "text": self.text,
            "position": self.position,
            "is_active": self.is_active,
        }


# ── TRACKER MODELS ─────────────────────────────────────────────────────────────

class DailyLog(db.Model):
    __tablename__ = "daily_logs"

    id         = db.Column(db.Integer, primary_key=True)
    log_date   = db.Column(db.Date, nullable=False, unique=True, index=True)
    notes      = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    completions     = db.relationship("RoutineCompletion", back_populates="daily_log",
                                      cascade="all, delete-orphan")
    journal_entries = db.relationship("JournalEntry", back_populates="daily_log",
                                      cascade="all, delete-orphan")


class RoutineCompletion(db.Model):
    __tablename__ = "routine_completions"

    id           = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey("daily_logs.id"), nullable=False)
    step_id      = db.Column(db.Integer, db.ForeignKey("routine_steps.id"), nullable=False)
    completed    = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    daily_log = db.relationship("DailyLog", back_populates="completions")
    step      = db.relationship("RoutineStep", back_populates="completions")

    __table_args__ = (
        db.UniqueConstraint("daily_log_id", "step_id", name="uq_log_step"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "step_id": self.step_id,
            "step_title": self.step.title,
            "step_description": self.step.description,
            "step_duration": self.step.duration_minutes,
            "routine": self.step.routine,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ── JOURNAL MODELS ─────────────────────────────────────────────────────────────

class JournalEntry(db.Model):
    __tablename__ = "journal_entries"

    id           = db.Column(db.Integer, primary_key=True)
    daily_log_id = db.Column(db.Integer, db.ForeignKey("daily_logs.id"), nullable=False)
    entry_type   = db.Column(db.String(20), nullable=False)  # "gratitude" | "evening"
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    daily_log = db.relationship("DailyLog", back_populates="journal_entries")
    responses = db.relationship("JournalResponse", back_populates="entry",
                                cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("daily_log_id", "entry_type", name="uq_log_entry_type"),
    )


class JournalResponse(db.Model):
    __tablename__ = "journal_responses"

    id        = db.Column(db.Integer, primary_key=True)
    entry_id  = db.Column(db.Integer, db.ForeignKey("journal_entries.id"), nullable=False)
    prompt_id = db.Column(db.Integer, db.ForeignKey("journal_prompts.id"), nullable=False)
    body      = db.Column(db.Text, nullable=True)

    entry  = db.relationship("JournalEntry", back_populates="responses")
    prompt = db.relationship("JournalPrompt", back_populates="responses")


# ── TODOS ──────────────────────────────────────────────────────────────────────

class Todo(db.Model):
    __tablename__ = "todos"

    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(300), nullable=False)
    notes        = db.Column(db.Text, nullable=True)
    done         = db.Column(db.Boolean, default=False, nullable=False)
    importance   = db.Column(db.Integer, nullable=False, default=3)  # 1–5
    effort       = db.Column(db.Integer, nullable=False, default=3)  # 1–5
    due_date     = db.Column(db.Date, nullable=True)
    # today = day list · overall = longer backlog · idea = idea inbox
    bucket       = db.Column(db.String(20), nullable=False, default="overall", index=True)
    for_date     = db.Column(db.Date, nullable=True, index=True)  # used when bucket=today
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    steps = db.relationship(
        "TodoStep",
        back_populates="todo",
        cascade="all, delete-orphan",
        order_by="TodoStep.position",
    )

    def to_dict(self, include_steps=True):
        data = {
            "id": self.id,
            "title": self.title,
            "notes": self.notes,
            "done": self.done,
            "importance": self.importance,
            "effort": self.effort,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "bucket": self.bucket,
            "for_date": self.for_date.isoformat() if self.for_date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "steps_done": sum(1 for s in self.steps if s.done),
            "steps_total": len(self.steps),
        }
        if include_steps:
            data["steps"] = [s.to_dict() for s in self.steps]
        return data


class TodoStep(db.Model):
    """Checklist steps under a big todo (e.g. Tax return → print forms)."""
    __tablename__ = "todo_steps"

    id           = db.Column(db.Integer, primary_key=True)
    todo_id      = db.Column(db.Integer, db.ForeignKey("todos.id"), nullable=False, index=True)
    title        = db.Column(db.String(300), nullable=False)
    done         = db.Column(db.Boolean, default=False, nullable=False)
    position     = db.Column(db.Integer, nullable=False, default=0)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    todo = db.relationship("Todo", back_populates="steps")

    def to_dict(self):
        return {
            "id": self.id,
            "todo_id": self.todo_id,
            "title": self.title,
            "done": self.done,
            "position": self.position,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ── NUTRITION ──────────────────────────────────────────────────────────────────

class NutritionTarget(db.Model):
    """Singleton: maintenance calories, protein goal, and daily step goal."""
    __tablename__ = "nutrition_targets"

    id                   = db.Column(db.Integer, primary_key=True)
    # Kept as calorie_goal in older DBs; migrate maps it → maintenance_calories usage
    maintenance_calories = db.Column(db.Integer, nullable=False, default=2200)
    protein_goal         = db.Column(db.Integer, nullable=False, default=150)
    steps_goal           = db.Column(db.Integer, nullable=False, default=8000)
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "maintenance_calories": self.maintenance_calories,
            "protein_goal": self.protein_goal,
            "steps_goal": self.steps_goal,
        }


class DailySteps(db.Model):
    """One step-count entry per calendar day."""
    __tablename__ = "daily_steps"

    id         = db.Column(db.Integer, primary_key=True)
    log_date   = db.Column(db.Date, nullable=False, unique=True, index=True)
    count      = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "log_date": self.log_date.isoformat(),
            "count": self.count,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NutritionEntry(db.Model):
    __tablename__ = "nutrition_entries"

    id         = db.Column(db.Integer, primary_key=True)
    log_date   = db.Column(db.Date, nullable=False, index=True)
    label      = db.Column(db.String(200), nullable=False)
    calories   = db.Column(db.Integer, nullable=False, default=0)
    protein    = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "log_date": self.log_date.isoformat(),
            "label": self.label,
            "calories": self.calories,
            "protein": self.protein,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── WORKOUTS ───────────────────────────────────────────────────────────────────

class Workout(db.Model):
    __tablename__ = "workouts"

    id               = db.Column(db.Integer, primary_key=True)
    log_date         = db.Column(db.Date, nullable=False, index=True)
    kind             = db.Column(db.String(20), nullable=False)  # zone2 | full | upper | lower
    title            = db.Column(db.String(200), nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    notes            = db.Column(db.Text, nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "log_date": self.log_date.isoformat(),
            "kind": self.kind,
            "title": self.title,
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── NEAR-TERM GOALS ────────────────────────────────────────────────────────────

class Goal(db.Model):
    __tablename__ = "goals"

    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    status      = db.Column(db.String(20), nullable=False, default="active")  # active|done|dropped
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ── REMINDERS (browser / computer push) ────────────────────────────────────────

class Reminder(db.Model):
    __tablename__ = "reminders"

    id           = db.Column(db.Integer, primary_key=True)
    label        = db.Column(db.String(200), nullable=False)
    kind         = db.Column(db.String(40), nullable=False, default="custom")
    # morning | evening | nutrition | workout | custom
    time_of_day  = db.Column(db.String(5), nullable=False)  # "HH:MM" 24h local
    enabled      = db.Column(db.Boolean, default=True, nullable=False)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "time_of_day": self.time_of_day,
            "enabled": self.enabled,
        }
