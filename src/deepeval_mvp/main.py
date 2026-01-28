"""Comment"""


from dotenv import load_dotenv
load_dotenv()
# custom libraries
from deepeval_mvp.eval import eval_function
from deepeval_mvp.get_message import get_message


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

    # valid file
    event_json = get_message("src/deepeval_mvp/valid_sample.txt")
    results = eval_function(event_json)
    print_results(results)

    # not valid file
    event_json2 = get_message("src/deepeval_mvp/not_valid_sample.txt")
    results2 = eval_function(event_json2)
    print_results(results2)


if __name__ == "__main__":
    main()
