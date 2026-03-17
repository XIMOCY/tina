import asyncio
import os
import sys


async def ainput(prompt: str) -> str:
    _input = asyncio.to_thread(input, prompt)
    return await _input


def run_agent_in_cli(agent):
    """
    tina 终端快速测试控制台
    """

    async def run():
        os.system("cls" if os.name == "nt" else "clear")
        print("\033[92m" + " tina 交互控制台 " + "\033[0m")
        print("─" * 50)
        print("\033[90m指令: #context (查看记忆) | #clear (清屏) | #exit (退出)\033[0m")

        while True:
            try:
                user_input = await ainput("\n\033[1;34m>>> 用户:\033[0m ")
                if not user_input.strip():
                    continue

                cmd = user_input.lower().strip()
                if cmd in ["exit", "quit", "退出"]:
                    break
                if cmd == "#context":
                    print(f"\n\033[2m{agent.context_manager.get_messages()}\033[0m")
                    continue
                if cmd == "#clear":
                    os.system("cls" if os.name == "nt" else "clear")
                    continue

                print("\033[1;35m>>> Agent:\033[0m ", end="", flush=True)

                # 使用 tool_name 作为 key 的追踪字典
                active_tools = {}
                last_role = None

                async for chunk in agent.apredict(instruction=user_input):
                    role = chunk.get("role")
                    content = chunk.get("content", "")
                    t_name = chunk.get("tool_name")
                    t_args = chunk.get("tool_arguments")

                    # 1. 处理普通对话文本
                    if role == "assistant" and content and not t_name:
                        if last_role == "tool":
                            print("\n")
                        print(content, end="", flush=True)
                        last_role = "assistant"

                    # 2. 处理工具调用开始 (必须有 t_name 且 t_args 为空)
                    elif role == "assistant" and t_name and t_args == "":
                        if t_name not in active_tools:
                            active_tools[t_name] = {"args": ""}
                            print(f"\n\n\033[1;33m🛠️  [调用工具] {t_name}\033[0m")
                            print(f"\033[90m   [参数构建]: \033[0m", end="", flush=True)
                        last_role = "assistant"

                    # 3. 处理工具参数流 (改用 t_name 索引，增加安全判断)
                    elif role == "assistant" and t_name and t_args:
                        if t_name in active_tools:
                            active_tools[t_name]["args"] += t_args
                            print(f"\033[90m{t_args}\033[0m", end="", flush=True)
                        last_role = "assistant"

                    # 4. 处理工具执行结果
                    elif role == "tool":
                        # 清理追踪
                        target_name = chunk.get("tool_name")
                        active_tools.pop(target_name, None)

                        print(f"\n\033[1;32m✅ [执行结果 ({target_name})]:\033[0m")
                        res = chunk.get("content", "")
                        display_res = (res[:200] + "...") if len(res) > 200 else res
                        print(f"   \033[3m{display_res}\033[0m")
                        last_role = "tool"

                    if chunk.get("usage"):
                        u = chunk["usage"]
                        print(
                            f"\n\033[90m[Tokens: {u.get('total_tokens')} (P:{u.get('prompt_tokens')} C:{u.get('completion_tokens')})]\033[0m"
                        )

                print("\n" + "─" * 50)

            except KeyboardInterrupt:
                print("\n\033[91m已停止。\033[0m")
                continue
            except Exception as e:
                print(f"\n\033[41m运行时错误\033[0m: {e}")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
