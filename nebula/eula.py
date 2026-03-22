"""
Nebula Minecraft Server - EULA检查模块
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

import os

from nebula.core.constants import EULA_LINK
from nebula.logging import log_info, log_warn, log_error

EULA_TEXT = f"""# By changing the setting below to TRUE you are indicating your agreement to our EULA ({EULA_LINK}).
# If you do not agree, please stop the server and delete this file.
eula=true
"""


def check_eula():
    """检查EULA是否已同意"""
    if os.path.exists("eula.txt"):
        with open("eula.txt", 'r', encoding='utf-8') as f:
            content = f.read()
            if 'eula=true' in content.lower():
                return True
    return False


def create_eula():
    """创建EULA文件"""
    with open("eula.txt", 'w', encoding='utf-8') as f:
        f.write(EULA_TEXT)


def first_start():
    """首次启动处理"""
    if not os.path.exists("eula.txt"):
        log_info("=" * 60)
        log_info("Welcome to Nebula Server!")
        log_info("")
        log_info("You need to agree to the Minecraft EULA to run this server.")
        log_info(f"Read it here: {EULA_LINK}")
        log_info("")
        log_info("Setting eula=true in eula.txt...")
        log_info("=" * 60)
        create_eula()
        log_info("EULA file created. Server will start...")
    elif not check_eula():
        log_error("=" * 60)
        log_error("You have not agreed to the EULA!")
        log_error(f"Please read {EULA_LINK}")
        log_error("and set eula=true in eula.txt")
        log_error("=" * 60)
        return False
    return True
