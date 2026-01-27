import asyncio

from ..agent import Agent

def run_agent_in_cli(agent: Agent):
    """
    提供一个测试使用的cli
    """
    async def run():

        print("tina 测试控制台")
        print("─" * 40)
        
        while True:
            try:
                # 使用带样式的输入提示
                input_text = input("\n>>>你: ").strip()
                
                if not input_text:
                    continue
                if input_text.lower() in ["exit", "quit", "退出"]:
                    print("\n over!")
                    break

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
                    if "tool_name" in chunk and chunk.get("role") == "assistant":
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

    # 启动异步循环
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

