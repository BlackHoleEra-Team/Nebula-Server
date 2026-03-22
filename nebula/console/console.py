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
        # 按命令名称排序输出
        for cmd_name in sorted(command_descriptions.keys()):
            desc = command_descriptions[cmd_name]
            # 找出这个命令的所有别名
            aliases = [name for name, f in commands.items() if name != cmd_name and f == commands.get(cmd_name)]
            alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
            log_info(f"  {cmd_name:<12} - {desc}{alias_str}")

    def cmd_time(args):
        """查看或设置世界时间"""
        from nebula.world.world_manager import get_world_manager
        world_manager = get_world_manager()
        
        if not args:
            # 显示当前时间
            current_time = int(world_manager.world_time) if world_manager else 6000
            total_ticks = int(world_manager.world_total_time) if world_manager else 0
            log_info(f"Current time: {current_time} (0=sunrise, 6000=noon, 12000=sunset, 18000=midnight)")
            log_info(f"Total ticks: {total_ticks}")
            return
        
        # 设置时间
        time_arg = args[0].lower()
        if time_arg == 'day':
            new_time = 1000
        elif time_arg == 'night':
            new_time = 13000
        elif time_arg == 'noon':
            new_time = 6000
        elif time_arg == 'midnight':
            new_time = 18000
        else:
            try:
                new_time = int(time_arg)
            except ValueError:
                log_info("Usage: time [day|night|noon|midnight|<number>]")
                return
        
        if world_manager:
            world_manager.world_time = new_time % 24000
            world_manager.broadcast_time_update()
            log_info(f"Time set to: {new_time}")

    def cmd_gamerule(args):
        """查看或设置游戏规则"""
        from nebula.world.world_manager import get_world_manager
        world_manager = get_world_manager()
        
        if not world_manager:
            log_info("World not initialized")
            return
        
        if not args:
            # 显示所有游戏规则
            log_info("Game rules:")
            for rule, value in world_manager.game_rules.items():
                log_info(f"  {rule}: {value}")
            return
        
        if len(args) == 1:
            # 显示特定规则
            rule = args[0]
            if rule in world_manager.game_rules:
                log_info(f"{rule}: {world_manager.game_rules[rule]}")
            else:
                log_info(f"Unknown game rule: {rule}")
            return
        
        # 设置规则
        rule = args[0]
        value = args[1].lower()
        
        if rule not in world_manager.game_rules:
            log_info(f"Unknown game rule: {rule}")
            return
        
        # 转换值为布尔值或保持字符串
        if value in ('true', '1', 'yes'):
            world_manager.game_rules[rule] = True
        elif value in ('false', '0', 'no'):
            world_manager.game_rules[rule] = False
        else:
            world_manager.game_rules[rule] = value
        
        log_info(f"Game rule {rule} set to: {world_manager.game_rules[rule]}")

    # 命令映射表
    commands = {
        "version": cmd_version,
        "ver": cmd_version,
        "help": cmd_help,
        "h": cmd_help,
        "?": cmd_help,
        "stop": stop_server,
    }

    # 命令描述映射表 - 使用命令名作为key，而不是函数
    command_descriptions = {
        "version": "Display server version and compatible Minecraft client version",
        "help": "Display this help message",
        "stop": "Stop the server",
        "time": "Show or set world time (time [day|night|noon|midnight|<number>])",
        "gamerule": "Show or set game rules (gamerule [rule] [value])",
    }

    # 主循环
    while True:
        if not server_state.is_running():
            break
        try:
            cmd_line = input("> ")
            if not cmd_line:  # 空输入直接忽略
                continue
            
            # 解析命令和参数
            parts = cmd_line.split()
            cmd = parts[0]
            args = parts[1:] if len(parts) > 1 else []
            
            if cmd == "time":
                cmd_time(args)
            elif cmd == "gamerule":
                cmd_gamerule(args)
            elif cmd in commands:
                commands[cmd]()
            else:
                log_info("Unknown command. Type 'help' for list.")
        except (EOFError, KeyboardInterrupt):
            break
