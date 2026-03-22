"""
Nebula Minecraft Server - 服务器状态管理模块
Copyright (C) 2026 BlackHoleEra-Team

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
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
