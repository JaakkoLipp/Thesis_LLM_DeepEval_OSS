import os
from dotenv import load_dotenv

load_dotenv()

from deepeval_mvp.get_message import get_message
from deepeval_mvp.eval import eval_function


def _parse_csv_env(name: str, default_csv: str = "") -> set[str]:
    raw = os.getenv(name, default_csv) or ""
    return {x.strip() for x in raw.split(",") if x.strip()}


ALLOWED_SYSTEMS = _parse_csv_env("ALLOWED_SYSTEMS", "enterprise-rag-chatbot,test-system")
ALLOWED_EVENT_TYPES = _parse_csv_env("ALLOWED_EVENT_TYPES", "ai-event")


def should_evaluate(meta: dict) -> bool:
    return (
        meta.get("system") in ALLOWED_SYSTEMS
        and meta.get("event_type") in ALLOWED_EVENT_TYPES
    )


def print_results(results: dict) -> None:
    print("\n=== Evaluation Results ===")
    for metric in results["metrics"]:
        print(f"\n[{metric['name']}]")
        print(f"  score      : {metric['score']}")
        print(f"  threshold  : {metric['threshold']}")
        print(f"  success    : {metric['success']}")
        print(f"  reason     : {metric['reason']}")
        if metric.get("error"):
            print(f"  error      : {metric['error']}")
    print("\nOverall success:", results["success"])


def main():
    print("Running Evaluation On Test Files!")

    for path in [
        "src/deepeval_mvp/valid_sample.txt",
        "src/deepeval_mvp/not_valid_sample.txt",
        "src/deepeval_mvp/wrong_system.txt",
        "src/deepeval_mvp/wrong_event_type.txt",
    ]:
        meta, (user_input, context, output) = get_message(path)

        if not should_evaluate(meta):
            print(f"Skipping event (system={meta.get('system')}, type={meta.get('event_type')})")
            continue

        results = eval_function(user_input, context, output)
        print_results(results)


if __name__ == "__main__":
    main()
