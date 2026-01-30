"""Comment"""


from dotenv import load_dotenv
load_dotenv()
# custom libraries
from deepeval_mvp.eval import eval_function
from deepeval_mvp.get_message import get_message


def should_evaluate(event: dict) -> bool:
    allowed_systems = {
        "enterprise-rag-chatbot",
        "test-system",
    }
    allowed_event_types = {
        "ai-event",
    }

    return (
        event.get("system") in allowed_systems
        and event.get("event_type") in allowed_event_types
    )


def print_results(results: dict) -> None:
    print("\n=== Evaluation Results ===")

    for metric in results["metrics"]:
        print(f"\n[{metric['name']}]")
        print(f"  score      : {metric['score']}")
        print(f"  threshold  : {metric['threshold']}")
        print(f"  success    : {metric['success']}")
        print(f"  reason     : {metric['reason']}")

    print("\nOverall success:", results["success"])


def main():
    """Comment"""
    print("Hello from main!")


    for path in [
        "src/deepeval_mvp/valid_sample.txt",
        "src/deepeval_mvp/not_valid_sample.txt",
        "src/deepeval_mvp/wrong_system.txt",
        "src/deepeval_mvp/wrong_event_type.txt",
    ]:
        event = get_message(path)

        if not should_evaluate(event):
            print(f"Skipping event (system={event.get('system')}, type={event.get('event_type')})")
            continue

        results = eval_function(event)
        print_results(results)
    return

if __name__ == "__main__":
    main()
