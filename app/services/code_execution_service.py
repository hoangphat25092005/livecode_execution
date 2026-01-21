from datetime import datetime
from app.models.db import db
from app.models.execution_model import Execution
from app.models.code_sessions_model import CodeSession

class CodeExecutionService:
    EXECUTION_TIMEOUT = 30

    @staticmethod
    def execute_code(session_id):
        """Execute code from a session asynchronously"""
        session = CodeSession.query.get(session_id)
        if not session:
            return None
        
        execution = Execution(
            session_id=session_id,
            status='QUEUED',
            queued_at=datetime.utcnow()
        )

        db.session.add(execution)
        db.session.commit()

        # Send task to Celery worker (asynchronous)
        from app.tasks.execution_tasks import execute_code_task
        execute_code_task.delay(
            str(execution.id),
            session.language,
            session.source_code
        )

        return {
            "execution_id": str(execution.id),
            "status": execution.status
        }
    
    @staticmethod
    def get_execution(execution_id):
        """Get execution status and result"""
        execution = Execution.query.get(execution_id)
        
        if not execution:
            return None
        
        result = {
            "execution_id": str(execution.id),
            "status": execution.status
        }
        
        # Add additional fields when completed
        if execution.status == 'COMPLETED':
            result.update({
                "stdout": execution.stdout or "",
                "stderr": execution.stderr or "",
                "execution_time_ms": execution.execution_time_ms
            })
        elif execution.status in ['FAILED', 'TIMEOUT']:
            result.update({
                "stdout": execution.stdout or "",
                "stderr": execution.stderr or ""
            })
        
        return result
    
    @staticmethod
    def get_session_executions(session_id):
        """Get all executions for a session"""
        executions = Execution.query.filter_by(session_id=session_id).order_by(Execution.queued_at.desc()).all()
        
        return [{
            "execution_id": str(exec.id),
            "status": exec.status,
            "queued_at": exec.queued_at.isoformat() if exec.queued_at else None,
            "finished_at": exec.finished_at.isoformat() if exec.finished_at else None,
            "execution_time_ms": exec.execution_time_ms
        } for exec in executions]

        