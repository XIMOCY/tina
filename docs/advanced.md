# tina 高级用法指南

本文档介绍 tina 的高级特性,包括自定义 Agent 行为、底层类继承、以及架构扩展。

## 目录

- [架构概览](#架构概览)
- [自定义 ContextManager](#自定义-contextmanager)
- [自定义 AgentRuntime](#自定义-agentruntime)
- [自定义 ToolsExecutor](#自定义-toolsexecutor)
- [完整示例](#完整示例)

---

## 架构概览

tina 的 Agent 采用模块化设计,核心组件包括:

```
Agent
├── LLM (BaseAPI)           # 大模型接口
├── Tools                   # 工具管理
│   └── ToolsExecutor      # 工具执行器
├── ContextManager          # 上下文管理
│   ├── messages           # 对话历史
│   ├── tool_calls         # 工具调用记录
│   └── tool_results       # 工具执行结果
├── AgentRuntime            # Agent运行时
│   └── 控制预测流程
└── MCPClient (可选)        # MCP客户端
```

### 可自定义的组件

| 组件 | 作用 | 自定义场景 |
|------|------|----------|
| **ContextManager** | 管理对话历史和上下文 | 自定义消息保存策略、添加记忆功能 |
| **AgentRuntime** | 控制 Agent 运行逻辑 | 实现 ReAct、CoT 等不同推理模式 |
| **ToolsExecutor** | 控制工具执行方式 | 并行执行、超时控制、错误处理 |

---

## 自定义 ContextManager

### 基础概念

`ContextManager` 负责管理:
- 对话消息历史 (`messages`)
- 工具调用记录 (`tool_calls`)
- 工具执行结果 (`tool_calls_result`)
- 消息长度限制

### 默认实现

```python
from tina.agent.core.context_manager import ContextManager

# 默认配置
context = ContextManager(
    max_length=100000,           # 最大消息长度
    max_tool_result_length=6000  # 单个工具结果最大长度
)
```

### 继承 BaseContextManager

创建自定义的上下文管理器:

```python
from tina.agent.core.context_manager import BaseContextManager
from typing import Any

class CustomContextManager(BaseContextManager):
    """自定义上下文管理器 - 添加记忆功能"""
    
    def __init__(self, memory_file="memory.json"):
        self.messages = []
        self.memory_file = memory_file
        self.load_memory()
    
    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.save_memory()
    
    def get_messages(self) -> list[dict[str, Any]]:
        return self.messages
    
    def add_user_message(self, message: str) -> list[dict[str, Any]]:
        self.messages.append({"role": "user", "content": message})
        self.save_memory()
        return self.messages
    
    def add_assistant_message(self, message: str) -> list[dict[str, Any]]:
        self.messages.append({"role": "assistant", "content": message})
        self.save_memory()
        return self.messages
    
    def add_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.messages.append({
            "role": "assistant",
            "tool_calls": tool_calls,
            "content": ""
        })
        return tool_calls
    
    def add_tool_calls_result(self, tool_calls_result: list[dict[str, Any]]) -> None:
        for item in tool_calls_result:
            self.messages.append({
                "role": "tool",
                "content": str(item.get("result", "")),
                "tool_call_id": item.get("tool_call_id")
            })
        self.save_memory()
    
    def clear_messages(self) -> None:
        self.messages.clear()
        self.save_memory()
    
    # 自定义方法 - 持久化记忆
    def save_memory(self):
        """保存记忆到文件"""
        import json
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)
    
    def load_memory(self):
        """从文件加载记忆"""
        import json
        import os
        if os.path.exists(self.memory_file):
            with open(self.memory_file, "r", encoding="utf-8") as f:
                self.messages = json.load(f)
```

### 使用自定义 ContextManager

```python
from tina import Agent, Tools
from tina.llm import BaseAPI

# 创建自定义上下文管理器
custom_context = CustomContextManager(memory_file="chat_history.json")

# 传递给 Agent
agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    context_manager=custom_context
)

# 使用 - 对话会自动保存
for chunk in agent.predict("你好"):
    print(chunk.get("content", ""), end="")

# 重启后依然有历史记忆
new_agent = Agent(
    llm=BaseAPI(),
    tools=Tools(),
    context_manager=CustomContextManager(memory_file="chat_history.json")
)
```

### 实用案例:总结式记忆

```python
class SummarizedContextManager(ContextManager):
    """当消息过多时,自动总结历史"""
    
    def __init__(self, llm, summary_threshold=15):
        super().__init__()
        self.llm = llm
        self.summary_threshold = summary_threshold
    
    def add_user_message(self, message: str):
        result = super().add_user_message(message)
        
        # 检查是否需要总结
        if len(self.messages) > self.summary_threshold:
            self.summarize_history()
        
        return result
    
    def summarize_history(self):
        """总结并压缩历史"""
        # 获取除了最近3条的所有消息
        to_summarize = self.messages[1:-3]  # 跳过system和最近消息
        
        if len(to_summarize) < 5:
            return
        
        # 构造总结请求
        summary_prompt = f"请简要总结以下对话:\n{to_summarize}"
        
        summary = self.llm.predict(
            input_text=summary_prompt,
            stream=False
        )
        
        # 替换历史为总结
        system_msg = self.messages[0]
        recent_msgs = self.messages[-3:]
        
        self.messages = [
            system_msg,
            {"role": "assistant", "content": f"[历史总结]: {summary['content']}"},
            *recent_msgs
        ]
```

---

## 自定义 AgentRuntime

### 基础概念

`AgentRuntime` 控制 Agent 的运行逻辑,包括:
- 如何调用 LLM
- 何时执行工具
- 如何处理流式/非流式输出
- 工具调用循环控制

### 默认实现: ToolCallingAgentRuntime

```python
from tina.agent.core.agent_runtime import ToolCallingAgentRuntime

runtime = ToolCallingAgentRuntime(
    llm=llm,
    tools=tools,
    context_manager=context,
    max_tool_loop=30  # 最大工具调用循环次数
)
```

### 继承 BaseAgentRuntime

创建自定义运行时,实现 ReAct 模式:

```python
from tina.agent.core.agent_runtime import BaseAgentRuntime, AgentStatus
from typing import Generator

class ReActAgentRuntime(BaseAgentRuntime):
    """ReAct 推理模式的 Agent Runtime
    
    ReAct 模式: Reasoning + Acting
    每次工具调用后,要求模型进行推理
    """
    
    def __init__(self, llm, tools, context_manager, mcp_client=None, max_steps=10):
        super().__init__(llm, tools, context_manager, mcp_client)
        self.max_steps = max_steps
    
    def run_prediction_stream(
        self,
        instruction=None,
        temperature=0.5,
        top_p=0.9,
        top_k=1,
        min_p=0
    ) -> Generator[dict, None, None]:
        """ReAct 流式预测"""
        self._instruction(instruction)
        
        for step in range(self.max_steps):
            # 添加推理提示
            if step > 0:
                self.context_manager.add_user_message(
                    "基于上述结果,继续推理下一步行动。"
                )
            
            self.status = AgentStatus.RUNNING
            
            # 调用 LLM
            llm_response = self.llm.predict_stream(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                temperature=temperature,
                top_p=top_p
            )
            
            content_parts = []
            tool_called = False
            
            for chunk in llm_response:
                if "tool_calls" in chunk and chunk.get("id"):
                    # 发现工具调用
                    whole_content = "".join(content_parts)
                    if whole_content:
                        self.context_manager.add_assistant_message(whole_content)
                        yield {"role": "assistant", "content": whole_content}
                    
                    # 执行工具
                    self.status = AgentStatus.TOOL_CALLING
                    self.context_manager.add_tool_calls(chunk["tool_calls"])
                    results = self._execute_tool(chunk["tool_calls"])
                    
                    for result in results:
                        yield result
                    
                    tool_called = True
                    break
                else:
                    # 收集内容
                    content = chunk.get("content", "")
                    if content:
                        content_parts.append(content)
                        yield {"role": "assistant", "content": content}
            
            # 如果没有调用工具,推理结束
            if not tool_called:
                whole_content = "".join(content_parts)
                if whole_content:
                    self.context_manager.add_assistant_message(whole_content)
                break
        
        self.status = AgentStatus.IDLE

# 使用
agent = Agent(
    llm=BaseAPI(),
    tools=tools,
    agent_runtime=ReActAgentRuntime(
        llm=BaseAPI(),
        tools=tools,
        context_manager=ContextManager(),
        max_steps=10
    )
)
```

### Chain-of-Thought (CoT) Runtime

```python
class CoTAgentRuntime(BaseAgentRuntime):
    """思维链模式的 Runtime"""
    
    def run_prediction_stream(
        self,
        instruction=None,
        temperature=0.7,
        top_p=0.9,
        top_k=1,
        min_p=0
    ) -> Generator[dict, None, None]:
        """CoT 流式预测"""
        self._instruction(instruction)
        
        # 第一步:思考
        yield {"role": "assistant", "content": "\n[思考中...]\n"}
        
        thinking_prompt = "请分步骤思考如何完成这个任务,列出需要的步骤。"
        self.context_manager.add_user_message(thinking_prompt)
        
        thinking_response = self.llm.predict_stream(
            messages=self.context_manager.get_messages(),
            temperature=temperature
        )
        
        thought_parts = []
        for chunk in thinking_response:
            content = chunk.get("content", "")
            if content:
                thought_parts.append(content)
                yield {"role": "assistant", "content": content}
        
        thought = "".join(thought_parts)
        self.context_manager.add_assistant_message(thought)
        
        # 第二步:执行
        yield {"role": "assistant", "content": "\n[执行中...]\n"}
        
        action_prompt = "现在按照上述步骤执行任务。"
        self.context_manager.add_user_message(action_prompt)
        
        # 使用工具执行
        action_response = self.llm.predict_stream(
            messages=self.context_manager.get_messages(),
            tools=self.tools.get_tools_for_llm(),
            temperature=0.5
        )
        
        for chunk in action_response:
            if "tool_calls" in chunk and chunk.get("id"):
                self.context_manager.add_tool_calls(chunk["tool_calls"])
                results = self._execute_tool(chunk["tool_calls"])
                for result in results:
                    yield result
            else:
                yield chunk
```

---

## 自定义 ToolsExecutor

### 基础概念

`ToolsExecutor` 控制工具的执行方式:
- 串行 vs 并行执行
- 超时控制
- 错误处理
- 执行日志

### 默认实现

```python
from tina.agent.core.executor import ToolsExecutor

executor = ToolsExecutor(parallel=True)  # 是否并行执行工具
```

### 自定义执行器

```python
from tina.agent.core.executor import ToolsExecutor
import asyncio
import time

class AdvancedToolsExecutor(ToolsExecutor):
    """高级工具执行器 - 添加超时、重试、日志"""
    
    def __init__(self, parallel=True, timeout=30, max_retries=2):
        super().__init__(parallel)
        self.timeout = timeout
        self.max_retries = max_retries
        self.execution_log = []
    
    def execute(self, tool_calls, tools, mcp_client=None):
        """同步执行,添加超时和重试"""
        results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            start_time = time.time()
            
            # 重试机制
            for attempt in range(self.max_retries + 1):
                try:
                    # 调用原始执行逻辑
                    result = self._execute_single_tool(
                        tool_call, tools, mcp_client
                    )
                    
                    # 记录日志
                    elapsed = time.time() - start_time
                    self.log_execution(tool_name, elapsed, "success", attempt)
                    
                    results.append(result)
                    break
                    
                except Exception as e:
                    if attempt < self.max_retries:
                        print(f"工具 {tool_name} 执行失败,重试 {attempt + 1}/{self.max_retries}")
                        time.sleep(1)
                    else:
                        # 最后一次尝试也失败
                        elapsed = time.time() - start_time
                        self.log_execution(tool_name, elapsed, f"failed: {e}", attempt)
                        results.append({
                            "content": f"工具执行失败: {str(e)}",
                            "tool_call_id": tool_call.get("id")
                        })
        
        return results
    
    def _execute_single_tool(self, tool_call, tools, mcp_client):
        """执行单个工具(带超时)"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f"工具执行超时({self.timeout}秒)")
        
        # 设置超时
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout)
        
        try:
            # 执行工具
            tool_name = tool_call["function"]["name"]
            tool = tools.get_tool(tool_name)
            
            if tool is None:
                raise ValueError(f"工具 {tool_name} 不存在")
            
            import json
            args = json.loads(tool_call["function"]["arguments"])
            result = tool(**args)
            
            return {
                "content": str(result),
                "tool_call_id": tool_call.get("id"),
                "tool_name": tool_name
            }
        finally:
            signal.alarm(0)  # 取消超时
    
    def log_execution(self, tool_name, elapsed, status, attempt):
        """记录执行日志"""
        log_entry = {
            "tool": tool_name,
            "elapsed": f"{elapsed:.2f}s",
            "status": status,
            "attempt": attempt,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.execution_log.append(log_entry)
        print(f"[LOG] {log_entry}")
    
    def get_log(self):
        """获取执行日志"""
        return self.execution_log

# 使用
tools = Tools(tools_executor=AdvancedToolsExecutor(
    parallel=False,
    timeout=30,
    max_retries=2
))
```

---

## 完整示例

### 示例1: 带记忆的对话 Agent

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina.agent.core.context_manager import BaseContextManager
import json
import os

class PersistentContextManager(BaseContextManager):
    """持久化上下文管理器"""
    
    def __init__(self, user_id, data_dir="./chat_data"):
        self.user_id = user_id
        self.data_dir = data_dir
        self.file_path = os.path.join(data_dir, f"{user_id}.json")
        self.messages = []
        
        os.makedirs(data_dir, exist_ok=True)
        self.load()
    
    def load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.messages = data.get("messages", [])
    
    def save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump({"messages": self.messages}, f, ensure_ascii=False, indent=2)
    
    def set_messages(self, messages):
        self.messages = messages
        self.save()
    
    def get_messages(self):
        return self.messages
    
    def add_user_message(self, message):
        self.messages.append({"role": "user", "content": message})
        self.save()
        return self.messages
    
    def add_assistant_message(self, message):
        self.messages.append({"role": "assistant", "content": message})
        self.save()
        return self.messages
    
    def add_tool_calls(self, tool_calls):
        self.messages.append({
            "role": "assistant",
            "tool_calls": tool_calls,
            "content": ""
        })
        return tool_calls
    
    def add_tool_calls_result(self, results):
        for item in results:
            self.messages.append({
                "role": "tool",
                "content": str(item.get("result", "")),
                "tool_call_id": item.get("tool_call_id")
            })
        self.save()
    
    def clear_messages(self):
        self.messages.clear()
        self.save()

# 使用
def create_user_agent(user_id):
    context = PersistentContextManager(user_id)
    
    return Agent(
        llm=BaseAPI(),
        tools=Tools(),
        context_manager=context,
        system_prompt=f"你是用户 {user_id} 的专属助手,记住我们的对话历史。"
    )

# 用户 A 的对话
agent_a = create_user_agent("user_a")
for chunk in agent_a.predict("我喜欢吃Pizza"):
    print(chunk.get("content", ""), end="")

# 稍后...
agent_a = create_user_agent("user_a")
for chunk in agent_a.predict("我喜欢吃什么?"):
    print(chunk.get("content", ""), end="")  # 会记得喜欢吃Pizza
```

### 示例2: 自监督的 Agent

```python
from tina.agent.core.agent_runtime import BaseAgentRuntime, AgentStatus

class SelfCheckAgentRuntime(BaseAgentRuntime):
    """自我检查的 Agent Runtime"""
    
    def run_prediction_stream(self, instruction=None, **kwargs):
        self._instruction(instruction)
        
        max_iterations = 3
        
        for iteration in range(max_iterations):
            yield {"role": "assistant", "content": f"\n[第{iteration+1}次尝试]\n"}
            
            # 执行任务
            response_parts = []
            llm_response = self.llm.predict_stream(
                messages=self.context_manager.get_messages(),
                tools=self.tools.get_tools_for_llm(),
                **kwargs
            )
            
            for chunk in llm_response:
                if "tool_calls" in chunk and chunk.get("id"):
                    self.context_manager.add_tool_calls(chunk["tool_calls"])
                    results = self._execute_tool(chunk["tool_calls"])
                    for result in results:
                        yield result
                else:
                    content = chunk.get("content", "")
                    if content:
                        response_parts.append(content)
                        yield chunk
            
            response = "".join(response_parts)
            if response:
                self.context_manager.add_assistant_message(response)
            
            # 自我检查
            yield {"role": "assistant", "content": "\n[检查结果...]\n"}
            
            check_prompt = "检查上述回答是否正确和完整。如果满意,回复'满意',否则说明问题。"
            self.context_manager.add_user_message(check_prompt)
            
            check_response = self.llm.predict(
                messages=self.context_manager.get_messages(),
                stream=False
            )
            
            check_result = check_response.get("content", "")
            yield {"role": "assistant", "content": f"检查: {check_result}\n"}
            
            if "满意" in check_result:
                yield {"role": "assistant", "content": "\n[任务完成]\n"}
                break
            else:
                yield {"role": "assistant", "content": "\n[重新尝试]\n"}
                self.context_manager.add_user_message("请改进你的回答。")

# 使用
agent = Agent(
    llm=BaseAPI(),
    tools=tools,
    agent_runtime=SelfCheckAgentRuntime(
        llm=BaseAPI(),
        tools=tools,
        context_manager=ContextManager()
    )
)
```

---

## 最佳实践

### 1. 选择合适的自定义级别

```python
# 简单需求 - 只自定义参数
agent = Agent(
    llm=llm,
    tools=tools,
    max_tool_loop=50
)

# 中等需求 - 自定义 ContextManager
agent = Agent(
    llm=llm,
    tools=tools,
    context_manager=CustomContextManager()
)

# 复杂需求 - 自定义 Runtime
agent = Agent(
    llm=llm,
    tools=tools,
    agent_runtime=CustomRuntime(...)
)
```

### 2. 保持接口一致

继承时务必实现所有抽象方法:

```python
# ✅ 正确
class MyContextManager(BaseContextManager):
    def set_messages(self, messages): ...
    def get_messages(self): ...
    def add_user_message(self, message): ...
    def add_assistant_message(self, message): ...
    def add_tool_calls(self, tool_calls): ...
    def add_tool_calls_result(self, results): ...
    def clear_messages(self): ...

# ❌ 错误 - 缺少方法
class MyContextManager(BaseContextManager):
    def get_messages(self): ...
    # 其他方法缺失会报错
```

### 3. 测试自定义组件

```python
# 单独测试自定义组件
context = CustomContextManager()
context.add_user_message("test")
assert len(context.get_messages()) == 1

# 再集成到 Agent
agent = Agent(llm=llm, tools=tools, context_manager=context)
```

---

## 参考资源

- [Agent API 文档](./api/agent.md)
- [源码: context_manager.py](../agent/core/context_manager.py)
- [源码: agent_runtime.py](../agent/core/agent_runtime.py)
- [源码: executor.py](../agent/core/executor.py)

---

[返回文档首页](./README.md)
