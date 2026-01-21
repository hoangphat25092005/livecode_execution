from flask_restx import Api

# Initialize API with Swagger documentation
api = Api(
    version='1.0',
    title='LiveCode Execution API',
    description='API for live code editing and execution with asynchronous processing',
    doc='/docs',  
    prefix='/api/v1'
)
