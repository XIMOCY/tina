import asyncio
import os

from ..agent import Agent
async def ainput(prompt:str) -> str:
    _input = asyncio.to_thread(input, prompt)
    return await _input
def run_agent_in_cli(agent: Agent):
    """
    提供一个测试使用的cli
    """
    async def run():

        show_ui()
        
        while True:
            try:
                # 使用带样式的输入提示
                input_text = await ainput("\n>>>你: ")
                
                if not input_text:
                    continue
                if input_text.lower() in ["exit", "quit", "退出"]:
                    print("\n over!")
                    break
                elif input_text.lower() == "#context":
                    content_length = 0
                    print(agent.context_manager.get_messages())
                    for message in agent.context_manager.get_messages():
                        content_length += len(message["content"])
                    print("\n当前上下文长度：", content_length, "字")
                    continue
                elif input_text.lower() == "#tools":
                    print(agent.tools)
                    continue
                elif input_text.lower().startswith("#tool"):
                    tool_name = input_text.split(" ")[1]
                    tool = agent.tools.get_tool_info(tool_name)
                    print(tool)
                elif input_text.lower() == "#clear":
                    os.system("cls" if os.name == "nt" else "clear")
                    show_ui()
                    print("\n已清理当前窗口")
                    continue
                elif input_text.lower() == "#clear_context":
                    agent.context_manager.clear_messages()
                    print("\n已清理上下文")
                    continue

                print(">>>Agent: ", end="", flush=True)
                
                # 初始化状态变量
                tool_call_in_progress = False
                current_tool_name = ""
                args_buffer = ""
                
                # 开始预测
                result = await agent.apredict(instruction=input_text)
                
                async for chunk in result:
                    # 1. 处理普通对话内容
                    if chunk.get("role") == "assistant" and chunk.get("content"):
                        content = chunk["content"]
                        # 如果是从工具状态切换回来，加个换行
                        if tool_call_in_progress:
                            print("\n")
                            tool_call_in_progress = False
                        print(content, end="", flush=True)

                    # 2. 处理工具调用开始
                    if "tool_name" in chunk and chunk.get("role") == "assistant" and chunk.get("tool_arguments") == '':
                        current_tool_name = chunk['tool_name']
                        print(f"\n\n 🛠️  [工具调用] {current_tool_name}")
                        print(f" ⚙️  [参数构建] ", end="", flush=True)
                        tool_call_in_progress = True
                        args_buffer = ""
                        continue

                    # 3. 处理工具参数流
                    if "tool_arguments" in chunk and tool_call_in_progress:
                        arg_snippet = chunk["tool_arguments"]
                        args_buffer += arg_snippet
                        print(arg_snippet, end="", flush=True)

                    # 4. 处理工具执行结果
                    if chunk.get("role") == "tool":
                        print(f"\n ✅ [执行结果] ", end="")
                        # 格式化输出结果，如果是长文本则截断
                        res_content = chunk.get("content", "")
                        if len(res_content) > 500:
                            print(f"{res_content[:500]}... (已截断)")
                        else:
                            print(res_content)

                
                print() # 对话结束换行

            except KeyboardInterrupt:
                print("\n 👋 操作已取消。")
                break
            except Exception as e:
                print(f"\n ⚠️  [运行时错误]: {e}")

    def show_ui():
        print("tina 测试控制台")
        print("─" * 40)
        print("指令：\n 查看当前上下文：#context  查看工具列表：#tools 查看对应工具信息：#tool(name)\n 清理当前窗口：#clear 清理上下文：#clear_context")

    # 启动异步循环
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

