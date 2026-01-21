import redis
from flask import Blueprint, jsonify
from app.config import Config

bp = Blueprint('health', __name__)

@bp.route('/health/redis')
def check_redis():
    """Check Redis connection status"""
    try:
        # Connect to Redis
        redis_client = redis.from_url(Config.CELERY_BROKER_URL)
        
        # Test connection
        redis_client.ping()
        
        # Get Redis info
        info = redis_client.info()
        
        return jsonify({
            "status": "connected",
            "redis_version": info.get('redis_version'),
            "connected_clients": info.get('connected_clients'),
            "used_memory_human": info.get('used_memory_human'),
            "uptime_in_seconds": info.get('uptime_in_seconds')
        }), 200
        
    except redis.ConnectionError as e:
        return jsonify({
            "status": "disconnected",
            "error": str(e),
            "message": "Cannot connect to Redis"
        }), 503
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@bp.route('/health/celery')
def check_celery():
    """Check Celery worker status"""
    try:
        from app.celery_app import celery
        
        # Check active workers
        inspect = celery.control.inspect()
        active_workers = inspect.active()
        stats = inspect.stats()
        
        if active_workers:
            return jsonify({
                "status": "running",
                "workers": list(active_workers.keys()),
                "stats": stats
            }), 200
        else:
            return jsonify({
                "status": "no_workers",
                "message": "No Celery workers are running"
            }), 503
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "Cannot connect to Celery"
        }), 500
