"""
玩家管理器
管理所有在线玩家
"""

import time
import struct
from typing import Dict, Optional
from nebula.logging import log_info, log_error
from .player import Player


class PlayerManager:
    """
    玩家管理器
    """
    
    def __init__(self):
        self.players: Dict[str, Player] = {}  # username -> Player
        self.players_by_entity: Dict[int, Player] = {}  # entity_id -> Player
    
    def add_player(self, username: str, entity_id: int, conn=None) -> Player:
        """添加玩家"""
        player = Player(username, entity_id, conn)
        self.players[username] = player
        self.players_by_entity[entity_id] = player
        log_info(f"Player added: {username} (entity_id={entity_id})")
        return player
    
    def remove_player(self, username: str):
        """移除玩家"""
        if username in self.players:
            player = self.players[username]
            del self.players_by_entity[player.entity_id]
            del self.players[username]
            log_info(f"Player removed: {username}")
    
    def get_player(self, username: str) -> Optional[Player]:
        """获取玩家"""
        return self.players.get(username)
    
    def get_player_by_entity(self, entity_id: int) -> Optional[Player]:
        """通过实体ID获取玩家"""
        return self.players_by_entity.get(entity_id)
    
    def update_player_position(self, username: str, x: float, y: float, z: float, 
                               yaw: float = None, pitch: float = None, on_ground: bool = True):
        """更新玩家位置"""
        player = self.get_player(username)
        if player:
            player.update_position(x, y, z, yaw, pitch, on_ground)
    
    def handle_player_move(self, username: str, packet_data: bytes, packet_id: int):
        """
        处理玩家移动包
        packet_id:
        - 0x0D: Player Position And Look (x, y, z, yaw, pitch, on_ground)
        - 0x0E: Player Position (x, y, z, on_ground)
        - 0x0F: Player Look (yaw, pitch, on_ground)
        """
        player = self.get_player(username)
        if not player:
            return
        
        try:
            offset = 1  # 跳过packet_id
            
            if packet_id == 0x0D:  # Player Position And Look
                # 1.12.2 格式: x(double), y(double), z(double), yaw(float), pitch(float), on_ground(bool) = 33 bytes
                # 但有些客户端可能发送不同格式，需要动态处理
                remaining = len(packet_data) - offset
                
                if remaining >= 33:  # 完整格式
                    x = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    y = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    z = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    yaw = struct.unpack('>f', packet_data[offset:offset+4])[0]
                    offset += 4
                    pitch = struct.unpack('>f', packet_data[offset:offset+4])[0]
                    offset += 4
                    on_ground = packet_data[offset] != 0
                    player.update_position(x, y, z, yaw, pitch, on_ground)
                elif remaining >= 25:  # 只有位置，没有旋转
                    x = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    y = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    z = struct.unpack('>d', packet_data[offset:offset+8])[0]
                    offset += 8
                    on_ground = packet_data[offset] != 0
                    player.update_position(x, y, z, player.yaw, player.pitch, on_ground)
                else:
                    log_error(f"Packet 0x0D too short: {len(packet_data)} bytes, remaining={remaining}")
                    return
                
            elif packet_id == 0x0E:  # Player Position
                # 检查数据长度
                if len(packet_data) < offset + 8 + 8 + 8 + 1:
                    log_error(f"Packet 0x0E too short: {len(packet_data)} bytes")
                    return
                # x (double), y (double), z (double), on_ground (bool)
                x = struct.unpack('>d', packet_data[offset:offset+8])[0]
                offset += 8
                y = struct.unpack('>d', packet_data[offset:offset+8])[0]
                offset += 8
                z = struct.unpack('>d', packet_data[offset:offset+8])[0]
                offset += 8
                on_ground = packet_data[offset] != 0
                
                player.update_position(x, y, z, player.yaw, player.pitch, on_ground)
                
            elif packet_id == 0x0F:  # Player Look
                # 检查数据长度
                if len(packet_data) < offset + 4 + 4 + 1:
                    log_error(f"Packet 0x0F too short: {len(packet_data)} bytes")
                    return
                # yaw (float), pitch (float), on_ground (bool)
                yaw = struct.unpack('>f', packet_data[offset:offset+4])[0]
                offset += 4
                pitch = struct.unpack('>f', packet_data[offset:offset+4])[0]
                offset += 4
                on_ground = packet_data[offset] != 0
                
                player.update_position(player.x, player.y, player.z, yaw, pitch, on_ground)
                
        except Exception as e:
            log_error(f"Error handling player move for {username}: {e}")
    
    def handle_player_abilities(self, username: str, packet_data: bytes):
        """
        处理玩家能力包（飞行状态）
        0x13: Player Abilities
        """
        player = self.get_player(username)
        if not player:
            return
        
        try:
            # flags (byte), flying speed (float), walking speed (float)
            flags = packet_data[1]
            # bit 0: invulnerable
            # bit 1: flying
            # bit 2: allow flying
            # bit 3: creative mode
            
            is_flying = (flags & 0x02) != 0
            player.set_flying(is_flying)
            
            log_info(f"Player {username} flying: {is_flying}")
            
        except Exception as e:
            log_error(f"Error handling player abilities for {username}: {e}")
    
    def update_all_physics(self, delta_time: float):
        """更新所有玩家的物理状态"""
        for player in self.players.values():
            player.update_physics(delta_time)
    
    def get_online_count(self) -> int:
        """获取在线玩家数"""
        return len(self.players)
    
    def get_all_players(self) -> Dict[str, Player]:
        """获取所有玩家"""
        return self.players.copy()


# 全局玩家管理器实例
_player_manager: Optional[PlayerManager] = None


def get_player_manager() -> PlayerManager:
    """获取全局玩家管理器实例"""
    global _player_manager
    if _player_manager is None:
        _player_manager = PlayerManager()
    return _player_manager
