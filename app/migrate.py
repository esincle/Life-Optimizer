"""Lightweight SQLite schema tweaks for existing local DBs."""
from sqlalchemy import inspect, text
from app.extensions import db


def migrate_schema():
    engine = db.engine
    # These ALTER tweaks are SQLite-only (local upgrades). Fresh Postgres uses create_all.
    if engine.dialect.name != "sqlite":
        return
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
                # Nullable: unset until the user saves a goal in Design
                conn.execute(text(
                    "ALTER TABLE nutrition_targets ADD COLUMN steps_goal INTEGER"
                ))
            if "steps_kcal_per_1k" not in cols:
                conn.execute(text(
                    "ALTER TABLE nutrition_targets "
                    "ADD COLUMN steps_kcal_per_1k INTEGER NOT NULL DEFAULT 45"
                ))

        # SQLite can't DROP NOT NULL — rebuild so protein_goal / steps_goal are nullable
        cols_info = inspect(engine).get_columns("nutrition_targets")
        by_name = {c["name"]: c for c in cols_info}
        needs_null_goals = False
        for goal_col in ("protein_goal", "steps_goal"):
            col = by_name.get(goal_col)
            if col is not None and col.get("nullable") is False:
                needs_null_goals = True
        if needs_null_goals:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE nutrition_targets_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        tdee_baseline INTEGER NOT NULL DEFAULT 2050,
                        steps_kcal_per_1k INTEGER NOT NULL DEFAULT 45,
                        protein_goal INTEGER,
                        steps_goal INTEGER,
                        updated_at DATETIME
                    )
                """))
                conn.execute(text("""
                    INSERT INTO nutrition_targets_new
                        (id, tdee_baseline, steps_kcal_per_1k, protein_goal, steps_goal, updated_at)
                    SELECT id,
                           COALESCE(tdee_baseline, 2050),
                           COALESCE(steps_kcal_per_1k, 45),
                           protein_goal,
                           steps_goal,
                           updated_at
                    FROM nutrition_targets
                """))
                conn.execute(text("DROP TABLE nutrition_targets"))
                conn.execute(text(
                    "ALTER TABLE nutrition_targets_new RENAME TO nutrition_targets"
                ))

    if "daily_logs" in tables:
        cols = {c["name"] for c in inspect(engine).get_columns("daily_logs")}
        with engine.begin() as conn:
            if "is_complete" not in cols:
                conn.execute(text(
                    "ALTER TABLE daily_logs "
                    "ADD COLUMN is_complete BOOLEAN NOT NULL DEFAULT 0"
                ))
            if "completed_at" not in cols:
                conn.execute(text(
                    "ALTER TABLE daily_logs ADD COLUMN completed_at DATETIME"
                ))
            if "available_hours" not in cols:
                conn.execute(text(
                    "ALTER TABLE daily_logs ADD COLUMN available_hours FLOAT"
                ))
            if "shutdown_step" not in cols:
                conn.execute(text(
                    "ALTER TABLE daily_logs ADD COLUMN shutdown_step INTEGER"
                ))
            if "morning_seen" not in cols:
                conn.execute(text(
                    "ALTER TABLE daily_logs "
                    "ADD COLUMN morning_seen BOOLEAN NOT NULL DEFAULT 0"
                ))

    # Phase 3: evening shutdown replaces "Next Day To-Dos" routine step
    if "routine_steps" in tables:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE routine_steps
                SET is_active = 0
                WHERE routine = 'evening'
                  AND is_active = 1
                  AND lower(title) LIKE '%next day%to-do%'
            """))
             
    if "app_settings" in tables:
        cols = {c["name"] for c in inspect(engine).get_columns("app_settings")}
        with engine.begin() as conn:
            if "todo_cap" not in cols:
                conn.execute(text(
                    "ALTER TABLE app_settings "
                    "ADD COLUMN todo_cap INTEGER NOT NULL DEFAULT 3"
                ))
            if "default_available_hours" not in cols:
                conn.execute(text(
                    "ALTER TABLE app_settings "
                    "ADD COLUMN default_available_hours FLOAT NOT NULL DEFAULT 4"
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
            if "estimate_minutes" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos ADD COLUMN estimate_minutes INTEGER"
                ))
            if "rollover_count" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos "
                    "ADD COLUMN rollover_count INTEGER NOT NULL DEFAULT 0"
                ))
            if "manual_position" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos ADD COLUMN manual_position INTEGER"
                ))
            if "manual_sort" not in cols:
                conn.execute(text(
                    "ALTER TABLE todos "
                    "ADD COLUMN manual_sort BOOLEAN NOT NULL DEFAULT 0"
                ))

        # One-time remap importance/effort from legacy 1–5 → 1–3
        with engine.begin() as conn:
            # Values > 3 only exist on the old scale
            high = conn.execute(text(
                "SELECT COUNT(*) FROM todos WHERE importance > 3 OR effort > 3"
            )).scalar()
            if high:
                conn.execute(text("""
                    UPDATE todos SET importance = CASE
                        WHEN importance <= 1 THEN 1
                        WHEN importance <= 3 THEN 2
                        ELSE 3
                    END
                """))
                conn.execute(text("""
                    UPDATE todos SET effort = CASE
                        WHEN effort <= 1 THEN 1
                        WHEN effort <= 3 THEN 2
                        ELSE 3
                    END
                """))
