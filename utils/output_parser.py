def process_result(result):
    rea = False  # 是否在推理状态
    reasoning_complete = False  # 推理是否已完成
    
    for r in result:
        # 处理推理内容
        if "reasoning_content" in r:
            if not rea:
                print("🤔 思考中：")
                rea = True
                reasoning_complete = False
            print(r["reasoning_content"], end="")
            continue  # 跳过后续处理
        
        # 处理工具相关消息
        if "tool_name" in r:
            # 如果之前在推理状态，先标记推理结束
            if rea:
                rea = False
                reasoning_complete = True
                print("\n😣 思考结束")
            print(f"🛠 {r['tool_name']} 正在执行...")
        
        elif "tool_arguments" in r:
            print(f"🔧 运行参数：{r['tool_arguments']}")
        
        elif r.get("role") == "tool":
            print(f"✅ 工具结果：{r['content']}")
        
        # 处理普通内容
        elif "content" in r and r["content"]:
            # 如果刚从推理状态切换到普通内容，且还没标记推理结束
            if rea and not reasoning_complete:
                rea = False
                reasoning_complete = True
                print("\n😣 思考结束")
            
            # 输出普通内容
            print(r["content"], end="")
