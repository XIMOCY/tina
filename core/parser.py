import re
import json
            
def tina_parser(text:str,tools:type,permission:bool = False)->tuple[str,bool,str]:
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
    match = re.findall(_pattern, text, re.DOTALL)
    if not match:
        return text,False,""
    tool_call = json.loads(match[0][2:-2])
    tool_name = tool_call['name']
    tool_params = tool_call['arguments']
    if not tools.checkTools(tool_name):
        return {"type": "text", "content": "不存在该工具"},False,tool_name
    else:
        execute_statement_son = ""
        for key,value in tool_params.items():
            if tools.queryParameterType(tool_name,key) == "int" or tools.queryParameterType(tool_name,key) == "float" or tools.queryParameterType(tool_name,key) == "bool":
                execute_statement_son += key + "=" + str(value) + ","
            elif tools.queryParameterType(tool_name,key) == "str":
                execute_statement_son += key + "='" + str(value) + "',"
            else:
                execute_statement_son = ""
            
        execute_statement = tool_name + "(" + execute_statement_son[:-1] + ")"
        
        return execute_statement,True,tool_name
    
def json_parser(json_format:str)->tuple[dict,bool]:
    """
    解析出json格式的消息，并返回字典格式的消息
    """
    pass
