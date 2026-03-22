"""
Nebula Minecraft Server - 服务器配置管理模块
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

import configparser
import os

from nebula.core.constants import (
    DEFAULT_HOST, DEFAULT_PORT, DEFAULT_MAX_PLAYERS,
    DEFAULT_MOTD, DEFAULT_ONLINE_MODE, DEFAULT_FAVICON_BASE64
)
from nebula.logging import log_info, log_warn, log_error

# -- 服务器运行时配置 --
HOST = DEFAULT_HOST
PORT = DEFAULT_PORT
MAX_PLAYERS = DEFAULT_MAX_PLAYERS
MOTD = DEFAULT_MOTD
ONLINE_MODE = DEFAULT_ONLINE_MODE
FAVICON_BASE64 = DEFAULT_FAVICON_BASE64
ONLINE_PLAYERS = 0
WORLD_NAME = "world"


def load_server_properties():
    """从server.properties读取配置"""
    global HOST, PORT, MAX_PLAYERS, MOTD, ONLINE_MODE, FAVICON_BASE64

    if not os.path.exists("server.properties"):
        log_error("=" * 60)
        log_error("Critical: server.properties file is missing!")
        log_error("Please restart the server to generate default config.")
        log_error("=" * 60)
        return False

    try:
        config = configparser.ConfigParser()
        with open("server.properties", 'r', encoding='utf-8') as f:
            config.read_string('[DEFAULT]\n' + f.read())

        # 读取配置
        port_str = config.get('DEFAULT', 'server-port', fallback=str(PORT)).strip()
        try:
            PORT = int(port_str)
        except ValueError:
            log_warn(f"Invalid server-port value '{port_str}', using default {DEFAULT_PORT}")
            PORT = DEFAULT_PORT

        HOST = config.get('DEFAULT', 'server-ip', fallback=HOST).strip() or HOST
        MAX_PLAYERS = config.getint('DEFAULT', 'max-players', fallback=MAX_PLAYERS)
        MOTD = config.get('DEFAULT', 'motd', fallback=MOTD)
        ONLINE_MODE = config.getboolean('DEFAULT', 'online-mode', fallback=ONLINE_MODE)

        log_info(f"Loaded server.properties: {HOST}:{PORT}, max-players={MAX_PLAYERS}")
        return True

    except Exception as e:
        log_error(f"Error loading server.properties: {e}")
        return False


def create_default_server_properties():
    """创建默认的server.properties文件"""
    if os.path.exists("server.properties"):
        return

    content = f"""# Nebula Server Configuration
# {DEFAULT_MOTD}

server-ip={DEFAULT_HOST}
server-port={DEFAULT_PORT}
max-players={DEFAULT_MAX_PLAYERS}
online-mode={str(DEFAULT_ONLINE_MODE).lower()}
motd={DEFAULT_MOTD}
"""
    with open("server.properties", 'w', encoding='utf-8') as f:
        f.write(content)
    log_info("Created default server.properties")
