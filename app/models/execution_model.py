import uuid
from datetime import datetime
from app.models.db import db


class Execution(db.Model):
    __tablename__ = "executions"

    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(db.UUID(as_uuid=True), db.ForeignKey("code_sessions.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)
    stdout = db.Column(db.Text)
    stderr = db.Column(db.Text)
    execution_time_ms = db.Column(db.Integer)
    queued_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
