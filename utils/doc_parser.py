import re
def parse_docstring(doc):
    """
    解析Google风格docstring，返回参数描述和返回值描述
    """
    param_desc = {}
    return_desc = ""
    if not doc:
        return param_desc, return_desc

    lines = doc.split('\n')
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
            # 匹配参数名和描述
            m = re.match(r"(\w+):\s*(.*)", line)
            if m:
                param_desc[m.group(1)] = m.group(2)
        if in_returns and line:
            return_desc += line + " "
    return param_desc, return_desc.strip()