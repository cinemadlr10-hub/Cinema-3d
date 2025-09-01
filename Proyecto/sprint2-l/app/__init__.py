from flask import Flask, redirect, url_for

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")

    # 🔹 Registrar blueprints
    from .blueprints.catalog import bp as catalog_bp
    app.register_blueprint(catalog_bp)

    from .blueprints.reservations import bp as reservations_bp
    app.register_blueprint(reservations_bp)

    # 🔹 Hacer que "/" vaya a /cartelera
    @app.get("/")
    def home():
        return redirect(url_for("catalog.cartelera"))

    return app
