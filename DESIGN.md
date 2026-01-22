# LiveCode Execution API - Design Document

## Table of Contents

1. [General Architecture](#1-general-architecture)
2. [Detailed Architecture & Request Flows](#2-detailed-architecture--request-flows)
3. [Reliability & Data Model](#3-reliability--data-model)
4. [Scalability Considerations](#4-scalability-considerations)
5. [Trade-offs](#5-trade-offs)

---

## 1. General Architecture

### 1.1 Complete System Architecture

The LiveCode Execution API is a **distributed, asynchronous code execution platform** that allows users to write, save, and execute code in multiple programming languages (Python, JavaScript, C++) through a RESTful API.

#### **Complete Architecture Diagram**

<div align="center">
  <img src="./docs/images/z7457077336734_932ee50b286ba2785462344479ee1947.jpg" alt="LiveCode Execution API - Complete System Architecture" width="1200">
  
  *Figure 1.1: Complete system architecture showing client layer, Flask API layer, PostgreSQL database, Redis message queue, Celery worker layer, and code execution environments with detailed data flow and safety mechanisms*
</div>

---

### 1.2 Architecture Overview

#### **DATA FLOW:**

1. **Client → API:** POST `/code-sessions` → Create session in PostgreSQL → Return `session_id`
2. **Client → API:** PATCH `/code-sessions/{id}` → Update source_code → Autosave
3. **Client → API:** POST `/code-sessions/{id}/run` → Create execution (QUEUED) → Push to Redis
4. **Worker ← Redis:** Pull task → Update status (RUNNING) → Execute subprocess
5. **Worker → PostgreSQL:** Update execution (COMPLETED) with stdout/stderr
6. **Client → API:** GET `/executions/{id}` (polling) → Return results when COMPLETED

#### **EXECUTION STATES:**

```
QUEUED (waiting in Redis) → RUNNING (worker executing) → COMPLETED/FAILED/TIMEOUT (done)
```

#### **KEY FEATURES:**

- ✓ **Asynchronous** - Non-blocking API with background workers
- ✓ **Persistent** - PostgreSQL stores all sessions/executions
- ✓ **Scalable** - Horizontal worker scaling, queue-based architecture
- ✓ **Reliable** - Retry mechanism, state tracking, comprehensive logging
- ✓ **Safe** - Timeout, output limits, rate limiting, process isolation

#### **SAFETY MECHANISMS:**

- **30-second timeout** - Kills infinite loops automatically
- **100KB output limit** - Prevents memory bombs
- **Rate limiting** - 10 executions/minute per session
- **Execution limit** - Maximum 100 executions per session
- **Process isolation** - Each execution runs in separate subprocess

