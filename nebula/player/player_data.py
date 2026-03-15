"""
玩家数据管理
保存和加载玩家位置、游戏模式等数据
"""

import os
import json
from typing import Optional, Dict, Any
from nebula.logging import log_info, log_error


class PlayerDataManager:
    """
    玩家数据管理器
    负责保存和加载玩家数据
    """
    
    def __init__(self, world_folder: str):
        self.world_folder = world_folder
        self.playerdata_folder = os.path.join(world_folder, "playerdata")
        
        # 确保文件夹存在
        os.makedirs(self.playerdata_folder, exist_ok=True)
    
    def _get_player_file(self, uuid: str) -> str:
        """获取玩家数据文件路径"""
        return os.path.join(self.playerdata_folder, f"{uuid}.dat")
    
    def save_player_data(self, uuid: str, data: Dict[str, Any]):
        """保存玩家数据"""
        try:
            file_path = self._get_player_file(uuid)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            log_info(f"Saved player data for {uuid}")
        except Exception as e:
            log_error(f"Error saving player data for {uuid}: {e}")
    
    def load_player_data(self, uuid: str) -> Optional[Dict[str, Any]]:
        """加载玩家数据"""
        try:
            file_path = self._get_player_file(uuid)
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            log_info(f"Loaded player data for {uuid}")
            return data
        except Exception as e:
            log_error(f"Error loading player data for {uuid}: {e}")
            return None


# 全局实例
_player_data_manager: Optional[PlayerDataManager] = None


def init_player_data_manager(world_folder: str):
    """初始化玩家数据管理器"""
    global _player_data_manager
    _player_data_manager = PlayerDataManager(world_folder)


def get_player_data_manager() -> PlayerDataManager:
    """获取玩家数据管理器"""
    global _player_data_manager
    if _player_data_manager is None:
        raise RuntimeError("PlayerDataManager not initialized")
    return _player_data_manager
