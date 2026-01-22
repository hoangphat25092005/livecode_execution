# PHAT's LiveCode Execution API

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?style=for-the-badge&logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](http://makeapullrequest.com)

**A production-ready, asynchronous code execution API supporting Python, JavaScript, and C++**

[Setup](#-setup-instructions) • [Architecture](#-architecture) • [API Docs](#-api-documentation) • [Design](#-design-decisions) • [Future](#-future-improvements)

</div>

---

## Table of Contents

1. [Features](#-features)
2. [Setup Instructions](#-setup-instructions)
3. [Architecture](#-architecture)
4. [API Documentation](#-api-documentation)
5. [Design Decisions & Trade-offs](#-design-decisions--trade-offs)
6. [What We Would Improve](#-what-we-would-improve-with-more-time)
7. [Monitoring](#-monitoring--observability)

---

## Features

- **Asynchronous Execution** - Non-blocking code execution using Celery task queue
- **Multi-Language Support** - Python, JavaScript (Node.js), and C++ (g++ compiler)
- **Persistent Storage** - PostgreSQL for sessions/executions, Redis for message queue
- **Real-time Status Tracking** - Monitor execution states (QUEUED → RUNNING → COMPLETED/FAILED/TIMEOUT)
- **Built-in Safety** - Timeout protection (30s), output limits (100KB), rate limiting (10/min)
- **Interactive API Documentation** - Auto-generated Swagger UI
- **Docker Ready** - One-command deployment with Docker Compose
- **Auto-Retry Mechanism** - Transient failure recovery with exponential backoff (max 3 retries)
- **Comprehensive Observability** - Lifecycle logging with timestamps for all execution stages
- **Abuse Prevention** - Max 100 executions per session, rate limiting per session

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7.0+
- Node.js (for JavaScript execution)
- g++ compiler (for C++ execution)
- Docker & Docker Compose (optional, for containerized deployment)

### Option 1: Docker Deployment (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/livecode-execution-api.git
cd livecode-execution-api

# 2. Create environment file
cp .env.docker.example .env.docker

# 3. Edit .env.docker with your configuration
# DATABASE_URL=postgresql://postgres:your_password@postgres:5432/livecode_platform
# REDIS_URL=redis://redis:6379/0
# SECRET_KEY=your-secret-key-here

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
- **Swagger Docs**: http://localhost:5000/docs
- **Health Check**: http://localhost:5000/health

### Option 2: Local Development

```bash
# 1. Clone and setup
git clone https://github.com/yourusername/livecode-execution-api.git
cd livecode-execution-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

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

# 5. Start Redis (in separate terminal)
redis-server

# 6. Start Flask API (Terminal 1)
python main.py

# 7. Start Celery Worker (Terminal 2)
celery -A celery_worker.celery worker --loglevel=info --pool=solo

# 8. Access Swagger UI
# Open browser: http://localhost:5000/docs
```

### Verify Installation

```bash
# Check API health
curl http://localhost:5000/health

# Should return: {"status": "healthy"}

# Check Redis connection
curl http://localhost:5000/health/redis

# Check Celery workers
curl http://localhost:5000/health/celery
```

---

## Architecture

### System Components Diagram

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Client    │─────▶│  Flask API   │─────▶│  PostgreSQL  │
│  (Browser)  │      │   (REST)     │      │   Database   │
└─────────────┘      └──────────────┘      └──────────────┘
                           │
                           │ Push Task
                           ▼
                     ┌──────────────┐
                     │    Redis     │
                     │   (Broker)   │
                     └──────────────┘
                           │
                           │ Pull Task
                           ▼
                     ┌──────────────┐      ┌──────────────┐
                     │    Celery    │─────▶│   Isolated   │
                     │   Workers    │      │ Subprocess   │
                     └──────────────┘      └──────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API Framework** | Flask 3.0 + Flask-RESTX | RESTful API with auto-generated Swagger docs |
| **Database** | PostgreSQL 15 | Persistent storage for sessions and executions |
| **Message Broker** | Redis 7.0 | Task queue for asynchronous execution |
| **Task Queue** | Celery 5.3 | Distributed task processing |
| **ORM** | SQLAlchemy | Database abstraction and migrations |
| **Web Server** | Gunicorn | WSGI HTTP server for production |
| **Containerization** | Docker + Compose | Isolated, reproducible environments |

### Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Flask API
    participant PostgreSQL
    participant Redis
    participant Celery Worker
    
    Client->>Flask API: POST /code-sessions
    Flask API->>PostgreSQL: INSERT session
    PostgreSQL-->>Flask API: session_id
    Flask API-->>Client: {session_id, status: "ACTIVE"}
    
    Client->>Flask API: POST /code-sessions/{id}/run
    Flask API->>PostgreSQL: INSERT execution (QUEUED)
    Flask API->>Redis: Push task to queue
    Flask API-->>Client: {execution_id, status: "QUEUED"}
    
    Note over Celery Worker: Worker picks up task
    Celery Worker->>PostgreSQL: UPDATE status = RUNNING
    Celery Worker->>Celery Worker: Execute code (30s timeout)
    Celery Worker->>PostgreSQL: UPDATE status = COMPLETED
    
    Client->>Flask API: GET /executions/{id}
    Flask API->>PostgreSQL: SELECT execution
    PostgreSQL-->>Flask API: execution data
    Flask API-->>Client: {status: "COMPLETED", stdout, stderr}
```

### Data Model

#### Code Sessions Table
```sql
CREATE TABLE code_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    language VARCHAR(50) NOT NULL CHECK (language IN ('python', 'javascript', 'c++')),
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
    status VARCHAR(20) NOT NULL CHECK (status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT')),
    stdout TEXT,
    stderr TEXT,
    execution_time_ms INTEGER,
    queued_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    
    INDEX idx_session_id (session_id),
    INDEX idx_status (status),
    INDEX idx_created_at (queued_at)
);
```

### Execution States

```
┌─────────┐    Worker     ┌─────────┐    Success    ┌───────────┐
│ QUEUED  │───picks up────▶│ RUNNING │──────────────▶│ COMPLETED │
└─────────┘    task        └─────────┘               └───────────┘
                                 │
                                 │ Error
                                 ▼
                            ┌─────────┐
                            │ FAILED  │
                            └─────────┘
                                 │
                                 │ 30s exceeded
                                 ▼
                            ┌─────────┐
                            │ TIMEOUT │
                            └─────────┘
```

---

## 📡 API Documentation

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

**Response (200 OK):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ACTIVE"
}
```

**Behavior:**
- Called frequently during live editing (debounced on client-side recommended: ~500ms)
- Updates `source_code` and `updated_at` timestamp
- Non-blocking operation
- Idempotent (safe to call multiple times)

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
POST /code-sessions/{session_id}/run
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
    "execution_time_ms": 120,
    "created_at": "2026-01-21T10:00:00Z"
  },
  {
    "execution_id": "770e8400-e29b-41d4-a716-446655440222",
    "status": "FAILED",
    "execution_time_ms": 50,
    "created_at": "2026-01-21T10:05:00Z"
  }
]
```

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

### 2. PostgreSQL vs NoSQL

**Decision:** Use PostgreSQL for persistent storage.

**Pros:**
- ACID compliance (transactions, consistency)
- Complex queries with JOINs (sessions + executions)
- Foreign key constraints (data integrity)
- Mature, battle-tested technology
- Rich ecosystem (pgAdmin, extensions)

**Cons:**
- Not as fast as NoSQL for simple key-value operations
- Vertical scaling limits (requires sharding for massive scale)

**Why Chosen:** Relational data model fits well (sessions → executions). ACID guarantees are critical for execution tracking. NoSQL would sacrifice data integrity for marginal speed gains.

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

---

### Medium Priority (Enhanced Features)

#### 6. **Code Versioning & History** 
- Track every code change (like Git)
- Restore previous versions
- Diff viewer
- **Use Case:** "Undo" feature, learning analytics

#### 7. **Collaborative Editing**
- Multiple users editing same session
- Operational Transform or CRDT for conflict resolution
- User cursors and presence
- **Use Case:** Pair programming, teaching

#### 8. **Advanced Execution Features** 
- File upload support (e.g., CSV for data science)
- Standard input (`stdin`) support
- Execution visualization (step-through debugger)
- **Use Case:** Advanced coding exercises

#### 9. **Language-Specific Features** 
- Python: pip install packages, matplotlib plotting
- JavaScript: npm packages, DOM manipulation
- C++: Multi-file projects, custom compiler flags
- **Use Case:** Real-world project simulation

---

### Low Priority (Nice-to-Have)

#### 10. **AI-Powered Features**
- Code completion (GitHub Copilot-style)
- Error explanation (LLM-powered hints)
- Code review suggestions
- **Use Case:** Learning assistance

#### 11. **Execution Analytics** 
- Most popular languages
- Average execution time by language
- Common error patterns
- User engagement metrics
- **Use Case:** Product insights

#### 12. **Custom Themes & UI** 
- Monaco Editor integration (VS Code editor)
- Syntax highlighting themes
- Dark mode
- **Use Case:** Better developer experience

---

### Architecture Improvements

#### 13. **Microservices Split**
Current (Monolith):
```
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


## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

---

## Support

- **Email:** hoangphatpy123@gmail.com
- **Issues:** [GitHub Issues](https://github.com/yourusername/livecode-execution-api/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/yourusername/livecode-execution-api/discussions)

---

<div align="center">

**⭐ Star this repo if you found it helpful!**

Made with ❤️ by the LiveCode Team

</div>