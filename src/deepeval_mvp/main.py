"""Comment"""


from dotenv import load_dotenv
load_dotenv()
# custom libraries
from deepeval_mvp.eval import eval_function
from deepeval_mvp.get_message import get_message


def main():
    """Comment"""
    print("Hello from main!")

    event_json = get_message()
    print(eval_function(event_json))


if __name__ == "__main__":
    main()
