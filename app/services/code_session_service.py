from datetime import datetime
from app.models.db import db
from app.models.code_sessions_model import CodeSession

class Session_Service:
    @staticmethod
    def create_session(language="python", source_code=''):
        new_code_session = CodeSession(language=language, source_code=source_code, status='Active')
        #adding new code session to database
        db.session.add(new_code_session)
        db.session.commit()

        return {
            "session_id": str(new_code_session.id),
            "status": new_code_session.status, 
        }
    

    #update the code session
    @staticmethod
    def update_session(session_id, language=None, source_code=None):
        code_session = CodeSession.query.get(session_id)

        if not code_session:
            return None
        
        if language is not None:
            code_session.language = language
        if source_code is not None:
            code_session.source_code = source_code

        code_session.updated_at = datetime.utcnow()
        db.session.commit()

        return {
            "session_id": str(code_session.id),
            "status": code_session.status
        }
    

    #get a coding sessiong by session_id
    @staticmethod
    def get_session(session_id):
        session = CodeSession.query.get(session_id)

        if not session:
            return None
        
        return {
            "session_id": str(session.id),
            "language": session.language,
            "source_code": session.source_code,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
    
    #delete base on session_id
    @staticmethod
    def delete_session(session_id):
        session = CodeSession.query.get(session_id)

        if not session:
            return False
        
        db.session.delete(session)
        db.session.commit()

        return True
