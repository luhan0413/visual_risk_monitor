import logging

from flask import Flask

import config
from routes.exemplar_routes import exemplar_bp
from routes.model_routes import model_bp
from routes.monitor_routes import monitor_bp
from routes.risk_routes import risk_bp
from routes.source_routes import source_bp
from routes.web_routes import web_bp
from services.container import init_services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 上傳範例圖片上限

    app.register_blueprint(web_bp)
    app.register_blueprint(source_bp)
    app.register_blueprint(model_bp)
    app.register_blueprint(exemplar_bp)
    app.register_blueprint(monitor_bp)
    app.register_blueprint(risk_bp)
    return app


app = create_app()


if __name__ == "__main__":
    init_services()
    app.run(
        host=config.SERVER["host"],
        port=config.SERVER["port"],
        debug=False,
        threaded=True,
    )
