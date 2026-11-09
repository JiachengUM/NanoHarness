# eval_tools/poi_compare/models.py
from pydantic import BaseModel, Field, model_validator


class CaseResult(BaseModel):
    score: int = Field(..., ge=1, le=5, description="1-5分，5=所有checklist项满足")
    pass_fail: bool = Field(..., description="score >= 4 为True")
    reason: str = Field(..., description="列出哪些must_contain项未满足，或说明通过原因")

    @model_validator(mode='after')
    def check_pass_fail_consistent(self) -> 'CaseResult':
        expected_pass_fail = self.score >= 4
        if self.pass_fail != expected_pass_fail:
            # Correct silently rather than raising, since LLM may produce inconsistent output
            self.pass_fail = expected_pass_fail
        return self


class ExperimentRecord(BaseModel):
    case_id: str
    dimension: str        # criteria_complexity / planning / error_recovery
    level: int            # 1/2/3
    goal: str
    expected: dict        # 含must_contain和description

    react_output: str
    react_result: CaseResult
    react_steps: int      # react实际使用的steps数
    react_trajectory: str | None = Field(default=None, description="ReAct 工具调用轨迹（可读文本）")

    ralph_output: str
    ralph_result: CaseResult
    ralph_rounds: int     # ralph实际用了几轮（1-indexed）
    ralph_trajectories: list[str] = Field(default_factory=list, description="Ralph 每轮的 ReAct 工具调用轨迹")
