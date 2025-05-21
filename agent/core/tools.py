"""
编写者：王出日
日期：2025，5，20
版本 0.4.2
描述：工具类，用于管理大模型的工具
包含：
Tools类：用于管理大模型的工具，包括注册、查询、调用等功能
"""
import pickle
import inspect
import re

class Tools:
    """
    使用此类来管理你的工具，可以注册、查询、调用等功能
    可以使用一些自带的工具来调试
    """
    _global_tools = []
    @classmethod
    def registers(cls,name:str=None,description:str=None,required_parameters:list=None,parameters:dict=None,path:str=None,post_handler:callable=None):
        """
        注册一个全局的工具，类方法
        """
        def decorator(func):
            nonlocal name, description, required_parameters, parameters, path
            doc = func.__doc__ or ""
            param_desc, return_desc = parse_docstring(doc)
            # 自动推导
            if name is None:
                name = func.__name__
            if description is None:
                description = func.__doc__ or f"{name}工具"
            sig = inspect.signature(func)
            if required_parameters is None:
                required_parameters = [p for p in sig.parameters if sig.parameters[p].default is inspect.Parameter.empty]
            if parameters is None:
                parameters = {}
                for p, v in sig.parameters.items():
                    parameters[p] = {
                        "type": str(v.annotation) if v.annotation != inspect.Parameter.empty else "str",
                        "description": param_desc.get(p, "")
                    }
            if path is None:
                path = inspect.getfile(func)
            cls._global_tools.append(
                {
                    "name": name,
                    "description": description,
                    "required_parameters": required_parameters,
                    "parameters": parameters,
                    "path": path,
                    "post_handler": post_handler
                }
            )
            return func
        return decorator

    def __add__(self, other):

        """运算符重载：合并两个Tools实例的工具列表（自动去重）"""
        if not isinstance(other, Tools):
            raise TypeError("只能合并Tools类实例")
    
        # 创建新实例
        combined = Tools()
    
        # 使用集合记录已存在的工具名称（排除NULLTools）
        existing_names = set()
    
        # 合并工具列表（过滤NULLTools并自动去重）
        combined_tools = []
    
        # 处理当前实例的工具
        for t in self.tools:
            name = t["function"]["name"]
            if name != "NULLTools":
                if name not in existing_names:
                    combined_tools.append(t)
                    existing_names.add(name)
    
        # 处理另一个实例的工具
        for t in other.tools:
            name = t["function"]["name"]
            if name != "NULLTools":
                if name not in existing_names:
                    combined_tools.append(t)
                    existing_names.add(name)
    
        # 恢复NULLTools作为首个元素（使用当前实例的NULLTools）
        if self.tools and self.tools[0]["function"]["name"] == "NULLTools":
            combined_tools.insert(0, self.tools[0])
    
        combined.tools = combined_tools
    
        # 合并其他属性
        combined.tools_name_list = list(set(self.tools_name_list + other.tools_name_list))
        combined.tools_parameters_list = self.tools_parameters_list + other.tools_parameters_list
        combined.tools_path = {**self.tools_path, **other.tools_path}

        return combined
    
    def __init__(self,useSystemTools=False,useRAG = False,useTerminal=False,setGoal=False):
        """
        使用此类来管理你的工具，可以注册、查询、调用等功能
        可以使用一些自带的工具来调试
        Args:
            useSystemTools (bool, optional): 是否使用系统工具. 默认为False.
            useRAG (bool, optional): 是否使用RAG工具. 默认为False.
            useTerminal (bool, optional): 是否使用终端工具.默认为False.
            setGoal (bool, optional): 是否使用目标工具.默认为False.
        """
        self.tools = []
        self.tools_name_list = []
        self.tools_parameters_list = []
        self.tools_path = {}
        self.post_handler = {}
        self.multiregister(self._global_tools)
        self.__extendTools(useSystemTools,useTerminal,setGoal)

    def __extendTools(self, useSystemTools:bool=False,useTerminal:bool=False,setGoal:bool=False):
        if useSystemTools:
            import tina.utils.systemTools
            SystemTools = [
                {
                    "name": "getTime",
                    "description": "获取当前时间",
                    "required_parameters": [],
                    "parameters": {},
                    "path": inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name": "shotdownSystem",
                    "description": "该工具会关闭计算机",
                    "required_parameters": [],
                    "parameters": {},
                    "path": inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"getSoftwareList",
                    "description":"获取系统软件列表",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"getSystemInfo",
                    "description":"获取系统信息",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"delay",
                    "description":"延时指定秒数",
                    "required_parameters":["seconds"],
                    "parameters":{
                        "seconds": {"type": "int", "description": "延时秒数"},
                        "why": {"type": "str", "description": "延时原因"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"startSoftware",
                    "description":"启动一个软件",
                    "required_parameters":["name"],
                    "parameters":{
                        "name": {"type": "str", "description": "软件名称"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"openFile",
                    "description":"打开一个文件",
                    "required_parameters":["path"],
                    "parameters":{
                        "path": {"type": "str", "description": "文件路径"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"getProcessList",
                    "description":"获取进程列表",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"killProcess",
                    "description":"结束一个进程",
                    "required_parameters":["pid"],
                    "parameters":{
                        "pid": {"type": "int", "description": "进程ID"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"getEnv",
                    "description":"获取环境变量",
                    "required_parameters":["var"],
                    "parameters":{
                        "var": {"type": "str", "description": "环境变量名称"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                },
                {
                    "name":"getDiskInfo",
                    "description":"获取磁盘信息",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.utils.systemTools)
                }
            ]
            self.multiregister(SystemTools)
            
        if useTerminal:
            import tina.utils.systemTools
            terminalTools =[
                {
                    "name":"terminal",
                    "description":"向终端发送一个指令",
                    "required_parameters":["command"],
                    "parameters":{
                        "command": {"type": "str", "description": "要发送的指令"}
                    },
                    "path":inspect.getfile(tina.utils.systemTools)
                }
            ]
            self.multiregister(terminalTools)
        if setGoal:
            GoalTools = [
                {
                    "name": "setGoal",
                    "description": "设置当前目标",
                    "required_parameters": ["goal"],
                    "parameters": {
                        "goal": {"type": "str", "description": "目标描述"}
                    }
                },
                {
                    "name":"cancelGoal",
                    "description":"取消当前目标",
                    "required_parameters":[],
                    "parameters":{}
                },
                {
                    "name":"updateGoalStatus",
                    "description":"更新目标达成情况和下一步指导",
                    "required_parameters":["status"],
                    "parameters":{
                        "status": {"type": "str", "description": "目标达成情况和下一步行动描述"}
                    }
                }
                ]
            self.multiregister(GoalTools)

    def multiregister(self, tools: list):
        """
        注册多个工具
        """
        for tool in tools:
            self.registerTool(
                name=tool["name"],
                description=tool["description"],
                required_parameters=tool.get("required_parameters", []),
                parameters=tool.get("parameters", {}),
                path=tool.get("path", None),
                post_handler=tool.get("post_handler", None)
            )

    def unregister(self, name: str):
        """
        注销工具
        Args:
            name (str): 工具名称
        """
        if name not in self.tools_name_list:
            raise ValueError("工具不存在")
        index = self.tools_name_list.index(name)
        del self.tools[index]
        del self.tools_name_list[index]
        del self.tools_parameters_list[index]
        del self.tools_path[name]
        return True
    
    def disable(self, name: str):
        """
        禁用工具（从工具列表中移除）
        Args:
            name (str): 工具名称
        """
        if name not in self.tools_name_list:
            return False
        for i in range(len(self.tools)):
            if self.tools[i]["function"]["name"] == name:
                del self.tools[i]
                break
        return True
        
    def enable(self, name: str):
        """
        启用工具（将工具添加回工具列表）
        Args:
            name (str): 工具名称
        """
        if name not in self.tools_name_list:
            return False
        # 检查工具是否已经在 tools 列表中
        for tool in self.tools:
            if tool["function"]["name"] == name:
                return True  # 已经启用，无需操作
        
        # 在 tools_name_list 中找到索引以获取完整工具定义
        index = self.tools_name_list.index(name)
        # 确保工具定义依然存在
        if index < len(self.tools_parameters_list):
            tool_info = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "",  # 这里可能需要保存描述以便恢复
                    "parameters": {}  # 这里需要重新构建参数
                }
            }
            self.tools.append(tool_info)
            return True
        return False

    def register(self, name=None, description=None, required_parameters:list=None, parameters:dict=None, path:str=None,post_handler:callable=None):
        """
        注册一个工具，既可以直接调用，也可以使用装饰器
        Args:
            name (str): 工具名称
            description (str): 工具描述
            required_parameters (list): 必填参数列表

                ["a", "b"] <- 像这样

            parameters (dict): 参数描述字典

                {

                    "a": {"type": "int", "description": "参数a的描述"},

                    "b": {"type": "str", "description": "参数b的描述"}
                    
                } <- 像这样
            path (str): 工具路径
            post_handler (callable, optional): 工具执行后的处理函数，用于处理工具返回的结果
        """
        def decorator(func):
            nonlocal name, description, required_parameters, parameters, path, post_handler
            doc = func.__doc__ or ""
            param_desc, return_desc = parse_docstring(doc)
            # 自动推导
            if name is None:
                name = func.__name__
            if description is None:
                description = func.__doc__ or f"{name}工具"
            sig = inspect.signature(func)
            if required_parameters is None:
                required_parameters = [p for p in sig.parameters if sig.parameters[p].default is inspect.Parameter.empty]
            if parameters is None:
                parameters = {}
                for p, v in sig.parameters.items():
                    parameters[p] = {
                        "type": str(v.annotation) if v.annotation != inspect.Parameter.empty else "str",
                        "description": param_desc.get(p, "")
                    }
            if path is None:
                path = inspect.getfile(func)
            # 注册
            self.registerTool(name, description, required_parameters, parameters, path, post_handler)
            decorator._original = func
            return func
        # 兼容直接调用
        if callable(name):
            # 直接@tools.register
            func = name
            name = None
            return decorator(func)
        
        return decorator

    def registerTool(self, name, description, required_parameters, parameters, path, post_handler:callable=None, tools:list=None):
        # 原有的注册逻辑
        if name in self.tools_name_list:
            self.unregister(name)
        self.tools_name_list.append(name)
        self.tools_parameters_list.append({
            "name": name,
            "parameters": [f"{k}:{v['type']}" for k, v in parameters.items()]
        })
        self.tools_path.update({name: path})
        self.post_handler.update({name: post_handler})
        self.tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "required": required_parameters,
                    "properties": parameters
                }
            }
        })
    def getPostHandler(self,name:str)->callable:
        """
        获取工具的后处理函数
        """
        return self.post_handler.get(name,None)
    def checkTools(self,name:str)->bool:
        """
        检查工具是否存在
        Args:
            name (str): 工具名称
        Returns:
            bool: 工具是否存在
        """
        return (name in self.tools_name_list)
    def queryParameterType(self,name:str,parameter_name:str)->str:
        """
        查询工具参数类型
        Returns:
            str: 工具参数类型
        """
        if name not in self.tools_name_list:
            raise ValueError("工具名称不存在")
        for tool in self.tools_parameters_list:
            if tool["name"] == name:
                for parameter in tool["parameters"]:
                    if parameter.split(":")[0] == parameter_name:
                        return parameter.split(":")[1]
        raise ValueError("参数名称不存在")
    def saveTools(self,file_path:str):
        """
        保存工具信息到文件
        Args:
            file_path (str): 文件路径
        """
        with open(file_path, "wb") as f:
            pickle.dump(self.tools, f)
         
    def getToolsPath(self,name:str)->str:
        """
        获取工具路径
        Args:
            name (str): 工具名称
        Returns:
            str: 工具路径
        """
        try:
            return self.tools_path[name]
        except KeyError:    
            raise ValueError("工具不存在")
    
    @staticmethod
    def loadToolsFromPyFile(file_path: str) -> 'Tools':
        """
        静态解析Python文件中的函数并注册工具
    
        参数：
            file_path: 需要解析的python文件路径
        
        返回：
            Tools实例（包含文件中所有函数的工具信息）
        """
        import ast
        import re
    
        def parse_docstring(doc: str) -> dict:
            params = {}
            if not doc:
                return params
            state = 0  # 0-等待参数段 1-解析参数中
            current_param = None
            param_pattern = re.compile(r"(\w+)\s*(?:$(.+?)$)?\s*:")
        
            for line in doc.split('\n'):
                line = line.strip()
                if 'args:' in line.lower():
                    state = 1
                    continue
                if state == 1 and not line:
                    break
                if state == 1:
                    match = param_pattern.match(line)
                    if match:
                        current_param = match.group(1)
                        param_type = match.group(2) or 'str'
                        desc = line.split(':', 1)[1].strip()
                        params[current_param] = {'type': param_type, 'desc': desc}
            return params

        tools = Tools()
        tool_list = []
    
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                doc = ast.get_docstring(node) or ""
                params_info = parse_docstring(doc)
            
                # 解析函数签名
                sig_params = {}
                required_params = []
                num_pos_args = len(node.args.args)
                num_defaults = len(node.args.defaults)
            
                # 收集参数信息
                for idx, arg in enumerate(node.args.args):
                    param_name = arg.arg
                    # 获取类型注解
                    param_type = ast.unparse(arg.annotation).strip() if arg.annotation else 'str'
                    # 从文档字符串获取类型覆盖
                    if param_name in params_info:
                        param_type = params_info[param_name].get('type', param_type)
                    # 判断是否必填参数
                    is_required = idx < (num_pos_args - num_defaults)
                    if is_required:
                        required_params.append(param_name)
                
                    sig_params[param_name] = {
                        "type": param_type,
                        "description": params_info.get(param_name, {}).get('desc', '')
                    }
            
                # 构建工具描述
                tool_desc = doc.split('\n')[0].strip() if doc else f"{node.name}函数"
            
                tool_list.append({
                    "name": node.name,
                    "description": tool_desc,
                    "required_parameters": required_params,
                    "parameters": sig_params,
                    "path": file_path
                })
    
        tools.multiregister(tool_list)
        return tools
    
    def getTools(self,enable:bool=True)->list:
        """返回工具"""
        return self.tools


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

if __name__ == "__main__":
    tools = Tools()
    tools.register("test", "测试工具", ["a", "b"], {"c": {"type": "int", "description": "参数c的描述"}})
    print(tools.tools)
    print(tools.tools_name_list)
    print(tools.tools_parameters_list)
    #查询工具参数
    print(tools.queryParameterType("test","c")) 