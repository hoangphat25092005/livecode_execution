# LiveCode Execution API - Design Document

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Reliability & Data Model](#2-reliability--data-model)
3. [Scalability Considerations](#3-scalability-considerations)
4. [Trade-offs](#4-trade-offs)

---

## 1. Architecture Overview

### 1.1 End-to-End Request Flow

#### **Code Session Creation**

```
┌─────────────┐                ┌──────────────┐                ┌──────────────┐
│   Client    │                │  Flask API   │                │  PostgreSQL  │
│  (Browser)  │                │   (REST)     │                │   Database   │
└─────────────┘                └──────────────┘                └──────────────┘
      │                               │                                │
      │ 1. POST /code-sessions        │                                │
      │    {language, source_code}    │                                │
      ├──────────────────────────────▶│                                │
      │                               │                                │
      │                               │ 2. Validate language           │
      │                               │    (python/javascript/c++)     │
      │                               │                                │
      │                               │ 3. INSERT INTO code_sessions   │
      │                               ├───────────────────────────────▶│
      │                               │                                │
      │                               │ 4. session_id (UUID)           │
      │                               │◀───────────────────────────────┤
      │                               │                                │
      │ 5. 201 Created                │                                │
      │    {session_id, status}       │                                │
      │◀──────────────────────────────┤                                │
      │                               │                                │
```

**Implementation:**
- **File:** `app/routes/session_api.py` → `SessionCreate.post()`
- **Service:** `app/services/code_session_service.py` → `create_session()`
- **Model:** `app/models/code_sessions_model.py` → `CodeSession`

**Flow Steps:**
1. Client sends POST request with `language` and `source_code`
2. API validates language (must be python/javascript/c++)
3. Service creates new `CodeSession` record with status `ACTIVE`
4. Database returns auto-generated UUID
5. API returns `201 Created` with `session_id`

**Response Time:** ~50ms (single database INSERT)

---

#### **Autosave Behavior**

```
┌─────────────┐                ┌──────────────┐                ┌──────────────┐
│   Client    │                │  Flask API   │                │  PostgreSQL  │
│  (Editor)   │                │   (REST)     │                │   Database   │
└─────────────┘                └──────────────┘                └──────────────┘
      │                               │                                │
      │ User types code...            │                                │
      │ (debounced ~500ms)            │                                │
      │                               │                                │
      │ 1. PATCH /code-sessions/{id}  │                                │
      │    {source_code}              │                                │
      ├──────────────────────────────▶│                                │
      │                               │                                │
      │                               │ 2. UPDATE code_sessions        │
      │                               │    SET source_code = ?,        │
      │                               │        updated_at = NOW()      │
      │                               │    WHERE id = ?                │
      │                               ├───────────────────────────────▶│
      │                               │                                │
      │                               │ 3. 1 row updated               │
      │                               │◀───────────────────────────────┤
      │                               │                                │
      │ 4. 200 OK                     │                                │
      │    {session_id, status}       │                                │
      │◀──────────────────────────────┤                                │
      │                               │                                │
      │ Continue typing...            │                                │
      │ (repeat every 500ms)          │                                │
      │                               │                                │
```

**Implementation:**
- **File:** `app/routes/session_api.py` → `SessionUpdate.patch()`
- **Service:** `app/services/code_session_service.py` → `update_session()`

**Design Decisions:**
- **Client-side debouncing (500ms):** Prevents excessive database writes during fast typing
- **Idempotent operation:** Safe to call multiple times with same data
- **Non-blocking:** User can continue typing while autosave happens
- **Optimistic UI:** Client shows "Saved" indicator immediately

**Database Impact:**
- Updates `source_code` field
- Updates `updated_at` timestamp (for analytics/audit)
- Uses indexed primary key (fast UPDATE)

**Response Time:** ~20ms (single UPDATE query)

---

#### **Execution Request**

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Client    │     │  Flask API   │     │  PostgreSQL  │     │    Redis     │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
      │                    │                     │                     │
      │ 1. POST /run       │                     │                     │
      ├───────────────────▶│                     │                     │
      │                    │                     │                     │
      │                    │ 2. Check session    │                     │
      │                    ├────────────────────▶│                     │
      │                    │◀────────────────────┤                     │
      │                    │                     │                     │
      │                    │ 3. CREATE execution │                     │
      │                    │    status = QUEUED  │                     │
      │                    │    queued_at = NOW()│                     │
      │                    ├────────────────────▶│                     │
      │                    │                     │                     │
      │                    │ 4. execution_id     │                     │
      │                    │◀────────────────────┤                     │
      │                    │                     │                     │
      │                    │ 5. RPUSH task queue │                     │
      │                    │    {execution_id,   │                     │
      │                    │     language,       │                     │
      │                    │     source_code}    │                     │
      │                    ├────────────────────────────────────────▶│
      │                    │                     │                     │
      │                    │ 6. Task queued (OK) │                     │
      │                    │◀────────────────────────────────────────┤
      │                    │                     │                     │
      │ 7. 202 Accepted    │                     │                     │
      │    {execution_id,  │                     │                     │
      │     status:QUEUED} │                     │                     │
      │◀───────────────────┤                     │                     │
      │                    │                     │                     │
```

**Implementation:**
- **File:** `app/routes/session_api.py` → `SessionRun.post()`
- **Service:** `app/services/code_execution_service.py` → `execute_code()`
- **Task:** `app/tasks/execution_tasks.py` → `execute_code_task.delay()`

**Flow Steps:**
1. Client sends POST request to `/code-sessions/{id}/run`
2. Service retrieves session from database
3. Create `Execution` record with status `QUEUED`, timestamp `queued_at`
4. Database returns `execution_id`
5. Service pushes task to Redis queue via Celery
6. Redis confirms task queued
7. API returns `202 Accepted` immediately (non-blocking)

**Critical Design:** API does NOT wait for execution to complete

**Response Time:** ~30ms (database write + Redis push)

---

#### **Background Execution**

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Redis     │     │Celery Worker │     │  PostgreSQL  │     │  Subprocess  │
│   (Broker)   │     │              │     │   Database   │     │  (Isolated)  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │                     │
      │ 1. LPOP task        │                     │                     │
      │◀────────────────────┤                     │                     │
      │                     │                     │                     │
      │ 2. Task data        │                     │                     │
      ├────────────────────▶│                     │                     │
      │                     │                     │                     │
      │                     │ 3. UPDATE execution │                     │
      │                     │    status = RUNNING │                     │
      │                     │    started_at=NOW() │                     │
      │                     ├────────────────────▶│                     │
      │                     │                     │                     │
      │                     │ 4. Check rate limit │                     │
      │                     │    (10 exec/min)    │                     │
      │                     ├────────────────────▶│                     │
      │                     │◀────────────────────┤                     │
      │                     │                     │                     │
      │                     │ 5. Execute code     │                     │
      │                     │    subprocess.run() │                     │
      │                     ├─────────────────────────────────────────▶│
      │                     │                     │                     │
      │                     │                     │    • Isolated env   │
      │                     │                     │    • 30s timeout    │
      │                     │                     │    • Captured I/O   │
      │                     │                     │                     │
      │                     │ 6. stdout, stderr   │                     │
      │                     │    return_code      │                     │
      │                     │◀─────────────────────────────────────────┤
      │                     │                     │                     │
      │                     │ 7. UPDATE execution │                     │
      │                     │    status=COMPLETED │                     │
      │                     │    stdout, stderr   │                     │
      │                     │    finished_at=NOW()│                     │
      │                     │    execution_time   │                     │
      │                     ├────────────────────▶│                     │
      │                     │                     │                     │
```

**Implementation:**
- **Worker:** `celery_worker.py`
- **Task:** `app/tasks/execution_tasks.py` → `execute_code_task()`
- **Executors:** `_execute_python()`, `_execute_javascript()`, `_execute_c_plusplus()`

**Flow Steps:**
1. Celery worker polls Redis for tasks (LPOP from queue)
2. Worker receives task data (execution_id, language, source_code)
3. Update execution status: `QUEUED` → `RUNNING`, record `started_at`
4. Check rate limiting (10 executions/minute per session)
5. Execute code in isolated subprocess with 30s timeout
6. Capture stdout, stderr, return code
7. Update execution: `RUNNING` → `COMPLETED/FAILED/TIMEOUT`, record `finished_at`

**Safety Mechanisms:**
- **Timeout:** Process killed after 30 seconds (prevents infinite loops)
- **Output limit:** Truncate stdout/stderr at 100KB (prevents memory bombs)
- **Rate limiting:** Max 10 executions/minute per session
- **Execution limit:** Max 100 executions per session
- **Isolation:** Subprocess isolation (future: Docker containers)

**Execution Time:** Variable (0ms - 30000ms depending on code)

---

#### **Result Polling**

```
┌─────────────┐                ┌──────────────┐                ┌──────────────┐
│   Client    │                │  Flask API   │                │  PostgreSQL  │
└─────────────┘                └──────────────┘                └──────────────┘
      │                               │                                │
      │ Loop every 1-2 seconds:       │                                │
      │                               │                                │
      │ 1. GET /executions/{id}       │                                │
      ├──────────────────────────────▶│                                │
      │                               │                                │
      │                               │ 2. SELECT * FROM executions    │
      │                               │    WHERE id = ?                │
      │                               ├───────────────────────────────▶│
      │                               │                                │
      │                               │ 3. Execution record            │
      │                               │◀───────────────────────────────┤
      │                               │                                │
      │ 4. 200 OK                     │                                │
      │    {status, stdout, stderr,   │                                │
      │     queued_at, started_at,    │                                │
      │     finished_at}               │                                │
      │◀──────────────────────────────┤                                │
      │                               │                                │
      │ If status = QUEUED/RUNNING:   │                                │
      │   → Wait 1-2s, poll again     │                                │
      │                               │                                │
      │ If status = COMPLETED/FAILED: │                                │
      │   → Stop polling, show result │                                │
      │                               │                                │
```

**Implementation:**
- **File:** `app/routes/execution_api.py` → `ExecutionStatus.get()`

**Polling Strategy:**
```javascript
// Client-side pseudo-code
async function pollExecution(executionId) {
  while (true) {
    const response = await fetch(`/executions/${executionId}`);
    const data = await response.json();
    
    if (data.status === 'COMPLETED' || data.status === 'FAILED' || data.status === 'TIMEOUT') {
      // Execution finished, display result
      displayResult(data.stdout, data.stderr);
      break;
    }
    
    // Still QUEUED or RUNNING, wait and poll again
    await sleep(1500);  // Poll every 1.5 seconds
  }
}
```

**Response States:**

1. **QUEUED:**
```json
{
  "execution_id": "...",
  "status": "QUEUED",
  "queued_at": "2026-01-21T10:00:00Z"
}
```

2. **RUNNING:**
```json
{
  "execution_id": "...",
  "status": "RUNNING",
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z"
}
```

3. **COMPLETED:**
```json
{
  "execution_id": "...",
  "status": "COMPLETED",
  "stdout": "Hello World\n",
  "stderr": "",
  "execution_time_ms": 120,
  "queued_at": "2026-01-21T10:00:00Z",
  "started_at": "2026-01-21T10:00:01Z",
  "finished_at": "2026-01-21T10:00:01.120Z"
}
```

**Response Time:** ~10ms (indexed database query)

**Alternative Design (WebSockets - Future):**
```javascript
// Instead of polling, use WebSocket for real-time updates
const ws = new WebSocket(`ws://api/executions/${executionId}`);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.status === 'COMPLETED') {
    displayResult(data.stdout, data.stderr);
  }
};
```

---

### 1.2 Queue-Based Execution Design

#### **Producer-Consumer Architecture**

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Producer Side                                │
└──────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────▼─────────────────────────┐
        │         Flask API (Producer)                       │
        │  - Validates request                               │
        │  - Creates execution record (QUEUED)               │
        │  - Pushes task to Redis queue                      │
        │  - Returns 202 Accepted immediately                │
        └─────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │           Redis (Message Broker)                 │
        │  - FIFO queue (First In, First Out)             │
        │  - Persistent storage (AOF enabled)              │
        │  - Task data: {execution_id, language, code}     │
        │  - Supports multiple workers (fan-out)           │
        └─────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │      Celery Workers (Consumers)                  │
        │  - Poll queue for tasks (LPOP)                   │
        │  - Execute code in subprocess                    │
        │  - Update execution status in database           │
        │  - Auto-retry on transient failures              │
        └──────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          Consumer Side                                │
└──────────────────────────────────────────────────────────────────────┘
```

**Key Benefits:**

1. **Decoupling:** API and execution logic are independent
   - API can restart without losing queued tasks
   - Workers can restart without affecting API

2. **Horizontal Scalability:**
   ```bash
   # Scale workers independently
   docker-compose up -d --scale celery_worker=10
   ```

3. **Load Balancing:** Redis distributes tasks across workers
   - Worker 1 picks task from queue
   - Worker 2 picks next task (parallel execution)

4. **Fault Tolerance:** If worker crashes, task returns to queue
   - Celery's acknowledgment mechanism
   - Task reprocessed by another worker

5. **Backpressure Handling:** Queue absorbs traffic spikes
   - 1000 requests in 1 second → All queued instantly
   - Workers process at sustainable rate

---

#### **Redis Queue Configuration**

```python
# app/config.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Task routing
CELERY_TASK_ROUTES = {
    'execute_code_task': {'queue': 'code_execution'}
}

# Worker concurrency
CELERY_WORKER_CONCURRENCY = 4  # Processes per worker
```

**Queue Structure:**
```
Redis List: celery
├── Task 1: {id: "abc123", language: "python", code: "..."}
├── Task 2: {id: "def456", language: "javascript", code: "..."}
├── Task 3: {id: "ghi789", language: "c++", code: "..."}
└── ...
```

**Task Lifecycle:**
1. **Producer:** `RPUSH celery {task_data}` (push to tail)
2. **Broker:** Task stored in Redis list
3. **Consumer:** `LPOP celery` (pop from head)
4. **Execution:** Worker processes task
5. **Acknowledgment:** Worker confirms completion

---

### 1.3 Execution Lifecycle and State Management

#### **State Transition Diagram**

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│                    Execution Lifecycle                                │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │   API Request    │
                    │  POST /run       │
                    └────────┬─────────┘
                             │
                             │ Create execution
                             │ Set queued_at timestamp
                             ▼
                    ┌──────────────────┐
                    │     QUEUED       │◀─────┐
                    │                  │      │
                    │ Waiting for      │      │ Retry
                    │ available worker │      │ (transient
                    └────────┬─────────┘      │ failure)
                             │                │
                             │ Worker picks   │
                             │ task from      │
                             │ queue          │
                             ▼                │
                    ┌──────────────────┐      │
                    │     RUNNING      │      │
                    │                  │      │
                    │ Executing code   │      │
                    │ Set started_at   │      │
                    └────────┬─────────┘      │
                             │                │
                ┌────────────┼────────────┐   │
                │            │            │   │
                │            │            │   │
         ┌──────▼──────┐ ┌──▼─────┐ ┌───▼───▼──┐
         │  COMPLETED  │ │ FAILED │ │ TIMEOUT  │
         │             │ │        │ │          │
         │ Success     │ │ Error  │ │ 30s      │
         │ exit_code=0 │ │ or     │ │ exceeded │
         │             │ │ crash  │ │          │
         └─────────────┘ └────────┘ └──────────┘
                │            │           │
                │            │           │
                └────────────┴───────────┘
                             │
                             │ Set finished_at
                             ▼
                    ┌──────────────────┐
                    │   Terminal       │
                    │   State          │
                    │   (No further    │
                    │    transitions)  │
                    └──────────────────┘
```

#### **State Definitions**

| State | Description | Database Fields | Duration |
|-------|-------------|-----------------|----------|
| **QUEUED** | Task created, waiting in Redis queue | `queued_at` | 0-5s (typical) |
| **RUNNING** | Worker executing code in subprocess | `started_at` | 0-30s (max) |
| **COMPLETED** | Execution finished successfully (exit code 0) | `finished_at`, `stdout`, `stderr`, `execution_time_ms` | Terminal state |
| **FAILED** | Execution error (syntax error, runtime exception, non-zero exit) | `finished_at`, `stderr`, `execution_time_ms` | Terminal state |
| **TIMEOUT** | Exceeded 30-second limit (infinite loop protection) | `finished_at`, `stderr`, `execution_time_ms` | Terminal state |

#### **State Transition Logic**

```python
# app/tasks/execution_tasks.py

@celery.task(max_retries=3, retry_backoff=True)
def execute_code_task(execution_id, language, source_code):
    execution = Execution.query.get(execution_id)
    
    # State: QUEUED → RUNNING
    execution.status = 'RUNNING'
    execution.started_at = datetime.utcnow()
    db.session.commit()
    logger.info(f"QUEUED → RUNNING: {execution_id}")
    
    try:
        # Execute code with timeout
        result = subprocess.run(
            ['python', '-c', source_code],
            timeout=30,
            capture_output=True
        )
        
        # State: RUNNING → COMPLETED (success)
        if result.returncode == 0:
            execution.status = 'COMPLETED'
            execution.stdout = result.stdout
            execution.stderr = result.stderr
        
        # State: RUNNING → FAILED (error)
        else:
            execution.status = 'FAILED'
            execution.stderr = result.stderr
            
    except subprocess.TimeoutExpired:
        # State: RUNNING → TIMEOUT
        execution.status = 'TIMEOUT'
        execution.stderr = 'Execution exceeded 30 second timeout'
    
    except Exception as e:
        # State: RUNNING → FAILED (unexpected error)
        execution.status = 'FAILED'
        execution.stderr = str(e)
        raise  # Trigger Celery retry
    
    finally:
        # Record final timestamp
        execution.finished_at = datetime.utcnow()
        execution.execution_time_ms = calculate_duration()
        db.session.commit()
        logger.info(f"RUNNING → {execution.status}: {execution_id}")
```

#### **Timestamp Tracking**

```python
# Database schema
class Execution(db.Model):
    queued_at = db.Column(db.DateTime)    # API creates execution
    started_at = db.Column(db.DateTime)   # Worker picks up task
    finished_at = db.Column(db.DateTime)  # Execution completes
```

**Metrics Calculation:**
```python
# Queue wait time
queue_time = started_at - queued_at  # How long task waited in queue

# Execution duration
execution_time = finished_at - started_at  # How long code ran

# Total latency (user perspective)
total_time = finished_at - queued_at  # End-to-end time
```

**Example Timeline:**
```
2026-01-21 10:00:00.000 → QUEUED (queued_at)
2026-01-21 10:00:00.500 → RUNNING (started_at) [500ms queue wait]
2026-01-21 10:00:01.250 → COMPLETED (finished_at) [750ms execution]
                          [1250ms total latency]
```

---

## 2. Reliability & Data Model

### 2.1 Execution States

#### **State Machine Implementation**

```python
# app/models/execution_model.py

from enum import Enum

class ExecutionStatus(str, Enum):
    QUEUED = "QUEUED"        # Task created, in Redis queue
    RUNNING = "RUNNING"      # Worker executing code
    COMPLETED = "COMPLETED"  # Success (exit code 0)
    FAILED = "FAILED"        # Error (syntax error, runtime exception)
    TIMEOUT = "TIMEOUT"      # Exceeded time limit

class Execution(db.Model):
    __tablename__ = "executions"
    
    id = db.Column(db.UUID, primary_key=True, default=uuid.uuid4)
    session_id = db.Column(db.UUID, db.ForeignKey("code_sessions.id"), nullable=False)
    
    # State management
    status = db.Column(
        db.Enum(ExecutionStatus),
        nullable=False,
        default=ExecutionStatus.QUEUED
    )
    
    # Results
    stdout = db.Column(db.Text)  # Standard output
    stderr = db.Column(db.Text)  # Error output
    execution_time_ms = db.Column(db.Integer)  # Duration in milliseconds
    
    # Timestamps for each state
    queued_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    
    # Indexes for fast queries
    __table_args__ = (
        db.Index('idx_session_id', 'session_id'),
        db.Index('idx_status', 'status'),
        db.Index('idx_queued_at', 'queued_at'),
    )
```

#### **State Validation Rules**

```python
# Valid state transitions
VALID_TRANSITIONS = {
    ExecutionStatus.QUEUED: [ExecutionStatus.RUNNING],
    ExecutionStatus.RUNNING: [
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT
    ],
    ExecutionStatus.COMPLETED: [],  # Terminal state
    ExecutionStatus.FAILED: [],     # Terminal state
    ExecutionStatus.TIMEOUT: []     # Terminal state
}

def transition_state(execution, new_status):
    """Validate and perform state transition"""
    current_status = execution.status
    
    if new_status not in VALID_TRANSITIONS[current_status]:
        raise InvalidStateTransition(
            f"Cannot transition from {current_status} to {new_status}"
        )
    
    execution.status = new_status
    
    # Update timestamps
    if new_status == ExecutionStatus.RUNNING:
        execution.started_at = datetime.utcnow()
    elif new_status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT]:
        execution.finished_at = datetime.utcnow()
    
    db.session.commit()
```

---

### 2.2 Idempotency Handling

#### **Prevent Duplicate Execution Runs**

**Problem:** User accidentally clicks "Run" button multiple times

**Solution 1: Client-side prevention (UI state)**
```javascript
// Disable button after first click
let isExecuting = false;

async function runCode() {
  if (isExecuting) {
    return;  // Prevent duplicate submission
  }
  
  isExecuting = true;
  document.getElementById('runButton').disabled = true;
  
  try {
    const response = await fetch('/code-sessions/123/run', {method: 'POST'});
    const data = await response.json();
    pollExecution(data.execution_id);
  } finally {
    isExecuting = false;
    document.getElementById('runButton').disabled = false;
  }
}
```

**Solution 2: Backend idempotency (database constraint)**
```python
# app/services/code_execution_service.py

def execute_code(session_id):
    """Execute code with duplicate prevention"""
    
    # Check for recent pending executions (last 5 seconds)
    recent_pending = Execution.query.filter(
        Execution.session_id == session_id,
        Execution.status.in_(['QUEUED', 'RUNNING']),
        Execution.queued_at >= datetime.utcnow() - timedelta(seconds=5)
    ).first()
    
    if recent_pending:
        # Return existing execution instead of creating duplicate
        logger.warning(f"Duplicate execution prevented for session {session_id}")
        return {
            "execution_id": str(recent_pending.id),
            "status": recent_pending.status,
            "message": "Execution already in progress"
        }
    
    # No pending execution, create new one
    execution = Execution(session_id=session_id, status='QUEUED')
    db.session.add(execution)
    db.session.commit()
    
    execute_code_task.delay(str(execution.id), ...)
    return {"execution_id": str(execution.id), "status": "QUEUED"}
```

**Solution 3: Idempotency key (enterprise approach)**
```python
# Client includes unique idempotency key
POST /code-sessions/123/run
Headers:
  Idempotency-Key: client-generated-uuid-456

# Server checks if request with this key was processed
def execute_code_idempotent(session_id, idempotency_key):
    # Check cache for previous response
    cached_response = redis.get(f"idempotency:{idempotency_key}")
    if cached_response:
        return json.loads(cached_response)  # Return same response
    
    # Process request
    response = execute_code(session_id)
    
    # Cache response for 24 hours
    redis.setex(
        f"idempotency:{idempotency_key}",
        86400,  # 24 hours
        json.dumps(response)
    )
    
    return response
```

#### **Safe Reprocessing of Jobs**

**Problem:** Worker crashes mid-execution, task needs reprocessing

**Solution: Celery's acknowledgment mechanism**

```python
# app/celery_app.py
celery = Celery(
    'livecode_execution',
    broker='redis://localhost:6379/0',
    task_acks_late=True,  # Only acknowledge after task completes
    task_reject_on_worker_lost=True  # Re-queue if worker crashes
)

@celery.task(
    bind=True,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def execute_code_task(self, execution_id, language, source_code):
    try:
        # Execute code
        result = subprocess.run(...)
        
        # Update database
        execution.status = 'COMPLETED'
        db.session.commit()
        
        # Task successful, Celery acknowledges (removes from queue)
        return result
        
    except Exception as e:
        # Task failed, Celery re-queues for retry
        logger.error(f"Task failed, retrying... (attempt {self.request.retries + 1}/3)")
        
        # Reset state for retry
        execution.status = 'QUEUED'
        execution.started_at = None
        db.session.commit()
        
        raise self.retry(exc=e, countdown=2 ** self.request.retries)
```

**Reprocessing Scenarios:**

1. **Worker crash during execution:**
   ```
   1. Task pops from queue (not acknowledged yet)
   2. Worker starts execution, updates status to RUNNING
   3. Worker crashes (power outage, OOM kill)
   4. Task not acknowledged → Returns to queue
   5. Another worker picks up task
   6. Status reset to QUEUED, execution retried
   ```

2. **Database connection lost:**
   ```
   1. Worker executes code successfully
   2. Attempts to update database (connection timeout)
   3. Celery auto-retries (max 3 times)
   4. On retry, check if execution already completed
   5. If completed, skip re-execution (idempotent)
   ```

3. **Redis connection lost:**
   ```
   1. Task acknowledgment fails
   2. Task remains in queue
   3. When Redis reconnects, task reprocessed
   4. Worker checks execution status before running
   5. If already COMPLETED, skip re-execution
   ```

**Idempotent Execution Check:**
```python
def execute_code_task(execution_id, language, source_code):
    execution = Execution.query.get(execution_id)
    
    # Safety check: Already completed?
    if execution.status in ['COMPLETED', 'FAILED', 'TIMEOUT']:
        logger.warning(f"Execution {execution_id} already finished, skipping")
        return {
            "execution_id": str(execution_id),
            "status": execution.status,
            "reprocessed": False
        }
    
    # Safe to execute
    execution.status = 'RUNNING'
    # ... rest of execution logic
```

---

### 2.3 Failure Handling

#### **Retry Mechanism**

```python
# app/tasks/execution_tasks.py

@celery.task(
    name='execute_code_task',
    bind=True,
    max_retries=3,              # Maximum 3 retry attempts
    retry_backoff=True,         # Exponential backoff
    autoretry_for=(
        ConnectionError,        # Database connection issues
        TimeoutError,           # Database query timeout
        RedisConnectionError    # Redis connectivity issues
    ),
    retry_kwargs={
        'max_retries': 3,
        'countdown': 5  # Base delay (multiplied by 2^retry_count)
    }
)
def execute_code_task(self, execution_id, language, source_code):
    try:
        # Execute code
        result = _execute_python(source_code)
        
        # Update database
        execution = Execution.query.get(execution_id)
        execution.status = 'COMPLETED'
        execution.stdout = result['stdout']
        db.session.commit()
        
    except (ConnectionError, TimeoutError) as e:
        # Transient error, retry with backoff
        logger.error(f"Transient error: {e}, retrying...")
        
        # Exponential backoff: 5s, 10s, 20s
        countdown = 5 * (2 ** self.request.retries)
        
        raise self.retry(exc=e, countdown=countdown)
    
    except SyntaxError as e:
        # Permanent error (user code issue), don't retry
        logger.warning(f"Syntax error in user code: {e}")
        execution.status = 'FAILED'
        execution.stderr = str(e)
        db.session.commit()
    
    except Exception as e:
        # Unexpected error, log and mark as failed
        logger.error(f"Unexpected error: {e}")
        execution.status = 'FAILED'
        execution.stderr = "Internal server error"
        db.session.commit()
```

**Retry Timeline:**
```
Attempt 1: Execute immediately
           ↓ (fails with ConnectionError)
Attempt 2: Retry after 5 seconds (2^0 * 5)
           ↓ (fails with ConnectionError)
Attempt 3: Retry after 10 seconds (2^1 * 5)
           ↓ (fails with ConnectionError)
Attempt 4: Retry after 20 seconds (2^2 * 5)
           ↓ (fails with ConnectionError)
Final:     Mark as FAILED, no more retries
```

#### **Error States**

```python
# app/tasks/execution_tasks.py

def _execute_python(source_code):
    try:
        result = subprocess.run(
            ['python', '-c', source_code],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check exit code
        if result.returncode == 0:
            return {
                'status': 'COMPLETED',
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        else:
            # Non-zero exit code (runtime error)
            return {
                'status': 'FAILED',
                'stdout': result.stdout,
                'stderr': result.stderr
            }
    
    except subprocess.TimeoutExpired:
        # Timeout exceeded (infinite loop)
        return {
            'status': 'TIMEOUT',
            'stdout': '',
            'stderr': 'Execution exceeded 30 second timeout'
        }
    
    except FileNotFoundError:
        # Python not installed (system error)
        return {
            'status': 'FAILED',
            'stdout': '',
            'stderr': 'Python interpreter not found'
        }
    
    except Exception as e:
        # Unexpected error
        return {
            'status': 'FAILED',
            'stdout': '',
            'stderr': f'Internal error: {str(e)}'
        }
```

**Error Classification:**

| Error Type | Status | Retry? | User Message |
|------------|--------|--------|--------------|
| Syntax Error | FAILED | No | `"SyntaxError: invalid syntax"` |
| Runtime Exception | FAILED | No | `"NameError: name 'x' is not defined"` |
| Timeout (30s) | TIMEOUT | No | `"Execution exceeded 30 second timeout"` |
| Database connection | QUEUED | Yes (3x) | (Transparent retry, user sees QUEUED) |
| Worker crash | QUEUED | Yes (requeue) | (Transparent retry) |
| Rate limit | FAILED | No | `"Rate limit exceeded: 10/min"` |
| Execution limit | FAILED | No | `"Execution limit exceeded: 100/session"` |

#### **Dead-Letter Queue / Failed Execution Handling**

**Failed Execution Persistence:**
```python
# All failed executions stored in database
execution.status = 'FAILED'
execution.stderr = error_message
execution.finished_at = datetime.utcnow()
db.session.commit()

# Indexed for analysis
db.Index('idx_failed_executions', 'status', 'finished_at')
```

**Failed Execution Queries:**
```sql
-- Find all failed executions
SELECT * FROM executions WHERE status = 'FAILED' ORDER BY finished_at DESC;

-- Failed executions by error type
SELECT 
  substr(stderr, 1, 50) AS error_type,
  COUNT(*) AS count
FROM executions
WHERE status = 'FAILED'
GROUP BY error_type
ORDER BY count DESC;

-- Sessions with high failure rate
SELECT 
  session_id,
  COUNT(*) FILTER (WHERE status = 'FAILED') * 100.0 / COUNT(*) AS failure_rate
FROM executions
GROUP BY session_id
HAVING failure_rate > 50;
```

**Alerting for Critical Failures:**
```python
# Monitor failed executions
def check_failure_rate():
    total = Execution.query.count()
    failed = Execution.query.filter(Execution.status == 'FAILED').count()
    failure_rate = failed / total * 100
    
    if failure_rate > 10:  # More than 10% failure rate
        alert_ops_team(f"High failure rate: {failure_rate}%")
```

**Manual Retry for Failed Executions:**
```python
# app/routes/execution_api.py

@execution_ns.route('/<string:execution_id>/retry')
class ExecutionRetry(Resource):
    def post(self, execution_id):
        """Manually retry a failed execution"""
        execution = Execution.query.get(execution_id)
        
        if not execution:
            return {'error': 'Execution not found'}, 404
        
        if execution.status not in ['FAILED', 'TIMEOUT']:
            return {'error': 'Only failed/timeout executions can be retried'}, 400
        
        # Reset execution state
        execution.status = 'QUEUED'
        execution.started_at = None
        execution.finished_at = None
        execution.stdout = None
        execution.stderr = None
        db.session.commit()
        
        # Re-queue task
        session = CodeSession.query.get(execution.session_id)
        execute_code_task.delay(str(execution.id), session.language, session.source_code)
        
        return {'execution_id': str(execution.id), 'status': 'QUEUED'}, 200
```

---

## 3. Scalability Considerations

### 3.1 Handling Many Concurrent Live Coding Sessions

#### **Current Capacity (Single Instance)**

| Component | Capacity | Bottleneck |
|-----------|----------|------------|
| **Flask API** | 1000 req/s | CPU (request handling) |
| **PostgreSQL** | 5000 queries/s | I/O (disk writes) |
| **Redis** | 100,000 ops/s | Memory |
| **Celery Worker** | 10 exec/s | CPU (subprocess execution) |

**Limiting Factor:** Celery workers (code execution is CPU-bound)

#### **Horizontal Scaling Strategy**

**1. Scale API Servers:**
```bash
# Load balancer distributes requests across multiple API instances
docker-compose up -d --scale api=5

# Nginx load balancer config
upstream api_backend {
    server api1:5000 weight=1;
    server api2:5000 weight=1;
    server api3:5000 weight=1;
    server api4:5000 weight=1;
    server api5:5000 weight=1;
}
```

**Capacity:** 5000 req/s (5 instances × 1000 req/s)

**2. Scale Celery Workers:**
```bash
# Add more workers for parallel execution
docker-compose up -d --scale celery_worker=20

# Each worker can handle 10 executions/s
# Total capacity: 20 workers × 10 = 200 executions/s
```

**Capacity:** 200 exec/s (20 workers)

**3. Database Connection Pooling:**
```python
# app/config.py
engine = create_engine(
    DATABASE_URL,
    pool_size=20,        # Persistent connections per API instance
    max_overflow=40,     # Additional connections during peak
    pool_recycle=3600,   # Recycle connections hourly
    pool_pre_ping=True   # Validate connections before use
)
```

**Capacity:** 300 concurrent connections (5 API × 20 pool + 20 workers × 5)

#### **Concurrent Session Handling**

**Scenario:** 10,000 concurrent users typing code

```
10,000 users typing simultaneously:
├── Autosave requests: 10,000 PATCH /code-sessions/{id} per 500ms
│   └── Load: 20,000 req/s (needs 20 API instances)
│
├── Database writes: 20,000 UPDATE queries/s
│   └── Bottleneck: PostgreSQL (max 5000 queries/s)
│   └── Solution: Write batching or read replicas
│
└── Run requests: ~100 POST /run per second (1% execute simultaneously)
    └── Queue: 100 tasks/s → Managed by Redis (no bottleneck)
    └── Workers: Need 10 workers (each handles 10 exec/s)
```

**Optimization: Autosave Batching**
```python
# Client-side: Batch multiple autosaves
let pendingUpdate = null;
let updateTimer = null;

function autosave(code) {
    pendingUpdate = code;
    
    clearTimeout(updateTimer);
    updateTimer = setTimeout(() => {
        // Send only the latest version
        fetch(`/code-sessions/${sessionId}`, {
            method: 'PATCH',
            body: JSON.stringify({source_code: pendingUpdate})
        });
    }, 500);  // Debounce: wait 500ms after last keystroke
}
```

**Result:** 20,000 → 2,000 req/s (10x reduction)

---

### 3.2 Horizontal Scaling of Workers

#### **Worker Pool Configuration**

```python
# celery_worker.py
celery = Celery('livecode_execution')

# Worker starts with multiple processes
celery worker \
    --loglevel=info \
    --concurrency=4 \      # 4 processes per worker
    --max-tasks-per-child=100  # Restart process after 100 tasks (prevent memory leaks)
```

**Scaling Workers:**
```bash
# Docker Compose
docker-compose up -d --scale celery_worker=10

# Kubernetes
kubectl scale deployment celery-worker --replicas=20

# AWS Auto Scaling Group
aws autoscaling set-desired-capacity \
    --auto-scaling-group-name celery-workers \
    --desired-capacity 50
```

#### **Worker Distribution (Geographic)**

```
┌───────────────────────────────────────────────────────────┐
│                     Redis (Centralized Queue)              │
│                   redis.example.com:6379                   │
└──────────────────────────┬────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼──────┐   ┌────▼─────┐   ┌─────▼──────┐
    │  US-East   │   │ EU-West  │   │ AP-Southeast│
    │  Workers   │   │ Workers  │   │   Workers   │
    │  (10)      │   │  (10)    │   │   (10)      │
    └────────────┘   └──────────┘   └─────────────┘
```

**Benefits:**
- Low latency (workers close to users)
- High availability (multi-region redundancy)
- Load distribution (regional traffic patterns)

#### **Worker Auto-Scaling (Kubernetes HPA)**

```yaml
# kubernetes/worker-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: celery-worker
  minReplicas: 5
  maxReplicas: 50
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70  # Scale up when CPU > 70%
  - type: External
    external:
      metric:
        name: redis_queue_length
      target:
        type: Value
        value: "100"  # Scale up when queue > 100 tasks
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50  # Increase by 50% at a time
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1  # Decrease by 1 pod at a time
        periodSeconds: 60
```

**Scaling Triggers:**
1. **CPU utilization > 70%:** Add more workers
2. **Queue length > 100:** Add more workers
3. **CPU utilization < 30%:** Remove workers (after 5min stabilization)

---

### 3.3 Queue Backlog Handling

#### **Queue Monitoring**

```python
# app/routes/health_routes.py

@health_ns.route('/queue')
class QueueHealth(Resource):
    def get(self):
        """Get queue statistics"""
        celery = current_app.extensions['celery']
        
        # Inspect queue
        inspect = celery.control.inspect()
        
        # Get queue length from Redis
        redis_client = Redis.from_url(current_app.config['CELERY_BROKER_URL'])
        queue_length = redis_client.llen('celery')  # Length of celery queue
        
        # Get active tasks
        active_tasks = inspect.active()
        total_active = sum(len(tasks) for tasks in active_tasks.values()) if active_tasks else 0
        
        # Get worker count
        stats = inspect.stats()
        worker_count = len(stats) if stats else 0
        
        return {
            'queue_length': queue_length,
            'active_tasks': total_active,
            'worker_count': worker_count,
            'avg_tasks_per_worker': total_active / worker_count if worker_count else 0
        }, 200
```

**Example Response:**
```json
{
  "queue_length": 250,
  "active_tasks": 40,
  "worker_count": 10,
  "avg_tasks_per_worker": 4.0
}
```

#### **Backlog Scenarios**

**Scenario 1: Traffic Spike**
```
Time: 10:00 AM - 1000 execution requests in 10 seconds

Queue State:
├── Before: 0 tasks in queue
├── After:  1000 tasks in queue
├── Workers: 10 workers × 10 exec/s = 100 exec/s capacity
└── Drain time: 1000 tasks ÷ 100 exec/s = 10 seconds

User Experience:
├── First 100 requests: Executed immediately (0-1s wait)
├── Next 900 requests: Queued (1-10s wait)
└── All requests completed within 11 seconds
```

**Scenario 2: Worker Outage**
```
Time: 2:00 PM - 5 workers crash (50% capacity loss)

Queue State:
├── Incoming rate: 100 req/s
├── Processing rate: 50 exec/s (5 workers × 10 exec/s)
├── Deficit: 50 req/s accumulating in queue
└── Queue growth: +50 tasks/second

Auto-scaling Response:
├── 1 minute: Queue length = 3000 tasks
├── HPA triggers: Scale up to 15 workers
├── 2 minutes: Additional workers online
├── 3 minutes: Queue draining at 150 exec/s
└── 5 minutes: Queue cleared, back to normal
```

#### **Backlog Mitigation Strategies**

**1. Priority Queues:**
```python
# app/celery_app.py
celery.conf.task_routes = {
    'execute_code_task': {
        'queue': 'default',
        'priority': 5  # Normal priority
    },
    'execute_code_task_premium': {
        'queue': 'priority',
        'priority': 10  # High priority (premium users)
    }
}

# Start workers with priority queue support
celery worker -Q priority,default -l info
```

**2. Task Expiration (TTL):**
```python
@celery.task(
    expires=300  # Task expires after 5 minutes in queue
)
def execute_code_task(execution_id, language, source_code):
    # If task waits > 5 min in queue, automatically discarded
    pass
```

**3. Queue Length Alerts:**
```python
def check_queue_health():
    queue_length = redis_client.llen('celery')
    
    if queue_length > 1000:
        alert_ops_team(
            severity='WARNING',
            message=f'Queue backlog: {queue_length} tasks'
        )
    
    if queue_length > 5000:
        alert_ops_team(
            severity='CRITICAL',
            message=f'Queue overload: {queue_length} tasks, scale workers immediately'
        )
```

**4. Rate Limiting at API Level:**
```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.headers.get('X-Session-ID'),
    default_limits=["100 per minute"]  # Max 100 executions/min per session
)

@app.route('/code-sessions/<id>/run', methods=['POST'])
@limiter.limit("10 per minute")  # Additional limit for execution endpoint
def run_code(id):
    # If rate limit exceeded, return 429 Too Many Requests
    pass
```

---

### 3.4 Potential Bottlenecks and Mitigation Strategies

#### **Bottleneck 1: Database Write Throughput**

**Problem:**
- PostgreSQL handles ~5000 writes/s
- 10,000 concurrent users autosaving every 500ms = 20,000 writes/s
- **Bottleneck:** Database cannot keep up

**Mitigation Strategies:**

**A. Write-through Cache (Redis):**
```python
# Cache recent autosaves in Redis
def autosave_session(session_id, source_code):
    # 1. Update cache immediately (fast)
    redis.setex(
        f"session:{session_id}:code",
        3600,  # 1 hour TTL
        source_code
    )
    
    # 2. Queue database write (async)
    write_to_db_task.delay(session_id, source_code)
```

**B. Database Read Replicas:**
```python
# app/config.py
SQLALCHEMY_DATABASE_URI = 'postgresql://master:5432/db'
SQLALCHEMY_BINDS = {
    'read_replica': 'postgresql://replica:5432/db'
}

# Read from replica
session = CodeSession.query.options(
    db.bind(db.session.bind.get_bind(mapper=None, clause='read_replica'))
).get(session_id)

# Write to master
session.source_code = new_code
db.session.commit()  # Goes to master
```

**C. Batch Writes:**
```python
# Collect autosaves and flush every 5 seconds
autosave_buffer = []

def autosave_session(session_id, source_code):
    autosave_buffer.append({'session_id': session_id, 'source_code': source_code})
    
    if len(autosave_buffer) >= 100:
        flush_autosaves()

def flush_autosaves():
    # Bulk update (single transaction)
    db.session.bulk_update_mappings(CodeSession, autosave_buffer)
    db.session.commit()
    autosave_buffer.clear()
```

---

#### **Bottleneck 2: Redis Memory**

**Problem:**
- Redis runs in-memory
- 1 million queued tasks × 10KB/task = 10GB memory
- **Bottleneck:** Redis out of memory

**Mitigation Strategies:**

**A. Redis Persistence (Disk Backup):**
```conf
# redis.conf
appendonly yes           # Enable AOF (Append-Only File)
appendfsync everysec     # Flush to disk every second
save 900 1               # Snapshot every 15 minutes if 1+ key changed
maxmemory 8gb            # Limit memory usage
maxmemory-policy allkeys-lru  # Evict least recently used keys
```

**B. Redis Cluster (Horizontal Scaling):**
```
┌────────────────────────────────────────────────────────┐
│              Redis Cluster (Sharded)                    │
├────────────────────────────────────────────────────────┤
│  Shard 1 (0-5460)   │  Shard 2 (5461-10922)  │ Shard 3 (10923-16383) │
│  redis1:6379        │  redis2:6379           │  redis3:6379          │
│  2GB memory         │  2GB memory            │  2GB memory           │
└─────────────────────┴────────────────────────┴───────────────────────┘
Total capacity: 6GB (3 shards × 2GB)
```

**C. Task Compression:**
```python
import zlib
import base64

def compress_task(data):
    json_str = json.dumps(data)
    compressed = zlib.compress(json_str.encode())
    return base64.b64encode(compressed).decode()

def decompress_task(compressed_data):
    decoded = base64.b64decode(compressed_data)
    decompressed = zlib.decompress(decoded)
    return json.loads(decompressed.decode())

# Celery task with compression
@celery.task
def execute_code_task(compressed_payload):
    data = decompress_task(compressed_payload)
    # Process task...
```

---

#### **Bottleneck 3: Worker CPU**

**Problem:**
- Code execution is CPU-intensive
- Single worker maxes out at 10 exec/s
- **Bottleneck:** Worker CPU at 100%

**Mitigation Strategies:**

**A. Vertical Scaling (Larger Instances):**
```yaml
# kubernetes/worker-deployment.yaml
resources:
  requests:
    cpu: "2000m"     # 2 CPU cores
    memory: "4Gi"
  limits:
    cpu: "4000m"     # Up to 4 CPU cores
    memory: "8Gi"
```

**B. Worker Specialization (Language-Specific Workers):**
```bash
# Python worker (optimized for Python execution)
celery worker -Q python_queue -c 10

# JavaScript worker (optimized for Node.js execution)
celery worker -Q javascript_queue -c 10

# C++ worker (optimized for compilation)
celery worker -Q cpp_queue -c 5  # Fewer workers (compilation is slow)
```

**C. Execution Offloading (Serverless):**
```python
# AWS Lambda integration
import boto3

lambda_client = boto3.client('lambda')

def execute_python_lambda(source_code):
    response = lambda_client.invoke(
        FunctionName='code-execution-python',
        InvocationType='RequestResponse',
        Payload=json.dumps({'source_code': source_code})
    )
    return json.loads(response['Payload'].read())
```

**Benefits:**
- Infinite scalability (Lambda auto-scales)
- Pay-per-execution pricing
- No worker management

---

#### **Bottleneck 4: Network Latency**

**Problem:**
- API in US-East, users in Asia = 200ms latency
- **Bottleneck:** User experience degraded

**Mitigation Strategies:**

**A. CDN + Edge Caching:**
```
┌─────────────┐        ┌─────────────┐        ┌─────────────┐
│   CloudFlare│        │   AWS S3    │        │  Origin API │
│     Edge    │───────▶│   (Static)  │───────▶│  (Dynamic)  │
│   (Cached)  │        │             │        │             │
└─────────────┘        └─────────────┘        └─────────────┘
      │
      │ Cache: 
      │ - GET /code-sessions/{id} (1 min TTL)
      │ - GET /executions/{id} (5 sec TTL)
      │
      ▼
   User (Asia)
   Latency: 10ms (cached) vs 200ms (origin)
```

**B. Multi-Region Deployment:**
```
┌──────────────────────────────────────────────────────────┐
│                    Route 53 (Global DNS)                  │
│               Geo-routing / Latency-based routing         │
└────────────────────────┬─────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼──────┐   ┌────▼─────┐   ┌─────▼──────┐
   │  US-East  │   │ EU-West  │   │ AP-Southeast│
   │   Region  │   │  Region  │   │   Region    │
   │           │   │          │   │             │
   │ - API (5) │   │ - API(5) │   │ - API (5)   │
   │ -Worker(10│   │ -Worker10│   │ -Worker(10) │
   │ - Redis   │   │ - Redis  │   │ - Redis     │
   └───────────┘   └──────────┘   └─────────────┘
        │                │                │
        └────────────────┴────────────────┘
                         │
              ┌──────────▼───────────┐
              │   PostgreSQL Global  │
              │   (Multi-region)     │
              │   - Master in US     │
              │   - Read replicas    │
              │     in EU & AP       │
              └──────────────────────┘
```

---

## 4. Trade-offs

### 4.1 Technology Choices and Why

#### **Flask vs FastAPI vs Django**

**Chosen:** Flask

**Reasoning:**
| Criteria | Flask | FastAPI | Django |
|----------|-------|---------|--------|
| **Simplicity** | ✅ Minimal boilerplate | ⚠️ More complex | ❌ Heavy framework |
| **Async Support** | ⚠️ Requires extensions | ✅ Native async/await | ❌ Limited async |
| **Learning Curve** | ✅ Easy to learn | ⚠️ Medium | ❌ Steep |
| **Documentation** | ✅ Excellent (Flask-RESTX) | ✅ Auto-generated | ⚠️ ORM-focused |
| **Ecosystem** | ✅ Mature (15+ years) | ⚠️ Newer (4 years) | ✅ Mature |
| **Performance** | ⚠️ Good (not best) | ✅ Fastest | ❌ Slower |

**Decision:** Flask for simplicity + ecosystem maturity. Async handled by Celery (not needed in API layer).

---

#### **PostgreSQL vs MongoDB vs MySQL**

**Chosen:** PostgreSQL

**Reasoning:**
| Criteria | PostgreSQL | MongoDB | MySQL |
|----------|------------|---------|-------|
| **ACID Compliance** | ✅ Full ACID | ❌ Limited | ✅ Full ACID |
| **Relationships** | ✅ Foreign keys | ❌ Manual | ✅ Foreign keys |
| **JSON Support** | ✅ JSONB type | ✅ Native | ⚠️ Limited |
| **Scalability** | ⚠️ Vertical first | ✅ Horizontal | ⚠️ Vertical first |
| **Maturity** | ✅ 30+ years | ⚠️ 15 years | ✅ 25+ years |
| **Advanced Features** | ✅ Excellent (full-text search, GIS) | ⚠️ Limited | ⚠️ Limited |

**Decision:** PostgreSQL for:
- ACID guarantees (execution tracking requires consistency)
- Foreign key constraints (sessions → executions)
- Rich query capabilities (analytics on execution data)

---

#### **Celery vs RQ vs Dramatiq**

**Chosen:** Celery

**Reasoning:**
| Criteria | Celery | RQ | Dramatiq |
|----------|--------|----|---------  |
| **Maturity** | ✅ 14+ years | ⚠️ 11 years | ⚠️ 6 years |
| **Features** | ✅ Rich (retry, routing, schedules) | ⚠️ Basic | ✅ Good |
| **Monitoring** | ✅ Flower (web UI) | ⚠️ Limited | ⚠️ Basic |
| **Broker Support** | ✅ Redis, RabbitMQ, SQS | ⚠️ Redis only | ✅ Redis, RabbitMQ |
| **Community** | ✅ Largest | ⚠️ Smaller | ⚠️ Smallest |
| **Learning Curve** | ⚠️ Steeper | ✅ Easy | ✅ Easy |

**Decision:** Celery for:
- Industry standard (most production-ready)
- Advanced retry mechanisms (critical for reliability)
- Flower monitoring (observability)

---

### 4.2 What We Optimized For

#### **Speed vs Reliability vs Simplicity**

**Optimization Priority: Reliability > Simplicity > Speed**

**Reliability (Highest Priority):**
- ✅ Celery retry mechanism (max 3 retries, exponential backoff)
- ✅ PostgreSQL ACID transactions (data consistency)
- ✅ Task acknowledgment (prevent task loss)
- ✅ Comprehensive logging (debugging production issues)
- ✅ Multiple safety mechanisms (timeout, output limits, rate limiting)

**Simplicity (Medium Priority):**
- ✅ Flask (minimalist framework, easy to understand)
- ✅ Subprocess execution (no Docker complexity for MVP)
- ✅ Single codebase (monolith, not microservices)
- ✅ Environment variables (simple configuration)
- ✅ Docker Compose (one-command deployment)

**Speed (Lower Priority):**
- ⚠️ Polling instead of WebSockets (simpler, but higher latency)
- ⚠️ Subprocess instead of Docker (faster startup, less secure)
- ⚠️ No caching layer (simpler architecture, more database load)
- ⚠️ Synchronous database writes (simpler code, slower autosave)

**Trade-off Example:**
```python
# Speed-optimized (not chosen):
@app.route('/code-sessions/<id>/run')
def run_code_fast(id):
    result = subprocess.run(['python', '-c', code], timeout=30)
    return {'stdout': result.stdout}  # Fast, but blocks API

# Reliability-optimized (chosen):
@app.route('/code-sessions/<id>/run')
def run_code_reliable(id):
    execution = Execution(status='QUEUED')
    db.session.add(execution)
    db.session.commit()  # Persisted before execution
    
    execute_code_task.delay(...)  # Async with retry
    return {'execution_id': execution.id}  # Non-blocking
```

---

### 4.3 Production Readiness Gaps

#### **Gap 1: Docker Container Isolation**

**Current:** Subprocess isolation (same OS, shared resources)

**Production Need:** Docker container per execution

```python
# Current (MVP)
result = subprocess.run(['python', '-c', code], timeout=30)

# Production-ready
docker_client = docker.from_env()
container = docker_client.containers.run(
    image='python:3.11-slim',
    command=['python', '-c', code],
    mem_limit='128m',
    cpu_quota=50000,
    network_mode='none',  # No network access
    read_only=True,       # Read-only filesystem
    remove=True,          # Auto-remove after execution
    timeout=30
)
```

**Impact:** Security (prevent file system access, network calls)

---

#### **Gap 2: Authentication & Authorization**

**Current:** No authentication (open API)

**Production Need:** JWT token-based authentication

```python
# Current (MVP)
@app.route('/code-sessions', methods=['POST'])
def create_session():
    # Anyone can create sessions
    session = CodeSession(...)
    return {'session_id': session.id}

# Production-ready
from flask_jwt_extended import jwt_required, get_jwt_identity

@app.route('/code-sessions', methods=['POST'])
@jwt_required()  # Requires valid JWT token
def create_session():
    user_id = get_jwt_identity()  # Extract user from token
    
    session = CodeSession(
        user_id=user_id,  # Track ownership
        ...
    )
    return {'session_id': session.id}
```

**Impact:** Security (prevent unauthorized access, track usage per user)

---

#### **Gap 3: Comprehensive Testing**

**Current:** No automated tests

**Production Need:** 80%+ code coverage

```bash
# Unit tests
tests/unit/
├── test_code_execution_service.py
├── test_execution_tasks.py
└── test_models.py

# Integration tests
tests/integration/
├── test_session_api.py
├── test_execution_api.py
└── test_health_endpoints.py

# Load tests
tests/load/
└── test_api_load.py  # Locust: 10,000 concurrent users

# Run tests
pytest --cov=app --cov-report=html
```

**Impact:** Confidence in deployments, catch regressions

---

#### **Gap 4: Monitoring & Alerting**

**Current:** Basic logging (stdout)

**Production Need:** Prometheus + Grafana + PagerDuty

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

execution_duration = Histogram(
    'execution_duration_seconds',
    'Time to execute code',
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0]
)

execution_status = Counter(
    'execution_status_total',
    'Execution outcomes',
    ['status']  # COMPLETED, FAILED, TIMEOUT
)

queue_length = Gauge(
    'queue_length',
    'Number of pending tasks'
)

# Usage
@execution_duration.time()
def execute_code():
    # ... execution logic
    execution_status.labels(status='COMPLETED').inc()
```

**Grafana Dashboard:**
- Execution latency (p50, p95, p99)
- Failure rate
- Queue backlog
- Worker utilization

**Alerts:**
- Failure rate > 10% (WARNING)
- Queue length > 1000 (WARNING)
- Queue length > 5000 (CRITICAL)
- No workers online (CRITICAL)

**Impact:** Observability (detect issues before users complain)

---

#### **Gap 5: WebSocket Support**

**Current:** HTTP polling (1-2s latency)

**Production Need:** WebSocket for real-time updates

```python
# Flask-SocketIO
from flask_socketio import SocketIO, emit

socketio = SocketIO(app)

@socketio.on('subscribe_execution')
def subscribe(data):
    execution_id = data['execution_id']
    # Client subscribes to execution updates
    join_room(execution_id)

# Worker emits updates
def execute_code_task(execution_id, ...):
    execution.status = 'RUNNING'
    socketio.emit('execution_update', {
        'status': 'RUNNING',
        'started_at': execution.started_at
    }, room=execution_id)
    
    # Execute code...
    
    execution.status = 'COMPLETED'
    socketio.emit('execution_update', {
        'status': 'COMPLETED',
        'stdout': execution.stdout
    }, room=execution_id)
```

**Impact:** User experience (instant feedback vs polling delay)

---

#### **Gap 6: Idempotency Keys**

**Current:** No idempotency protection

**Production Need:** Idempotency keys for duplicate prevention

```python
# Client includes idempotency key
POST /code-sessions/123/run
Headers:
  Idempotency-Key: client-uuid-456

# Server deduplicates
@app.route('/code-sessions/<id>/run', methods=['POST'])
def run_code(id):
    idempotency_key = request.headers.get('Idempotency-Key')
    
    # Check if request already processed
    cached = redis.get(f"idempotency:{idempotency_key}")
    if cached:
        return json.loads(cached)  # Return cached response
    
    # Process request
    response = execute_code(id)
    
    # Cache response for 24 hours
    redis.setex(f"idempotency:{idempotency_key}", 86400, json.dumps(response))
    
    return response
```

**Impact:** Reliability (prevent duplicate executions from double-clicks)

---

#### **Gap 7: Database Backups & Disaster Recovery**

**Current:** No automated backups

**Production Need:** Daily backups + point-in-time recovery

```bash
# PostgreSQL continuous archiving
# postgresql.conf
archive_mode = on
archive_command = 'aws s3 cp %p s3://backups/wal/%f'

# Daily backup script
pg_dump livecode_platform | gzip | aws s3 cp - s3://backups/daily/$(date +%Y%m%d).sql.gz

# Restore from backup
aws s3 cp s3://backups/daily/20260121.sql.gz - | gunzip | psql livecode_platform
```

**Impact:** Business continuity (recover from data loss)

---

## Summary

### Architecture Highlights
- **Asynchronous execution** with Celery + Redis queue
- **Non-blocking API** (returns 202 Accepted immediately)
- **Reliable execution** with retry mechanism and state tracking
- **Horizontal scalability** (API servers, workers, database replicas)
- **Safety mechanisms** (timeout, output limits, rate limiting, execution limits)

### Design Philosophy
1. **Reliability over speed** - Chose tools/patterns that prevent data loss
2. **Simplicity over features** - MVP with clear upgrade path to production
3. **Observability** - Comprehensive logging at every stage
4. **Fault tolerance** - Retry mechanisms, graceful error handling
5. **Scalability** - Designed for horizontal scaling from day one

### Production Readiness
- ✅ **MVP Complete:** Functional system with core features
- ⚠️ **Production Gaps:** Docker isolation, authentication, monitoring, testing
- 📈 **Upgrade Path:** Clear roadmap for production deployment

### Key Trade-offs
- **Polling vs WebSockets:** Chose polling for simplicity (1-2s latency acceptable for MVP)
- **Subprocess vs Docker:** Chose subprocess for faster development (Docker planned for production)
- **Monolith vs Microservices:** Chose monolith for simplicity (can split later)
- **Sync writes vs Caching:** Chose sync writes for data consistency (caching planned for scale)

This design document provides a comprehensive view of the architecture, reliability mechanisms, scalability considerations, and trade-offs made during development.
