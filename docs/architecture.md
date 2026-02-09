# docs/ARCHITECTURE.md

Core processing flow:

fixture/kafka input → `AIEvent` → filter → evaluate → results

Key code path:

1. Input adapter produces an `AIEvent`

* fixtures: `deepeval_mvp.get_message.get_event(path) -> AIEvent`

2. Central processing

* `deepeval_mvp.pipeline.process_event(event) -> dict | None`

  * returns `None` if filtered out
  * returns evaluation results dict if evaluated

3. Evaluation

* `deepeval_mvp.eval.eval_function(user_input, context, output) -> dict`

Modules:

* `models.py`: `AIEvent` dataclass
* `get_message.py`: fixture parser, provides `get_event()`
* `filtering.py`: `should_evaluate(system, event_type)`
* `pipeline.py`: `process_event(event)`
* `eval.py`: DeepEval orchestration (judge + metrics)
* `demo.py`: one-shot fixture runner
* `service.py`: directory-polling service loop (temporary input source)
* `main.py`: CLI wiring only

Kafka/DB integration later:

* replace the fixture input adapter with Kafka consumer adapter producing `AIEvent`
* add DB storage after `process_event` returns results
* keep `process_event` as the single shared path
