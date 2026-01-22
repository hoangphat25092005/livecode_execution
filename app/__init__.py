from flask import Flask, jsonify
from app.config import Config
from app.models.db import db
from app.celery_app import init_celery
from app.api import api

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    print(f"Connecting to database successfully!")

    db.init_app(app)
    init_celery(app)

    with app.app_context():
        from app.models import code_sessions_model, execution_model
        db.create_all()
    
    # Initialize API with Swagger
    api.init_app(app)
    
    # Register API namespaces
    from app.routes.session_api import ns as session_ns
    from app.routes.execution_api import ns as execution_ns
    api.add_namespace(session_ns, path='/code-sessions')
    api.add_namespace(execution_ns, path='/executions')
    
    # Keep legacy routes for backward compatibility
    from app.routes import code_session_route, execution_routes, health_routes
    app.register_blueprint(code_session_route.bp)
    app.register_blueprint(execution_routes.bp)
    app.register_blueprint(health_routes.bp)

    @app.route("/")
    def home():
        return jsonify({
            "message": "LiveCode Execution API is running!",
            "status": "success",
            "documentation": "/docs"
        })
    
    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})
    
    
    return app

