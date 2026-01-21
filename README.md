# LiveCode Execution API - System Design Documentation

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?style=for-the-badge&logo=celery&logoColor=white)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![API Status](https://img.shields.io/badge/API-Active-success?style=for-the-badge)](http://localhost:5000/health)
[![Documentation](https://img.shields.io/badge/Docs-Swagger-85EA2D?style=for-the-badge&logo=swagger&logoColor=black)](http://localhost:5000/docs)

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [End-to-End Request Flow](#end-to-end-request-flow)
3. [Reliability & Data Model](#reliability--data-model)
4. [Scalability Considerations](#scalability-considerations)
5. [Trade-offs](#trade-offs)

---

## 1. Architecture Overview

### System Components

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Client    │─────▶│  Flask API   │─────▶│  PostgreSQL  │
│  (Browser)  │      │   (REST)     │      │   Database   │
└─────────────┘      └──────────────┘      └──────────────┘
                           │
                           │
                           ▼
                     ┌──────────────┐
                     │    Redis     │
                     │   (Broker)   │
                     └──────────────┘
                           │
                           ▼
                     ┌──────────────┐      ┌──────────────┐
                     │    Celery    │─────▶│   Isolated   │
                     │   Workers    │      │ Execution Env│
                     └──────────────┘      └──────────────┘
```

### Technology Stack

- **API Framework**: Flask + Flask-RESTX (Swagger)
- **Database**: PostgreSQL (persistent storage)
- **Message Broker**: Redis (task queue)
- **Task Queue**: Celery (async execution)
- **ORM**: SQLAlchemy
- **API Documentation**: Swagger UI

---

## 2. End-to-End Request Flow

### 2.1 Code Session Creation

```mermaid
sequenceDiagram
    participant Client
    participant Flask API
    participant PostgreSQL
    
    Client->>Flask API: POST /api/v1/code-sessions
    Note over Client,Flask API: {language, source_code}
    Flask API->>PostgreSQL: INSERT INTO code_sessions
    PostgreSQL-->>Flask API: session_id
    Flask API-->>Client: {session_id, status: "ACTIVE"}
```

**Endpoint**: `POST /api/v1/code-sessions`

**Request**:
```json
{
  "language": "python",
  "source_code": "print('Hello World')"
}
```

**Response**:
```json
{
  "session_id": "uuid",
  "status": "ACTIVE"
}
```

### 2.2 Autosave Behavior

**Endpoint**: `PATCH /api/v1/code-sessions/{session_id}`

**Behavior**:
- Called frequently during live editing (debounced on client-side)
- Updates `source_code` and `updated_at` timestamp
- Non-blocking operation
- Optimistic locking to prevent race conditions

**Request**:
```json
{
  "source_code": "print('Hello World!\\nprint('Updated')"
}
```

### 2.3 Execution Request (Background)

```mermaid
sequenceDiagram
    participant Client
    participant Flask API
    participant PostgreSQL
    participant Redis
    participant Celery Worker
    
    Client->>Flask API: POST /executions/session/{id}/execute
    Flask API->>PostgreSQL: INSERT execution (status: QUEUED)
    Flask API->>Redis: Push task to queue
    Flask API-->>Client: {execution_id, status: "QUEUED"}
    
    Note over Celery Worker: Worker picks up task
    Celery Worker->>PostgreSQL: UPDATE status = RUNNING
    Celery Worker->>Celery Worker: Execute code (isolated)
    Celery Worker->>PostgreSQL: UPDATE status = COMPLETED/FAILED
```

**Endpoint**: `POST /api/v1/executions/session/{session_id}/execute`

**Response (Immediate)**:
```json
{
  "execution_id": "uuid",
  "status": "QUEUED"
}
```

### 2.4 Result Polling

**Endpoint**: `GET /api/v1/executions/{execution_id}`

**States**:
```
QUEUED → RUNNING → COMPLETED / FAILED / TIMEOUT
  ⏱️       ⚙️           ✅       ❌       ⏰
```

**Response (When Completed)**:
```json
{
  "execution_id": "uuid",
  "status": "COMPLETED",
  "stdout": "Hello World!",
  "stderr": "",
  "execution_time_ms": 120
}
```

---

## 3. Reliability & Data Model

### 3.1 Database Schema

#### Code Sessions Table
```sql
CREATE TABLE code_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    language VARCHAR(50) NOT NULL,
    source_code TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

#### Executions Table
```sql
CREATE TABLE executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES code_sessions(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,
    stdout TEXT,
    stderr TEXT,
    execution_time_ms INTEGER,
    queued_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_status (status)
);
```

### 3.2 Execution States

| State | Description | Transitions |
|-------|-------------|-------------|
| `QUEUED` | Task submitted to Redis | → RUNNING |
| `RUNNING` | Worker executing code | → COMPLETED, FAILED, TIMEOUT |
| `COMPLETED` | Execution successful | Terminal state |
| `FAILED` | Execution error | Terminal state |
| `TIMEOUT` | Exceeded 30s limit | Terminal state |

### 3.3 Idempotency Handling

**Prevent Duplicate Execution Runs**:
- Client-side: Disable execute button during execution
- Server-side: Check for active executions before creating new one
- Redis: Use task IDs to track in-flight tasks

**Safe Reprocessing of Jobs**:
- Celery task retry mechanism
- Max retries: 3 attempts
- Exponential backoff: 2^n seconds

### 3.4 Failure Handling

**Retries**:
```python
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_code_task(self, execution_id, language, source_code):
    try:
        # Execute code
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

**Error States**:
- **Connection errors**: Retry with backoff
- **Timeout errors**: Mark as TIMEOUT, no retry
- **Syntax errors**: Mark as FAILED, no retry

**Dead-Letter Queue**:
- Failed tasks after max retries go to DLQ
- Manual inspection and reprocessing

---

## 4. Scalability Considerations

### 4.1 Handling Many Concurrent Live Coding Sessions

**Database Connection Pooling**:
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=10,              # Max connections
    max_overflow=20,           # Overflow connections
    pool_recycle=3600,         # Recycle after 1 hour
    pool_pre_ping=True         # Test connections
)
```

**Optimizations**:
- Index on `session_id` for fast lookups
- Batch updates for autosave operations
- Read replicas for GET requests
- Write to primary database only

### 4.2 Horizontal Scaling of Workers

**Multiple Celery Workers**:
```bash
# Start multiple workers
celery -A celery_worker.celery worker -n worker1@%h --loglevel=info
celery -A celery_worker.celery worker -n worker2@%h --loglevel=info
celery -A celery_worker.celery worker -n worker3@%h --loglevel=info
```

**Auto-scaling Strategy**:
- Monitor queue length in Redis
- Scale workers based on pending tasks
- Use Kubernetes HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-hpa
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: External
    external:
      metric:
        name: redis_queue_length
      target:
        type: AverageValue
        averageValue: "10"
```

### 4.3 Queue Backlog Handling

**Priority Queues**:
```python
# High priority for interactive sessions
execute_code_task.apply_async(
    args=[execution_id, language, code],
    queue='high_priority'
)

# Low priority for batch jobs
execute_code_task.apply_async(
    args=[execution_id, language, code],
    queue='low_priority'
)
```

**Rate Limiting**:
```python
# Limit executions per user
@app.before_request
def rate_limit():
    user_id = get_user_id()
    key = f"rate_limit:{user_id}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 60)  # 1 minute window
    if count > 10:  # Max 10 executions per minute
        abort(429, "Rate limit exceeded")
```

### 4.4 Potential Bottlenecks and Mitigation

| Bottleneck | Mitigation Strategy |
|------------|---------------------|
| **Database** | Read replicas, connection pooling, caching |
| **Redis** | Redis Cluster, separate queues by priority |
| **Workers** | Auto-scaling, multiple worker pools |
| **Network** | Load balancer, CDN for static assets |
| **Code Execution** | Resource limits, containerization (Docker) |

---

## 5. Trade-offs

### 5.1 Technology Choices and Why

| Choice | Pros | Cons | Why Chosen |
|--------|------|------|------------|
| **Celery + Redis** | Mature, scalable, supports retries | Additional infrastructure | Industry standard for async tasks |
| **PostgreSQL** | ACID compliance, relational data | Not NoSQL-fast for simple KV | Need for complex queries and relationships |
| **Flask** | Lightweight, flexible | Less opinionated than Django | Simple API, easy to extend |
| **Subprocess for execution** | Simple, isolated | Security concerns | Good for MVP, Docker isolation for production |

### 5.2 Optimizations

**What We Optimized For**:
- ✅ **Speed**: Async execution, non-blocking API
- ✅ **Reliability**: State persistence, retries, error handling
- ✅ **Simplicity**: Clear architecture, RESTful design

**What We Traded Off**:
- ❌ **Real-time updates**: Polling instead of WebSockets (simpler to implement)
- ❌ **Advanced sandboxing**: subprocess instead of Docker containers (faster for MVP)
- ❌ **Multi-region**: Single region deployment (cost-effective for MVP)

### 5.3 Production Readiness Gaps

**Current State** (MVP):
- ✅ Basic async execution
- ✅ PostgreSQL persistence
- ✅ Swagger documentation
- ✅ Error handling

**Production Needs**:
- ⚠️ **Security**: Docker containers for code execution
- ⚠️ **Monitoring**: Prometheus + Grafana for metrics
- ⚠️ **Authentication**: JWT tokens, user management
- ⚠️ **Rate limiting**: Per-user execution limits
- ⚠️ **Logging**: Centralized logging (ELK stack)
- ⚠️ **Testing**: Unit tests, integration tests, load tests
- ⚠️ **CI/CD**: Automated deployments

---

## API Endpoints Summary

### Code Sessions
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/code-sessions` | Create new session |
| GET | `/api/v1/code-sessions/{id}` | Get session details |
| PATCH | `/api/v1/code-sessions/{id}` | Update session (autosave) |
| DELETE | `/api/v1/code-sessions/{id}` | Delete session |

### Code Execution
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/executions/session/{id}/execute` | Execute code (async) |
| GET | `/api/v1/executions/{execution_id}` | Get execution result |
| GET | `/api/v1/executions/session/{id}` | Get all executions for session |

### Health Checks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | API health |
| GET | `/health/redis` | Redis connection status |
| GET | `/health/celery` | Celery worker status |
| GET | `/docs` | Swagger documentation |

---

## Running the System

### Development Setup

1. **Install dependencies**:
```bash
pip install -r requirements.txt
```

2. **Set up environment** (`.env`):
```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/livecode_platform
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
```

3. **Start services**:
```bash
# Terminal 1: Flask API
python main.py

# Terminal 2: Celery Worker
celery -A celery_worker.celery worker --loglevel=info --pool=solo
```

4. **Access Swagger UI**:
http://localhost:5000/docs

---

## Monitoring & Observability

### Key Metrics to Track

1. **Queue Metrics**:
   - Pending tasks in Redis
   - Task processing rate
   - Average wait time

2. **Execution Metrics**:
   - Success/failure rate
   - Average execution time
   - Timeout frequency

3. **System Metrics**:
   - API response time
   - Database connection pool usage
   - Worker CPU/memory usage

### Health Check Endpoints

```bash
# Check Redis connection
curl http://localhost:5000/health/redis

# Check Celery workers
curl http://localhost:5000/health/celery
```

---

## Future Enhancements

1. **WebSocket Support**: Real-time execution updates instead of polling
2. **Docker Isolation**: Run code in containerized environments
3. **Multi-language Support**: Add more languages (Java, C++, Go)
4. **Collaborative Editing**: Multiple users editing same session
5. **Code Versioning**: Track code changes over time
6. **Execution Limits**: CPU, memory, and network restrictions
7. **User Management**: Authentication and authorization
8. **Analytics**: Track usage patterns and popular languages

---

**Version**: 1.0  
**Last Updated**: January 2026  
**Maintainer**: LiveCode Execution Team
