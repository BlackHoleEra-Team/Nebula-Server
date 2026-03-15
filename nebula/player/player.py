"""
玩家类
表示一个在线玩家
"""

import time
from typing import Optional


class Player:
    """
    玩家实体
    """
    
    def __init__(self, username: str, entity_id: int, conn=None):
        self.username = username
        self.entity_id = entity_id
        self.conn = conn
        
        # 位置
        self.x = 0.5
        self.y = 65.0
        self.z = 0.5
        self.yaw = 0.0
        self.pitch = 0.0
        
        # 速度
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        
        # 状态
        self.on_ground = False
        self.is_flying = False
        self.is_sneaking = False
        self.is_sprinting = False
        
        # 游戏模式
        self.gamemode = 1  # 创造模式
        
        # 最后活动时间
        self.last_active = time.time()
    
    def update_position(self, x: float, y: float, z: float, yaw: float = None, pitch: float = None, on_ground: bool = True):
        """更新玩家位置"""
        self.x = x
        self.y = y
        self.z = z
        if yaw is not None:
            self.yaw = yaw
        if pitch is not None:
            self.pitch = pitch
        self.on_ground = on_ground
        self.last_active = time.time()
    
    def set_flying(self, flying: bool):
        """设置飞行状态"""
        self.is_flying = flying
    
    def apply_gravity(self, delta_time: float):
        """
        应用重力
        使用标准重力加速度 g = 9.8 m/s²
        力 F = mg，加速度 a = g = 9.8 m/s²
        """
        if self.is_flying or self.gamemode == 1:  # 创造模式不应用重力
            return
        
        if not self.on_ground:
            # 重力加速度 9.8 m/s²，方向向下（y轴负方向）
            GRAVITY = 9.8  # m/s²
            self.vy -= GRAVITY * delta_time
            
            # 终端速度（空气阻力限制）约 78.4 m/s
            TERMINAL_VELOCITY = 78.4  # m/s
            self.vy = max(self.vy, -TERMINAL_VELOCITY)
    
    def update_physics(self, delta_time: float):
        """更新物理状态"""
        # 应用重力
        self.apply_gravity(delta_time)
        
        # 更新位置
        self.x += self.vx * delta_time
        self.y += self.vy * delta_time
        self.z += self.vz * delta_time
        
        # 简单的地面检测（y < 60 视为地面）
        if self.y < 60:
            self.y = 60
            self.vy = 0
            self.on_ground = True
    
    def get_position_packet(self) -> bytes:
        """获取位置数据用于发送给其他玩家"""
        import struct
        packet = bytearray()
        packet.extend(struct.pack('>i', self.entity_id))  # Entity ID
        packet.extend(struct.pack('>d', self.x))  # X
        packet.extend(struct.pack('>d', self.y))  # Y
        packet.extend(struct.pack('>d', self.z))  # Z
        packet.extend(struct.pack('>B', int(self.yaw * 256 / 360) & 0xFF))  # Yaw
        packet.extend(struct.pack('>B', int(self.pitch * 256 / 360) & 0xFF))  # Pitch
        packet.append(0x01 if self.on_ground else 0x00)  # On ground
        return bytes(packet)
