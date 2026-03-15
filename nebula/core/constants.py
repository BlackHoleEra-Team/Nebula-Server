"""
核心常量定义模块
对应Minecraft 1.12.2版本
"""

import sys
import os

# -- 日志常量 --
LOG_FORMAT = '[%(asctime)s %(levelname)s]: %(message)s'
DATE_FORMAT = '%H:%M:%S'

# -- EULA相关常量 --
EULA_LINK = "https://aka.ms/MinecraftEULA"

# -- IDE开发模式检测 --
IS_RUNNING_IN_IDE = sys.flags.interactive == 1 or 'PYCHARM_HOSTED' in os.environ or 'VSCODE_PID' in os.environ

# -- 服务器基本信息 --
VERSION = "0.0.1-Alpha"

# -- Minecraft 1.12.2 协议相关 --
PROTOCOL_VERSION = 340  # 1.12.2 协议版本号
MINECRAFT_VERSION_NAME = "1.12.2"

# -- 默认服务器配置 --
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 25565
DEFAULT_ONLINE_MODE = False
DEFAULT_MAX_PLAYERS = 20
DEFAULT_MOTD = "§cNebula §71.12.2 §fServer"
DEFAULT_FAVICON_BASE64 = ""

# -- 游戏相关常量 --
CHUNK_SECTION_SIZE = 16  # 区块段大小
MAX_BUILD_HEIGHT = 256   # 1.12.2最大建筑高度
MIN_BUILD_HEIGHT = 0     # 1.12.2最小建筑高度
