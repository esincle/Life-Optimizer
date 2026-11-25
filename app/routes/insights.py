from flask import Blueprint, render_template

insights_bp = Blueprint("insights", __name__, url_prefix="/insights")


@insights_bp.route("/")
def index():
    return render_template("insights/index.html")
