from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

from outlet_monitor.scrape import ScrapeError, fetch_all_products
from outlet_monitor.storage import (
    DEFAULT_DB_PATH,
    append_snapshots,
    connect,
    get_category_counts,
    get_latest_snapshots,
    get_product_history,
)


def create_app(db_path: Path | str = DEFAULT_DB_PATH) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    @app.after_request
    def add_cors_headers(response):
        # Local dev tool, no auth/cookies involved — the frontend (a different
        # origin/port) needs to call this API directly from the browser.
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/scrape")
    def scrape():
        try:
            products = fetch_all_products()
        except ScrapeError as exc:
            return jsonify({"error": str(exc)}), 502

        conn = connect(app.config["DB_PATH"])
        try:
            written = append_snapshots(conn, products)
        finally:
            conn.close()

        return (
            jsonify(
                {
                    "fetched": len(products),
                    "written": written,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
            201,
        )

    @app.get("/categories")
    def list_categories():
        conn = connect(app.config["DB_PATH"])
        try:
            categories = get_category_counts(conn)
        finally:
            conn.close()
        return jsonify(categories)

    @app.get("/products")
    def list_products():
        category = request.args.get("category")
        conn = connect(app.config["DB_PATH"])
        try:
            products = get_latest_snapshots(conn, category=category)
        finally:
            conn.close()
        return jsonify(products)

    @app.get("/products/<product_id>/history")
    def product_history(product_id: str):
        conn = connect(app.config["DB_PATH"])
        try:
            history = get_product_history(conn, product_id)
        finally:
            conn.close()

        if not history:
            return jsonify({"error": f"no history for product_id {product_id!r}"}), 404
        return jsonify(history)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
