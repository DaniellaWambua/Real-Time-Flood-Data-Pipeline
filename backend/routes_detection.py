"""
Internal endpoint the ingestion consumer calls after saving a day's readings.
Not for dashboard users: it needs the shared INTERNAL_API_TOKEN instead of a session.
"""
import datetime
import hmac

from flask import Blueprint, jsonify, request

import config
import flood_detection

detection_bp = Blueprint("detection", __name__, url_prefix="/internal")


@detection_bp.route("/detect", methods=["POST"])
def detect():
    if not hmac.compare_digest(request.headers.get("X-Internal-Token", ""), config.INTERNAL_API_TOKEN):
        return jsonify({"error": "not allowed"}), 403
    data = request.get_json(silent=True) or {}
    try:
        catchment_id = int(data["catchment_id"])
        day = datetime.date.fromisoformat(data["date"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "catchment_id and date (YYYY-MM-DD) are required"}), 400
    result = flood_detection.detect(catchment_id, day, data.get("hydro_data_record_id"))
    return jsonify(result), 200 if result["scored"] else 422