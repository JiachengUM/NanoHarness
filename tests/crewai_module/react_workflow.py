from crewai import Agent, Task, Crew, Process
from llm import llm_client
from tools import all_tools

class ReactWorkflow:
    """
    React工作流类，支持定制化agent、task、crew，并调用tools.py中的工具进行React推理
    """
    
    def __init__(self, **kwargs):
        """
        初始化React工作流
        
        Args:
            **kwargs: 工作流配置参数
        """
        self.llm = llm_client(**kwargs)
        self.tools = all_tools
    
    def create_agent(self, name, role, goal, backstory, tools=None):
        """
        创建定制化Agent
        
        Args:
            name: Agent名称
            role: Agent角色
            goal: Agent目标
            backstory: Agent背景故事
            tools: 可选的工具列表，默认为所有工具
        
        Returns:
            Agent对象
        """
        return Agent(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            tools=tools or self.tools,
            llm=self.llm,
            verbose=True
        )
    
    def create_task(self, description, expected_output, agent, context=None):
        """
        创建定制化Task
        
        Args:
            description: 任务描述
            expected_output: 期望输出
            agent: 执行任务的Agent
            context: 任务上下文
        
        Returns:
            Task对象
        """
        return Task(
            description=description,
            expected_output=expected_output,
            agent=agent,
            context=context,
            output_file="report.md"
        )
    
    def create_crew(self, agents, tasks, process=Process.sequential):
        """
        创建定制化Crew
        
        Args:
            agents: Agent列表
            tasks: Task列表
            process: 执行流程，默认为顺序执行
        
        Returns:
            Crew对象
        """
        return Crew(
            agents=agents,
            tasks=tasks,
            process=process,
            verbose=True,
            tracing=True
        )
    
    def run_react_workflow(self, query):
        """
        运行React工作流
        
        Args:
            query: 用户查询
        
        Returns:
            工作流执行结果
        """
        # 创建React Agent
        react_agent = self.create_agent(
            name="React Assistant",
            role="决策与调度中心",
            goal="通过推理和工具使用解决用户问题",
            backstory="你是一个使用React模式的AI助手，能够通过推理和使用工具来解决用户的各种问题。你会分析问题，决定使用哪些工具，执行工具调用，然后根据结果进行推理，最终给出解决方案。"
        )
        
        # 创建React Task
        react_task = self.create_task(
            description=f"分析用户查询并提供解决方案: {query}\n\n使用React模式:\n1. 分析问题\n2. 决定需要使用哪些工具\n3. 执行工具调用\n4. 根据工具结果进行推理\n5. 给出最终解决方案",
            expected_output="详细的解决方案，包括推理过程和使用的工具",
            agent=react_agent
        )
        
        # 创建并运行Crew
        crew = self.create_crew(
            agents=[react_agent],
            tasks=[react_task]
        )
        
        # 执行工作流
        result = crew.kickoff()
        return result

# 示例使用
if __name__ == "__main__":
    # 创建并运行React工作流
    workflow = ReactWorkflow()
    # 示例查询
    query = "北京的天气怎么样？并计算123+456的结果"
    print(f"用户查询: {query}")
    print("\n运行React工作流...\n")
    
    result = workflow.run_react_workflow(query)
    print("\n工作流执行结果:")
    print(result)