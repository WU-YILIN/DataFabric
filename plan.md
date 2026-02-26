# Project: Genesis-Tracking V2.0 (Enterprise Edition) - Master Development Plan

## 1. Executive Summary & Role Definition
*   **Role**: Staff Software Engineer / Lead Architect.
*   **Objective**: Build a production-ready **Data Contract Sentinel System**. It must support high concurrency, horizontal scaling, audit logging, and asynchronous processing.
*   **Constraint**: No "Hello World" code. All implementations must follow **SOLID principles**, utilize **Dependency Injection**, and include **Error Handling**.

## 2. Technology Stack & Standards
*   **Core**: Python 3.11+ (AsyncIO).
*   **Web Framework**: FastAPI (with Middleware for CORS, Auth, Correlation IDs).
*   **Database (OLTP)**: PostgreSQL 15+ (Asyncpg + SQLAlchemy 2.0).
*   **Vector Database**: Qdrant (Cluster mode ready).
*   **Cache & Queue**: Redis 7.0 (for Caching + Celery Broker).
*   **Task Queue**: Celery (for async ingestion & heavy analysis).
*   **Search Engine**: Hybrid (Dense Vector + BM25/Sparse).
*   **LLM Orchestration**: OpenAI SDK + `Instructor` (for patched Pydantic validation) or LangChain (LCEL).
*   **Observability**: Structlog (JSON logs), Prometheus (Metrics), OpenTelemetry (Tracing).
*   **Package Manager**: Poetry.

## 3. Directory Structure (Domain-Driven Design)
Enforce this strict structure to ensure separation of concerns:

```text
genesis_backend/
├── pyproject.toml
├── docker-compose.yml
├── alembic.ini
├── src/
│   ├── app.py                  # ASGI entry point
│   ├── config.py               # Pydantic Settings (Env vars)
│   ├── container.py            # Dependency Injection Container
│   ├── api/                    # Presentation Layer
│   │   ├── v1/
│   │   │   ├── endpoints/      # Routes
│   │   │   └── dependencies.py # API Dependencies (Auth, RateLimit)
│   │   └── middlewares/        # Error handling, Context, Timing
│   ├── domain/                 # Business Logic Layer (Pure Python)
│   │   ├── events/             # Event entities
│   │   ├── patterns/           # Pattern logic
│   │   ├── search/             # Search abstractions
│   │   └── governance/         # Arbitration logic
│   ├── infrastructure/         # External Interfaces (DB, LLM, Redis)
│   │   ├── database/           # SQLAlchemy models & session
│   │   ├── vector_store/       # Qdrant implementation
│   │   ├── llm/                # OpenAI/Claude Adapter
│   │   └── cache/              # Redis Adapter
│   ├── worker/                 # Celery Tasks
│   │   ├── celery_app.py
│   │   └── tasks/
│   └── utils/                  # Logger, Helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── scripts/
```

---

## 4. Execution Phases (Prompt-to-Code Instructions)

**Instruction to Agent**: Execute strictly phase by phase. Do not hallucinate simplification.

### Phase 0: Infrastructure & Scaffolding
**Goal**: Establish the runtime environment and base configuration.
1.  **Dependency Management**: Initialize `pyproject.toml` with `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `asyncpg`, `qdrant-client`, `redis`, `celery`, `structlog`, `pydantic-settings`, `openai`, `tenacity`.
2.  **Containerization**: Create `docker-compose.yml` containing:
    *   `postgres`: Healthcheck enabled, volume persistent.
    *   `qdrant`: Healthcheck enabled.
    *   `redis`: Alpine version.
    *   `jaeger`: For tracing (optional but recommended for enterprise).
3.  **Configuration**: Implement `src/config.py` using `BaseSettings`. Load DB_URL, REDIS_URL, OPENAI_KEY, ENVIRONMENT (dev/prod).
4.  **Logging**: Setup `src/utils/logger.py` using `structlog`. Ensure logs are JSON formatted in production and colored in development.
5.  **Database**: Setup `src/infrastructure/database/session.py` with an async session factory. Initialize Alembic.

### Phase 1: Core Domain Modeling (The "Truth")
**Goal**: Define the Data Governance Schema (Relational).
1.  **Models**: Create SQLAlchemy models in `src/infrastructure/database/models/`:
    *   `AuditLog`: `id`, `user_id`, `action`, `entity_type`, `entity_id`, `timestamp` (Crucial for enterprise).
    *   `Project`: `id`, `name`, `api_key` (hashed), `tech_stack` (JSON).
    *   `EventPattern`: `id`, `template` (e.g., `evt_{action}_{obj}`), `domain`, `is_active`.
    *   `TrackingEvent`: `id`, `code` (unique), `name`, `description`, `properties` (JSON Schema), `domain`, `status`, `version`, `project_id`.
2.  **Migrations**: Generate initial Alembic migration (`alembic revision --autogenerate`) and apply it.
3.  **Repositories**: Implement the Repository Pattern (Generic + Specific) to decouple API from DB logic.
    *   `BaseRepository`: CRUD operations.
    *   `EventRepository`: Specialized queries (e.g., find by domain).

### Phase 2: Hybrid Search Engine (The "Eyes")
**Goal**: High-performance retrieval system.
1.  **Vector Store**: Implement `QdrantClient` wrapper in `src/infrastructure/vector_store/`.
    *   Method `upsert_event(event_id, vector, payload)`.
    *   Method `search_similar(vector, limit, threshold)`.
2.  **Keyword Search (Enterprise)**:
    *   Since we are not using Elasticsearch yet, implement a **BM25 In-Memory Cache with Redis persistence**.
    *   Or leverage Qdrant's payload full-text search index if relying on 1.7+ features. *Decision: Use Qdrant's sparse vector support or payload search for simplicity in maintenance.*
3.  **Hybrid Logic**: Implement `src/domain/search/engine.py`.
    *   **Strategy**: Retrieve Top 50 Dense + Retrieve Top 50 Sparse/Keyword.
    *   **Algorithm**: Implement **RRF (Reciprocal Rank Fusion)** to merge two lists into one ranked list.
4.  **Sync Mechanism**: Implement a listener or hook: When a `TrackingEvent` is created/updated in PG, it must asynchronously update Qdrant.

### Phase 3: The Semantic Brain (LLM Layer)
**Goal**: Robust, retry-safe reasoning.
1.  **Prompt Management**: Do not hardcode strings. Create `src/domain/governance/prompts.py` using **Jinja2** templates for dynamic context injection.
2.  **LLM Adapter**: Create `src/infrastructure/llm/client.py`.
    *   Use `tenacity` library for exponential backoff retries (rate limit handling).
    *   Implement **Circuit Breaker**: If OpenAI fails 5 times, switch to a fallback (or fail gracefully).
3.  **Structured Output**: Use `Pydantic` models to define `ArbitrationResponse` (verdict, score, reasoning).
    *   Use OpenAI's "Function Calling" or "JSON Mode" to guarantee 100% schema compliance.

### Phase 4: API & Security Layer
**Goal**: Production-ready HTTP interface.
1.  **Middleware**:
    *   `CorrelationIdMiddleware`: Attach a UUID to every request log.
    *   `ProcessTimeMiddleware`: Log duration of requests.
2.  **Authentication**: Implement **API Key Auth** (Header `X-API-KEY`). Validate against `Project` table.
3.  **Endpoints (`src/api/v1/`)**:
    *   `POST /governance/check`: The main entry point.
        *   Validates Request Body -> Hybrid Search -> LLM Arbitrate -> Audit Log -> Response.
    *   `POST /events`: Register new event.
        *   Includes strictly typed `properties` schema validation.
    *   `GET /health`: Deep health check (ping DB, Redis, Qdrant).
4.  **Exception Handling**: Implement a global exception handler in `src/main.py`. Catch `DomainException`, `InfraException`, and return standardized JSON error codes (RFC 7807).

### Phase 5: Async Workers (Scalability)
**Goal**: Offload heavy tasks.
1.  **Celery Setup**: Configure `src/worker/celery_app.py` connecting to Redis.
2.  **Task: Code Scanning**:
    *   Create a task `scan_repository_for_events(repo_url, branch)`.
    *   This task pulls code, uses Regex/AST (Abstract Syntax Tree) to find `tracker.log()`, and cross-checks with the DB.
3.  **Task: Batch Ingestion**:
    *   Task `ingest_csv_batch(file_path)`: Process 10,000 row CSV uploads for legacy data migration without blocking the API.

### Phase 6: Testing & Quality Assurance
**Goal**: Ensure reliability.
1.  **Fixtures**: Create `tests/conftest.py` with `async_client`, `test_db_session` (rollback transaction after each test).
2.  **Unit Tests**: Test `RRF` algorithm, `LLM` output parsing (with mocks), `Pydantic` validation.
3.  **Integration Tests**: Test the `/check` endpoint. Ensure data actually flows to DB and Qdrant mock.
4.  **Linting**: Add configuration for `ruff` (linter) and `mypy` (type checker) in `pyproject.toml`.

---

## 5. Development Prompt Sequence (For Agent)

You can feed these prompts one by one to your Code Agent.

**Prompt 1 (Setup)**:
> "Act as a Senior Python Architect. Initialize the `genesis_backend` project following the Domain-Driven Design directory structure specified in the plan. Setup Poetry, Docker Compose (PG, Redis, Qdrant), and the basic FastAPI app with structlog configuration. Do not implement business logic yet. just infrastructure."

**Prompt 2 (Database)**:
> "Now implement the Database layer. Create the SQLAlchemy models for `Project`, `TrackingEvent`, and `EventPattern` as defined in Phase 1. Setup Alembic and create the initial migration script. Ensure all models have `repr` methods and standard timestamps."

**Prompt 3 (Search Engine)**:
> "Implement the Hybrid Search Engine (Phase 2). Create the Qdrant adapter. Implement the Reciprocal Rank Fusion (RRF) algorithm in pure Python under `src/domain/search/`. Create a service that accepts a query string and returns a ranked list of similar events using both Vector and Keyword simulation."

**Prompt 4 (LLM & Logic)**:
> "Implement the Semantic Arbitrator (Phase 3). Create the LLM client with Tenacity retries. Use Jinja2 for prompts. Define the `ArbitrationResponse` Pydantic model. Connect the Search Engine results to the LLM prompt context to generate a governance verdict."

**Prompt 5 (API & Async)**:
> "Expose the logic via FastAPI endpoints (Phase 4). Implement API Key authentication. Then, setup Celery with Redis (Phase 5) and create a background task that simulates scanning a code snippet for unregistered events."

---
