# Flowcharts

## End-to-End Processing Flow

```mermaid
flowchart TD
    A[Service Startup] --> B[Load .env]
    B --> C[Configure Logging]
    C --> D[Run Preflight with db_ping]
    D -->|fail| X[Exit non-zero]
    D -->|ok| E[Start Service Loop]

    E --> SIG{SIGTERM received?}
    SIG -->|yes| STOP[Log shutdown and exit cleanly]
    SIG -->|no| F[MessageSource.iter_messages]

    F --> G[Receive IncomingMessage]
    G --> H[MessageSource.parse_event to AIEvent]

    H --> FILT{should_evaluate?}
    FILT -->|no| FSKIP[Log filter-skipped and continue]
    FSKIP --> E

    FILT -->|yes| J[ResultStore.claim_event by event_id]
    J --> K{Claimed?}
    K -->|no| L[Log duplicate and continue]
    L --> E

    K -->|yes| M[pipeline.process_event to evaluation dict]

    M --> SOF{STORE_ONLY_FAILS and success?}
    SOF -->|yes| REL[ResultStore.release_claim and log skipped]
    REL --> E

    SOF -->|no| Q[Log evaluation results]
    Q --> R[ResultStore.mark_done]
    R --> S[Log stored]
    S --> E

    H -->|parse error| T[ResultStore.mark_error with fallback ingest_id]
    M -->|pipeline or store error| T
    T --> U[Log error and continue]
    U --> E
```

## Claim-First Idempotency Flow

```mermaid
flowchart LR
    A[Incoming AIEvent] --> B[ResultStore.claim_event computes deterministic event_id]
    B --> C[Atomic upsert with status=processing]
    C --> D{Claimed successfully?}
    D -->|yes| E[This worker owns event]
    E --> F[Proceed to evaluation and persistence]

    D -->|no| G[Already claimed or processed]
    G --> H[Skip expensive evaluation]
```

## Source-Agnostic Service Lifecycle

```mermaid
flowchart TD
    A[Process start] --> B[main.py]
    B --> C[preflight.py - db_ping callable]
    C -->|ok| D[service.py run_service]
    C -->|fail| E[Exit 1]

    subgraph Ingestion Boundary MessageSource protocol
      F1[FixtureMessageSource - MVP]
      F2[KafkaMessageSource - production fork]
    end

    subgraph Persistence Boundary ResultStore protocol
      S1[MongoResultStore - MVP]
      S2[CosmosDBResultStore - production fork]
    end

    F1 --> G[iter_messages]
    F2 --> G

    D --> G
    G --> H[process_message]
    H --> I[parse_event]
    I --> FIL[filtering.should_evaluate]
    FIL -->|pass| J[ResultStore.claim_event]
    J --> K[pipeline.process_event]
    K --> L[eval.py]
    L --> M[deepeval metrics - sync no asyncio]
    M --> N[ResultStore.mark_done / mark_error]
    FIL -->|reject| SKIP[log skipped]
```
