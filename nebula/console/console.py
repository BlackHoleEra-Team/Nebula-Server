"""
控制台命令处理模块
实现服务器的交互式控制台和命令系统
"""

from nebula.core.constants import VERSION, MINECRAFT_VERSION_NAME
from nebula.logging import log_info
from nebula.util.state import server_state


def stop_server():
    """停止服务器"""
    log_info("Stopping Server...")
    server_state.stop()


def console_handler():
    """控制台命令处理器主循环"""

    def cmd_version():
        """显示服务器版本信息"""
        log_info(f"Nebula Server Version {VERSION}")
        log_info(f"Compatible Minecraft Client Version {MINECRAFT_VERSION_NAME}")

    def cmd_help():
        """显示帮助信息"""
        log_info("Available commands:")
        # 收集每个函数的主命令名和描述
        items = []
        for func, desc in command_descriptions.items():
            # 找出这个函数的所有别名
            aliases = [name for name, f in commands.items() if f == func]
            primary = aliases[0]  # 取第一个作为主命令名
            alias_str = f" (aliases: {', '.join(aliases[1:])})" if len(aliases) > 1 else ""
            items.append((primary, desc + alias_str))
        # 按命令名称排序输出
        for primary, desc in sorted(items):
            log_info(f"  {primary:<12} - {desc}")

    # 命令映射表
    commands = {
        "version": cmd_version,
        "ver": cmd_version,
        "help": cmd_help,
        "h": cmd_help,
        "?": cmd_help,
        "stop": stop_server,
    }

    # 命令描述映射表
    command_descriptions = {
        cmd_version: "Display server version and compatible Minecraft client version",
        cmd_help: "Display this help message",
        stop_server: "Stop the server",
    }

    # 主循环
    while True:
        if not server_state.is_running():
            break
        try:
            cmd = input("> ")
            if not cmd:  # 空输入直接忽略
                continue
            if cmd in commands:
                commands[cmd]()
            else:
                log_info("Unknown command. Type 'help' for list.")
        except (EOFError, KeyboardInterrupt):
            break
