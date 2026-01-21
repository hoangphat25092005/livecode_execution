from flask import Blueprint, request, jsonify
from app.services.code_session_service import Session_Service

bp = Blueprint('sessions', __name__, url_prefix="/code-sessions")

@bp.route('', methods=['POST'])
def create_session():
    #get data from user
    data = request.get_json()

    language = data.get('language', 'python')
    source_code = data.get('source_code', '')

    result = Session_Service.create_session(language=language, source_code=source_code)

    return jsonify(result), 201

@bp.route('/<uuid:session_id>', methods=['PATCH'])
def update_session(session_id):
    data = request.get_json()
    language = data.get('language')
    source_code = data.get('source_code')

    result = Session_Service.update_session(session_id=session_id, language=language, source_code=source_code)

    if result is None:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify(result), 200

@bp.route('/<uuid:session_id>', methods=['GET'])
def get_session(session_id):
    result = Session_Service.get_session(session_id=session_id)

    if result is None:
        return jsonify({"error": "Session not found"}), 404
    
    return jsonify(result), 200


@bp.route('/<uuid:session_id>', methods=['DELETE'])
def delete_session(session_id):
    success = Session_Service.delete_session(session_id=session_id)

    if not success:
        return jsonify({"error": "session deleted unsuccessfully!"}), 404
    
    return jsonify({"message": "session deleted successfully"}), 201

