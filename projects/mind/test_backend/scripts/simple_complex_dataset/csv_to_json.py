import json
import csv


def csv_to_json(csv_path: str, output_path: str) -> list:
    result = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            query = row.get("query", "").strip()
            label = row.get("label", "").strip()
            source = row.get("source", "").strip()
            domain = row.get("domain", "").strip()

            if not query:
                continue

            tags = []
            if source:
                tags.append(source)
            if domain:
                tags.append(domain)

            user_query_lists = [[{"role": "user", "content": query}]]

            code_assertion = {"intent_type": "complex" if label == "complex" else "simple"}

            case = {
                "case_id": query,
                "context_config": {},
                "max_round": 1,
                "user_query_lists": user_query_lists,
                "expected_script": "",
                "nl_assertion": [],
                "code_assertion": code_assertion,
                "case_description": "",
                "tags": tags,
            }

            result.append(case)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Successfully converted {len(result)} records to {output_path}")
    return result


if __name__ == "__main__":
    csv_path = r"d:\projects\AI-Car\nanoai\projects\sgm_prod\classification\assets\default\data\complex_byd.csv"
    output_path = r"d:\projects\AI-Car\nanoai\projects\mind\test_backend\scripts\simple_complex_dataset\complex_byd.json"

    csv_to_json(csv_path, output_path)

# python -m projects.mind.test_backend.scripts.simple_complex_dataset.csv_to_json