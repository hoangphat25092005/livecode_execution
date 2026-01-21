import uuid
from datetime import datetime
from app.models.db import db


class CodeSession(db.Model):
    __tablename__ = "code_sessions"

    id = db.Column(db.UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    language = db.Column(db.String(20), nullable=False)
    source_code = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="ACTIVE")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    executions = db.relationship("Execution", backref="session", lazy=True, cascade="all, delete-orphan")
