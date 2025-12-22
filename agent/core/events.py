import inspect

class Events:
    def __init__(self):
        """
        事件管理器
        注意：异步的事件处理函数只会在使用了异步方法的时候起作用
        同步的事件处理函数会在异步和同步的方法里面都执行
        如果要在同步的调用中使用异步的事件处理函数，请自己包裹为同步方法
        """
        
        self.event_handler = {
            # 发生了工具执行之前
            'before_tool_call':[],
            # 发生了工具执行之后
            # 要求监听者接受工具名称和结果
            'after_tool_call':[],
            # 发生了工具调用之前
            'before_tool_calls':[],
            # 发生了工具调用之后
            'after_tool_calls':[],
            # 发生了用户输入之前
            'before_user_instruction':[],
            # 发生了用户输入之后
            # 要求监听者接受用户输入，默认str
            'after_user_instruction':[],
            # 如果工具需要验证的情况，请监听此事件
            'on_tool_confirmation':None,

        }

    def get_handler(self,event_name:str):
        return self.event_handler[event_name]
    def get_tool_confirmation_handler(self):
        return self.event_handler['on_tool_confirmation']
    def _validate_event_handler_signature(self, event_name: str, func: callable):
        """
        验证事件处理函数的签名是否符合要求
        """
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
    
        # 定义各事件的参数要求
        event_requirements = {
            'before_tool_call': {
                'min_params': 2,
                'param_types': [str,dict]  # 简化检查，实际可能需要更详细的类型检查
            },
            'after_tool_call': {
                'min_params': 3,
                'param_types': [str,dict,any]
            },
            'before_tool_calls':{
                'min_params': 1,
                'param_types': [list]
            },
            'after_tool_calls':{
                'min_params': 1,
                'param_types': [list]
            },
            'before_user_instruction': {
                'min_params': 1,
                'param_types': [str]
            },
            'after_user_instruction': {
                'min_params': 2,
                'param_types': [str,str]
            },
            'on_tool_confirmation': {
                'min_params': 2,
                'param_types': [str,dict]
            }
        }
    
        if event_name not in event_requirements:
            return  # 未知事件类型，跳过验证
        
        requirements = event_requirements[event_name]
    
        # 检查参数数量
        if len(params) < requirements['min_params']:
            raise ValueError(f'{event_name} 事件处理函数至少需要 {requirements["min_params"]} 个参数')
    
   
    def add_handler(self,event_name:str,func):
        self.event_handler[event_name].append(func)

    def before_tool_call(self):
        """
        在执行工具调用之 前  
        需要事件处理函数接受下面的参数：  
        tool_name: str,tool_arguments: dict,
        """
        def wrapper(func):
            self._validate_event_handler_signature('before_tool_call',func)
            self.add_handler('before_tool_call',func)
            return func
        return wrapper
    
    def after_tool_call(self):
        """
        在执行工具调用之 后
        需要事件处理函数接受下面的参数：  
        tool_name: str,tool_arguments: dict,tool_result: any
        """
        def wrapper(func):
            self._validate_event_handler_signature('after_tool_call',func)
            self.add_handler('after_tool_call',func)
            return func
        return wrapper
    
    def before_tool_calls(self):
        """
        在工具调用被大模型处理之前
        需要事件处理函数接受下面的参数：  
        tool_calls: list[dict[str,str]]
        """
        def wrapper(func):
            self._validate_event_handler_signature('before_tool_calls',func)
            self.add_handler('before_tool_calls',func)
            return func
        return wrapper
    
    def after_tool_calls(self):
        """
        在工具调用被大模型处理之后
        需要事件处理函数接受下面的参数：  
        tool_calls: list[dict[str,str]]
        """
        def wrapper(func):
            self._validate_event_handler_signature('after_tool_calls',func)
            self.add_handler('after_tool_calls',func)
            return func
        return wrapper
    
    def on_tool_confirmation(self):
        """
        如果一个工具被登记为需要验证猜可以运行，请监听此事件  
        需要事件处理函数接受下面的参数：  
        tool_name: str tool_arguments: dict
        """
        def wrapper(func):
            self._validate_event_handler_signature("on_tool_confirmation",func)
            self.event_handler["on_tool_confirmation"] = func
            return func
        return wrapper
    
    def before_user_instruction(self):
        """
        在用户输入被大模型处理之前
        需要事件处理函数接受下面的参数：  
        user_message: str
        """
        def wrapper(func):
            self.add_handler('before_user_instruction',func)
            return func
        return wrapper
    
    def after_user_instruction(self):
        """
        在用户输入被大模型处理之后
        需要事件处理函数接受下面的参数：  
        user_message: str assistant_message: str
        """
        def wrapper(func):
            self.add_handler('after_user_instruction',func)
            return func
        return wrapper
    
    

            

