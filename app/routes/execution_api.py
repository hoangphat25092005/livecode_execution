from flask_restx import Namespace, Resource, fields
from app.services.code_execution_service import CodeExecutionService

# Create namespace
ns = Namespace('executions', description='Code execution operations')

# Define models for Swagger documentation
execution_response_model = ns.model('ExecutionResponse', {
    'execution_id': fields.String(description='Execution ID'),
    'status': fields.String(description='Execution status', enum=['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT'])
})

execution_detail_model = ns.model('ExecutionDetail', {
    'execution_id': fields.String(description='Execution ID'),
    'status': fields.String(description='Execution status'),
    'stdout': fields.String(description='Standard output'),
    'stderr': fields.String(description='Standard error'),
    'execution_time_ms': fields.Integer(description='Execution time in milliseconds')
})

execution_list_item = ns.model('ExecutionListItem', {
    'execution_id': fields.String(description='Execution ID'),
    'status': fields.String(description='Execution status'),
    'queued_at': fields.String(description='Queue timestamp'),
    'finished_at': fields.String(description='Finish timestamp'),
    'execution_time_ms': fields.Integer(description='Execution time in milliseconds')
})

execution_list_response = ns.model('ExecutionListResponse', {
    'session_id': fields.String(description='Session ID'),
    'executions': fields.List(fields.Nested(execution_list_item))
})

error_model = ns.model('Error', {
    'error': fields.String(description='Error message')
})


@ns.route('/<string:execution_id>')
@ns.param('execution_id', 'The execution identifier')
class ExecutionDetail(Resource):
    @ns.doc('get_execution')
    @ns.marshal_with(execution_detail_model)
    @ns.response(404, 'Execution not found', error_model)
    @ns.response(200, 'Success')
    def get(self, execution_id):
        """Retrieve execution status and result"""
        result = CodeExecutionService.get_execution(execution_id)
        
        if result is None:
            ns.abort(404, "Execution not found")
        
        return result, 200


@ns.route('/session/<string:session_id>')
@ns.param('session_id', 'The session identifier')
class SessionExecutionList(Resource):
    @ns.doc('get_session_executions')
    @ns.marshal_with(execution_list_response)
    def get(self, session_id):
        """Get all executions for a session"""
        executions = CodeExecutionService.get_session_executions(session_id)
        
        return {
            "session_id": str(session_id),
            "executions": executions
        }, 200


@ns.route('/session/<string:session_id>/execute')
@ns.param('session_id', 'The session identifier')
class SessionExecute(Resource):
    @ns.doc('execute_session')
    @ns.marshal_with(execution_response_model, code=202)
    @ns.response(404, 'Session not found', error_model)
    @ns.response(202, 'Execution queued successfully')
    def post(self, session_id):
        """Execute code from a session (asynchronous)"""
        result = CodeExecutionService.execute_code(session_id)
        
        if result is None:
            ns.abort(404, "Session not found")
        
        return result, 202
