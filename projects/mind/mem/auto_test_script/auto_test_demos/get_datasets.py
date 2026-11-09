import asyncio

from beanie import PydanticObjectId
from rich import print
from asgiref.sync import async_to_sync

from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.complex_reasoning.task_mdb_models.dataset import ComplexReasoningDatasetDoc
from projects.mind.advisor.repositories import mdb_api
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree
from projects.mind.mem.auto_test_script.case_schema import TestCase



MUSIC = "音乐数据集"
SGM = "SGM数据集"
COMPLEX_REASONING_TOOL = "复杂推理工具调用数据集"
COMPLEX_REASONING_MEMORY = "复杂推理记忆能力测试数据集"


async def get_dataset_list(dataset_name: str | list[str]) -> list[TestCase]:
    await init_db()
    # 根据 name 查询数据集获取 id
    dataset_names = []
    dataset_ids = []
    if isinstance(dataset_name, str):
        dataset_names = [dataset_name]
    dataset_names = dataset_name
    for name in dataset_names:
        a_dataset = await mdb_api.get_list(ComplexReasoningDatasetDoc, query={"name": name})
        if not a_dataset:
            print(f"❌ 未找到数据集: {name}, 请检查数据集名称是否正确，最终数据集里将排除这个数据集。")
            continue
        a_dataset_id = a_dataset[0].id
        dataset_ids.append(a_dataset_id)
    
    # dataset_id = datasets[0].id
    # print(f"✅ 找到数据集: {dataset_name}, id: {dataset_id}")
    
    # 根据 dataset_id 查询 case，按 id 排序
    case_list = []
    for dataset_id in dataset_ids:
        a_case_list = await mdb_api.get_list(
            ComplexReasoningCaseDoc,
            query={"dataset_id": PydanticObjectId(dataset_id)},
            sort="_id"
        )
        case_list.extend(a_case_list)
        print(f"✅ 加载 {name} case总数: {len(a_case_list)} 条")
    new_case_list = []
    for case in case_list:
        case_dict = case.model_dump()
        case_dict["id"] = str(case.id)
        case_dict["dataset_id"] = str(case.dataset_id)
        new_case_list.append(case_dict)
    concated_cases = [TestCase.model_validate(case_dict) for case_dict in new_case_list]
    print(f"✅ 加载 {dataset_name} 总 case总数: {len(concated_cases)} 条")
    return concated_cases


def get_dataset_list_sync(dataset_name: str | list[str]) -> list[TestCase]:
    """同步加载数据集"""
    return async_to_sync(get_dataset_list)(dataset_name)


def filter_cases_by_tag_tree_nodes(
    cases: list[TestCase],
    node_names: list[str],
    *,
    tag_tree: TagTree | None = None,
) -> list[TestCase]:
    """
    按 ``node_names`` 筛选 case。

    - **``tag_tree`` 非空**：先校验 ``node_names`` 中每一项均为树中节点名；对每个节点取其子树内
      全部节点的 ``name`` 并集，再与各 ``case.tags`` 求交；命中任一即保留该 case。
    - **``tag_tree`` 为 ``None``**：不校验树；``allowed`` 即为 ``node_names``（去空白、去重后仍保留顺序）
      中的字面标签名与 ``case.tags`` 求交。

    - ``node_names`` 不能为空列表；元素须为非空白字符串。
    - 返回结果按 ``cases`` 原有顺序、按 ``TestCase.id`` 去重。
    - 对每个逻辑入口名（``node_names`` 去重保序），若 **当前 ``cases`` 中无任何一条** 的 ``tags``
      与该入口对应的匹配标签集合相交，则将该项记入「未匹配」并通过 Rich ``print`` 输出。
    """
    if not node_names:
        raise ValueError("node_names 不能为空列表")

    resolved: list[str] = []
    for raw in node_names:
        if not isinstance(raw, str):
            raise ValueError(f"node_names 必须为字符串列表，收到: {type(raw).__name__}")
        name = raw.strip()
        if not name:
            raise ValueError("node_names 中包含空名称（全空白）")
        resolved.append(name)

    uniq_names = list(dict.fromkeys(resolved))
    name_to_match_tags: dict[str, set[str]] = {}
    allowed: set[str] = set()

    if tag_tree is None:
        for n in uniq_names:
            name_to_match_tags[n] = {n}
        allowed = set(uniq_names)
    else:
        tree_names = {n.name for n in tag_tree.root.iter_nodes()}
        missing = [n for n in uniq_names if n not in tree_names]
        if missing:
            raise ValueError(
                "以下节点不在 tag_tree 中: "
                + ", ".join(repr(x) for x in sorted(set(missing)))
            )
        for n in uniq_names:
            node = tag_tree.get_node_by_name(n)
            sub = {x.name for x in node.iter_nodes()}
            name_to_match_tags[n] = sub
            allowed |= sub

    out: list[TestCase] = []
    seen_ids: set[str] = set()
    for c in cases:
        cid = str(c.id)
        if cid in seen_ids:
            continue
        case_tag_set = set(c.tags)
        if allowed & case_tag_set:
            seen_ids.add(cid)
            out.append(c)

    unmatched = [
        n
        for n in uniq_names
        if not any(name_to_match_tags[n] & set(c.tags) for c in cases)
    ]
    if unmatched:
        print(
            "⚠️ 以下 node_names 在当前 case 集中未匹配到任何用例: "
            + ", ".join(repr(x) for x in unmatched)
        )

    return out


def main():
    result = asyncio.run(get_dataset_list(COMPLEX_REASONING_MEMORY))
    print(result)


if __name__ == "__main__":
    main()