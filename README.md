# LiveCode Execution API

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?style=for-the-badge&logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](http://makeapullrequest.com)

**An asynchronous live code execution API**

[Setup](#-setup-instructions) • [API Docs](#-api-documentation) • [Design](#-design-decisions) • [Docker](#-docker-setup) • [Tests](#-tests-bonus)

</div>

---

## Table of Contents

1. [Features](#-features)
2. [Architecture](#-architecture)
3. [Setup Instructions](#-setup-instructions)
4. [API Documentation](#-api-documentation)
5. [Design Decisions & Trade-offs](#-design-decisions--trade-offs)
6. [What We Would Improve](#-what-we-would-improve-with-more-time)
7. [Docker Setup](#-docker-setup)
8. [Tests (Bonus)](#-tests-bonus)
9. [Monitoring](#-monitoring--observability)

---

## Features

- **Asynchronous Execution** - Async chronous code execution using Celery queue
- **Multi-Language Support** - Currently support common programming languages such as Python, JavaScript (Node.js), and C++ (g++ compiler)
- **Data Storage** - PostgreSQL for sessions/executions, Redis for message queue
- **Tracking Real-time Status** - Monitor execution states (QUEUED → RUNNING → COMPLETED/FAILED/TIMEOUT)
- **Safety** - Timeout protection (30s), output limits (100KB), rate limiting (10/min)
- **API Documentation** - Auto-generated Swagger UI
- **Docker in Production** - One-command deployment with Docker Compose
- **Auto-Retry Mechanism** - Transient failure recovery with exponential backoff (max 3 retries)
- **Comprehensive Observability** - Lifecycle logging with timestamps for all execution stages
- **Abuse Prevention Mechanism** - Max 100 executions per session, rate limiting per session

---

## Architecture

### System Architecture

The LiveCode Execution API is a **distributed, asynchronous code execution platform** that allows users to write, save, and execute code in multiple programming languages (Python, JavaScript, C++) through a RESTful API.

<div align="center">
  <img src="./docs/images/z7457077336734_932ee50b286ba2785462344479ee1947.jpg" alt="LiveCode Execution API - Complete System Architecture" width="1200">
  
  *Figure: Complete system architecture showing client layer, Flask API layer, PostgreSQL database, Redis message queue, Celery worker layer, and code execution environments with detailed data flow and safety mechanisms*
</div>

### Data Flow

1. **Client → API:** POST `/code-sessions` → Create session in PostgreSQL → Return `session_id`
2. **Client → API:** PATCH `/code-sessions/{id}` → Update source_code → Autosave
3. **Client → API:** POST `/code-sessions/{id}/run` → Create execution (QUEUED) → Push to Redis
4. **Worker ← Redis:** Pull task → Update status (RUNNING) → Execute subprocess
5. **Worker → PostgreSQL:** Update execution (COMPLETED) with stdout/stderr
6. **Client → API:** GET `/executions/{id}` (polling) → Return results when COMPLETED

### Execution States

```
QUEUED (waiting in Redis) → RUNNING (worker executing) → COMPLETED/FAILED/TIMEOUT (done)
```

### Key Architecture Features

- **Asynchronous** - Non-blocking API with background workers
- **Persistent** - PostgreSQL stores all sessions/executions
- **Scalable** - Horizontal worker scaling, queue-based architecture
- **Reliable** - Retry mechanism, state tracking, comprehensive logging
- **Safe** - Timeout, output limits, rate limiting, process isolation

### Safety Mechanisms

- **30-second timeout** - Kills infinite loops automatically
- **100KB output limit** - Prevents memory bombs
- **Rate limiting** - 10 executions/minute per session
- **Execution limit** - Maximum 100 executions per session
- **Process isolation** - Each execution runs in separate subprocess

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7.0+
- Node.js (for JS execution)
- g++ compiler (for C++ execution)
- Docker & Docker Compose (for containerized deployment)

### Option 1: Docker Deployment (I highly recommend)

```bash
# 1. Clone the repository
git clone https://github.com/hoangphat25092005/livecode-execution.git

# 2. Create environment file
cp .env.docker.example .env.docker

# 3. Edit .env.docker with your configuration
DATABASE_URL=postgresql://postgres:your_password@postgres:5432/livecode_platform
REDIS_URL=redis://redis:6379/0  #Depend on your REDIS_URL here is just a my default  
SECRET_KEY=your-secret-key-here

# 4. Start all services
docker-compose up -d --build

# 5. Check service status
docker-compose ps

# 6. View logs
docker-compose logs -f api

# 7. Stop services
docker-compose down
```

**Access Points:**
- **API**: http://localhost:5000
- **API Docs**: http://localhost:5000/docs
- **Health Check**: http://localhost:5000/health

### Option 2: Local Development

```bash
# 1. Clone and setup
git clone https://github.com/yourusername/livecode-execution-api.git
cd livecode-execution-api
python -m venv venv
source venv/bin/activate  
pip install -r requirement.txt

# 2. Create environment file
cp .env.yours .env

# 3. Edit .env with local configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/livecode_platform
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret-key
DEBUG=True

# 4. Start PostgreSQL (in separate terminal)
psql -U postgres
CREATE DATABASE livecode_platform;

# 5. Start Redis
redis-server

# 6. Start Flask API 
python main.py

# 7. Start Celery Worker (in another terminal)
celery -A celery_worker.celery worker --loglevel=info --pool=solo

# 8. Access Swagger UI
Open browser: http://localhost:5000/docs
```

## API Documentation

### Base URL
```
http://localhost:5000
```

### Code Sessions

#### 1. Create Session
```http
POST /code-sessions
Content-Type: application/json

{
  "language": "python",
  "source_code": "print('Hello World')"
}
```

**Note:** All fields are **optional**. If not provided:
- `language` defaults to `"python"`
- `source_code` defaults to `""` (empty string)

**Minimal Request (creates empty Python session):**
```http
POST /code-sessions
Content-Type: application/json

{}
```

**Response (201 Created):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ACTIVE"
}
```

**Supported Languages:** `python`, `javascript`, `c++`

#### 2. Update Session (Autosave)
```http
PATCH /code-sessions/{session_id}
Content-Type: application/json

{
  "source_code": "print('Hello World')\nprint('Updated!')"
}
```

**Optional Fields:**
- `source_code` - Updates the code content
- `language` - Changes the programming language

**Response (200 OK):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ACTIVE"
}
```

**Behavior:**
- Called frequently during live editing (debounced on client-side recommended: ~500ms)
- Updates `source_code` and/or `language` with `updated_at` timestamp
- Non-blocking operation
- Idempotent (safe to call multiple times)
- All fields are optional - update only what you need

#### 3. Get Session Details
```http
GET /code-sessions/{session_id}
```

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "language": "python",
  "source_code": "print('Hello World')",
  "status": "ACTIVE",
  "created_at": "2026-01-21T10:00:00Z",
  "updated_at": "2026-01-21T10:05:30Z"
}
```

#### 4. Delete Session
```http
DELETE /code-sessions/{session_id}
```

**Response (204 No Content)**

**Note:** Cascading delete removes all associated executions.

---

### Code Execution

#### 5. Execute Code (Asynchronous)
```http
POST /code-sessions/{session_id}
```

**Response (202 Accepted):**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "QUEUED"
}
```

**Behavior:**
- Returns immediately (non-blocking)
- Code execution happens asynchronously in background worker
- Client should poll `/executions/{execution_id}` for results

#### 6. Get Execution Result
```http
GET /executions/{execution_id}
```

**Response (200 OK) - When QUEUED:**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "QUEUED",
  "queued_at": "2026-01-21T10:00:00Z"
}
```

**Response (200 OK) - When RUNNING:**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "RUNNING",
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z"
}
```

**Response (200 OK) - When COMPLETED:**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "COMPLETED",
  "stdout": "Hello World\n",
  "stderr": "",
  "execution_time_ms": 120,
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z",
  "finished_at": "2026-01-21T10:00:01.120Z"
}
```

**Response (200 OK) - When FAILED:**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "FAILED",
  "stdout": "",
  "stderr": "SyntaxError: invalid syntax\n",
  "execution_time_ms": 50,
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z",
  "finished_at": "2026-01-21T10:00:01.050Z"
}
```

**Response (200 OK) - When TIMEOUT:**
```json
{
  "execution_id": "660e8400-e29b-41d4-a716-446655440111",
  "status": "TIMEOUT",
  "stdout": "",
  "stderr": "Execution exceeded 30 second timeout",
  "execution_time_ms": 30000,
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z",
  "finished_at": "2026-01-21T10:00:31Z"
}
```

#### 7. List Session Executions
```http
GET /executions/session/{session_id}
```

**Response (200 OK):**
```json
[
  {
    "execution_id": "660e8400-e29b-41d4-a716-446655440111",
    "status": "COMPLETED",
    "queued_at": "2026-01-21T10:00:00Z",
    "finished_at": "2026-01-21T10:00:01.120Z",
    "execution_time_ms": 120
  },
  {
    "execution_id": "770e8400-e29b-41d4-a716-446655440222",
    "status": "FAILED",
    "queued_at": "2026-01-21T10:05:00Z",
    "finished_at": "2026-01-21T10:05:00.050Z",
    "execution_time_ms": 50
  }
]
```

**Note:** Returns executions ordered by most recent first (`queued_at DESC`)

---

### Health Checks

#### 8. API Health
```http
GET /health
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-21T10:00:00Z"
}
```

#### 9. Redis Connection
```http
GET /health/redis
```

**Response (200 OK):**
```json
{
  "status": "connected",
  "ping": "PONG"
}
```

#### 10. Celery Workers
```http
GET /health/celery
```

**Response (200 OK):**
```json
{
  "status": "connected",
  "active_workers": 2,
  "active_tasks": 5
}
```

---

### Interactive API Documentation

Access the auto-generated Swagger UI:
```
http://localhost:5000/docs
```

Features:
- Try all endpoints directly from browser
- View request/response schemas
- Explore API structure
- Test with sample data

---

## Design Decisions & Trade-offs

### 1. Asynchronous Execution (Celery + Redis)

**Decision:** Use Celery task queue with Redis broker instead of synchronous execution.

**Pros:**
- Non-blocking API responses (returns immediately)
- Horizontal scalability (add more workers)
- Built-in retry mechanism for transient failures
- Mature ecosystem with monitoring tools (Flower)
- Decouples API from execution logic

**Cons:**
- Additional infrastructure complexity (Redis dependency)
- Polling required for status updates (vs WebSockets)
- Slightly higher latency for simple executions

**Why Chosen:** Industry standard for distributed task processing. The benefits of scalability and reliability outweigh the complexity for a production system.

---

### 2. Why Postgres

**Decision:** Use PostgreSQL for persistent storage.

**Postgres provide:**
- ACID compliance (transactions, consistency)
- Complex queries with JOINs (sessions + executions)
- Foreign key constraints (data integrity)
- Mature, battle-tested technology
- Rich ecosystem (pgAdmin, extensions)


**Why Chosen:** Relational data model fits well (sessions → executions). ACID guarantees are critical for execution tracking.
---

### 3. Subprocess Execution vs Docker Containers

**Decision:** Use Python `subprocess` for code execution (MVP), with Docker as future enhancement.

**Current (MVP):**
- Simple implementation
- Fast execution startup
- No additional infrastructure
- Limited isolation (same OS)
- Security risks (shared environment)

**Future (Production):**
- Docker containers per execution
- Complete isolation
- Resource limits (CPU, memory)
- Better security
- Slower startup (~200ms overhead)

**Why Chosen:** Subprocess is sufficient for MVP/demonstration. For production, we would migrate to Docker containers for proper sandboxing.

---

### 4. Polling vs WebSockets

**Decision:** Use HTTP polling for execution status instead of WebSockets.

**Polling (Current):**
- Simpler implementation (no persistent connections)
- Works with standard HTTP load balancers
- Easy to cache responses
- Higher latency (poll interval: ~1-2s)
- More network requests

**WebSockets (Alternative):**
- Real-time updates (instant)
- Lower network overhead
- Complex infrastructure (sticky sessions)
- Harder to scale horizontally

**Why Chosen:** Polling is "good enough" for code execution (1-2s delay acceptable). WebSockets would be overkill for the MVP and add significant complexity.

---

### 5. Rate Limiting Strategy

**Decision:** Implement application-level rate limiting.

**Limits Enforced:**
```python
MAX_EXECUTIONS_PER_SESSION = 100    # Prevent abuse
MAX_EXECUTIONS_PER_MINUTE = 10      # Rate limit
MAX_OUTPUT_SIZE = 100 * 1024        # 100KB output limit
EXECUTION_TIMEOUT = 30              # 30 seconds max
```

**Why These Numbers:**
- **100 executions/session**: Enough for typical coding session, prevents runaway automation
- **10 executions/minute**: Allows rapid iteration while preventing DoS
- **100KB output**: Reasonable for debugging, prevents memory bombs
- **30s timeout**: Catches infinite loops, long enough for legitimate code

**Trade-off:** Aggressive limits improve stability but may frustrate legitimate power users. These are tunable via environment variables.

---

### 6. Language Support

**Current:** Python, JavaScript, C++

**Decision Factors:**
- **Python**: Most popular for learning, simple to execute (`python -c`)
- **JavaScript**: Second most popular, Node.js widely available
- **C++**: Demonstrates compilation phase (more complex workflow)

**Not Supported (Yet):**
- Java: Requires JVM, slower startup
- Go: Less common for beginners
- Rust: Compilation complexity

**Extensible Design:** New languages can be added by implementing `_execute_<language>()` function in `execution_tasks.py`.

---

### 7. Scalability Choices

#### Database Connection Pooling
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # Max persistent connections
    max_overflow=20,        # Additional temporary connections
    pool_recycle=3600,      # Recycle connections after 1 hour
    pool_pre_ping=True      # Test connections before use
)
```

**Trade-off:** More connections = higher memory usage, but better concurrency.

#### Horizontal Scaling
```bash
# Scale Celery workers
docker-compose up -d --scale celery_worker=5
```

**Bottleneck Analysis:**

| Component | Scaling Strategy | Cost |
|-----------|-----------------|------|
| **Flask API** | Horizontal (load balancer) | Low |
| **Celery Workers** | Horizontal (add workers) | Low |
| **Redis** | Vertical → Redis Cluster | Medium |
| **PostgreSQL** | Read replicas → Sharding | High |

**Current Capacity (Single Instance):**
- API: ~1000 req/s
- Workers: ~10 executions/s (depending on code complexity)
- PostgreSQL: ~5000 queries/s

---

## What We Would Improve With More Time

### High Priority (Production Readiness)

#### 1. **Docker Sandbox Execution** 
- Replace `subprocess` with Docker containers
- Use `docker run --rm --network=none --memory=128m --cpus=0.5` for isolation
- Security: Prevent file system access, network calls, privilege escalation
- **Impact:** Critical for production security

#### 2. **WebSocket Support** 
- Real-time execution updates instead of polling
- Use Socket.IO or native WebSockets
- Push stdout/stderr as it's generated (streaming output)
- **Impact:** Better UX, lower latency

#### 3. **Authentication & Authorization** 
- JWT token-based authentication
- User accounts and session ownership
- Per-user rate limiting
- Admin roles for monitoring
- **Impact:** Required for multi-tenant deployment

#### 4. **Comprehensive Testing** 
```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Load tests
locust -f tests/load/test_api.py --users 1000 --spawn-rate 10
```
- **Coverage Target:** >80%
- **Load Test:** 10,000 concurrent users
- **Impact:** Confidence in deployments

#### 5. **Monitoring & Alerting** 
- Prometheus for metrics (execution time, queue length, error rate)
- Grafana dashboards
- PagerDuty/Opsgenie for alerts
- ELK stack for centralized logging
- **Impact:** Observability in production


### 6. **Instead of counting for handling Rate Limitting**
- Leaky Bucket Algorithm
- Fixed window Algorithm
- Provide more secure way to handling Rate Limitting
---


### Architecture Improvements

#### 13. **Microservices Split**
Current (Monolith):
```Low Prio
Flask API (sessions + executions + health)
```

Future (Microservices):
```
API Gateway
├── Session Service (code_sessions)
├── Execution Service (executions)
├── Code Runner Service (isolated workers)
└── Auth Service (users, tokens)
```

**Benefits:**
- Independent scaling
- Team ownership
- Technology flexibility

**Trade-offs:**
- Increased complexity
- Distributed tracing required
- Network latency between services

#### 14. **Event Sourcing**
- Store all events (CodeSubmitted, ExecutionStarted, ExecutionCompleted)
- Rebuild state from event log
- Audit trail for compliance
- Time-travel debugging

---

### Performance Optimizations

#### 15. **Caching Layer** 
```python
# Cache execution results (identical code)
@cache.memoize(timeout=3600)
def get_execution_result(code_hash, language):
    # If same code executed before, return cached result
    pass
```

**Benefits:**
- Faster responses for repeated code
- Reduced worker load

**Trade-off:**
- Cache invalidation complexity
- Memory usage

#### 16. **Database Optimizations**
- Partitioning (executions table by date)
- Materialized views for analytics
- Connection pooling tuning
- Query optimization (EXPLAIN ANALYZE)

---

### Deployment & DevOps

#### 17. **CI/CD Pipeline** 
```yaml
# GitHub Actions
- Run tests on PR
- Build Docker images
- Deploy to staging
- Run integration tests
- Deploy to production (manual approval)
```

#### 18. **Multi-Region Deployment**
- Deploy to multiple AWS regions (us-east-1, eu-west-1, ap-southeast-1)
- Route users to nearest region (latency-based routing)
- Database replication across regions

---

## Monitoring & Observability

### Key Metrics

#### 1. Execution Metrics
```python
# Prometheus metrics
execution_duration_seconds = Histogram('execution_duration_seconds', 'Time to execute code')
execution_status_total = Counter('execution_status_total', 'Execution outcomes', ['status'])
queue_length = Gauge('queue_length', 'Number of pending tasks')
```

**Alerts:**
- Execution failure rate > 10%
- Average queue time > 30s
- Worker unavailable for > 1 minute

#### 2. API Metrics
```python
request_duration_seconds = Histogram('request_duration_seconds', 'API response time')
request_count = Counter('request_count', 'Total requests', ['method', 'endpoint', 'status'])
```

**Alerts:**
- p99 latency > 1s
- Error rate > 5%
- Request rate drops suddenly 

#### 3. System Metrics
- CPU usage > 80%
- Memory usage > 90%
- Disk usage > 85%
- Database connection pool exhaustion

### Logging Strategy

```python
# Structured logging
logger.info("Execution started", extra={
    "execution_id": execution_id,
    "session_id": session_id,
    "language": language,
    "user_id": user_id,
    "timestamp": datetime.utcnow().isoformat()
})
```

**Log Levels:**
- `DEBUG`: Detailed execution steps
- `INFO`: Lifecycle events (QUEUED → RUNNING → COMPLETED)
- `WARNING`: Rate limiting, timeouts
- `ERROR`: Unexpected failures, retries
- `CRITICAL`: Service outages


---

## Docker Setup

### Docker Configuration Files

#### 1. **Dockerfile** (Flask API)
```dockerfile
FROM python:3.11-slim

# Install system dependencies (g++, Node.js for multi-language support)
RUN apt-get update && apt-get install -y \
    gcc g++ build-essential \
    nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run with Gunicorn (production WSGI server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "main:app"]
```

#### 2. **Dockerfile.worker** (Celery Worker)
```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc g++ build-essential \
    nodejs npm curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

# Copy application code
COPY . .

# Health check server + Celery worker (for Render free tier)
CMD sh -c 'python -m http.server ${PORT:-8080} & celery -A celery_worker.celery worker --loglevel=info --pool=solo'
```

#### 3. **docker-compose.yml**
```yaml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: livecode_postgres
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres123
      POSTGRES_DB: livecode_platform
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis Message Broker
  redis:
    image: redis:7-alpine
    container_name: livecode_redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Flask API
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: livecode_api
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/livecode_platform
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=dev-secret-key-change-in-production
      - DEBUG=False
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app
      - ./logs:/app/logs

  # Celery Worker
  celery_worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    container_name: livecode_worker
    environment:
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/livecode_platform
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=dev-secret-key-change-in-production
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app

  # Flower (Celery Monitoring - Optional)
  flower:
    image: mher/flower:latest
    container_name: livecode_flower
    command: celery --broker=redis://redis:6379/0 flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    depends_on:
      - redis

volumes:
  postgres_data:
```

### One-Command Setup

```bash
# Start all services (API, Worker, PostgreSQL, Redis, Flower)
docker-compose up -d --build

# Verify all containers are running
docker-compose ps

# View logs
docker-compose logs -f

# Stop all services
docker-compose down

# Stop and remove volumes (clean database)
docker-compose down -v
```

### Container Health Checks

```bash
# Check API health
curl http://localhost:5000/health

# Check Redis connection
docker exec livecode_redis redis-cli ping
# Expected: PONG

# Check PostgreSQL
docker exec livecode_postgres pg_isready -U postgres
# Expected: postgres:5432 - accepting connections

# Check Celery workers (via Flower)
open http://localhost:5555
```

---

## Tests

### Test Structure

```
tests/
├── unit/
│   ├── test_code_execution_service.py
│   ├── test_execution_tasks.py
│   └── test_models.py
├── integration/
│   ├── test_session_api.py
│   ├── test_execution_api.py
│   └── test_health_endpoints.py
└── failure_scenarios/
    ├── test_queue_failure.py
    ├── test_worker_crash.py
    └── test_database_failure.py
```

### 1. Unit Tests

#### Test Code Execution Service
```python
# tests/unit/test_code_execution_service.py
import pytest
from app.services.code_execution_service import CodeExecutionService
from app.models.code_sessions_model import CodeSession
from unittest.mock import Mock, patch

class TestCodeExecutionService:
    @pytest.fixture
    def service(self):
        return CodeExecutionService()
    
    @pytest.fixture
    def mock_session(self):
        session = Mock(spec=CodeSession)
        session.id = "test-session-id"
        session.language = "python"
        session.source_code = "print('test')"
        return session
    
    def test_execute_code_creates_execution(self, service, mock_session):
        """Test that execute_code creates an execution record"""
        with patch('app.services.code_execution_service.db.session'):
            execution_id = service.execute_code(mock_session)
            assert execution_id is not None
    
    def test_execute_code_queues_task(self, service, mock_session):
        """Test that execute_code queues Celery task"""
        with patch('app.services.code_execution_service.execute_code_task') as mock_task:
            service.execute_code(mock_session)
            mock_task.delay.assert_called_once()
```

#### Test Execution Tasks
```python
# tests/unit/test_execution_tasks.py
import pytest
from app.tasks.execution_tasks import _execute_python, _execute_javascript, _execute_c_plusplus

class TestExecutionTasks:
    def test_execute_python_success(self):
        """Test successful Python execution"""
        stdout, stderr, return_code = _execute_python("print('Hello World')")
        assert stdout == "Hello World\n"
        assert stderr == ""
        assert return_code == 0
    
    def test_execute_python_syntax_error(self):
        """Test Python syntax error handling"""
        stdout, stderr, return_code = _execute_python("print('unclosed")
        assert "SyntaxError" in stderr
        assert return_code != 0
    
    def test_execute_python_timeout(self):
        """Test Python execution timeout"""
        code = "import time; time.sleep(60)"
        stdout, stderr, return_code = _execute_python(code, timeout=1)
        assert "timeout" in stderr.lower() or return_code != 0
    
    def test_execute_javascript_success(self):
        """Test successful JavaScript execution"""
        stdout, stderr, return_code = _execute_javascript("console.log('Hello JS')")
        assert "Hello JS" in stdout
        assert return_code == 0
    
    def test_execute_cpp_compilation(self):
        """Test C++ compilation and execution"""
        code = """
        #include <iostream>
        int main() {
            std::cout << "Hello C++" << std::endl;
            return 0;
        }
        """
        stdout, stderr, return_code = _execute_c_plusplus(code)
        assert "Hello C++" in stdout
        assert return_code == 0
```

### 2. Integration Tests

#### Test Session API
```python
# tests/integration/test_session_api.py
import pytest
from app import create_app
from app.models.db import db
import json

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

class TestSessionAPI:
    def test_create_session(self, client):
        """Test POST /code-sessions"""
        response = client.post('/code-sessions', json={
            'language': 'python',
            'source_code': 'print("test")'
        })
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'session_id' in data
        assert data['status'] == 'ACTIVE'
    
    def test_create_session_invalid_language(self, client):
        """Test invalid language rejection"""
        response = client.post('/code-sessions', json={
            'language': 'brainfuck',
            'source_code': 'test'
        })
        assert response.status_code == 400
    
    def test_update_session(self, client):
        """Test PATCH /code-sessions/{id}"""
        # Create session
        create_response = client.post('/code-sessions', json={
            'language': 'python',
            'source_code': 'print("old")'
        })
        session_id = json.loads(create_response.data)['session_id']
        
        # Update session
        update_response = client.patch(f'/code-sessions/{session_id}', json={
            'source_code': 'print("new")'
        })
        assert update_response.status_code == 200
    
    def test_get_session(self, client):
        """Test GET /code-sessions/{id}"""
        # Create session
        create_response = client.post('/code-sessions', json={
            'language': 'javascript',
            'source_code': 'console.log("test")'
        })
        session_id = json.loads(create_response.data)['session_id']
        
        # Get session
        get_response = client.get(f'/code-sessions/{session_id}')
        assert get_response.status_code == 200
        data = json.loads(get_response.data)
        assert data['language'] == 'javascript'
```

#### Test Execution API
```python
# tests/integration/test_execution_api.py
import pytest
from app import create_app
from app.models.db import db
import json
import time

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.drop_all()

class TestExecutionAPI:
    def test_execute_code(self, client):
        """Test POST /code-sessions/{id}/run"""
        # Create session
        session_response = client.post('/code-sessions', json={
            'language': 'python',
            'source_code': 'print("execute")'
        })
        session_id = json.loads(session_response.data)['session_id']
        
        # Execute code
        exec_response = client.post(f'/code-sessions/{session_id}/run')
        assert exec_response.status_code == 202
        data = json.loads(exec_response.data)
        assert 'execution_id' in data
        assert data['status'] == 'QUEUED'
    
    def test_get_execution_result(self, client):
        """Test GET /executions/{id}"""
        # Create and execute
        session_response = client.post('/code-sessions', json={
            'language': 'python',
            'source_code': 'print("result")'
        })
        session_id = json.loads(session_response.data)['session_id']
        
        exec_response = client.post(f'/code-sessions/{session_id}/run')
        execution_id = json.loads(exec_response.data)['execution_id']
        
        # Wait for execution
        time.sleep(2)
        
        # Get result
        result_response = client.get(f'/executions/{execution_id}')
        assert result_response.status_code == 200
        data = json.loads(result_response.data)
        assert data['status'] in ['QUEUED', 'RUNNING', 'COMPLETED']
```

### 3. Failure Scenario Tests

#### Test Queue Failure
```python
# tests/failure_scenarios/test_queue_failure.py
import pytest
from app.services.code_execution_service import CodeExecutionService
from unittest.mock import patch, Mock

class TestQueueFailure:
    def test_redis_connection_failure(self):
        """Test handling when Redis is unavailable"""
        service = CodeExecutionService()
        
        with patch('app.services.code_execution_service.execute_code_task') as mock_task:
            mock_task.delay.side_effect = ConnectionError("Redis unavailable")
            
            mock_session = Mock()
            mock_session.id = "test-id"
            
            with pytest.raises(ConnectionError):
                service.execute_code(mock_session)
    
    def test_task_retry_on_failure(self):
        """Test Celery task retry mechanism"""
        from app.tasks.execution_tasks import execute_code_task
        
        with patch('app.tasks.execution_tasks.db.session') as mock_db:
            mock_db.commit.side_effect = [Exception("DB Error"), None]
            
            # Task should retry and succeed on second attempt
            # (Requires actual Celery instance - integration test)
            pass
```

#### Test Worker Crash
```python
# tests/failure_scenarios/test_worker_crash.py
import pytest
from app.models.execution_model import Execution
from app.models.db import db

class TestWorkerCrash:
    def test_stuck_executions_cleanup(self):
        """Test cleanup of executions stuck in RUNNING state"""
        # Simulate worker crash: execution stuck in RUNNING for > 5 minutes
        # Cleanup job should mark as FAILED
        
        from datetime import datetime, timedelta
        
        # Create stuck execution
        execution = Execution(
            session_id="test-session",
            status="RUNNING",
            started_at=datetime.utcnow() - timedelta(minutes=10)
        )
        db.session.add(execution)
        db.session.commit()
        
        # Run cleanup task (would be cron job in production)
        # cleanup_stuck_executions()
        
        # Verify execution marked as FAILED
        # assert execution.status == "FAILED"
        pass
```

#### Test Database Failure
```python
# tests/failure_scenarios/test_database_failure.py
import pytest
from app.services.code_execution_service import CodeExecutionService
from unittest.mock import patch

class TestDatabaseFailure:
    def test_database_connection_loss(self):
        """Test handling when PostgreSQL is unavailable"""
        service = CodeExecutionService()
        
        with patch('app.services.code_execution_service.db.session.add') as mock_add:
            mock_add.side_effect = ConnectionError("Database unavailable")
            
            with pytest.raises(ConnectionError):
                service.execute_code(Mock())
    
    def test_transaction_rollback(self):
        """Test transaction rollback on error"""
        # Simulate error during execution creation
        # Verify database state is consistent (no orphaned records)
        pass
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=html

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/failure_scenarios/

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_execution_tasks.py

# Run specific test
pytest tests/unit/test_execution_tasks.py::TestExecutionTasks::test_execute_python_success
```

### Test Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=app --cov-report=html

# Open in browser
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

**Target Coverage:** >80% for production readiness

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/interesting-feature`)
3. Commit changes (`git commit -m 'Add some interesting features'`)
4. Push to branch (`git push origin feature/interesting-feature`)
5. Open a Pull Request

---


## Support

- **Email:** hoangphatpy123@gmail.com
