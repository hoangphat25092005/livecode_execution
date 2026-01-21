from datetime import datetime
from app.celery_app import celery
from app.models.db import db
from app.models.execution_model import Execution
import subprocess
import time

@celery.task(name='execute_code_task', bind=True)
def execute_code_task(self, execution_id, language, source_code):
    
    from app import create_app
    app = create_app()
    
    with app.app_context():
        execution = Execution.query.get(execution_id)
        
        if not execution:
            return {'error': 'Execution not found'}
        
        # Update status to RUNNING
        execution.status = 'RUNNING'
        execution.started_at = datetime.utcnow()
        db.session.commit()
        
        try:
            start_time = time.time()
            
            # Execute code based on language
            if language == 'python':
                result = _execute_python(source_code)
            elif language == 'javascript':
                result = _execute_javascript(source_code)
            else:
                result = {
                    'stdout': '',
                    'stderr': f'Unsupported language: {language}',
                    'status': 'FAILED'
                }
            
            execution_time = int((time.time() - start_time) * 1000)
            
            # Update execution with results
            execution.status = result['status']
            execution.stdout = result['stdout']
            execution.stderr = result['stderr']
            execution.execution_time_ms = execution_time
            execution.finished_at = datetime.utcnow()
            
        except Exception as e:
            execution.status = 'FAILED'
            execution.stderr = str(e)
            execution.finished_at = datetime.utcnow()
        
        db.session.commit()
        
        return {
            'execution_id': str(execution_id),
            'status': execution.status
        }

def _execute_python(source_code):
    """Execute Python code in isolated environment"""
    try:
        result = subprocess.run(
            ['python', '-c', source_code],
            capture_output=True,
            text=True,
            timeout=30  # 30 seconds timeout
        )
        
        status = 'COMPLETED' if result.returncode == 0 else 'FAILED'
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'status': status
        }
        
    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': 'Execution timeout exceeded (30 seconds)',
            'status': 'TIMEOUT'
        }
    except Exception as e:
        return {
            'stdout': '',
            'stderr': str(e),
            'status': 'FAILED'
        }

def _execute_javascript(source_code):
    """Execute JavaScript code using Node.js"""
    try:
        result = subprocess.run(
            ['node', '-e', source_code],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        status = 'COMPLETED' if result.returncode == 0 else 'FAILED'
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'status': status
        }
        
    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': 'Execution timeout exceeded (30 seconds)',
            'status': 'TIMEOUT'
        }
    except FileNotFoundError:
        return {
            'stdout': '',
            'stderr': 'Node.js is not installed',
            'status': 'FAILED'
        }
    except Exception as e:
        return {
            'stdout': '',
            'stderr': str(e),
            'status': 'FAILED'
        }
