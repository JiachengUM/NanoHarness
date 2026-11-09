from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TagTreeNode(BaseModel):
    """
    标签树节点。

    约定：
    - `name` 是节点唯一业务标识（在同一棵树内必须全局唯一）。
    - 只有叶子节点（children 为空）允许用于 case.tags 打标。
    """

    name: str = Field(..., min_length=1, description="标签名，写入case.tags时使用该值。")
    description: str = Field(default="", description="标签说明。")
    children: list["TagTreeNode"] = Field(
        default_factory=list,
        description="子节点列表。空列表表示叶子节点。",
    )

    @property
    def is_leaf(self) -> bool:
        """
        判断当前节点是否为叶子节点。

        Returns:
            若无子节点则返回 True，否则返回 False。
        """
        return len(self.children) == 0

    def iter_nodes(self) -> list["TagTreeNode"]:
        """
        深度优先遍历当前节点及其全部后代节点。

        Returns:
            以当前节点为起点的所有节点列表（包含自身）。
        """
        nodes: list[TagTreeNode] = [self]
        for child in self.children:
            nodes.extend(child.iter_nodes())
        return nodes

    def iter_leaf_nodes(self) -> list["TagTreeNode"]:
        """
        深度优先收集当前节点子树中的所有叶子节点。

        Returns:
            叶子节点列表；若当前节点本身是叶子则仅返回自身。
        """
        if self.is_leaf:
            return [self]
        leaves: list[TagTreeNode] = []
        for child in self.children:
            leaves.extend(child.iter_leaf_nodes())
        return leaves


class TagTree(BaseModel):
    """
    标签树模型。

    设计目标：
    - 管理标签树结构（增删改查、导入导出、可视化）。
    - 强约束“全树节点名唯一”，避免同名标签导致打标歧义。
    - 提供面向打标器的配置（`tagging_guideline`）。
    """

    root: TagTreeNode = Field(..., description="标签树根节点。")
    tagging_guideline: str = Field(
        default="请基于case目标与通过标准，从叶子标签中选择最有证据支持的标签。",
        description="该标签树专属的打标思路/准则。auto_tagger 会直接引用此内容作为打标指导。",
    )

    @classmethod
    def _validate_raw_node_payload(
        cls,
        node: Any,
        *,
        path: str,
        visiting_ids: set[int],
    ) -> None:
        """
        对原始 dict 结构做预校验（在 pydantic 解析前）：
        - 必须是单节点对象（dict）
        - children 必须是 list（可缺省）
        - 不允许环引用

        Args:
            node: 当前待校验节点对象。
            path: 当前节点在 payload 中的路径，便于报错定位。
            visiting_ids: 当前递归路径上的对象 id 集合，用于检测环。

        Returns:
            None。校验通过则静默返回。

        Raises:
            ValueError: 当节点结构非法、name 非法或检测到环时抛出。
        """
        if not isinstance(node, dict):
            raise ValueError(f"{path} 必须是对象（dict）")

        node_id = id(node)
        if node_id in visiting_ids:
            raise ValueError(f"检测到非法环结构: {path}")

        name = node.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name 必须是非空字符串")

        children = node.get("children", [])
        if children is None or not isinstance(children, list):
            raise ValueError(f"{path}.children 必须是列表")

        visiting_ids.add(node_id)
        for index, child in enumerate(children):
            cls._validate_raw_node_payload(
                child,
                path=f"{path}.children[{index}]",
                visiting_ids=visiting_ids,
            )
        visiting_ids.remove(node_id)

    @classmethod
    def from_json(cls, json_data: str | dict[str, Any]) -> "TagTree":
        """
        从 JSON 字符串或字典构建标签树。

        Args:
            json_data: JSON 字符串或字典对象。

        Returns:
            构建完成并通过模型校验的 TagTree 对象。

        Raises:
            ValueError: 输入类型非法、缺失 root、基础结构非法或字段类型不合法时抛出。
        """
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        if not isinstance(data, dict):
            raise ValueError("json_data 必须是 JSON object（字典）")
        if "root" not in data:
            raise ValueError("json_data 最外层必须且只能提供一个 root 字段")

        root_payload = data["root"]
        cls._validate_raw_node_payload(
            root_payload,
            path="root",
            visiting_ids=set(),
        )

        tagging_guideline = data.get("tagging_guideline")
        if tagging_guideline is None:
            return cls(root=TagTreeNode.model_validate(root_payload))
        if not isinstance(tagging_guideline, str):
            raise ValueError("tagging_guideline 必须是字符串")
        return cls(
            root=TagTreeNode.model_validate(root_payload),
            tagging_guideline=tagging_guideline,
        )

    @classmethod
    def from_json_file(cls, file_path: str) -> "TagTree":
        """
        从 JSON 文件构建标签树。

        Args:
            file_path: JSON 文件路径。

        Returns:
            构建完成并通过模型校验的 TagTree 对象。
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_json(data)

    def to_json(self, ensure_ascii: bool = False, indent: int = 2) -> str:
        """
        将标签树导出为 JSON 字符串。

        Args:
            ensure_ascii: 是否将非 ASCII 字符转义。
            indent: JSON 缩进空格数。

        Returns:
            序列化后的 JSON 字符串。
        """
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=ensure_ascii, indent=indent)

    def to_json_file(self, file_path: str, ensure_ascii: bool = False, indent: int = 2) -> None:
        """
        将标签树导出为 JSON 文件。

        Args:
            file_path: 输出文件路径。
            ensure_ascii: 是否将非 ASCII 字符转义。
            indent: JSON 缩进空格数。

        Returns:
            None。
        """
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, ensure_ascii=ensure_ascii, indent=indent)

    def _ensure_unique_node_names(self) -> None:
        """
        内部唯一性检查：全树任何层级都不允许重名。

        Returns:
            None。

        Raises:
            ValueError: 当存在重名节点时抛出。
        """
        all_names = [node.name for node in self.root.iter_nodes()]
        duplicate_names = sorted({name for name in all_names if all_names.count(name) > 1})
        if duplicate_names:
            raise ValueError(
                f"标签树中存在重名节点，不允许重复: {duplicate_names}"
            )

    def _ensure_strict_tree_structure(self) -> None:
        """
        树结构校验（基于 TagTree 数据本身）：
        - 不允许环
        - 除根节点外，每个节点必须且只能有一个父节点（防DAG）

        Returns:
            None。

        Raises:
            ValueError: 当检测到环或多父节点结构时抛出。
        """
        visiting_ids: set[int] = set()
        visited_ids: set[int] = set()
        parent_count: dict[int, int] = {id(self.root): 0}

        def dfs(node: TagTreeNode) -> None:
            node_id = id(node)
            if node_id in visiting_ids:
                raise ValueError("标签树结构非法：检测到环")
            visiting_ids.add(node_id)
            for child in node.children:
                child_id = id(child)
                parent_count[child_id] = parent_count.get(child_id, 0) + 1
                if parent_count[child_id] > 1:
                    raise ValueError("标签树结构非法：检测到节点存在多个父节点（疑似DAG）")
                if child_id not in visited_ids:
                    dfs(child)
            visiting_ids.remove(node_id)
            visited_ids.add(node_id)

        dfs(self.root)

    @model_validator(mode="after")
    def validate_unique_node_names(self) -> "TagTree":
        """
        Pydantic 模型后置校验入口。

        Returns:
            当前 TagTree 对象本身。
        """
        self._ensure_strict_tree_structure()
        self._ensure_unique_node_names()
        return self

    def get_leaf_tag_names(self) -> list[str]:
        """
        返回可用于 case.tags 的所有叶子标签名。

        Returns:
            叶子节点名称列表。
        """
        return [node.name for node in self.root.iter_leaf_nodes()]

    def get_node_by_name(self, node_name: str) -> TagTreeNode:
        """
        按节点名称精确查找节点。

        Args:
            node_name: 目标节点名称。

        Returns:
            命中的 TagTreeNode 对象。

        Raises:
            ValueError: 未找到对应节点时抛出。
        """
        for node in self.root.iter_nodes():
            if node.name == node_name:
                return node
        raise ValueError(f"节点不存在: {node_name}")

    def _find_parent_of(self, node_name: str) -> tuple[TagTreeNode | None, TagTreeNode]:
        """
        返回 (parent, node)。
        - 如果命中根节点，parent 为 None。
        - 采用显式栈做 DFS，避免递归深度问题。

        Args:
            node_name: 目标节点名称。

        Returns:
            一个二元组 `(parent, node)`。

        Raises:
            ValueError: 未找到对应节点时抛出。
        """
        if self.root.name == node_name:
            return None, self.root
        stack: list[tuple[TagTreeNode, TagTreeNode]] = [(self.root, child) for child in self.root.children]
        while stack:
            parent, current = stack.pop()
            if current.name == node_name:
                return parent, current
            for child in current.children:
                stack.append((current, child))
        raise ValueError(f"节点不存在: {node_name}")

    def add_node(self, parent_name: str, node: TagTreeNode) -> None:
        """
        在 parent_name 节点下新增一个子节点。
        新增前会校验新节点子树中的所有节点名均未在当前树中出现。

        Args:
            parent_name: 父节点名称。
            node: 待新增节点（可带子树）。

        Returns:
            None。

        Raises:
            ValueError: 当父节点不存在或新增后出现重名时抛出。
        """
        # 先做前置冲突检查：新子树里任一节点名都不能和当前树重名。
        existing_names = {n.name for n in self.root.iter_nodes()}
        new_subtree_names = [n.name for n in node.iter_nodes()]
        duplicate_names = sorted({name for name in new_subtree_names if name in existing_names})
        if duplicate_names:
            raise ValueError(
                f"新增失败，以下节点名已存在于标签树中: {duplicate_names}"
            )
        # parent 不存在时 get_node_by_name 会直接抛错，调用方可感知具体失败原因。
        parent = self.get_node_by_name(parent_name)
        parent.children.append(node)
        # 二次兜底校验：保证外部直接改 children 后也能复用同一检查逻辑。
        self._ensure_unique_node_names()

    def update_node_info(
        self,
        node_name: str,
        *,
        new_name: str | None = None,
        new_description: str | None = None,
    ) -> None:
        """
        修改指定节点的信息。

        支持修改：
        - `new_name`：节点名称（会触发全树重名校验）
        - `new_description`：节点描述

        Args:
            node_name: 目标节点名称。
            new_name: 新节点名；不传则不修改名称。
            new_description: 新描述；不传则不修改描述。

        Returns:
            None。

        Raises:
            ValueError: 节点不存在、new_name 为空或改名后重名时抛出。
        """
        node = self.get_node_by_name(node_name)

        if new_name is not None:
            if not new_name.strip():
                raise ValueError("new_name 不能为空")
            node.name = new_name
            # 改名后需要立刻做全树唯一校验，避免出现重名节点。
            self._ensure_unique_node_names()

        if new_description is not None:
            node.description = new_description

    def delete_node(self, node_name: str) -> None:
        """
        删除指定节点及其整棵子树。禁止删除根节点。

        Args:
            node_name: 目标节点名称。

        Returns:
            None。

        Raises:
            ValueError: 删除根节点或目标节点不存在时抛出。
        """
        if self.root.name == node_name:
            raise ValueError("不允许删除根节点")
        parent, target = self._find_parent_of(node_name)
        if parent is None:
            raise ValueError("不允许删除根节点")
        # 直接在父节点子列表中过滤删除目标子树。
        parent.children = [child for child in parent.children if child.name != target.name]

    def move_subtree(self, source_name: str, target_parent_name: str) -> None:
        """
        将 source_name 对应子树移动到 target_parent_name 节点下。
        禁止移动根节点；禁止移动到自身或其后代下。

        Args:
            source_name: 源子树根节点名称。
            target_parent_name: 目标父节点名称。

        Returns:
            None。

        Raises:
            ValueError: 当移动非法（根节点/自引用/环风险/节点不存在）时抛出。
        """
        if self.root.name == source_name:
            raise ValueError("不允许移动根节点")

        source_parent, source_node = self._find_parent_of(source_name)
        target_parent = self.get_node_by_name(target_parent_name)

        if source_node.name == target_parent.name:
            raise ValueError("目标父节点不能是源节点自身")

        # 防环：不允许把一个节点移动到它自己的后代节点下。
        descendant_names = {n.name for n in source_node.iter_nodes()}
        if target_parent.name in descendant_names:
            raise ValueError("不允许将节点移动到其自身子树下")

        if source_parent is None:
            raise ValueError("不允许移动根节点")
        # 先从原父节点摘除，再挂到新父节点。
        source_parent.children = [child for child in source_parent.children if child.name != source_node.name]
        target_parent.children.append(source_node)

    def validate_case_tags(self, tags: list[str]) -> None:
        """
        校验一个 case 的 tags 是否全部是叶子标签。
        失败时抛 ValueError。

        Args:
            tags: 待校验标签列表。

        Returns:
            None。

        Raises:
            ValueError: 存在非叶子或树外标签时抛出。
        """
        leaf_names = set(self.get_leaf_tag_names())
        # 允许重复输入，但校验只关注是否超出叶子标签集合。
        invalid_tags = sorted(set(tags) - leaf_names)
        if invalid_tags:
            raise ValueError(
                f"以下标签不是叶子节点标签，不能用于case打标: {invalid_tags}"
            )

    def to_pretty_string(self, show_leaf_mark: bool = True) -> str:
        """
        将标签树转为便于阅读的树形字符串。

        Example:
        根
        ├── 一级A
        │   ├── 叶子A1 [leaf]
        │   └── 叶子A2 [leaf]
        └── 一级B [leaf]

        Args:
            show_leaf_mark: 是否在叶子节点后追加 `[leaf]` 标记。

        Returns:
            便于阅读的树形字符串。
        """
        return self._format_subtree(
            node=self.root,
            prefix="",
            is_last=True,
            show_leaf_mark=show_leaf_mark,
            is_root=True,
        )

    def _format_subtree(
        self,
        node: TagTreeNode,
        prefix: str,
        is_last: bool,
        show_leaf_mark: bool,
        is_root: bool = False,
    ) -> str:
        """
        递归格式化单个子树为树形文本。

        Args:
            node: 当前节点。
            prefix: 当前行前缀缩进。
            is_last: 当前节点是否为同层最后一个节点。
            show_leaf_mark: 是否显示叶子标记。
            is_root: 当前节点是否为整棵树根节点。

        Returns:
            当前子树的格式化字符串。
        """
        node_label = node.name
        if show_leaf_mark and node.is_leaf:
            node_label = f"{node_label} [leaf]"

        # 根节点不显示连接符，子节点按是否末尾选择不同连接符。
        if is_root:
            current_line = node_label
        else:
            connector = "└── " if is_last else "├── "
            current_line = f"{prefix}{connector}{node_label}"

        if not node.children:
            return current_line

        child_prefix = prefix + ("    " if is_last or is_root else "│   ")
        child_lines: list[str] = []
        for index, child in enumerate(node.children):
            child_is_last = index == len(node.children) - 1
            child_lines.append(
                self._format_subtree(
                    node=child,
                    prefix=child_prefix,
                    is_last=child_is_last,
                    show_leaf_mark=show_leaf_mark,
                )
            )
        return current_line + "\n" + "\n".join(child_lines)
