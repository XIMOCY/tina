# KeywordActions 关键词动作

对应 Unity Tina 的 **Keyword Actions**：说出关键词触发**无参**副作用。  
对照 `Tools`：需要参数、要进 LLM tools 列表 → 用 `Tools`；只触发副作用、不进 schema → 用 `KeywordActions`。

## 与 Tools 的区别

| | Tools | KeywordActions |
|---|---|---|
| 触发 | 官方 tool_calls | 回复文本里出现关键词 |
| 参数 | 可带参 | **无参**（有参请改用 Tools） |
| schema | 进入 tools 列表 | **不进入** |
| 合并 | 可挂载子包 | **不合并** |

## 用法

```python
from tina import KeywordActions, Tools, Agent
from tina.llm import BaseAPI

ka = KeywordActions()

@ka.bind(keyword="[Happy]", match="contains", display=False)
def play_happy():
    """无参副作用。"""
    ...

ka.bind_action(
    keyword="[Happy]",
    func=play_happy,
    match="contains",   # 默认 contains；或 exact
    display=False,      # True 显示关键词，False 隐藏（仅可见过滤）
    description="播放开心表情",  # 可选；不传则读 docstring
)

agent = Agent(
    llm=BaseAPI(...),
    tools=Tools(),
    keyword_actions=ka,
    system_prompt="你是助手...",
)
# 会自动在 system prompt 末尾追加：
# <keyword_action>
# 当你说的话里面包括了"[Happy]"的时候会触发 播放开心表情
# </keyword_action>
# 并发出 Warning（经 logger.warn）：使用了关键词动作，会影响你的系统提示词
```

约定：
- `match`：`"contains"` | `"exact"`（匹配**忽略大小写**）
- `display`：`True` 显示 / `False` 隐藏（默认 `True`）
- `description`：可选；不传则像 Tools 一样读函数文档字符串
- 同一关键词绑多个函数时，prompt 合并为「会调用以下的工具：名称: 描述」
- 也可事后 `agent.set_keyword_actions(ka)`（同样会改写 system prompt 末尾块）

## 触发时机

只要某段 **assistant 原文** 凑齐（本轮最终回复，或 tool_calls 前的那段正文），就会立刻 `check` / `acheck`。  
不是等整个 predict 完全结束才调；也不是每个 token 实时匹配（避免关键词被切半误触发）。

- `predict`（同步）：只跑同步回调；`async def` 绑定会被忽略并 warning
- `apredict`（异步）：同步回调直接调，`async def` 会 `await`

## Hide 与流式

`on_stream_chunk` 是**监听型，不能改写 chunk**（设计如此，不会为 Hide 做成拦截）。  
需要隐藏关键词时，在消费流式输出时自行调用：

```python
for chunk in agent.predict("..."):
    visible = agent.filter_visible(chunk.content or "")
    if visible:
        print(visible, end="")
tail = agent.flush_visible()
```

Hide 剥离**大小写敏感**，且支持跨 chunk 前缀缓冲（对齐 Unity）。

## Prompt 块

Agent 挂载 KeywordActions 后会自动把 `build_prompt_block()` 包进 `<keyword_action>` 追加到 system prompt 末尾。  
也可手动取块：`ka.build_prompt_block()` / `agent.build_keyword_actions_prompt_block()`。
