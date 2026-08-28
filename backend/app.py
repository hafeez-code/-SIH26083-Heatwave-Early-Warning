"""
app.py – Flask application entry point for SIH26083.

Sprint 1: Minimal backend foundation with health-check endpoint.
"""

from flask import Flask, jsonify

from config import config


def create_app(config_name="default"):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ------------------------------------------------------------------ #
    # Health-check endpoint                                                #
    # ------------------------------------------------------------------ #
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify(
            {
                "status": "success",
                "message": "SIH26083 backend is running",
            }
        )

    return app


# Local development entry point
if __name__ == "__main__":
    app = create_app("development")
    app.run(host="127.0.0.1", port=5000)
