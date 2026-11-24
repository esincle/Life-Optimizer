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
            # Legacy path: calorie_goal → maintenance_calories
            if "calorie_goal" in cols and "maintenance_calories" not in cols and "tdee_baseline" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "RENAME COLUMN calorie_goal TO maintenance_calories"
                ))
            elif "maintenance_calories" not in cols and "tdee_baseline" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN maintenance_calories INTEGER NOT NULL DEFAULT 2050"
                ))

        cols = {c["name"] for c in inspect(engine).get_columns("nutrition_targets")}
        with engine.begin() as conn:
            # maintenance_calories → tdee_baseline (dynamic TDEE)
            if "maintenance_calories" in cols and "tdee_baseline" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "RENAME COLUMN maintenance_calories TO tdee_baseline"
                ))
            elif "tdee_baseline" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN tdee_baseline INTEGER NOT NULL DEFAULT 2050"
                ))

        cols = {c["name"] for c in inspect(engine).get_columns("nutrition_targets")}
        with engine.begin() as conn:
            if "steps_goal" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN steps_goal INTEGER NOT NULL DEFAULT 8000"
                ))
            if "steps_kcal_per_1k" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN steps_kcal_per_1k INTEGER NOT NULL DEFAULT 45"
                ))

    if "workouts" in tables:
        cols = {c["name"] for c in inspect(engine).get_columns("workouts")}
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE workouts SET kind = 'full' WHERE kind = 'lifting'"
            ))
            if "calories_burned" not in cols:
                conn.execute(text(
                    "ALTER TABLE workouts ADD COLUMN calories_burned INTEGER"
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
