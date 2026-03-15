"""
日志工具模块
参考Minecraft官方日志系统，提供统一的日志管理
"""

import logging
import logging.handlers
import os
import re
import sys
from datetime import datetime, timezone

from nebula.core.constants import LOG_FORMAT, DATE_FORMAT


def setup_logging():
    """初始化日志系统，包括日志文件管理和控制台输出"""
    os.makedirs('logs', exist_ok=True)

    # 处理旧的latest.log文件
    if os.path.exists("logs/latest.log"):
        try:
            with open("logs/latest.log", "r", encoding="utf-8") as old_log:
                old_log_first_line = next(old_log, None)

            if not old_log_first_line:
                print(f"[{datetime.now().strftime('%H:%M:%S')} WARN]: Old latest.log appears empty; skipping log renaming(No first line found in log file)")
            else:
                # 提取时间字符串（兼容行尾空格）
                match = re.search(r"#Create at (.*)", old_log_first_line.strip())
                if not match:
                    print(f"[{datetime.now().strftime('%H:%M:%S')} WARN]: Old latest.log has no valid create time; skipping log renaming")
                else:
                    # 解析时间（保留UTC时区，避免解析错误）
                    time_str = match.group(1).strip()
                    try:
                        # 完整解析带UTC的时间字符串
                        dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %Z %Y")
                        dt = dt.replace(tzinfo=timezone.utc)  # 强制设置UTC时区
                        # 生成新文件名
                        new_log_filename = dt.strftime("%Y-%m-%d-%H-%M-%S-UTC.log")
                        new_log_path = f"logs/{new_log_filename}"

                        # 重命名旧日志（避免覆盖已存在的文件）
                        if not os.path.exists(new_log_path):
                            os.rename("logs/latest.log", new_log_path)
                            print(f"[{datetime.now().strftime('%H:%M:%S')} INFO]: Old log renamed to {new_log_filename}")
                        else:
                            print(f"[{datetime.now().strftime('%H:%M:%S')} WARN]: {new_log_filename} already exists; skip renaming")

                    except ValueError as e:
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')} ERROR]: Failed to parse log create time: {e}; skipping log renaming")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')} ERROR]: Error loading OLD latest.log: {e}; old log may be discarded")

    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    # 控制台处理器
    c_h = logging.StreamHandler(sys.stdout)
    c_h.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(c_h)

    # 清理旧的latest.log（如果有）
    if os.path.exists("logs/latest.log"):
        try:
            os.remove("logs/latest.log")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')} ERROR]: Failed to delete old latest.log: {str(e)}")

    # 创建新的日志文件
    with open("logs/latest.log", "w", encoding="utf-8") as logfile:
        logfile.write(f"#Create at {datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y')}\n")
        logfile.write("#WARNING: Please DO NOT remove or modify the above timestamp line,This action may lead to permanent loss of old log files.\n")

    # 文件处理器
    f_h = logging.FileHandler('logs/latest.log', encoding='UTF-8')
    f_h.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(f_h)


def log_info(msg):
    """记录信息级别日志"""
    logging.info(msg)


def log_warn(msg):
    """记录警告级别日志"""
    logging.warning(msg)


def log_error(msg):
    """记录错误级别日志"""
    logging.error(msg)
