# Flowcharts

## End-to-End Processing Flow

```mermaid
flowchart TD
    A[Service Startup] --> B[Load .env]
    B --> C[Configure Logging]
    C --> D[Run Preflight]
    D -->|fail| X[Exit non-zero]
    D -->|ok| E[Start Service Loop]

    E --> F[get_message.iter_incoming_messages]
    F --> G[Receive IncomingMessage]
    G --> H[parse_incoming_event to AIEvent]

    H --> J[Claim event in Mongo by event_id]
    J --> K{Claimed?}
    K -->|no| L[Log duplicate and skip]
    L --> F

    K -->|yes| M[Run filtering and evaluation pipeline]
    M --> N{Result is None?}
    N -->|yes| O[Mark skipped in Mongo]
    O --> P[Log skipped]
    P --> F

    N -->|no| Q[Print evaluation results]
    Q --> R[Mark done in Mongo]
    R --> S[Log stored]
    S --> F

    H -->|parse error| T[Mark error in Mongo]
    M -->|pipeline/store error| T
    T --> U[Log error and continue]
    U --> F
```

## Claim-First Idempotency Flow

```mermaid
flowchart LR
    A[Incoming AIEvent] --> B[Compute deterministic event_id]
    B --> C[Mongo upsert with $setOnInsert status=processing]
    C --> D{upserted_id present?}
    D -->|yes| E[This worker owns event]
    E --> F[Proceed to pipeline and persistence]

    D -->|no| G[Already claimed or processed]
    G --> H[Skip expensive evaluation]
```

## Source-Agnostic Service Lifecycle

```mermaid
flowchart TD
    A[Process start] --> B[main.py]
    B --> C[preflight.py]
    C -->|ok| D[service.py run_service]
    C -->|fail| E[Exit 1]

    subgraph Ingestion Boundary get_message.py
      F1[fixture mode]
      F2[kafka mode]
    end

    F1 --> G[iter_incoming_messages]
    F2 --> G

    D --> G
    G --> H[process_message]
    H --> I[process_incoming_event]
    I --> J[store_mongo claim and status writes]
    I --> K[pipeline process_event]
    K --> L[eval.py]
    L --> M[deepeval backend]
```
