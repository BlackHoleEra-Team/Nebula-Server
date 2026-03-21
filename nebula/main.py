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
        
        # 7. 主循环
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
        server_socket.close()
        log_info("Server stopped.")


if __name__ == "__main__":
    start_server()
