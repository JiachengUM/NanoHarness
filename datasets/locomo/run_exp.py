from nanoai.model import llm

def run(session_id: int, result_path: str) -> list[TestCase]:
    session = Session()

    messages = session.get_messages()

    test_case = []

    for q in session.QA:
        answer = llm(q, messages)

        test_case.append(TestCase(q, answer))


def load_result(result_path: str) -> list[TestCase]:
    pass


def eval(test_cases: list[TestCase]):
    llm_judge = Judge(llm, test_cases)


if __name__ == "__main__":
    run(session_id, result_path="./result.json")

    eval(load_result(result_path))
    