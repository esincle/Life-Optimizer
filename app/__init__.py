from flask import Flask, redirect, url_for
from app.extensions import db
from config import DevelopmentConfig


def create_app(config=DevelopmentConfig):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)

    db.init_app(app)

    from app.routes.design import design_bp
    from app.routes.tracker import tracker_bp
    from app.routes.journal import journal_bp

    app.register_blueprint(design_bp)
    app.register_blueprint(tracker_bp)
    app.register_blueprint(journal_bp)

    @app.route("/")
    def index():
        return redirect(url_for("tracker.index"))

    with app.app_context():
        db.create_all()

    return app
