#!/usr/bin/env python3
"""
Nebula Minecraft Server 1.12.2
启动脚本
"""

import sys
import os

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nebula.main import start_server

if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
