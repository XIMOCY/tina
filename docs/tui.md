# 终端界面 TUI（可选扩展）

终端界面由配套包 **`tina-tui`**（基于 [Textual](https://textual.textualize.io/)）提供。它是**可选扩展**，不是 tina 核心能力，定位有两层：

1. **测试你自己写的 Agent**：写工具、调提示词、看流式输出和工具调用，比在脚本里 `print` 方便得多；
2. **当作你自己的 TUI 来用**：直接把它作为应用的交互界面，或参照它自建界面。

> 核心不依赖它：`tina-tui` 是独立发行包，不安装它也能正常使用 tina；`run_agent_in_cli` 仍是零依赖的轻量方案。

## 安装

```bash
pip install tina-python[tui]   # 等价于安装 tina-tui
# 或直接安装
pip install tina-tui
```

## 命令行入口 `tinacode`

装好 `tina-tui` 后会多一个 `tinacode` 命令，用来**在任意目录直接起一个编码 agent**，不用写任何 Python：

```bash
cd <你的项目>
tinacode
```

行为：

| 项目 | 说明 |
| --- | --- |
| 工作目录 | **你敲命令时所在的目录**，`code_*` 工具的相对路径都以它为准 |
| 会话历史 | 存到 `<cwd>/.tina/chat_sessions/`，**按目录隔离**（换个目录就是另一份历史） |
| 模型配置 | 优先 `<cwd>/tina.env` 或 `<cwd>/.env`；没有就用全局 `~/.tina/tina.env` |
| 工具集 | `CodingTools`（`code_read` / `code_glob` / `code_grep` / `code_write` / `code_edit` / `code_patch` / `code_bash`） |
| 目录级定制 | 目录里的 `.tinacode.md` / `AGENTS.md` / `.tina.md` 会被自动注入系统提示，**不用改代码** |

全局配置放一份，任何目录都能直接跑：

```bash
mkdir -p ~/.tina
# 把 tina.env 复制进去（LLM_API_KEY / BASE_URL / MODEL_NAME）
```

> `tinacode` 会在启动时按 `base_url` / `model` 判断是不是 DeepSeek，是的话自动开启
> 「思考 + 工具调用」的 `reasoning_content` 回传（否则多轮后会报 400）。
> 用兼容思考模式但 URL 里没有 `deepseek` 字样的代理时，设 `TINACODE_REASONING=1` 强制开启。

## 快速开始

```python
from tina import Agent, Tools
from tina.llm import BaseAPI
from tina_tui import run_agent_in_tui

llm = BaseAPI()          # 读取 tina.env
tools = Tools()
agent = Agent(llm=llm, tools=tools, system_prompt="你是一个有用的助手")

run_agent_in_tui(agent, max_tokens=32000)
```

`run_agent_in_tui` 参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `agent` | `Agent` | 必填 | 要交互的 Agent |
| `max_tokens` | `int \| None` | `None` | 用户设置的最大 token 数，用于进度与超限警告 |
| `reasoning_collapsed` | `bool` | `True` | 推理/工具块默认是否折叠 |
| `auto_confirm` | `bool` | `True` | 是否自动注册工具确认弹条（仅在 Agent 未设置确认处理器时注册） |
| `unlimited_context` | `bool` | `False` | 用 tina 提供的无限制上下文管理器替换 Agent 的（见下） |

### 无限制上下文（`unlimited_context=True`）

Agent 默认的上下文管理器有长度限制：历史超过 `max_context_length`（默认 10 万字符）会丢弃最旧的消息，单条工具结果超过 `max_tool_result_length`（默认 6000 字符）会被截断。本地调试或长任务时，这些限制可能不是你想要的行为。

传入 `unlimited_context=True` 会用 tina 提供的无限制管理器替换掉 Agent 的：

```python
run_agent_in_tui(agent, unlimited_context=True)
```

- 不裁剪历史、不截断工具结果
- 现有历史（含 system）会被接管，不会丢
- 内部调用 `agent.set_context_manager(...)`，会一并同步 `agent.runtime.context_manager` 与 `agent.messages`
- 上下文会持续增长，需自行确认模型窗口足够大

运行中也可以用 `app.install_context_manager(cm)` 随时替换（同样是委托 `agent.set_context_manager`）。

也可以直接使用这些类（`from tina_tui import ...`）：

| 名称 | 说明 |
| --- | --- |
| `UnlimitedContextManager` | 无限制的文本上下文管理器 |
| `UnlimitedMultimodalContextManager` | 无限制的多模态上下文管理器 |
| `make_unlimited_context_manager(agent)` | 按 Agent 现有类型构造无限制版并接管历史 |

## 特性

- **流式渲染**：助手正文以 Markdown 流式显示；消费与渲染解耦（定时渲染泵），极快或极长的输出都不掉帧
- **可折叠**：推理内容（`reasoning_content`）与工具调用卡片均可折叠
- **工具确认**：`require_confirmation=True` 的工具会弹出内联选择条（`允许一次` / `始终允许此工具` / `拒绝`），拒绝会以红色提示「工具「x」被用户拒绝使用」；多个工具并发确认会逐个弹出，参数过长时只显示提示（按 `Ctrl+O` 弹窗查看完整参数）
- **打断**：`Esc` 打断本轮回复；已生成的部分正文写回上下文，进行中的工具调用记为「该次调用被打断」，Agent 状态复位
- **token 占用**：显示当前上下文 token 占用与百分比，≥80% 变黄、超限变红；运行时状态栏显示动画。服务端返回缓存信息时还会显示 **prompt 缓存命中率**（`缓存 99.9%`）——上下文越长命中率越高，直接决定实际费用
- **整轮统计**：底部（耗时那一行）显示**本轮（turn）**的总耗时、生成 token（跨该轮多次 LLM 请求累加）与平均 tps；单次工具耗时仍实时显示在工具卡片标题上
- **余额 / 花费**：`#balance` 打开后，状态栏显示账户余额，每轮结束再查一次余额、把两次的差值当作本轮花费追加到底部统计末尾。用差值估算就不必维护单价表；代价是精度受服务端小数点限制（小于一分钱显示 `¥<0.01`），且同一账号下的其它会话也会算进来。依赖服务端的 `GET /user/balance`（DeepSeek 有，OpenAI 官方没有），拿不到时 `#balance` 会直接说明并保持关闭
- **多行输入**：支持粘贴多行；`Enter` 发送、`Shift+Enter` / `Alt+Enter` 换行
- **命令补全**：输入 `#` 显示候选，`Tab` 循环补全；`#switch` / `#delete` 后可直接 `Tab` 补全会话 id
- **图片粘贴**：`#paste` 或 `Alt+V` 把系统剪贴板里的图片附加到下一条消息，`#paste 路径.png` 也可按路径指定文件（需安装 `Pillow`；仅多模态 Agent 生效，普通 Agent 会提示忽略）。终端常把 `Ctrl+V` 当成「粘贴文本」吃掉（Windows Terminal / VS Code 默认如此），此时按键根本到不了程序，所以 `Ctrl+V` 只在终端愿意透传时可用，**`#paste` 才是可靠入口**
- **会话归档**：每轮对话结束自动存到 `<项目>/.tina/chat_sessions/`，支持切换 / 重命名 / 删除，首轮结束后自动起名（也可自定义）
- **粘性滚动**：在底部时自动跟随输出；向上滚动查看历史时不打扰；滚回底部自动恢复
- **窗口化渲染（默认关闭，可选）**：`TinaTUI.WINDOWED = True` 时只把视口附近的块挂成 widget，其余用占位块撑高度。Textual 的整屏重排开销随 widget 数线性增长（300 条消息约 1200 个 widget 时一帧要 30ms+），窗口化后 DOM 降到几十个 widget、重排降到 ~1ms。**但默认是关的**：真实终端里代价大头是「重绘」而非「布局」，窗口化靠不断挂载/卸载 widget 换少排几个块，而 agent 会话的常态是持续流式追加（每次追加都可能触发窗口移动）；实测 Windows Terminal 下开启反而更卡。适合「长历史里频繁滚动」的场景，长会话滚动时才划算

## 指令

| 指令 | 别名 | 功能 |
| --- | --- | --- |
| `#help` | `#?` `#h` | 查看可用命令 |
| `#tools` | | 查看工具包列表（名称 / metadata / 工具数）；`#tools 包名` 查看该包的工具（名称/描述/参数），包名可 Tab 补全 |
| `#context` | | 查看当前上下文（消息块摘要） |
| `#paste` | | 附加图片到下一条消息：`#paste` 取系统剪贴板，`#paste 路径.png` 按路径指定 |
| `#model` | | 查看当前模型信息（model / base_url） |
| `#tokens` | | 查看当前上下文 token 占用（total / prompt / completion / 占比 / 缓存命中） |
| `#balance` | | 开关余额显示：状态栏显示账户余额，每轮结束在底部统计末尾显示本轮花费 |
| `#sessions` | | 列出已保存的会话（可跟关键字过滤，如 `#sessions 登录`） |
| `#switch` | | 切换会话，如 `#switch 登录重构`（也可用 id 或 id 前缀） |
| `#new` | | 新建会话（当前会话自动保存），可带名字：`#new 登录重构` |
| `#rename` | | 重命名当前会话，如 `#rename 登录模块重构` |
| `#delete` | | 删除会话，如 `#delete 登录重构`（匹配到多个时会要求更精确的 id） |
| `#compact` | `#compress` `#summary` | 压缩上下文：让 Agent 自我总结，并写入 system 后清空其余消息 |
| `#clear` | | 清空界面与渲染上下文（不会清除发送给模型的上下文；要压缩请用 `#compact`） |
| `#export` | `#save` | 导出本次会话为 Markdown 文件（默认 `./tina_session.md`，可 `#export 路径.md` 指定） |
| `#exit` | `#quit` | 退出 |

> 只有首个 token 是**已知命令**时才按命令处理；`# 标题`（Markdown 标题）、`## xxx` 或不认识的 `#foo` 都会当作普通消息发送给模型。

## 会话归档

会话存在项目目录下的 `.tina/chat_sessions/`，每个会话一个 JSON 文件（含标题与完整消息历史）：

```
<项目>/.tina/chat_sessions/
    20250101-120000-ab12.json   # 一个会话
```

- 每次打开都是全新对话；只有在发出第一条真正的消息（非 `#switch` / `#sessions` 等切换历史的指令）时，才会创建会话文件
- 最底部（耗时那一行）右侧显示当前对话：还没开始时显示「无」，有标题显示标题，没有标题则显示会话 id
- 每轮回复结束后自动落盘，退出不会丢历史
- 首轮结束后由模型自动起名（12 字以内的中文标题）；用 `#rename` 自定义过的名字不会被自动标题覆盖
- `#switch` / `#delete` / `#sessions` 支持按 id、id 前缀或标题模糊匹配，输入时会给出候选提示
- 想接着上次聊，用 `#switch` 切回某个历史会话

## 快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Enter` | 发送 |
| `Shift+Enter` / `Alt+Enter` | 换行 |
| `Tab` | 补全 `#` 命令 / 会话 id |
| `Ctrl+↑` / `Ctrl+↓` | 上一条 / 下一条消息 |
| `Ctrl+Home` / `Ctrl+End` | 第一条 / 最后一条消息 |
| `Ctrl+R` | 折叠 / 展开所有思考块 |
| `Ctrl+T` | 折叠 / 展开所有工具与结果块 |
| `Ctrl+L` | 清空界面 |
| `Ctrl+O` | 确认工具时，弹窗查看完整参数 |
| `Esc` | 有参数弹窗/工具确认时关闭；否则打断本轮回复 |

## 用作你自己的 TUI

界面层与数据层是分开的，`TuiMessageStore`（渲染块列表）和 `TokenCounter`（token 计数）**不依赖 textual**，可以单独导入：

```python
from tina_tui import TuiMessageStore, TokenCounter

store = TuiMessageStore()
counter = TokenCounter(max_tokens=32000)

store.add_user("你好")
for chunk in agent.predict(instruction="你好"):
    block = store.handle_chunk(chunk)     # 把流式分片聚合成渲染块
    counter.add_from_chunk(chunk)         # 记录本次请求的上下文占用
    # 在这里刷新你自己的界面

for block in store.get_blocks():
    print(block.role, block.status, block.content)
```

渲染块类型（`block.role`）：`user` / `assistant` / `reasoning` / `tool` / `result` / `error` / `system`。

也可以继承 `TinaTUI` 自定义界面：

```python
from tina_tui.tui import TinaTUI, run_agent_in_tui

class MyTUI(TinaTUI):
    CSS = TinaTUI.CSS + """
    Screen { background: #10141a; }
    """
```

## 已知限制

- 推理内容与思考链的处理依赖**流式输出**；非流式路径不会通过事件派发 `reasoning_content`。
- `TokenCounter` 记录的是**最近一次请求**返回的 `usage`（当前上下文占用），不是历史累计消耗；因为每次请求都发送全量消息，服务端返回的 total 即当前占用。
- 未设置 `max_tokens` 时，token 只显示占用值，不显示百分比。
- 打断只能停止等待：已经在后台线程里执行的工具本体不会立即终止（副作用无法撤销），但上下文会把该次调用记为「该次调用被打断」，Agent 状态会复位，可继续下一轮。
- 界面用定时渲染泵驱动更新（默认 0.1s 一次），流式正文约每秒刷新数次；内容越长节流间隔越大。
- 界面基于 Textual，版本迭代较快；升级后建议跑一遍 TUI 相关测试。
