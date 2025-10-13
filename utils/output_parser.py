import json
import httpx
import sys
import time
def stream_generator_parser(base_url, payload, headers, timeout):
    tool_calls_buffer = {}
    final_tool_calls = None
    received_ids = {}  # 
    tool_name_sent = set()  # 记录已经发送过名称的工具索引
    reasoning_buffer = ""  # 缓存推理内容
    retry_count = 0  
    with httpx.stream("POST", f"{base_url}", json=payload, headers=headers, timeout=timeout) as response:
        try:
            if response.status_code != 200:
                raise Exception(f"请求失败了，状态码：{response.status_code}")
        except Exception as e:
            rep = response.read()
            yield {"role":"assistant", "content": str(e) + f"\n{rep.decode('utf-8')}"}
        for line in response.iter_lines():
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})

                        # 处理普通内容
                        if "content" in delta:
                            content = delta.get("content", "")
                            if content:  # 只有当内容非空时才发送
                                yield {"role": "assistant", "content": content}
                                
                        # 处理推理模型的内容，只有存在推理内容时才发送，同时防止出现空值，我只会在有值的情况下发送
                        if "reasoning_content" in delta:
                            reasoning_content = delta.get("reasoning_content", "")
                            if reasoning_content:  # 累积推理内容
                                reasoning_buffer += reasoning_content
                                yield {"role": "assistant", "reasoning_content": reasoning_content, "content": ""}

                        # 处理工具调用
                        if "tool_calls" in delta:
                            for tool_call in delta["tool_calls"]:
                                index = tool_call["index"]
                                
                                # 初始化缓冲区
                                if index not in tool_calls_buffer:
                                    tool_calls_buffer[index] = {
                                        "index": index,
                                        "function": {"arguments": ""},
                                        "type": "",
                                        "id": ""
                                        }
                                
                                # 保留首次收到的ID
                                if tool_call.get("id") and index not in received_ids:
                                    received_ids[index] = tool_call["id"]
                                
                                # 更新字段（保留首次ID，这里是因为我在debug的时候发现流式的回复总是截取不到ID所以搞了个缓冲区来保存）
                                current = tool_calls_buffer[index]
                                current["id"] = received_ids.get(index, "")
                                current["type"] = tool_call.get("type") or current["type"]
                                
                                # 处理函数参数
                                if tool_call.get("function"):
                                    func = tool_call["function"]
                                    current["function"]["name"] = func.get("name") or current["function"].get("name", "")
                                            
                                    # 如果这是第一次接收到工具名称且未发送过，会发送工具名称，在外部通过tool_name获取
                                    if current["function"].get("name") and index not in tool_name_sent:
                                        tool_name_sent.add(index)
                                        yield {
                                            "role": "assistant",
                                            "content": "",
                                            "tool_name": current["function"]["name"]
                                        }
                                            
                                    if func.get("arguments") is None:
                                        continue
                                    current["function"]["arguments"] += func.get("arguments", "")
                            
                            # 暂存当前状态
                            final_tool_calls = [v for k, v in sorted(tool_calls_buffer.items())]

                except json.JSONDecodeError:
                    continue
        # 第一次会发送工具名称，而后会将完整的工具调用语句发送
        if final_tool_calls:
            yield {
                "role": "assistant",
                "content": "",
                "tool_calls": final_tool_calls,
                "id": final_tool_calls[0]["id"] if final_tool_calls else ""
            }


def process_result(result, max_tool_output_length=200):
    in_reasoning = False  # 是否处于推理中
    last_tool_name = ""   # 上一个工具名称

    for r in result:
        # -------- 推理内容 --------
        if "reasoning_content" in r:
            if not in_reasoning:
                print("\n🤔 ──── 开始推理 ────")
                in_reasoning = True
            print(r["reasoning_content"], end="", flush=True)
            continue

        # 结束推理状态
        if in_reasoning:
            print("\n😣 ──── 推理结束 ────\n")
            in_reasoning = False

        # -------- 工具启动 --------
        if "tool_name" in r:
            tool_name = r["tool_name"]
            last_tool_name = tool_name

            if tool_name == "remember":
                print("\n📝 记忆已更新！")
                continue

            # 显示工具加载动画
            sys.stdout.write(f"\n🛠 正在执行工具：{tool_name}")
            sys.stdout.flush()
            for dot in [".", "..", "..."]:
                sys.stdout.write(f"\r🛠 正在执行工具：{tool_name}{dot}")
                sys.stdout.flush()
                time.sleep(0.3)
            print()

        # -------- 工具参数 --------
        elif "tool_arguments" in r:
            if last_tool_name != "remember":
                print(f"🔧 参数：{r['tool_arguments']}")

        # -------- 工具结果 --------
        elif r.get("role") == "tool":
            if last_tool_name == "remember":
                continue
            content = r["content"]
            if len(content) > max_tool_output_length:
                preview = content[:max_tool_output_length].rstrip()
                print(f"✅ 工具结果（部分）：\n{preview}...\n🔽 内容过长（共 {len(content)} 字符）")
            else:
                print(f"✅ 工具结果：{content}")

        # -------- 普通内容 --------
        elif "content" in r and r["content"]:
            print(r["content"], end="")