"""
Minecraft 1.12.2 协议处理模块
实现Handshake、Status、Login、Play阶段
"""

import socket
import struct
import uuid
import json
from typing import Tuple, Optional

from nebula.core.constants import PROTOCOL_VERSION, MINECRAFT_VERSION_NAME
from nebula.config.config import MAX_PLAYERS, MOTD, ONLINE_PLAYERS
from nebula.logging import log_info, log_warn, log_error
from nebula.network.packet_utils import (
    read_var_int, pack_var_int, pack_string, read_var_int_from_bytes,
    read_string_from_bytes, pack_int, pack_long, pack_short, pack_byte,
    pack_bool, pack_position, pack_uuid
)
from nebula.world.chunk import Chunk


# ========== Handshake阶段 ==========

def handle_handshake(conn: socket.socket) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """
    处理客户端的Handshake包
    返回: (next_state, server_address, server_port)
    next_state: 1=Status, 2=Login
    """
    try:
        packet_length = read_var_int(conn)
        packet_data = conn.recv(packet_length)
        
        pos = 0
        packet_id, pos = read_var_int_from_bytes(packet_data, pos)
        
        if packet_id != 0x00:
            log_warn(f"Expected Handshake packet (0x00), got {packet_id:02x}")
            return None, None, None
        
        # 协议版本
        protocol_version, pos = read_var_int_from_bytes(packet_data, pos)
        
        # 服务器地址
        server_address_len, pos = read_var_int_from_bytes(packet_data, pos)
        server_address = packet_data[pos:pos + server_address_len].decode('utf-8')
        pos += server_address_len
        
        # 服务器端口
        server_port = struct.unpack('>H', packet_data[pos:pos + 2])[0]
        pos += 2
        
        # 下一个状态
        next_state, pos = read_var_int_from_bytes(packet_data, pos)
        
        log_info(f"Handshake: protocol={protocol_version}, address={server_address}, port={server_port}, next_state={next_state}")
        return next_state, server_address, server_port
        
    except Exception as e:
        log_error(f"Error handling handshake: {e}")
        return None, None, None


# ========== Status阶段 ==========

def handle_status_request(conn: socket.socket):
    """处理Status Request并发送响应"""
    try:
        packet_length = read_var_int(conn)
        packet_data = conn.recv(packet_length)
        
        if packet_data[0] != 0x00:
            log_error(f"Expected Status Request (0x00), got {packet_data[0]:02x}")
            return
        
        log_info("Received Status Request")
        
        # 构建响应JSON
        response = {
            "version": {
                "name": MINECRAFT_VERSION_NAME,
                "protocol": PROTOCOL_VERSION
            },
            "players": {
                "max": MAX_PLAYERS,
                "online": ONLINE_PLAYERS,
                "sample": []
            },
            "description": {
                "text": MOTD
            }
        }
        
        response_json = json.dumps(response, ensure_ascii=False)
        
        # 发送响应: [包长度][包ID(0x00)][JSON字符串]
        response_packet = b'\x00' + pack_string(response_json)
        conn.send(pack_var_int(len(response_packet)) + response_packet)
        log_info("Sent Status Response")
        
    except Exception as e:
        log_error(f"Error handling status request: {e}")


def handle_ping_request(conn: socket.socket):
    """处理Ping请求"""
    try:
        packet_length = read_var_int(conn)
        packet_data = conn.recv(packet_length)
        
        if packet_data[0] != 0x01:
            log_error(f"Expected Ping (0x01), got {packet_data[0]:02x}")
            return
        
        payload = packet_data[1:9] if len(packet_data) >= 9 else b'\x00' * 8
        log_info(f"Received Ping, payload={payload.hex()}")
        
        # 返回Pong
        pong_packet = b'\x01' + payload
        conn.send(pack_var_int(len(pong_packet)) + pong_packet)
        log_info("Sent Pong Response")
        
    except Exception as e:
        log_error(f"Error handling ping: {e}")


# ========== Login阶段 ==========

def handle_login_start(conn: socket.socket) -> Tuple[Optional[str], Optional[uuid.UUID]]:
    """
    处理Login Start包
    返回: (username, player_uuid)
    """
    try:
        packet_length = read_var_int(conn)
        packet_data = conn.recv(packet_length)
        
        if packet_data[0] != 0x00:
            log_error(f"Expected Login Start (0x00), got {packet_data[0]:02x}")
            return None, None
        
        pos = 1
        username_len, pos = read_var_int_from_bytes(packet_data, pos)
        username = packet_data[pos:pos + username_len].decode('utf-8')
        
        # 生成离线UUID
        offline_string = f"OfflinePlayer:{username}"
        player_uuid = uuid.uuid3(uuid.NAMESPACE_DNS, offline_string)
        
        log_info(f"Player logging in: {username} (UUID: {player_uuid})")
        return username, player_uuid
        
    except Exception as e:
        log_error(f"Error handling login start: {e}")
        return None, None


def send_login_success(conn: socket.socket, username: str, player_uuid: uuid.UUID):
    """发送Login Success包"""
    try:
        packet = bytearray()
        packet.append(0x02)  # Login Success包ID
        
        # UUID (字符串格式，1.12.2使用带横杠的格式)
        uuid_str = str(player_uuid)
        packet.extend(pack_string(uuid_str))
        
        # 用户名
        packet.extend(pack_string(username))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Login Success for {username}")
        
    except Exception as e:
        log_error(f"Error sending login success: {e}")


# ========== Play阶段 ==========

def send_join_game(conn: socket.socket, entity_id: int, gamemode: int = 1, dimension: int = 1):
    """
    发送Join Game包 (0x23)
    让玩家进入游戏世界
    参考Cuberite的SendLogin实现
    """
    try:
        packet = bytearray()
        packet.append(0x23)  # Join Game包ID
        
        # Entity ID (UInt32) - 注意是无符号32位整数
        packet.extend(struct.pack('>I', entity_id))
        
        # Gamemode (UInt8) 0=生存, 1=创造, 2=冒险, 3=spectator
        # bit 4 (0x08)是hardcore标志
        packet.append(gamemode & 0xFF)
        
        # Dimension (Int32) -1=下界, 0=主世界, 1=末地
        packet.extend(struct.pack('>i', dimension))
        
        # Difficulty (UInt8) 0=和平, 1=简单, 2=普通, 3=困难
        packet.append(2)
        
        # Max players (UInt8)
        packet.append(min(MAX_PLAYERS, 255))
        
        # Level type (string) - "default", "flat", "largeBiomes", "amplified", "default_1_1"
        packet.extend(pack_string("default"))
        
        # Reduced debug info (boolean)
        packet.append(0x00)
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Join Game: entity_id={entity_id}, gamemode={gamemode}, dimension={dimension}")
        
    except Exception as e:
        log_error(f"Error sending join game: {e}")


def send_spawn_position(conn: socket.socket, x: int = 0, y: int = 64, z: int = 0):
    """
    发送Spawn Position包 (0x46)
    设置世界出生点
    """
    try:
        packet = bytearray()
        packet.append(0x46)  # Spawn Position包ID
        
        # Position (8字节: 26位X, 12位Y, 26位Z)
        packet.extend(pack_position(x, y, z))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Spawn Position: ({x}, {y}, {z})")
        
    except Exception as e:
        log_error(f"Error sending spawn position: {e}")


def send_player_abilities(conn: socket.socket, creative_mode: bool = True, flying: bool = True, 
                          allow_flying: bool = True, invulnerable: bool = True):
    """
    发送Player Abilities包 (0x2C)
    设置玩家能力
    """
    try:
        packet = bytearray()
        packet.append(0x2C)  # Player Abilities包ID
        
        # Flags (byte)
        flags = 0
        if invulnerable:
            flags |= 0x01
        if flying:
            flags |= 0x02
        if allow_flying:
            flags |= 0x04
        if creative_mode:
            flags |= 0x08
        packet.append(flags)
        
        # Flying speed (float)
        packet.extend(struct.pack('>f', 0.05))
        
        # Field of View modifier (float)
        packet.extend(struct.pack('>f', 0.1))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Player Abilities: flying={flying}, creative={creative_mode}")
        
    except Exception as e:
        log_error(f"Error sending player abilities: {e}")


# Teleport ID计数器
teleport_id_counter = 0

def send_player_position_and_look(conn: socket.socket, x: float = 0.0, y: float = 64.0, z: float = 0.0,
                                  yaw: float = 0.0, pitch: float = 0.0):
    """
    发送Player Position And Look包 (0x2F)
    设置玩家位置和视角
    参考Cuberite的SendPlayerMoveLook实现
    """
    global teleport_id_counter
    try:
        packet = bytearray()
        packet.append(0x2F)  # Player Position And Look包ID
        
        # X (double)
        packet.extend(struct.pack('>d', x))
        
        # Y (double)
        packet.extend(struct.pack('>d', y))
        
        # Z (double)
        packet.extend(struct.pack('>d', z))
        
        # Yaw (float)
        packet.extend(struct.pack('>f', yaw))
        
        # Pitch (float)
        packet.extend(struct.pack('>f', pitch))
        
        # Flags (byte) - 0x00表示绝对位置，0xFF表示相对位置
        packet.append(0x00)
        
        # Teleport ID (VarInt) - 1.9+版本需要这个字段
        teleport_id_counter += 1
        packet.extend(pack_var_int(teleport_id_counter))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Player Position And Look: ({x:.2f}, {y:.2f}, {z:.2f}), yaw={yaw}, pitch={pitch}, teleport_id={teleport_id_counter}")
        
    except Exception as e:
        log_error(f"Error sending player position and look: {e}")


def send_time_update(conn: socket.socket, world_age: int = 0, time_of_day: int = 6000):
    """
    发送Time Update包 (0x47)
    设置世界时间
    1.12.2版本使用0x47
    """
    try:
        packet = bytearray()
        packet.append(0x47)  # Time Update包ID (1.12.2)
        
        # World age (long)
        packet.extend(pack_long(world_age))
        
        # Time of day (long)
        packet.extend(pack_long(time_of_day))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Time Update: age={world_age}, time={time_of_day}")
        
    except Exception as e:
        log_error(f"Error sending time update: {e}")


def send_keep_alive(conn: socket.socket, keep_alive_id: int):
    """
    发送Keep Alive包 (0x1F)
    1.12.2格式: keep_alive_id (long)
    注意: 1.12.2的Keep Alive使用long而不是VarInt
    """
    try:
        packet = bytearray()
        packet.append(0x1F)  # Keep Alive包ID
        
        # Keep Alive ID (long) - 1.12.2使用long
        packet.extend(pack_long(keep_alive_id))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Keep Alive: id={keep_alive_id}")
        
    except Exception as e:
        log_error(f"Error sending keep alive: {e}")





def send_empty_chunk(conn: socket.socket, chunk_x: int, chunk_z: int):
    """
    发送完全空的区块（用于虚空世界）
    参考Cuberite的Serialize110实现（1.12.2协议）
    
    1.12.2 Chunk Data格式 (0x20)：
    - Chunk X (BEInt32)
    - Chunk Z (BEInt32)
    - Ground-up continuous (Bool) - True表示包含biome数据
    - Primary bit mask (VarInt32) - 哪些区块段存在
    - Chunk大小 (VarInt32) - 后续数据的总字节数
    - 区块段数据（每个存在的段）:
      * Bits per block (UInt8) - 13表示使用全局调色板
      * Palette length (VarInt) - 0表示使用全局调色板
      * Data array length (VarInt) - 数据数组长度（long数组）
      * Block data - 区块方块数据
      * Block light - 方块光照
      * Sky light - 天空光照（只在主世界）
    - Biome数据 (256字节) - 16x16的biome ID
    - Tile entity list - 以0字节结束
    """
    try:
        packet = bytearray()
        packet.append(0x20)  # Chunk Data包ID
        
        # Chunk X (BEInt32)
        packet.extend(struct.pack('>i', chunk_x))
        
        # Chunk Z (BEInt32)
        packet.extend(struct.pack('>i', chunk_z))
        
        # Ground-up continuous (Bool) - True
        packet.append(0x01)
        
        # Primary bit mask (VarInt32) - 0表示没有区块段
        packet.append(0x00)
        
        # Chunk大小 (VarInt32) - 只有256字节的biome数据
        packet.extend(pack_var_int(256))
        
        # 没有区块段数据（因为bitmask=0）
        
        # Biome数据 (256字节)
        packet.extend(bytes(256))  # 全0表示海洋biome
        
        # Number of block entities (varint) - 0
        packet.extend(pack_var_int(0))
        
        # 发送：包长度(varint) + 完整包
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Empty Chunk: ({chunk_x}, {chunk_z}), size={len(packet)}")
        
    except Exception as e:
        log_error(f"Error sending empty chunk: {e}")


def send_chunk_data(conn: socket.socket, chunk: Chunk):
    """
    发送真实区块数据
    参考 MCP940 的 SPacketChunkData 实现
    """
    try:
        packet = bytearray()
        packet.append(0x20)  # Chunk Data包ID
        
        # Chunk X (BEInt32)
        packet.extend(struct.pack('>i', chunk.chunk_x))
        
        # Chunk Z (BEInt32)
        packet.extend(struct.pack('>i', chunk.chunk_z))
        
        # Ground-up continuous (Bool) - True
        packet.append(0x01)
        
        # Primary bit mask (VarInt32)
        section_mask = chunk.get_section_mask()
        packet.extend(pack_var_int(section_mask))
        
        # 计算并构建区块数据
        chunk_data = bytearray()
        
        # 写入每个存在的区块段（支持 64 sections = 1024 格高度）
        for i in range(64):
            if section_mask & (1 << i):
                section = chunk.sections[i]
                
                # 获取区块段的完整数据（包含 bits_per_entry, palette, data_array）
                section_block_data = section.get_block_data()
                chunk_data.extend(section_block_data)
                
                # Block light (2048 bytes)
                chunk_data.extend(bytes(section.block_light))
                
                # Sky light (2048 bytes) - 只在主世界
                chunk_data.extend(bytes(section.sky_light))
        
        # Biome数据 (256字节)
        chunk_data.extend(bytes(chunk.biomes))
        
        # Chunk大小 (VarInt32)
        packet.extend(pack_var_int(len(chunk_data)))
        
        # 区块数据
        packet.extend(chunk_data)
        
        # Number of block entities (varint) - 0
        packet.extend(pack_var_int(0))
        
        # 发送：包长度(varint) + 完整包
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        
        # 计算实际发送的区块段数量
        section_count = bin(section_mask).count('1')
        log_info(f"Sent Chunk Data: ({chunk.chunk_x}, {chunk.chunk_z}), mask={section_mask:04x}, sections={section_count}, chunk_data_size={len(chunk_data)}, total_size={len(packet)}")
        
    except Exception as e:
        log_error(f"Error sending chunk data: {e}")


def send_block_change(conn: socket.socket, x: int, y: int, z: int, block_state: int):
    """
    发送 Block Change 包 (0x0B)
    通知客户端方块已改变
    1.12.2 格式: position (8 bytes), block_id (varint)
    """
    try:
        packet = bytearray()
        packet.append(0x0B)  # Block Change 包 ID
        
        # Position (8 bytes: 26位X, 12位Y, 26位Z)
        from nebula.network.packet_utils import pack_position
        packet.extend(pack_position(x, y, z))
        
        # Block ID (VarInt) - 使用全局调色板的方块状态 ID
        packet.extend(pack_var_int(block_state))
        
        conn.send(pack_var_int(len(packet)) + bytes(packet))
        log_info(f"Sent Block Change: ({x}, {y}, {z}) = {block_state}")
        
    except Exception as e:
        log_error(f"Error sending block change: {e}")
