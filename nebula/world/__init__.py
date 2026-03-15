"""
世界管理模块
处理世界生成、区块加载/保存、地形生成等功能
"""

from .world_manager import WorldManager, get_world_manager
from .chunk import Chunk
from .anvil import AnvilRegion

__all__ = ['WorldManager', 'get_world_manager', 'Chunk', 'AnvilRegion']
