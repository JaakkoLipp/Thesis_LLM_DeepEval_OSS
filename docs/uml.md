# UML Design Artifacts

## Class Diagram (Core Modules)

```mermaid
classDiagram
    class EnvUtils {
      +env_bool(name, default) bool
      +env_float(name, default) float
      +env_int(name, default) int
      +env_csv(name, default_csv) list
    }

    class IncomingMessage {
      +raw: bytes
      +kafka: dict
      +source_id: str
    }

    class AIEvent {
      +system: str
      +event_type: str
      +user_input: str
      +context: str
      +output: str
      +raw_meta: dict
    }

    class MessageAdapter {
      +iter_incoming_messages(poll_seconds, max_cycles) Iterator
      +parse_incoming_event(message) AIEvent
    }

    class Filtering {
      +allowed_systems() set
      +allowed_event_types() set
      +should_evaluate(system, event_type) bool
    }

    class Service {
      +run_service(poll_seconds, max_cycles) int
      +process_message(message, store, owner_id, run_mode, store_only_fails) str
      +process_incoming_event(event, store, owner_id, run_mode, store_only_fails) str
      +resolve_owner_id() str
      -_fallback_error_id(message) str
      -_print_results(results) None
      -_install_signal_handlers() Any
      -_restore_signal_handlers(prev) None
    }

    class Pipeline {
      +process_event(event) dict
    }

    class Eval {
      +eval_function(user_input, context, output) dict
      -_get_judge() Any
      -_build_metrics(judge) list
      -_run_metric(m, test_case, name_override) dict
      -_call_ollama(prompt, stream) tuple
      -_get_system_prompt() str
      -_clean(text) str
    }

    class MongoResultStore {
      +compute_event_id(event) str
      +exists(event_id) bool
      +claim_event(event, owner_id) tuple
      +release_claim(event_id) None
      +mark_done(event_id, event, evaluation) None
      +mark_skipped(event_id, event) None
      +mark_error(event_id, error_type, error_message) None
      +get_owner(event_id) str
    }

    class Preflight {
      +run_preflight(logger) bool
    }

    class LoggingUtils {
      +configure_logging() None
      +get_logger(run_mode) LoggerAdapter
      +event_log_context(event, event_id) dict
    }

    class Main {
      +build_parser() ArgumentParser
      +cmd_run(poll_seconds, max_cycles) int
      +main() int
    }

    Main --> Preflight
    Main --> LoggingUtils
    Main --> Service

    MessageAdapter --> IncomingMessage
    MessageAdapter --> AIEvent

    Service --> MessageAdapter
    Service --> Filtering
    Service --> Pipeline
    Service --> MongoResultStore
    Service --> LoggingUtils

    Pipeline --> Eval
    Pipeline --> AIEvent

    Filtering --> EnvUtils
    Eval --> EnvUtils
    MongoResultStore --> AIEvent
    MongoResultStore --> EnvUtils
```

## Sequence Diagram (Single Event)

```mermaid
sequenceDiagram
    participant S as service.py
    participant GM as get_message.py
    participant F as filtering.py
    participant DB as store_mongo.py
    participant P as pipeline.py
    participant E as eval.py

    S->>GM: iter_incoming_messages()
    GM-->>S: IncomingMessage

    S->>GM: parse_incoming_event(message)
    GM-->>S: AIEvent

    S->>F: should_evaluate(system, event_type)
    alt filtered out
        F-->>S: False
        S->>S: log filter-skipped and continue
    else passes filter
        F-->>S: True

        S->>DB: claim_event(event, owner_id)
        DB-->>S: (event_id, claimed)

        alt not claimed
            S->>S: log duplicate and continue
        else claimed
            S->>P: process_event(event)
            P->>E: eval_function(user_input, context, output)
            E-->>P: evaluation dict
            P-->>S: evaluation dict

            alt STORE_ONLY_FAILS and success
                S->>DB: release_claim(event_id)
            else persist
                S->>DB: mark_done(event_id, event, evaluation)
            end
        end
    end

    alt parse failure
        S->>DB: mark_error(fallback_ingest_id, ...)
    end
    alt pipeline or store error
        S->>DB: mark_error(event_id, ...)
    end
```

## State Diagram (Event Persistence Status)

```mermaid
stateDiagram-v2
    [*] --> FilterSkipped: should_evaluate returns False
    [*] --> ParseError: parse_incoming_event raises
    [*] --> DuplicateSkipped: claim_event not claimed
    [*] --> Processing: claim_event success

    Processing --> ReleasedClaim: STORE_ONLY_FAILS and success
    Processing --> Done: mark_done
    Processing --> Error: exception in pipeline or store

    FilterSkipped --> [*]
    ParseError --> [*]
    DuplicateSkipped --> [*]
    ReleasedClaim --> [*]
    Done --> [*]
    Error --> [*]
```
