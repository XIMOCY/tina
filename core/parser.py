import re
import json
            
def tina_parser(text:str,tools:type,LLM:type=None)->tuple[str,str,bool]:
    r"""
    因为llama_cpp的消息格式和chatGPT的消息格式不一样，
    无法直接根据字典值直接确定是否为工具调用，
    所以使用字符串解析检测是否存在<tool_call><\tool_call>标签，
    若存在则提取工具名和参数。
    Args:
        text (str): 输入的文本
        permission (bool): 是否开放代码修改权限，默认为False，暂时没有补充
    Returns:
        str: 返回执行字符串
    """
    _pattern = r'<tool_call>(.*?)</tool_call>'
    match = re.search(_pattern, text, re.DOTALL)
    if not match:
        return text,False,""
    tool_call = json_parser(result=match[0],LLM=LLM)
    if not tools.checkTools(tool_call['name']):
        return tool_call["name"],tool_call["arguments"],False
    return tool_call["name"],tool_call["arguments"],True

def json_parser(result,LLM):
    _pattern =  r'\{\s*"name":\s*"[^"]*",\s*"arguments":\s*\{[^{}]*\}\s*\}'
    result = re.search(_pattern, result, re.DOTALL)[0]
    result = result.replace("\n","\\n")
    try:
        tool_call = json.loads(rf"{result}")
        return tool_call
    except Exception as e:
        result = LLM.predict(
                input_text = result,
                sys_prompt = "该json数据有问题，请修正"
            )["content"]
        json_parser(result=result,LLM=LLM)
        
        return tool_call


    