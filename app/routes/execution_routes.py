from flask import Blueprint, request, jsonify
from app.services.code_execution_service import CodeExecutionService

bp = Blueprint('executions', __name__, url_prefix='/executions')

@bp.route('/<uuid:execution_id>', methods=['GET'])
def get_execution(execution_id):
    """Retrieve execution status and result"""
    result = CodeExecutionService.get_execution(execution_id)
    
    if result is None:
        return jsonify({"error": "Execution not found"}), 404
    
    return jsonify(result), 200

@bp.route('/session/<uuid:session_id>', methods=['GET'])
def get_session_executions(session_id):
    """Get all executions for a session"""
    executions = CodeExecutionService.get_session_executions(session_id)
    
    return jsonify({
        "session_id": str(session_id),
        "executions": executions
    }), 200

@bp.route('/session/<uuid:session_id>/execute', methods=['POST'])
def execute_session(session_id):
    """Execute code from a session"""
    result = CodeExecutionService.execute_code(session_id)
    
    if result is None:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify(result), 202  # 202 Accepted for async operation
