from flask import Flask, render_template, request, Response, jsonify

from core.LLM.tina import tina
# from tools.query import query
# from tools.QwenDocToVec import QwenDocToVec
app = Flask(__name__)

# 存储聊天历史
chat_history = []
context_length = 10240  # 调整为训练时的上下文长度
#初始化工作目录
# 创建一个ChatBot实例
llm = tina(
    context_length=context_length  # 调整为训练时的上下文长度
)

# 挂载静态文件
app.static_folder ='static'

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.form['message']
    chat_history.append({'user': user_message})

    def generate():
        chat_history_str = ""
        for i in chat_history:
            if 'user' in i:
                chat_history_str += i['user'] + '\n'
            elif 'bot' in i:
                chat_history_str += i['bot'] + '\n'
        
        # 调用llm.predict方法生成响应
        if len(chat_history_str) > context_length*0.7:
            chat_history_str = chat_history_str[-int(context_length*0.7):]
        sys_prompt = f"""作为一个AI助手，我的目标是帮助用户获得有用的信息和解决问题。为了使我的回答更具人性化和趣味性，我会尝试在回答中加入一些幽默元素和个性化的表达方式。同时，我也会关注用户的需求和兴趣，尽可能地提供相关和有趣的内容。通过不断学习和改进，我相信我能够成为一个更加出色和受欢迎的AI助手。
        前文的记录:\n{chat_history_str}\n"""
        bot_response = llm.predict(
            input_text=user_message,
            sys_prompt=sys_prompt,
            temperature=0.6,
            stream=True
        )
        
        collected_messages = ""
        for chunk in bot_response:
            delta = chunk["choices"][0]["delta"]
            if 'role' in delta:
                continue
            elif 'content' in delta:
                collected_messages += delta['content']

            yield f"data: {collected_messages}\n\n"
        
        chat_history[-1]['bot'] = collected_messages

    return Response(generate(), content_type='text/event-stream')


    
if __name__ == '__main__':
    app.run(debug=True)
