# UML Design Artifacts

## UML Class Diagram (Core Modules)

```mermaid
classDiagram
    class AIEvent {
      +system: str
      +event_type: str
      +user_input: str
      +context: str
      +output: str
      +raw_meta: dict
    }
    # UML Design Artifacts

    ## UML Class Diagram (Core Modules)

    ```mermaid
    classDiagram
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
          +get_event(filepath) AIEvent
          +get_message(filepath) tuple
        }

        class Service {
          +run_service(poll_seconds, max_cycles) int
          +process_message(message, store, owner_id, run_mode) str
          +process_incoming_event(event, store, owner_id, run_mode) str
          +resolve_owner_id() str
          -_fallback_error_id(message) str
          -_print_results(results) None
        }

        class Pipeline {
          +run_pipeline(event) PipelineOutcome
          +process_event(event) dict|None
        }

        class Eval {
          +eval_function(user_input, context, output) dict
        }

        class MongoResultStore {
          +compute_id(event) str
          +exists(event_id) bool
          +claim_event(event, owner_id) tuple[str,bool]
          +mark_processing(event, event_id, owner_id) str
          +mark_done(event_id, event, evaluation) None
          +mark_skipped(event_id, event) None
          +mark_error(event_id, ...) None
          +save(event, evaluation) str
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
        Service --> Pipeline
        Service --> MongoResultStore
        Service --> LoggingUtils

        Pipeline --> Eval
        Pipeline --> AIEvent
        MongoResultStore --> AIEvent
    ```

    ## Sequence Diagram (Single Event)

    ```mermaid
    sequenceDiagram
        participant S as service.py
        participant GM as get_message.py
        participant DB as store_mongo.py
        participant P as pipeline.py
        participant E as eval.py

        S->>GM: iter_incoming_messages()
        GM-->>S: IncomingMessage

        S->>GM: parse_incoming_event(message)
        GM-->>S: AIEvent

        S->>DB: claim_event(event, owner_id)
        DB-->>S: (event_id, claimed)

        alt not claimed
            S->>S: log duplicate and skip
        else claimed
            S->>P: process_event(event)
            P->>E: eval_function(...)
            E-->>P: evaluation dict
            P-->>S: evaluation or None

            alt filtered
                S->>DB: mark_skipped(event_id, event)
            else evaluated
                S->>DB: mark_done(event_id, event, evaluation)
            end
        end

        alt parse failure before AIEvent
            S->>DB: mark_error(fallback_ingest_id, error_type, error_message)
        end
    ```

    ## State Diagram (Event Persistence Status)

    ```mermaid
    stateDiagram-v2
        [*] --> ParseError: parse_incoming_event failure
        [*] --> DuplicateSkipped: claim_event not claimed
        [*] --> Processing: claim_event success

        Processing --> Skipped: filter rejects event
        Processing --> Done: evaluation persisted
        Processing --> Error: pipeline/store failure

        ParseError --> [*]
        DuplicateSkipped --> [*]
        Skipped --> [*]
        Done --> [*]
        Error --> [*]
    ```
