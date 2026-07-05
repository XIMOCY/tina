import re


def parse_docstring(doc):
    """
    解析Google风格docstring，返回参数描述和返回值描述
    """
    param_desc = {}
    return_desc = ""
    if not doc:
        return param_desc, return_desc

    lines = doc.split("\n")
    in_args = False
    in_returns = False
    for line in lines:
        line = line.strip()
        if line.startswith("Args:"):
            in_args = True
            in_returns = False
            continue
        if line.startswith("Returns:"):
            in_args = False
            in_returns = True
            continue
        if in_args and line:
            # 匹配参数名和描述 - 改进正则表达式以处理带类型注解的格式
            # 匹配格式如：param_name (type): description 或 param_name: description
            m = re.match(r"(\w+(?:\s*\([^)]*\))?)\s*:\s*(.*)", line)
            if m:
                # 提取参数名，移除类型信息（括号内的内容）
                full_param = m.group(1)
                param_name = re.sub(r"\s*\([^)]*\)", "", full_param).strip()
                param_desc[param_name] = m.group(2)
        if in_returns and line:
            return_desc += line + " "
    return param_desc, return_desc.strip()
