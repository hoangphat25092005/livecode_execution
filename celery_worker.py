from app import create_app
from app.celery_app import celery

# Create Flask app context
app = create_app()
app.app_context().push()

# Import tasks to register them with Celery
from app.tasks import execution_tasks
