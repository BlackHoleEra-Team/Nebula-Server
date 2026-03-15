"""
服务器状态管理模块
管理服务器的全局运行时状态
参考Minecraft官方状态管理模式
"""


class ServerState:
    """服务器状态类，用于管理全局状态"""
    def __init__(self):
        self.running = True
    
    def stop(self):
        """停止服务器"""
        self.running = False
    
    def is_running(self):
        """检查服务器是否正在运行"""
        return self.running


# 全局服务器状态实例
server_state = ServerState()

# 向后兼容的变量
running = True
