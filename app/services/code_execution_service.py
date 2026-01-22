from datetime import datetime
import logging
from app.models.db import db
from app.models.execution_model import Execution
from app.models.code_sessions_model import CodeSession
from app.tasks.execution_tasks import execute_code_task

# Configure logging
logger = logging.getLogger(__name__)

class CodeExecutionService:
    EXECUTION_TIMEOUT = 30

    @staticmethod
    def execute_code(session_id):
        """Execute code from a session asynchronously"""
        logger.info(f"🚀 Starting execution for session {session_id}")
        
        session = CodeSession.query.get(session_id)
        if not session:
            logger.error(f"❌ Session {session_id} not found")
            return None
        
        # Create execution record with QUEUED status
        execution = Execution(
            session_id=session_id,
            status='QUEUED',
            queued_at=datetime.utcnow()
        )

        db.session.add(execution)
        db.session.commit()
        
        logger.info(f"📝 Execution {execution.id} created with status QUEUED at {execution.queued_at}")

        # Send task to Celery worker
        execute_code_task.delay(
            str(execution.id),
            session.language,
            session.source_code
        )
        
        logger.info(f"📤 Task sent to Celery for execution {execution.id}")

        return {
            "execution_id": str(execution.id),
            "status": execution.status
        }
    
    @staticmethod
    def get_execution(execution_id):
        """Get execution status and result"""
        execution = Execution.query.get(execution_id)
        
        if not execution:
            logger.warning(f"⚠️ Execution {execution_id} not found")
            return None
        
        logger.info(f"📊 Retrieving execution {execution_id} - Status: {execution.status}")
        
        result = {
            "execution_id": str(execution.id),
            "status": execution.status
        }
        
        # Include timestamps for tracking lifecycle
        if execution.queued_at:
            result["queued_at"] = execution.queued_at.isoformat()
        if execution.started_at:
            result["started_at"] = execution.started_at.isoformat()
        if execution.finished_at:
            result["finished_at"] = execution.finished_at.isoformat()
        
        # Additional information when completed
        if execution.status == 'COMPLETED':
            result.update({
                "stdout": execution.stdout or "",
                "stderr": execution.stderr or "",
                "execution_time_ms": execution.execution_time_ms
            })
            logger.info(f"✅ Execution {execution_id} completed in {execution.execution_time_ms}ms")
        elif execution.status in ['FAILED', 'TIMEOUT']:
            result.update({
                "stdout": execution.stdout or "",
                "stderr": execution.stderr or ""
            })
            logger.warning(f"⚠️ Execution {execution_id} ended with status {execution.status}")
        
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

        