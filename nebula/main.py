"""
Nebula Minecraft Server 1.12.2
主服务器入口
"""

import socket
import threading
import sys
import time

from nebula.core.constants import VERSION, MINECRAFT_VERSION_NAME, PROTOCOL_VERSION
from nebula.eula import first_start
from nebula.config.config import load_server_properties, create_default_server_properties, HOST, PORT
from nebula.network.client_handler import handle_client
from nebula.logging import log_info, log_error, setup_logging
from nebula.console.console import console_handler
from nebula.util.state import server_state


def start_server():
    """启动服务器"""
    # 记录启动开始时间
    start_time = time.time()
    
    # 初始化日志系统
    setup_logging()
    
    log_info("=" * 60)
    log_info(f"Starting Nebula Server {VERSION}")
    log_info(f"Minecraft Version: {MINECRAFT_VERSION_NAME} (Protocol {PROTOCOL_VERSION})")
    log_info("=" * 60)
    
    # 1. 检查EULA
    if not first_start():
        return
    
    # 2. 创建默认配置文件
    create_default_server_properties()
    
    # 3. 加载配置
    if not load_server_properties():
        log_error("Failed to load server configuration!")
        return
    
    # 4. 创建socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        # 5. 绑定并监听
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        server_socket.settimeout(1)
        
        # 计算启动耗时
        startup_time = time.time() - start_time
        
        log_info("")
        log_info(f"Done ({startup_time:.3f}s)! For help, type \"help\"")
        log_info(f"Server is running on {HOST}:{PORT}")
        log_info("")
        
        # 6. 启动控制台线程
        console_thread = threading.Thread(target=console_handler, daemon=True)
        console_thread.start()
        
        # 7. 启动游戏 tick 线程（时间流逝）
        def game_tick_loop():
            """游戏主循环 - 处理时间流逝（参考原版 Minecraft 逻辑）"""
            from nebula.world.world_manager import get_world_manager
            tick_count = 0
            while server_state.is_running():
                time.sleep(0.05)  # 20 ticks per second
                world_manager = get_world_manager()
                if world_manager:
                    # 每 tick 增加总游戏时间（总是增加）
                    world_manager.world_total_time += 1
                    
                    # 日夜循环时间总是增加（冻结通过发送负数实现，而不是停止增加）
                    world_manager.world_time = (world_manager.world_time + 1) % 24000
                    
                    # 每 20 ticks (1秒) 广播一次时间更新
                    tick_count += 1
                    if tick_count >= 20:
                        world_manager.broadcast_time_update()
                        tick_count = 0
        
        tick_thread = threading.Thread(target=game_tick_loop, daemon=True)
        tick_thread.start()
        
        # 8. 主循环
        while server_state.is_running():
            try:
                conn, addr = server_socket.accept()
                # 为每个连接创建新线程
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
                
            except socket.timeout:
                continue
            except OSError:
                # 服务器关闭时socket会被关闭
                break
                
    except KeyboardInterrupt:
        log_info("\nStopping server...")
    except Exception as e:
        log_error(f"Server error: {e}")
    finally:
        # 保存世界数据
        from nebula.world.world_manager import get_world_manager
        world_manager = get_world_manager()
        if world_manager:
            log_info("Saving world data...")
            world_manager.save_all()
        
        server_socket.close()
        log_info("Server stopped.")


if __name__ == "__main__":
    start_server()
