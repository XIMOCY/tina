"""
Ollama使用示例
展示如何在Tina框架中使用Ollama运行本地大语言模型

使用前请确保：
1. 已安装Ollama: https://ollama.ai
2. 已启动Ollama服务: ollama serve
3. 已下载所需模型: ollama pull llama3.2
"""

import asyncio
from tina.LLM import Ollama
from tina.agent import Agent
from tina.agent.core.tools import Tools

def basic_ollama_usage():
    """基础Ollama使用示例"""
    print("=== 基础Ollama使用示例 ===")
    
    # 初始化Ollama客户端
    ollama = Ollama(model="llama3.2")  # 确保已下载此模型
    
    # 检查模型是否可用
    if not ollama.check_model_available():
        print(f"模型 {ollama.model} 不可用，请先下载:")
        print(f"ollama pull {ollama.model}")
        return
    
    # 简单对话
    result = ollama.generate(input_text="你好，请简单介绍一下你自己")
    print("AI回复:", result["content"])
    
def advanced_parameters():
    """高级参数使用示例"""
    print("\n=== 高级参数使用示例 ===")
    
    ollama = Ollama(model="llama3.2")
    
    # 使用高级参数进行创意写作
    result = ollama.generate(
        input_text="写一首关于春天的短诗",
        temperature=0.8,      # 增加创造性
        top_p=0.9,           # 核采样
        top_k=50,            # Top-K采样
        max_tokens=200       # 限制输出长度
    )
    print("创意诗歌:", result["content"])

def streaming_example():
    """流式输出示例"""
    print("\n=== 流式输出示例 ===")
    
    ollama = Ollama(model="llama3.2")
    
    print("AI正在回答（流式输出）: ", end="", flush=True)
    for chunk in ollama.generate(
        input_text="请详细解释什么是人工智能",
        stream=True,
        temperature=0.7
    ):
        content = chunk.get("content", "")
        if content:
            print(content, end="", flush=True)
    print("\n")

def json_mode_example():
    """JSON模式示例"""
    print("\n=== JSON模式示例 ===")
    
    ollama = Ollama(model="llama3.2")
    
    result = ollama.generate(
        input_text="请以JSON格式返回北京的基本信息，包括人口、面积、著名景点",
        format="json",
        temperature=0.3
    )
    print("JSON回复:", result["content"])

def multi_model_example():
    """多模型切换示例"""
    print("\n=== 多模型切换示例 ===")
    
    # 获取可用模型列表
    ollama = Ollama()
    models = ollama.list_models()
    
    print("可用模型列表:")
    for model in models:
        print(f"- {model['name']} (大小: {model['size']//1024//1024}MB)")
    
    if len(models) >= 2:
        # 使用不同模型进行对话
        for model in models[:2]:  # 使用前两个模型
            model_name = model['name']
            ollama_client = Ollama(model=model_name)
            result = ollama_client.generate(
                input_text="请用一句话介绍你的特点",
                temperature=0.5
            )
            print(f"\n{model_name}: {result['content']}")

def agent_integration_example():
    """Agent集成示例"""
    print("\n=== Agent集成示例 ===")
    
    # 创建Ollama LLM
    ollama_llm = Ollama(model="llama3.2")
    
    # 创建工具集（可以添加自定义工具）
    tools = Tools()
    
    # 创建Agent
    agent = Agent(
        LLM=ollama_llm,
        tools=tools,
        sys_prompt="你是一个有用的AI助手，可以帮助用户解决各种问题。"
    )
    
    print("与Ollama Agent对话（输入'退出'结束）:")
    while True:
        user_input = input("\n用户: ")
        if user_input.lower() in ['退出', 'exit', 'quit']:
            break
            
        print("AI: ", end="", flush=True)
        for chunk in agent.predict(input_text=user_input, stream=True):
            content = chunk.get("content", "")
            if content:
                print(content, end="", flush=True)
        print()

def model_management_example():
    """模型管理示例"""
    print("\n=== 模型管理示例 ===")
    
    ollama = Ollama()
    
    # 列出所有模型
    models = ollama.list_models()
    print(f"当前已安装 {len(models)} 个模型:")
    for model in models:
        size_mb = model['size'] // 1024 // 1024
        print(f"  - {model['name']} ({size_mb}MB)")
    
    # 检查特定模型
    test_models = ["llama3.2", "mistral", "phi3"]
    for model_name in test_models:
        available = ollama.check_model_available(model_name)
        status = "✅ 可用" if available else "❌ 未安装"
        print(f"  {model_name}: {status}")
    
    # 示例：拉取新模型（注释掉避免实际下载）
    # print("\n拉取新模型示例:")
    # success = ollama.pull_model("phi3")
    # if success:
    #     print("模型拉取成功!")
    # else:
    #     print("模型拉取失败")

def error_handling_example():
    """错误处理示例"""
    print("\n=== 错误处理示例 ===")
    
    try:
        # 尝试连接到不存在的Ollama服务
        ollama = Ollama(host="http://localhost:9999")
        result = ollama.generate(input_text="测试")
        print("连接成功:", result["content"])
        
    except Exception as e:
        print(f"连接失败（这是预期的）: {e}")
    
    try:
        # 使用不存在的模型
        ollama = Ollama(model="non-existent-model")
        result = ollama.generate(input_text="测试")
        print("模型调用成功:", result["content"])
        
    except Exception as e:
        print(f"模型不存在（这是预期的）: {e}")

def performance_comparison():
    """性能对比示例"""
    print("\n=== 性能对比示例 ===")
    
    import time
    
    ollama = Ollama(model="llama3.2")
    
    if not ollama.check_model_available():
        print("模型不可用，跳过性能测试")
        return
    
    test_prompt = "请解释什么是机器学习，要求回答简洁明了"
    
    # 非流式调用
    start_time = time.time()
    result = ollama.generate(input_text=test_prompt, stream=False)
    end_time = time.time()
    
    print(f"非流式调用耗时: {end_time - start_time:.2f}秒")
    print(f"回复长度: {len(result['content'])}字符")
    
    # 流式调用
    start_time = time.time()
    content_parts = []
    for chunk in ollama.generate(input_text=test_prompt, stream=True):
        content = chunk.get("content", "")
        if content:
            content_parts.append(content)
    end_time = time.time()
    
    print(f"流式调用耗时: {end_time - start_time:.2f}秒")
    print(f"回复长度: {len(''.join(content_parts))}字符")

if __name__ == "__main__":
    print("🚀 Ollama + Tina 框架使用示例")
    print("=" * 50)
    
    try:
        basic_ollama_usage()
        advanced_parameters()
        streaming_example()
        json_mode_example()
        multi_model_example()
        model_management_example()
        error_handling_example()
        performance_comparison()
        
        # 交互式示例（可选）
        print("\n" + "=" * 50)
        choice = input("是否进行Agent集成测试？(y/n): ")
        if choice.lower() == 'y':
            agent_integration_example()
            
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        print("请确保:")
        print("1. Ollama已安装并运行")
        print("2. 已下载所需模型")
        print("3. 网络连接正常")
    
    print("\n🎉 示例运行完成！")
    print("更多信息请参考: https://ollama.ai") 