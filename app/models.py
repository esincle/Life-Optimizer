from datetime import datetime
from app.extensions import db


# ── DESIGN / CONFIGURATION MODELS ─────────────────────────────────────────────

class RoutineStep(db.Model):
    __tablename__ = "routine_steps"

    id               = db.Column(db.Integer, primary_key=True)
    routine          = db.Column(db.String(10), nullable=False)  # "morning" | "evening"
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
