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
      <<TypedDict>>
      +raw: bytes
      +kafka: dict
      +source_id: str
    }

    class AIEvent {
      <<frozen dataclass>>
      +system: str
      +event_type: str
      +user_input: str
      +context: str
      +output: str
      +raw_meta: dict
    }

    class MessageSource {
      <<Protocol>>
      +iter_messages(poll_seconds, max_cycles) Iterator~IncomingMessage~
      +parse_event(message) AIEvent
    }

    class FixtureMessageSource {
      +iter_messages(poll_seconds, max_cycles) Iterator~IncomingMessage~
      +parse_event(message) AIEvent
    }

    class ResultStore {
      <<Protocol>>
      +claim_event(event, owner_id) tuple~str_bool~
      +release_claim(event_id) None
      +mark_done(event_id, event, evaluation) None
      +mark_error(event_id, error_type, error_message) None
    }

    class MongoResultStore {
      +compute_event_id(event) str
      +claim_event(event, owner_id) tuple
      +release_claim(event_id) None
      +mark_done(event_id, event, evaluation) None
      +mark_error(event_id, error_type, error_message) None
    }

    class Filtering {
      +allowed_systems() set
      +allowed_event_types() set
      +should_evaluate(system, event_type) bool
    }

    class Service {
      +run_service(poll_seconds, max_cycles, store, message_source) int
      +process_message(message, store, owner_id, ..., message_source) str
      +process_incoming_event(event, store, owner_id, ...) str
      +resolve_owner_id() str
      -_default_store() ResultStore
      -_default_message_source() MessageSource
      -_fallback_error_id(message) str
      -_format_results(results) str
      -_print_results(results) None
      -_install_signal_handlers() tuple
      -_restore_signal_handlers(prev) None
    }

    class Pipeline {
      +process_event(event) dict
    }

    class _SanitizingOllamaModel {
      +generate(prompt) str
      +a_generate(prompt) str
      -_call_ollama(prompt, stream) tuple
      -_clean(text) str
    }

    class Eval {
      +eval_function(user_input, context, output) dict
      -_get_judge() _SanitizingOllamaModel
      -_build_metrics(judge) list
      -_run_metric(m, test_case, name_override) dict
    }

    class Preflight {
      +run_preflight(logger, db_ping) bool
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

    MessageSource <|.. FixtureMessageSource : implements
    ResultStore <|.. MongoResultStore : implements

    Main --> Preflight
    Main --> LoggingUtils
    Main --> Service

    FixtureMessageSource --> IncomingMessage
    FixtureMessageSource --> AIEvent

    Service --> MessageSource : depends on protocol
    Service --> ResultStore : depends on protocol
    Service --> Filtering
    Service --> Pipeline
    Service --> LoggingUtils

    Pipeline --> Eval
    Pipeline --> AIEvent

    Eval --> _SanitizingOllamaModel
    Filtering --> EnvUtils
    Eval --> EnvUtils
    MongoResultStore --> AIEvent
    MongoResultStore --> EnvUtils
```

## Sequence Diagram (Single Event)

```mermaid
sequenceDiagram
    participant S as service.py
    participant MS as MessageSource (protocol)
    participant F as filtering.py
    participant RS as ResultStore (protocol)
    participant P as pipeline.py
    participant E as eval.py

    S->>MS: iter_messages()
    MS-->>S: IncomingMessage

    S->>MS: parse_event(message)
    MS-->>S: AIEvent

    S->>F: should_evaluate(system, event_type)
    alt filtered out
        F-->>S: False
        S->>S: log filter-skipped and continue
    else passes filter
        F-->>S: True

        S->>RS: claim_event(event, owner_id)
        RS-->>S: (event_id, claimed)

        alt not claimed
            S->>S: log duplicate and continue
        else claimed
            S->>P: process_event(event)
            P->>E: eval_function(user_input, context, output)
            E-->>P: evaluation dict
            P-->>S: evaluation dict

            alt STORE_ONLY_FAILS and success
                S->>RS: release_claim(event_id)
            else persist
                S->>RS: mark_done(event_id, event, evaluation)
            end
        end
    end

    alt parse failure
        S->>RS: mark_error(fallback_ingest_id, ...)
    end
    alt pipeline or store error
        S->>RS: mark_error(event_id, ...)
    end
```

## State Diagram (Event Persistence Status)

```mermaid
stateDiagram-v2
    [*] --> FilterSkipped: should_evaluate returns False
    [*] --> ParseError: parse_event raises
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
