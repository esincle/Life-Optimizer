from flask import Blueprint, render_template

review_bp = Blueprint("review", __name__, url_prefix="/review")


@review_bp.route("/")
def index():
    return render_template("review/index.html")
