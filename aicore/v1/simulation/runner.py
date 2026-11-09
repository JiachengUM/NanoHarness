from aicore.simulation.agent_runner import AgentRunnerBase
from aicore.v1.experiments.agent import AgentEvent

Runner = AgentRunnerBase[AgentEvent, AgentEvent, str]
