import tempfile
import os
from datetime import datetime, timedelta
from flask import current_app
from app.celery_app import celery
from app.models.db import db
from app.models.execution_model import Execution
import subprocess
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Limit Constraint
MAX_EXECUTIONS_PER_SESSION = 100  
MAX_OUTPUT_SIZE = 1024 * 100  
RATE_LIMIT_WINDOW = 60  


@celery.task(
    name='execute_code_task',
    bind=True,
    max_retries=3,
    retry_backoff=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3}
)
def execute_code_task(self, execution_id, language, source_code):
        
    execution = Execution.query.get(execution_id)
    
    if not execution:
        logger.error(f"Execution {execution_id} not found")
        return {'error': 'Execution not found'}
    
    # moving from queue to running
    logger.info(f"Execution {execution_id}: QUEUED → RUNNING")
    
    # too many executions handling
    session_exec_count = Execution.query.filter_by(session_id=execution.session_id).count()
    if session_exec_count > MAX_EXECUTIONS_PER_SESSION:
        logger.warning(f"Session {execution.session_id} exceeded execution limit ({session_exec_count})")
        execution.status = 'FAILED'
        execution.stderr = f'Execution limit exceeded: {MAX_EXECUTIONS_PER_SESSION} executions per session'
        execution.finished_at = datetime.utcnow()
        db.session.commit()
        return {'execution_id': str(execution_id), 'status': 'FAILED'}
    
    # rapid repeated executions
    recent_window = datetime.utcnow() - timedelta(seconds=RATE_LIMIT_WINDOW)
    recent_executions = Execution.query.filter(
        Execution.session_id == execution.session_id,
        Execution.queued_at >= recent_window
    ).count()
    
    if recent_executions > 10: 
        logger.warning(f"Session {execution.session_id} rate limited: {recent_executions} executions in {RATE_LIMIT_WINDOW}s")
        execution.status = 'FAILED'
        execution.stderr = f'Rate limit exceeded: Maximum 10 executions per minute'
        execution.finished_at = datetime.utcnow()
        db.session.commit()
        return {'execution_id': str(execution_id), 'status': 'FAILED'}
    
    execution.status = 'RUNNING'
    execution.started_at = datetime.utcnow()
    db.session.commit()
    logger.info(f"Execution {execution_id} started at {execution.started_at}")
    
    try:
        start_time = time.time()
        
        # execute code based on language
        logger.info(f"Executing {language} code for execution {execution_id}")
        
        if language == 'python':
            result = _execute_python(source_code)
        elif language == 'javascript':
            result = _execute_javascript(source_code)
        elif language == 'c++':
            result = _execute_c_plusplus(source_code)
        else:
            logger.error(f"Unsupported language: {language}")
            result = {
                'stdout': '',
                'stderr': f'Unsupported language: {language}',
                'status': 'FAILED'
            }
        
        execution_time = int((time.time() - start_time) * 1000)
        
        # handling excessive output (prevent memory/storage abuse)
        stdout = result['stdout'] or ''
        stderr = result['stderr'] or ''
        
        if len(stdout) > MAX_OUTPUT_SIZE:
            logger.warning(f"Execution {execution_id} stdout truncated from {len(stdout)} to {MAX_OUTPUT_SIZE} bytes")
            stdout = stdout[:MAX_OUTPUT_SIZE] + "\n... [Output truncated - exceeded 100KB limit]"
        
        if len(stderr) > MAX_OUTPUT_SIZE:
            logger.warning(f"Execution {execution_id} stderr truncated from {len(stderr)} to {MAX_OUTPUT_SIZE} bytes")
            stderr = stderr[:MAX_OUTPUT_SIZE] + "\n... [Error output truncated - exceeded 100KB limit]"
        
        # Update results
        execution.status = result['status']
        execution.stdout = stdout
        execution.stderr = stderr
        execution.execution_time_ms = execution_time
        execution.finished_at = datetime.utcnow()
        
        # from RUNNING → COMPLETED/FAILED/TIMEOUT
        logger.info(f"Execution {execution_id}: RUNNING → {execution.status} ({execution_time}ms)")
        
    except Exception as e:
        logger.error(f"Execution {execution_id} failed with exception: {str(e)}")
        execution.status = 'FAILED'
        execution.stderr = str(e)
        execution.finished_at = datetime.utcnow()
    
    db.session.commit()
    
    # Log final state
    logger.info(f"Execution {execution_id} lifecycle: QUEUED({execution.queued_at}) → RUNNING({execution.started_at}) → {execution.status}({execution.finished_at})")
    
    return {
        'execution_id': str(execution_id),
        'status': execution.status
    }

def _execute_python(source_code):
    try:
        logger.info(f"Executing Python code (timeout: 30s)")
        
        result = subprocess.run(
            ['python', '-c', source_code],
            capture_output=True,
            text=True,
            timeout=30, 
        )
        
        status = 'COMPLETED' if result.returncode == 0 else 'FAILED'
        
        if status == 'FAILED':
            logger.warning(f"Python execution failed with return code {result.returncode}")
        else:
            logger.info(f"Python execution completed successfully")
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'status': status
        }
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Python execution timed out")
        return {
            'stdout': '',
            'stderr': 'Execution timeout exceeded(30 seconds)',
            'status': 'TIMEOUT'
        }
    except Exception as e:
        logger.error(f"Python execution error: {str(e)}")
        return {
            'stdout': '',
            'stderr': str(e),
            'status': 'FAILED'
        }

def _execute_javascript(source_code):
    try:
        logger.info(f"Executing JavaScript code (timeout: 30s)")
        
        result = subprocess.run(
            ['node', '-e', source_code],
            capture_output=True,
            text=True,
            timeout=30  # Timeout prevents infinite loops
        )
        
        status = 'COMPLETED' if result.returncode == 0 else 'FAILED'
        
        if status == 'FAILED':
            logger.warning(f"JavaScript execution failed with return code {result.returncode}")
        else:
            logger.info(f"JavaScript execution completed successfully")
        
        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'status': status
        }
        
    except subprocess.TimeoutExpired:
        logger.warning(f"JavaScript execution timed out")
        return {
            'stdout': '',
            'stderr': 'Execution timeout exceeded (30 seconds)',
            'status': 'TIMEOUT'
        }
    except FileNotFoundError:
        logger.error(f"Node.js not found")
        return {
            'stdout': '',
            'stderr': 'Node.js is not installed',
            'status': 'FAILED'
        }
    except Exception as e:
        logger.error(f"JavaScript execution error: {str(e)}")
        return {
            'stdout': '',
            'stderr': str(e),
            'status': 'FAILED'
        }

def _execute_c_plusplus(source_code): 
    try:
        logger.info(f"Executing C++ code (timeout: 30s)")
        
        # Create temporary directory for compilation
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, 'program.cpp')
            executable_file = os.path.join(temp_dir, 'program.exe' if os.name == 'nt' else 'program')
            
            with open(source_file, 'w') as f:
                f.write(source_code)
            
            # Compile the code
            logger.info(f"Compiling C++ code...")
            compile_result = subprocess.run(
                ['g++', source_file, '-o', executable_file, '-std=c++17'],
                capture_output=True,
                text=True,
                timeout=10  # 10 seconds for compilation
            )
            
            if compile_result.returncode != 0:
                logger.warning(f"C++ compilation failed")
                return {
                    'stdout': compile_result.stdout,
                    'stderr': f"Compilation Error:\n{compile_result.stderr}",
                    'status': 'FAILED'
                }
            
            logger.info(f"C++ compilation successful, running executable...")
            
            
            run_result = subprocess.run(
                [executable_file],
                capture_output=True,
                text=True,
                timeout=30  # 30 seconds for execution
            )
            
            status = 'COMPLETED' if run_result.returncode == 0 else 'FAILED'
            
            if status == 'FAILED':
                logger.warning(f"C++ execution failed with return code {run_result.returncode}")
            else:
                logger.info(f"C++ execution completed successfully")
            
            return {
                'stdout': run_result.stdout,
                'stderr': run_result.stderr,
                'status': status
            }
        
    except subprocess.TimeoutExpired:
        logger.warning(f"C++ execution timed out")
        return {
            'stdout': '',
            'stderr': 'Execution timeout exceeded (30 seconds)',
            'status': 'TIMEOUT'
        }
    except FileNotFoundError:
        logger.error(f"G++ compiler not found")
        return {
            'stdout': '',
            'stderr': 'G++ compiler (g++) is not installed. Please install it to compile C++ code.',
            'status': 'FAILED'
        }
    except Exception as e:
        logger.error(f"C++ execution error: {str(e)}")
        return {
            'stdout': '',
            'stderr': str(e),
            'status': 'FAILED'
        }

