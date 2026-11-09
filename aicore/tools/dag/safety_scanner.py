from typing import Dict, Any, List

from .base_classes import DAGIR, detect_cycle
from .issues import SafetyIssue, IssueSeverity, CheckResult, _issue_utils
from .operator_registry import OperatorRegistry


class SafetyScanner:
    """DAG 安全扫描器

    对 DAGIR 进行静态安全检查，输出 CheckResult（含 SafetyIssue 列表）。
    检查项依次为：算子白名单 → 循环依赖 → 敏感参数 → 参数类型 → 节点数量上限。

    装饰器化：scan 方法用 @_issue_utils.capture_issues() 装饰，
    返回 CheckResult，装饰器自动从 .issues 提取并汇入 IssueReport。
    各 _check_* 子方法为实例方法（符合 §9.2，业务逻辑归属实例），
    _check_type 为纯工具函数保留 staticmethod（§9.2 例外）。
    """

    @_issue_utils.capture_issues()
    def scan(self, dag_ir: DAGIR) -> CheckResult:
        """执行全部安全检查，返回 CheckResult（含所有 SafetyIssue）。

        装饰器化：检查结果通过 CheckResult.issues 返回，装饰器自动汇入 IssueReport。
        各 _check_* 子方法保持返回 List[SafetyIssue]，scan 聚合到 CheckResult。

        输入：DAGIR（DAG 中间表示）
        输出：CheckResult（issues 字段含安全问题列表，passed 表示是否通过）
        """
        result = CheckResult()
        for issue in self._check_operator_whitelist(dag_ir):
            result.add_issue(issue)
        for issue in self._check_circular_dependency(dag_ir):
            result.add_issue(issue)
        for issue in self._check_sensitive_params(dag_ir):
            result.add_issue(issue)
        for issue in self._check_param_types(dag_ir):
            result.add_issue(issue)
        for issue in self._check_node_limit(dag_ir):
            result.add_issue(issue)
        return result

    def _check_operator_whitelist(self, dag_ir: DAGIR) -> List[SafetyIssue]:
        """检查所有节点的算子是否在白名单中（critical）。

        operator 为 None → 报告"未知算子类型"；
        operator 未在 OperatorRegistry 注册 → 报告"不在白名单中"。
        修复建议与可用算子列表统一参考 `suggestion_readme.md`。
        """
        issues: List[SafetyIssue] = []
        # 获取可用算子列表，供 message 引用
        available_ops = sorted(OperatorRegistry.get_registry_model().operators.keys())
        for node_id, node in dag_ir.nodes.items():
            if node.operator is None:
                issues.append(SafetyIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"节点 {node_id} 使用了未知算子类型（operator 为 None），可用算子: {', '.join(available_ops)}",
                    node_id=node_id,
                ))
            elif not OperatorRegistry.get_operator(node.operator.value):
                issues.append(SafetyIssue(
                    severity=IssueSeverity.CRITICAL,
                    message=f"算子 {node.operator.value} 不在白名单中，拒绝执行，可用算子: {', '.join(available_ops)}",
                    node_id=node_id,
                    operator_type=node.operator.value,
                ))
        return issues

    def _check_circular_dependency(self, dag_ir: DAGIR) -> List[SafetyIssue]:
        """检查 DAG 是否存在循环依赖（critical）。

        复用 base_classes.detect_cycle（DFS 三色标记法），检测到回边时记录完整循环路径，
        不依赖 topological_order 抛异常，
        符合 AGENTS.md 第 3 条"无捕获·全记录·直抛出"。
        """
        issues: List[SafetyIssue] = []

        # 构建邻接表并复用统一的循环检测函数
        adj: Dict[str, List[str]] = {
            nid: list(node.dependencies) for nid, node in dag_ir.nodes.items()
        }
        cycle = detect_cycle(adj)

        if cycle:
            cycle_str = " → ".join(cycle)
            issues.append(SafetyIssue(
                severity=IssueSeverity.CRITICAL,
                message=f"DAG存在循环依赖: {cycle_str}（检测方法: DFS 三色标记法）",
            ))
        return issues

    def _check_sensitive_params(self, dag_ir: DAGIR) -> List[SafetyIssue]:
        """检查参数名是否包含敏感关键字（medium）。

        匹配 password / secret / token / api_key / credential（子串匹配，大小写不敏感）。
        """
        issues: List[SafetyIssue] = []
        sensitive_patterns = ["password", "secret", "token", "api_key", "credential"]
        for node_id, node in dag_ir.nodes.items():
            for param_key, param_value in node.params.items():
                key_lower = param_key.lower()
                matched_pattern = next((p for p in sensitive_patterns if p in key_lower), None)
                if matched_pattern:
                    issues.append(SafetyIssue(
                        severity=IssueSeverity.MEDIUM,
                        message=f"节点 {node_id} 包含敏感参数 {param_key}（命中关键字: {matched_pattern}）",
                        node_id=node_id,
                        operator_type=node.operator.value if node.operator else None,
                    ))
        return issues

    def _check_param_types(self, dag_ir: DAGIR) -> List[SafetyIssue]:
        """检查参数实际类型是否与算子 input_model schema 声明类型匹配（low）。

        支持 JSON Schema 的 type 直接声明与 anyOf/oneOf 联合类型；
        以 $ 开头的字符串视为占位符引用（依赖注入），直接通过校验；
        对子模型（$ref）或嵌套 object schema，dict 是合法输入（Pydantic 会自动构造子模型）。
        实际值类型已写入 message，便于快速定位类型错误。
        """
        issues: List[SafetyIssue] = []
        for node_id, node in dag_ir.nodes.items():
            if node.operator is None:
                continue
            operator = OperatorRegistry.get_operator(node.operator.value)
            if operator:
                schema = operator.input_model.model_json_schema() if operator.input_model else {}
                if isinstance(schema, dict):
                    properties = schema.get("properties", {})
                    for param_key, param_value in node.params.items():
                        if param_key not in properties:
                            continue
                        prop_schema = properties[param_key]
                        # 收集候选类型：直接 type 声明 + anyOf/oneOf 联合类型中的 type 子项
                        # 注意：Union[str, Location] 会生成 anyOf: [{"type":"string"}, {"$ref":"...Location"}]
                        expected_types: List[str] = []
                        has_nested_object = False
                        if isinstance(prop_schema.get("type"), str):
                            expected_types.append(prop_schema["type"])
                        if prop_schema.get("type") == "object" or "$ref" in prop_schema:
                            has_nested_object = True
                        for sub in (prop_schema.get("anyOf") or prop_schema.get("oneOf") or []):
                            if not isinstance(sub, dict):
                                continue
                            if isinstance(sub.get("type"), str):
                                expected_types.append(sub["type"])
                            # $ref 子项或嵌套 object schema 表示子模型，dict 是合法输入
                            if sub.get("type") == "object" or "$ref" in sub:
                                has_nested_object = True
                        # 子模型字段：dict 输入合法，直接放行（Pydantic 会自动构造子模型）
                        if has_nested_object and isinstance(param_value, dict):
                            continue
                        # 有类型约束且全部不匹配时报告；无类型约束（如纯 $ref）则跳过
                        if expected_types and not any(
                            self._check_type(param_value, t) for t in expected_types
                        ):
                            actual_type = type(param_value).__name__
                            issues.append(SafetyIssue(
                                severity=IssueSeverity.LOW,
                                message=f"节点 {node_id} 参数 {param_key} 类型不匹配，期望 {expected_types}，实际 {actual_type}（值预览: {str(param_value)[:200]}）",
                                node_id=node_id,
                                operator_type=node.operator.value,
                            ))
        return issues

    def _check_node_limit(self, dag_ir: DAGIR) -> List[SafetyIssue]:
        """检查 DAG 节点数量是否超过上限（high）。

        上限硬编码为 100 个节点。
        """
        issues: List[SafetyIssue] = []
        max_nodes = 100
        if len(dag_ir.nodes) > max_nodes:
            issues.append(SafetyIssue(
                severity=IssueSeverity.HIGH,
                message=f"DAG节点数量({len(dag_ir.nodes)})超过限制({max_nodes})",
            ))
        return issues

    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """检查值是否匹配 JSON Schema 类型字符串。

        以 $ 开头的字符串视为占位符引用，直接返回 True；
        未知类型字符串返回 True（不校验）。
        纯工具函数，保留 staticmethod（§9.2 例外）。
        """
        type_mapping: Dict[str, Any] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict
        }

        expected_python_type = type_mapping.get(expected_type)
        if not expected_python_type:
            return True

        if isinstance(value, str) and value.startswith("$"):
            return True

        return isinstance(value, expected_python_type)
