"""手动验证 aicore/agents/plan/dag_checker.py 的 check_dag 各项检查。

放在 tests/ 下但文件名不以 test_ 开头，不参与 pytest 收集（pytest.ini python_files = test_*.py）。

Run directly:
    uv run python -m tests.agents.verify_dag_checker
"""

from rich.console import Console

console = Console()

from aicore.agents.plan.dag_checker import check_dag
from aicore.agents.plan.experiment.plan_schema_v1 import PlanStepV1
from tests.agents._plan_verify_helpers import (
    outputs as _outputs,
    step as _step,
    build as _build,
    emit,
    finish,
)

KNOWN_OPS = {"op"}


# 每条用例：(label, steps, known_ops, expected error kinds)
CASES: list[tuple[str, list[PlanStepV1], set[str], set[str]]] = [
    (
        "baseline / 合法 DAG，s3 直接 ref 祖先 s1（跨级引用允许）",
        [
            _step("s1"),
            _step(
                "s2", depends_on=["s1"], inputs={"x": "{{ .s1.outputs.Out[0].field }}"}
            ),
            _step(
                "s3", depends_on=["s2"], inputs={"y": "{{ .s1.outputs.Out[0].field }}"}
            ),
        ],
        KNOWN_OPS,
        set(),
    ),
    (
        # check_dag 在环检测前按 step_id 去重节点，dup 不应再连带触发一个
        # members 为空的假 cycle（回归用例，对应 dag_checker.py 第 5 项检查的修复）。
        "1. dup_step_id",
        [_step("s1"), _step("s1")],
        KNOWN_OPS,
        {"logic.dup_step_id"},
    ),
    (
        "2a. self_dep",
        [_step("s1"), _step("s2", depends_on=["s2"])],
        KNOWN_OPS,
        {"logic.self_dep"},
    ),
    (
        "2b. unknown_dep",
        [_step("s1"), _step("s2", depends_on=["s_missing"])],
        KNOWN_OPS,
        {"logic.unknown_dep"},
    ),
    (
        "3. unknown_op",
        [_step("s1", op="not_registered")],
        KNOWN_OPS,
        {"logic.unknown_op"},
    ),
    (
        "4. undeclared_ref via inputs（s3 只 depends_on s2，却在 inputs 中 ref 非祖先 s1）",
        [
            _step("s1"),
            _step("s2"),
            _step(
                "s3", depends_on=["s2"], inputs={"x": "{{ .s1.outputs.Out[0].field }}"}
            ),
        ],
        KNOWN_OPS,
        {"logic.undeclared_ref"},
    ),
    (
        "5. cycle（s1 -> s2 -> s3 -> s1）",
        [
            _step("s1", depends_on=["s3"]),
            _step("s2", depends_on=["s1"]),
            _step("s3", depends_on=["s2"]),
        ],
        KNOWN_OPS,
        {"logic.cycle"},
    ),
    (
        "6. invalid_condition（jq 语法错误）",
        [_step("s1"), _step("s2", depends_on=["s1"], condition="((((")],
        KNOWN_OPS,
        {"logic.invalid_condition"},
    ),
    (
        "7. undeclared_ref via condition（s3 只 depends_on s2，condition 却引用非祖先 s1）",
        [
            _step("s1"),
            _step("s2"),
            _step("s3", depends_on=["s2"], condition=".s1.outputs.Out.field"),
        ],
        KNOWN_OPS,
        {"logic.undeclared_ref"},
    ),
    (
        "8a. valid array iterator（单层 [] 紧跟叶子属性，合法）",
        [
            _step("s1"),
            _step(
                "s2", depends_on=["s1"], inputs={"x": "{{ .s1.outputs.Out[].field }}"}
            ),
        ],
        KNOWN_OPS,
        set(),
    ),
    (
        "8b. ref_shape_mismatch（同一路径出现两个 []，段数与 is_list 声明不符）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={"x": "{{ .s1.outputs.Out[].nested[].field }}"},
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_shape_mismatch"},
    ),
    (
        "8c. ref_shape_mismatch（[] 是路径最后一段，缺 attribute_name 段）",
        [
            _step("s1"),
            _step("s2", depends_on=["s1"], inputs={"x": "{{ .s1.outputs.Out[] }}"}),
        ],
        KNOWN_OPS,
        {"logic.ref_shape_mismatch"},
    ),
    (
        "8d. ref_malformed（第二段不是字面量 outputs）",
        [
            _step("s1"),
            _step(
                "s2", depends_on=["s1"], inputs={"x": "{{ .s1.output.Out[0].field }}"}
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_malformed"},
    ),
    (
        "8e. ref_concept_mismatch（ConceptName 与 s1 实际声明的 Out 不一致）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={"x": "{{ .s1.outputs.Wrong[0].field }}"},
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_concept_mismatch"},
    ),
    (
        "8f. ref_shape_mismatch（下标段既不是数字也不是 []）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={"x": "{{ .s1.outputs.Out.first.field }}"},
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_shape_mismatch"},
    ),
    (
        "8g. ref_shape_mismatch（s1 声明 is_list=False，ref 却多写了下标段）",
        [
            _step("s1", step_outputs=_outputs(is_list=False)),
            _step(
                "s2", depends_on=["s1"], inputs={"x": "{{ .s1.outputs.Out[0].field }}"}
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_shape_mismatch"},
    ),
    (
        "8h. ref_unknown_attribute（field 名不在 s1 声明的 attributes 中）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={"x": "{{ .s1.outputs.Out[0].unknown_field }}"},
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_unknown_attribute"},
    ),
    (
        "8i. ref_malformed（input 引用不支持 jq 切片）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={"x": "{{ .s1.outputs.Out[0:2].field }}"},
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_malformed"},
    ),
    (
        "9. ref_malformed via {{ if }}...{{ else }}...{{ end }}（inputs 不支持 Jinja 分支语法，"
        "即使被包裹的两个真实 ref 本身合法，if/else/end 三个 tag 也要单独报错）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                inputs={
                    "x": (
                        "{{ if (.s1.outputs.Out.field) }}"
                        "{{ .s1.outputs.Out[0].field }}"
                        "{{ else }}fallback{{ end }}"
                    )
                },
            ),
        ],
        KNOWN_OPS,
        {"logic.ref_malformed"},
    ),
    (
        "10a. invalid_success_check（success_check jq 语法错误）",
        [_step("s1", success_check="((((")],
        KNOWN_OPS,
        {"logic.invalid_success_check"},
    ),
    (
        "10b. success_check_not_self_constrained（s2 的 success_check 只引用祖先 s1、不约束自身 outputs）",
        [
            _step("s1"),
            _step("s2", depends_on=["s1"], success_check=".s1.outputs.Out.field == 1"),
        ],
        KNOWN_OPS,
        {"logic.success_check_not_self_constrained"},
    ),
    (
        "10c. success_check 自引用 + 引用祖先，两者都合法（不报错）",
        [
            _step("s1"),
            _step(
                "s2",
                depends_on=["s1"],
                success_check="(.s2.outputs.Out | length) > 0 and (.s1.outputs.Out.field == 1)",
            ),
        ],
        KNOWN_OPS,
        set(),
    ),
    (
        "mixed / 混合错误一次性全部报出，验证所有检查项不提前中断",
        [
            _step("s1"),
            _step("s1"),  # dup
            _step(
                "s2", op="not_registered", depends_on=["s_missing"]
            ),  # unknown_op + unknown_dep
            _step("s3", depends_on=["s4"]),
            _step("s4", depends_on=["s3"]),  # cycle
        ],
        KNOWN_OPS,
        {"logic.dup_step_id", "logic.unknown_dep", "logic.unknown_op", "logic.cycle"},
    ),
]


def main() -> int:
    all_ok = True
    for label, steps, known_ops, expected_kinds in CASES:
        errors = check_dag(_build(steps), known_ops)
        actual_kinds = {e.detail.kind for e in errors}
        detail = "\n".join(f"  - {e.nl_repr()}" for e in errors) or "  (no errors)"
        all_ok = (
            emit(
                console,
                label,
                sorted(actual_kinds),
                sorted(expected_kinds),
                extra=detail,
            )
            and all_ok
        )
    return finish(console, all_ok)


if __name__ == "__main__":
    raise SystemExit(main())
