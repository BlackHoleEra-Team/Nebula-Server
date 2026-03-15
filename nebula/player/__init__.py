"""
玩家管理模块
处理玩家状态、位置、移动等
"""

from .player_manager import PlayerManager, get_player_manager
from .player import Player

__all__ = ['PlayerManager', 'get_player_manager', 'Player']
