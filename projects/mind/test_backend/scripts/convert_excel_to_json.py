import json
import pandas as pd

columns = ["意图领域", "具体功能", "Query", "意图类型"]


def excel_to_json(excel_path: str, output_path: str, sheet_name: str) -> list:
    df = pd.read_excel(excel_path, sheet_name=sheet_name)

    result = []

    for _, row in df.iterrows():
        intent_domain = str(row.get("意图领域", "")).strip()
        specific_function = str(row.get("具体功能", "")).strip()
        type = str(row.get("意图类型", "")).strip()

        tags = []
        if intent_domain and intent_domain != "nan":
            tags.append(intent_domain)
        if specific_function and specific_function != "nan":
            tags.append(specific_function)

        query = str(row.get("Query", row.get("query", ""))).strip()

        user_query_lists = []
        if query and query != "nan":
            query_list = query.split("\n")
            for q in query_list:
                if not q.strip():
                    continue

                user_query_lists = [[{"role": "user", "content": q.strip()}]]
                code_assertion = {"intent_type": "simple"}
                if type and type != "nan":
                    code_assertion["intent_type"] = (
                        "complex" if type == "复杂" else "simple"
                    )

                case = {
                    "case_id": q,
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
    excel_path = r"d:\projects\AI-Car\nanoai\projects\mind\test_backend\scripts\dataset_excel\C1_导航_全量功能清单.xlsx"
    sheet_map = {
        "【整理】SGM导航": "simple",
    }
    for sheet_name in sheet_map.keys():
        output_path = r"d:\projects\AI-Car\nanoai\projects\mind\test_backend\scripts\{}.json".format(
            sheet_name
        )

        excel_to_json(excel_path, output_path, sheet_name)

# python -m projects.mind.test_backend.scripts.convert_excel_to_json
