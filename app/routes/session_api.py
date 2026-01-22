from flask_restx import Namespace, Resource, fields
from app.services.code_session_service import Session_Service

# Create namespace
ns = Namespace('code-sessions', description='Code session operations')

# Define models for Swagger documentation
session_create_model = ns.model('SessionCreate', {
    'language': fields.String(
        required=False, 
        default='python', 
        description='Programming language (python, javascript, c++)',
        enum=['python', 'javascript', 'c++']
    ),
    'source_code': fields.String(required=False, default='', description='Source code')
})

session_update_model = ns.model('SessionUpdate', {
    'language': fields.String(
        required=False, 
        description='Programming language (python, javascript, c++)',
        enum=['python', 'javascript', 'c++']
    ),
    'source_code': fields.String(required=False, description='Source code')
})

session_response_model = ns.model('SessionResponse', {
    'session_id': fields.String(description='Session ID'),
    'status': fields.String(description='Session status'),
    'language': fields.String(description='Programming language'),
    'source_code': fields.String(description='Source code'),
    'created_at': fields.String(description='Creation timestamp'),
    'updated_at': fields.String(description='Update timestamp')
})

session_brief_response_model = ns.model('SessionBriefResponse', {
    'session_id': fields.String(description='Session ID'),
    'status': fields.String(description='Session status')
})

error_model = ns.model('Error', {
    'error': fields.String(description='Error message')
})

success_model = ns.model('Success', {
    'message': fields.String(description='Success message')
})


@ns.route('')
class SessionList(Resource):
    @ns.doc('create_session')
    @ns.expect(session_create_model, validate=False)  # Disable strict validation
    @ns.marshal_with(session_brief_response_model, code=201)
    @ns.response(201, 'Session created successfully')
    @ns.response(400, 'Invalid request data')
    def post(self):
        """Create a new live coding session
        
        Example payload:
        {
            "language": "python",
            "source_code": "print('Hello World!')"
        }
        """
        try:
            data = ns.payload or {}
            language = data.get('language', 'python')
            source_code = data.get('source_code', '')
            
            result = Session_Service.create_session(language=language, source_code=source_code)
            return result, 201
        except Exception as e:
            ns.abort(400, f'Invalid request: {str(e)}')


@ns.route('/<string:session_id>')
@ns.param('session_id', 'The session identifier')
class SessionDetail(Resource):
    @ns.doc('get_session')
    @ns.marshal_with(session_response_model)
    @ns.response(404, 'Session not found', error_model)
    def get(self, session_id):
        """Get session details"""
        result = Session_Service.get_session(session_id=session_id)
        
        if result is None:
            ns.abort(404, "Session not found")
        
        return result, 200
    
    @ns.doc('update_session')
    @ns.expect(session_update_model)
    @ns.marshal_with(session_brief_response_model)
    @ns.response(404, 'Session not found', error_model)
    def patch(self, session_id):
        """Autosave the learner's current source code"""
        data = ns.payload
        language = data.get('language')
        source_code = data.get('source_code')
        
        result = Session_Service.update_session(session_id=session_id, language=language, source_code=source_code)
        
        if result is None:
            ns.abort(404, "Session not found")
        
        return result, 200
    
    @ns.doc('delete_session')
    @ns.marshal_with(success_model)
    @ns.response(404, 'Session not found', error_model)
    def delete(self, session_id):
        """Delete a session"""
        success = Session_Service.delete_session(session_id=session_id)
        
        if not success:
            ns.abort(404, "Session not found")
        
        return {"message": "Session deleted successfully"}, 200


@ns.route('/<string:session_id>/run')
@ns.param('session_id', 'The session identifier')
class SessionRun(Resource):
    @ns.doc('run_session_code')
    @ns.marshal_with(ns.model('ExecutionResponse', {
        'execution_id': fields.String(description='Execution ID'),
        'status': fields.String(description='Execution status')
    }), code=202)
    @ns.response(202, 'Execution queued successfully')
    @ns.response(404, 'Session not found', error_model)
    def post(self, session_id):
        """Execute the current code asynchronously
        
        Returns immediately with execution ID and QUEUED status
        """
        from app.services.code_execution_service import CodeExecutionService
        
        result = CodeExecutionService.execute_code(session_id)
        
        if result is None:
            ns.abort(404, "Session not found")
        
        return result, 202
