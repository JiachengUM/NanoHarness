from pathlib import Path
import pandas as pd

SHEET_NAMES = ['传统垂域', '出行助手', '搜索助手', '趣味助手', '用车助手']

def load_query_from_excel(file_path: str, sheet_names: list[str]) -> list[str]:
    queries: list[str] = []

    sheets = pd.read_excel(file_path, sheet_name=None)

    # return [sheet_name for sheet_name, _ in sheets.items()]

    for sheet_name, df in sheets.items():
        if sheet_name not in sheet_names:
            print("sheet_name invalid", sheet_name)
            continue

        # 获取当前 Sheet
        for index, row in df.iterrows():
            queries.append(row.iloc[0])

    return queries


def save_as_textfile(data:list[str], file_path: str):
    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(item + '\n')


def load_from_textfile(file_path: str) -> list[str]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines()]


def decompose_excel(file_path: str, sheet_names: list[str]):
    for sheet_name in sheet_names:
        queries = load_query_from_excel(file_path, [sheet_name])
        out_filename = str(dataset_path / f"{sheet_name}.txt")
        save_as_textfile(queries, out_filename)
        print(f"save {sheet_name} to {out_filename}")


if __name__ == "__main__":
    dataset_path = Path(".") / "projects" / "hwhms" / "datasets"    
    filepath = dataset_path / "huawei_0928_1_clean.xlsx"
    
    decompose_excel(str(filepath), SHEET_NAMES)
