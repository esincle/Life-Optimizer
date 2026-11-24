"""Lightweight SQLite schema tweaks for existing local DBs."""
from sqlalchemy import inspect, text
from app.extensions import db


def migrate_schema():
    engine = db.engine
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if "nutrition_targets" in tables:
        cols = {c["name"] for c in insp.get_columns("nutrition_targets")}
        with engine.begin() as conn:
            if "calorie_goal" in cols and "maintenance_calories" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "RENAME COLUMN calorie_goal TO maintenance_calories"
                ))
            elif "maintenance_calories" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN maintenance_calories INTEGER NOT NULL DEFAULT 2200"
                ))

        # Re-inspect after possible rename, then add steps_goal if missing
        cols = {c["name"] for c in inspect(engine).get_columns("nutrition_targets")}
        if "steps_goal" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN steps_goal INTEGER NOT NULL DEFAULT 8000"
                ))

    # Remap legacy lifting workouts → full (counts for upper + lower)
    if "workouts" in tables:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE workouts SET kind = 'full' WHERE kind = 'lifting'"
            ))

    if "todos" in tables:
        cols = {c["name"] for c in inspect(engine).get_columns("todos")}
        with engine.begin() as conn:
            if "bucket" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos ADD COLUMN bucket VARCHAR(20) NOT NULL DEFAULT 'overall'"
                ))
            if "for_date" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos ADD COLUMN for_date DATE"
                ))
