"""
EULA检查模块
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
