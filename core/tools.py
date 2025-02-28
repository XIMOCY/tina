"""
编写者：王出日
日期：2024，12，1
版本？
描述：
注册工具类
包含：
tools
"""
import pickle
import inspect
import tina.RAG.query.query
import tina.tools.systemTools
class Tools:
    def __init__(self,isSystemTools=False,isRAG = False):
        self.tools = [{
            "type": "function",
            "function": {
                "name": "NULLTools",
                "description": "防止出现工具错误，无任何内容的工具，当agent发现没有可以调用的工具调用这个",
                "parameters": {}
            }
        }]
        self.tools_name_list = ["NULLTools"]
        self.tools_parameters_list = []
        self.tools_path = []
        self.extendTools(isSystemTools, isRAG)

    def extendTools(self, isSystemTools, isRAG):
        if isSystemTools:
            SystemTools = [
                {
                    "name": "getTime",
                    "description": "获取当前时间",
                    "required_parameters": [],
                    "parameters": {},
                    "path": inspect.getfile(tina.RAG.query.query)
                },
                {
                    "name": "shotdownSystem",
                    "description": "该工具会关闭计算机",
                    "required_parameters": [],
                    "parameters": {},
                    "path": inspect.getfile(tina.tools.systemTools)
                },
                {
                    "name":"getSoftwareList",
                    "description":"获取系统软件列表",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.tools.systemTools)
                },
                {
                    "name":"getSystemInfo",
                    "description":"获取系统信息",
                    "required_parameters":[],
                    "parameters":{},
                    "path":inspect.getfile(tina.tools.systemTools)
                }
            ]
            self.multiregister(SystemTools)
        if isRAG:
            RAGTools =[
                            {
                                "name": "query",
                                "description": "使用该工具可以在用户的文档里面查询有关信息",
                                "required_parameters": ["query_text"],
                                "parameters": {
                                "query_text": {"type": "str", "description": "要查询的文本"},
                                "n": {"type": "int", "description": "返回的结果数量,默认为10"}
                                },
                            "path": inspect.getfile(tina.RAG.query.query)
                            }
                        ]
            self.multiregister(RAGTools)

    def multiregister(self, tools: list):
        for tool in tools:
            self.register(
                name=tool["name"],
                description=tool["description"],
                required_parameters=tool.get("required_parameters", []),
                parameters=tool.get("parameters", {}),
                path=tool.get("path", None)
            )

    def register(self, name:str, description:str, required_parameters:list, parameters:dict,path:str=None):
        """
        注册工具，将工具信息添加到tools列表中
        Args:
            name (str): 函数的名称，一定要正确
            description (str): 函数的描述，可以详细描述函数的功能
            required_parameters (list): 一定要有输入的参数列表
            parameters (dict): 参数的详细信息，所有的参数都要有类型和描述
                格式：
                    {
                    "参数名": {
                        "type": "参数类型",
                        "description": "参数描述"
                        }
                    }
            path (str): 工具的路径，如果没有则为None
        Raises:
            ValueError: 如果输入参数不符合要求
        """
        # 验证输入参数的有效性
        if not isinstance(name, str) or not name:
            raise ValueError("函数名称必须是非空字符串")
        if not isinstance(description, str):
            raise ValueError("函数描述必须是字符串")
        if not isinstance(required_parameters, list):
            raise ValueError("必需参数必须是一个列表")
        if not isinstance(parameters, dict):
            raise ValueError("参数必须是一个字典")
        #将名称添加到tools_list中
        self.tools_name_list.append(name)
        # 将参数信息添加到tools_parameters_dict中
        self.tools_parameters_list.append(
            {
                "name": name,
                "parameters":[f"{k}:{v['type']}" for k,v in parameters.items()] 
            }
        )
        # 如果有路径，则添加到tools_path中
        self.tools_path.append(
            {
                "name": name,
                "path": path
            }
        )
        # 将工具信息添加到tools列表中
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
    
    def loadToolsInfoFromFile(self,file_path:str):
        """
        从文件中加载工具信息
        Args:
            file_path (str): 文件路径
        """
        with open(file_path, "rb") as f:
            self.tools = pickle.load(f)    
        
    def getToolsPath(self,name:str)->str:
        """
        获取工具路径
        Args:
            name (str): 工具名称
        Returns:
            str: 工具路径
        """
        for tool in self.tools_path:
            if tool["name"] == name:
                return tool["path"]
                
        raise ValueError("工具不存在")
    


if __name__ == "__main__":
    tools = Tools()
    tools.register("test", "测试工具", ["a", "b"], {"c": {"type": "int", "description": "参数c的描述"}})
    print(tools.tools)
    print(tools.tools_name_list)
    print(tools.tools_parameters_list)
    #查询工具参数
    print(tools.queryParameterType("test","c")) 