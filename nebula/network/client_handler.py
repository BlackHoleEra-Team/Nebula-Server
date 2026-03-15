"""
客户端连接处理模块
处理每个客户端的完整生命周期
"""

import socket
import struct
import time
import random
import math

from nebula.logging import log_info, log_warn, log_error
from nebula.config.config import ONLINE_PLAYERS
import nebula.config.config as config_module
from nebula.network.protocol import (
    handle_handshake, handle_status_request, handle_ping_request,
    handle_login_start, send_login_success, send_join_game, send_spawn_position,
    send_player_abilities, send_player_position_and_look, send_time_update,
    send_keep_alive, send_empty_chunk, send_chunk_data, send_block_change,
    read_var_int, pack_var_int
)
from nebula.network.packet_utils import read_exact_bytes
from nebula.world.world_manager import get_world_manager
from nebula.player.player_manager import get_player_manager
from nebula.player.player_data import get_player_data_manager


def handle_client(conn: socket.socket, addr):
    """处理客户端连接的主入口"""
    log_info(f"Connection from {addr}")
    
    try:
        conn.settimeout(30)
        
        # 1. Handshake阶段
        next_state, _, _ = handle_handshake(conn)
        if next_state is None:
            conn.close()
            return
        
        # 2. 根据状态处理
        if next_state == 1:  # Status阶段
            handle_status_request(conn)
            handle_ping_request(conn)
            log_info(f"Status ping from {addr} completed")
            
        elif next_state == 2:  # Login阶段
            handle_login_flow(conn, addr)
            
        else:
            log_warn(f"Unknown next_state: {next_state}")
            
    except Exception as e:
        log_error(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        log_info(f"Connection {addr} closed")


def handle_login_flow(conn: socket.socket, addr):
    """处理登录流程"""
    # 1. Login Start
    username, player_uuid = handle_login_start(conn)
    if username is None:
        return
    
    # 2. 发送Login Success
    send_login_success(conn, username, player_uuid)
    
    # 3. 更新在线玩家数
    config_module.ONLINE_PLAYERS += 1
    log_info(f"Player {username} logged in. Online: {config_module.ONLINE_PLAYERS}")
    
    # 4. 进入Play阶段
    player = None
    try:
        player = enter_play_phase(conn, username, player_uuid)
    except Exception as e:
        log_error(f"Error in play phase for {username}: {e}")
    finally:
        # 保存玩家数据（在玩家被移除之前）
        if player:
            try:
                player_data_manager = get_player_data_manager()
                player_data = {
                    'username': username,
                    'x': player.x,
                    'y': player.y,
                    'z': player.z,
                    'yaw': player.yaw,
                    'pitch': player.pitch,
                    'gamemode': player.gamemode,
                    'is_flying': player.is_flying
                }
                player_data_manager.save_player_data(player_uuid, player_data)
                log_info(f"Saved player data for {username}")
            except Exception as e:
                log_error(f"Error saving player data for {username}: {e}")
            
            # 移除玩家
            try:
                player_manager = get_player_manager()
                player_manager.remove_player(username)
            except Exception as e:
                log_error(f"Error removing player {username}: {e}")
        
        # 玩家断开
        config_module.ONLINE_PLAYERS = max(0, config_module.ONLINE_PLAYERS - 1)
        log_info(f"Player {username} disconnected. Online: {config_module.ONLINE_PLAYERS}")


def enter_play_phase(conn: socket.socket, username: str, player_uuid: str):
    """进入游戏阶段 - 发送平坦世界，返回玩家对象"""
    log_info(f"Entering play phase for {username}")
    
    # 获取管理器
    world_manager = get_world_manager()
    player_manager = get_player_manager()
    player_data_manager = get_player_data_manager()
    
    # 1. 发送Join Game包
    entity_id = random.randint(1000, 9999)
    send_join_game(conn, entity_id, gamemode=1, dimension=0)  # 创造模式，主世界
    
    # 2. 注册玩家
    player = player_manager.add_player(username, entity_id, conn)
    
    # 3. 加载玩家数据（位置等）
    player_data = player_data_manager.load_player_data(player_uuid)
    if player_data:
        # 恢复玩家位置
        player.x = player_data.get('x', 0.5)
        player.y = player_data.get('y', 65.0)
        player.z = player_data.get('z', 0.5)
        player.yaw = player_data.get('yaw', 0.0)
        player.pitch = player_data.get('pitch', 0.0)
        player.is_flying = player_data.get('is_flying', False)
        log_info(f"Loaded player position for {username}: ({player.x}, {player.y}, {player.z}), flying={player.is_flying}")
    else:
        log_info(f"No saved data for {username}, using default position")
    
    # 4. 发送出生点
    send_spawn_position(conn, x=0, y=64, z=0)
    
    # 5. 发送玩家能力（飞行）
    send_player_abilities(conn, creative_mode=True, flying=player.is_flying, allow_flying=True)
    
    # 6. 发送玩家位置和视角（等待Teleport Confirm）
    send_player_position_and_look(conn, x=player.x, y=player.y, z=player.z, yaw=player.yaw, pitch=player.pitch)
    
    # 7. 等待客户端的Teleport Confirm
    log_info(f"Waiting for Teleport Confirm from {username}...")
    if not wait_for_teleport_confirm(conn, timeout=5.0):
        log_error(f"Teleport confirm timeout for {username}")
        return player
    log_info(f"Received Teleport Confirm from {username}")
    
    # 8. 发送时间
    send_time_update(conn, world_age=0, time_of_day=6000)
    
    # 9. 发送周围的区块（视距 12 = 25x25 区域）
    VIEW_DISTANCE = 12
    log_info(f"Loading chunks for {username} (view distance: {VIEW_DISTANCE})...")
    
    # 按距离排序，先发送近的区块
    chunks_to_load = []
    for cx in range(-VIEW_DISTANCE, VIEW_DISTANCE + 1):
        for cz in range(-VIEW_DISTANCE, VIEW_DISTANCE + 1):
            distance = math.sqrt(cx * cx + cz * cz)
            chunks_to_load.append((distance, cx, cz))
    
    # 按距离排序
    chunks_to_load.sort(key=lambda x: x[0])
    
    # 发送区块数据
    for distance, cx, cz in chunks_to_load:
        try:
            # 从世界管理器获取或生成区块
            chunk = world_manager.get_chunk(cx, cz)
            if chunk:
                # 发送区块数据
                send_chunk_data(conn, chunk)
        except Exception as e:
            log_error(f"Error loading chunk ({cx}, {cz}): {e}")
    
    log_info(f"Player {username} entered the world! Loaded {len(chunks_to_load)} chunks")
    
    # 10. 保持连接，处理Keep Alive和玩家输入
    keep_alive_loop(conn, username, player_manager, world_manager, VIEW_DISTANCE)
    
    return player


def wait_for_teleport_confirm(conn: socket.socket, timeout: float = 5.0) -> bool:
    """等待客户端发送Teleport Confirm包"""
    start_time = time.time()
    conn.settimeout(0.1)
    
    while time.time() - start_time < timeout:
        try:
            packet_length = read_var_int(conn)
            if packet_length > 0:
                packet_data = read_exact_bytes(conn, packet_length, timeout=0.1)
                if len(packet_data) > 0:
                    packet_id = packet_data[0]
                    
                    # Teleport Confirm (0x00)
                    if packet_id == 0x00:
                        # 读取teleport ID
                        from nebula.network.packet_utils import read_var_int_from_bytes
                        teleport_id, _ = read_var_int_from_bytes(packet_data, 1)
                        log_info(f"Received Teleport Confirm: id={teleport_id}")
                        return True
                    
                    # 也可能收到Keep Alive或其他包，忽略它们
                    elif packet_id == 0x0C:  # Keep Alive
                        pass
                    else:
                        log_info(f"Received packet while waiting for teleport: 0x{packet_id:02x}")
                        
        except socket.timeout:
            continue
        except Exception as e:
            log_error(f"Error waiting for teleport confirm: {e}")
            return False
    
    return False


def keep_alive_loop(conn: socket.socket, username: str, player_manager=None, world_manager=None, view_distance=12):
    """保持连接循环，包含动态区块加载"""
    last_keep_alive = time.time()
    keep_alive_id = 0
    last_physics_update = time.time()
    last_chunk_update = time.time()
    
    # 记录玩家当前所在的区块坐标
    last_chunk_x = 0
    last_chunk_z = 0
    
    # 已发送的区块集合
    sent_chunks = set()
    
    conn.settimeout(1.0)  # 1秒超时用于轮询
    
    while True:
        try:
            current_time = time.time()
            
            # 每10秒发送一次Keep Alive
            if current_time - last_keep_alive >= 10:
                keep_alive_id += 1
                send_keep_alive(conn, keep_alive_id)
                last_keep_alive = current_time
            
            # 更新物理（重力等）
            if player_manager and current_time - last_physics_update >= 0.05:  # 20 TPS
                delta_time = current_time - last_physics_update
                player_manager.update_all_physics(delta_time)
                last_physics_update = current_time
            
            # 每0.5秒检查一次是否需要加载新区块
            if world_manager and current_time - last_chunk_update >= 0.5:
                last_chunk_update = current_time
                
                # 获取玩家当前位置
                if player_manager and username in player_manager.players:
                    player = player_manager.players[username]
                    player_x = getattr(player, 'x', 0)
                    player_z = getattr(player, 'z', 0)
                    
                    # 计算玩家所在的区块坐标
                    current_chunk_x = int(player_x) // 16
                    current_chunk_z = int(player_z) // 16
                    
                    # 如果玩家移动到了新的区块，加载周围的区块
                    if current_chunk_x != last_chunk_x or current_chunk_z != last_chunk_z:
                        last_chunk_x = current_chunk_x
                        last_chunk_z = current_chunk_z
                        
                        # 加载视距范围内的区块
                        chunks_to_send = []
                        for dx in range(-view_distance, view_distance + 1):
                            for dz in range(-view_distance, view_distance + 1):
                                chunk_x = current_chunk_x + dx
                                chunk_z = current_chunk_z + dz
                                chunk_key = (chunk_x, chunk_z)
                                
                                # 只发送之前没发送过的区块
                                if chunk_key not in sent_chunks:
                                    distance = math.sqrt(dx * dx + dz * dz)
                                    if distance <= view_distance:
                                        chunks_to_send.append((distance, chunk_x, chunk_z))
                        
                        # 按距离排序，先发送近的
                        chunks_to_send.sort(key=lambda x: x[0])
                        
                        # 每次最多发送 5 个新区块，避免卡顿
                        for i, (distance, chunk_x, chunk_z) in enumerate(chunks_to_send[:5]):
                            try:
                                chunk = world_manager.get_chunk(chunk_x, chunk_z)
                                if chunk:
                                    send_chunk_data(conn, chunk)
                                    sent_chunks.add((chunk_x, chunk_z))
                            except Exception as e:
                                log_error(f"Error sending chunk ({chunk_x}, {chunk_z}): {e}")
            
            # 尝试读取客户端数据
            try:
                packet_length = read_var_int(conn)
                if packet_length > 0:
                    # 使用read_exact_bytes确保读取完整的数据包
                    packet_data = read_exact_bytes(conn, packet_length, timeout=5.0)
                    if len(packet_data) > 0:
                        packet_id = packet_data[0]
                        
                        # 调试：记录所有收到的包
                        if packet_id in [0x0B, 0x06, 0x1D]:
                            log_info(f"Received packet 0x{packet_id:02x} from {username}, length={len(packet_data)}, data={packet_data.hex()}")
                        
                        # 处理客户端Keep Alive响应 (0x0C)
                        if packet_id == 0x0C:
                            # 1.12.2格式: keep_alive_id (long, 8 bytes)
                            try:
                                if len(packet_data) >= 9:
                                    received_id = struct.unpack('>q', packet_data[1:9])[0]
                                    log_info(f"Received Keep Alive response from {username}: {received_id}")
                                else:
                                    log_error(f"Keep Alive response too short: {len(packet_data)} bytes, data={packet_data.hex()}")
                            except Exception as e:
                                log_error(f"Error parsing Keep Alive response from {username}: {e}, data={packet_data.hex()}")
                        
                        # 处理玩家位置包 (0x0E)
                        elif packet_id == 0x0E:
                            if player_manager:
                                player_manager.handle_player_move(username, packet_data, packet_id)
                        
                        # 处理玩家移动包 (0x0F)
                        elif packet_id == 0x0F:
                            if player_manager:
                                player_manager.handle_player_move(username, packet_data, packet_id)
                        
                        # 处理玩家位置和视角包 (0x0D)
                        elif packet_id == 0x0D:
                            if player_manager:
                                player_manager.handle_player_move(username, packet_data, packet_id)
                        
                        # 处理玩家能力包 (0x13) - 飞行状态
                        elif packet_id == 0x13:
                            if player_manager:
                                player_manager.handle_player_abilities(username, packet_data)
                        
                        # 处理聊天消息 (0x02)
                        elif packet_id == 0x02:
                            log_info(f"Received chat from {username}")
                        
                        # 处理Teleport Confirm (0x00)
                        elif packet_id == 0x00:
                            # Teleport确认，暂时忽略
                            pass
                        
                        # 处理玩家放置方块 (0x0B)
                        elif packet_id == 0x0B:
                            handle_player_block_placement(username, packet_data, conn)
                        
                        # 处理玩家破坏方块 (0x06)
                        elif packet_id == 0x06:
                            handle_player_block_break(username, packet_data, conn)
                        
                        else:
                            log_info(f"Received packet from {username}: 0x{packet_id:02x}")
                            
            except socket.timeout:
                # 正常超时，继续循环
                continue
                
        except ConnectionError:
            log_info(f"Connection lost for {username}")
            # 不要在这里移除玩家，让 finally 块处理保存和移除
            break
        except Exception as e:
            log_error(f"Error in keep alive loop for {username}: {e}")
            # 不要在这里移除玩家，让 finally 块处理保存和移除
            break


def decode_block_pos(pos: int) -> tuple:
    """
    解码 BlockPos (参考 Minecraft 1.12.2 的 BlockPos.fromLong)
    NUM_X_BITS = 26, NUM_Y_BITS = 12, NUM_Z_BITS = 26
    """
    NUM_X_BITS = 26
    NUM_Y_BITS = 12
    NUM_Z_BITS = 26
    Y_SHIFT = 0 + NUM_Z_BITS
    X_SHIFT = Y_SHIFT + NUM_Y_BITS
    
    x = (pos << (64 - X_SHIFT - NUM_X_BITS)) >> (64 - NUM_X_BITS)
    y = (pos << (64 - Y_SHIFT - NUM_Y_BITS)) >> (64 - NUM_Y_BITS)
    z = (pos << (64 - NUM_Z_BITS)) >> (64 - NUM_Z_BITS)
    
    return int(x), int(y), int(z)


def handle_player_block_placement(username: str, packet_data: bytes, conn: socket.socket = None):
    """
    处理玩家放置方块包 (0x0B)
    1.12.2格式: position (8 bytes long), face (varint), hand (varint), cursor_x (float), cursor_y (float), cursor_z (float)
    注意: 有些客户端可能发送简化格式，只有 position (9字节)
    """
    try:
        from nebula.network.packet_utils import read_var_int_from_bytes
        from nebula.world.world_manager import get_world_manager
        from nebula.world.chunk import BLOCK_STATE_STONE
        
        offset = 1  # 跳过packet_id
        
        log_info(f"Block placement packet length: {len(packet_data)}, data: {packet_data.hex()}")
        
        # 检查包长度是否足够读取 position (最小 1 + 8 = 9 字节)
        if len(packet_data) < 9:
            log_error(f"Block placement packet too short: {len(packet_data)} bytes, expected at least 9 bytes")
            return
        
        # 读取位置 (8 bytes long, big-endian)
        pos = struct.unpack('>q', packet_data[offset:offset+8])[0]
        offset += 8
        
        # 解码位置
        x, y, z = decode_block_pos(pos)
        log_info(f"Decoded position: ({x}, {y}, {z}), offset after pos: {offset}")
        
        # 读取 face (varint) - 0=下, 1=上, 2=北, 3=南, 4=西, 5=东
        # 如果数据不足，默认使用 1 (顶部)
        face = 1  # 默认值
        if offset < len(packet_data):
            try:
                face, offset = read_var_int_from_bytes(packet_data, offset)
                log_info(f"Face: {face}, offset after face: {offset}")
            except Exception as e:
                log_warn(f"Failed to read face, using default 1: {e}")
        else:
            log_warn(f"No data for face, using default 1")
        
        # 读取 hand (varint) - 0=主手, 1=副手
        # 如果数据不足，默认使用 0 (主手)
        hand = 0  # 默认值
        if offset < len(packet_data):
            try:
                hand, offset = read_var_int_from_bytes(packet_data, offset)
            except Exception as e:
                log_warn(f"Failed to read hand, using default 0: {e}")
        else:
            log_warn(f"No data for hand, using default 0")
        
        # 根据 face 计算实际放置位置
        if face == 0:  # 底部
            y -= 1
        elif face == 1:  # 顶部
            y += 1
        elif face == 2:  # 北
            z -= 1
        elif face == 3:  # 南
            z += 1
        elif face == 4:  # 西
            x -= 1
        elif face == 5:  # 东
            x += 1
        
        # 获取世界管理器
        world_manager = get_world_manager()
        
        # 获取区块
        chunk_x = x >> 4
        chunk_z = z >> 4
        chunk = world_manager.get_chunk(chunk_x, chunk_z)
        
        # 在区块内设置方块
        local_x = x & 0xF
        local_z = z & 0xF
        
        # 检查 y 坐标范围
        if y < 0 or y >= 256:
            log_error(f"Invalid y coordinate: {y}")
            return
        
        # 放置石头方块 (ID=1, meta=0, state=16)
        chunk.set_block(local_x, y, local_z, BLOCK_STATE_STONE)
        chunk.is_modified = True
        
        # 保存区块
        world_manager._save_chunk(chunk)
        
        # 发送 Block Change 包给客户端确认
        if conn:
            send_block_change(conn, x, y, z, BLOCK_STATE_STONE)
        
        log_info(f"Player {username} placed block at ({x}, {y}, {z})")
        
    except Exception as e:
        import traceback
        log_error(f"Error handling block placement for {username}: {e}")
        log_error(traceback.format_exc())


def handle_player_block_break(username: str, packet_data: bytes, conn: socket.socket = None):
    """
    处理玩家破坏方块包 (0x06)
    1.12.2格式: status (byte), position (8 bytes long), face (byte)
    """
    try:
        from nebula.world.world_manager import get_world_manager
        from nebula.world.chunk import BLOCK_STATE_AIR
        
        if len(packet_data) < 10:
            log_error(f"Block break packet too short")
            return
        
        offset = 1  # 跳过packet_id
        
        # 读取 status (0=开始破坏, 1=取消, 2=完成)
        status = packet_data[offset]
        offset += 1
        
        if status != 2:  # 只处理完成破坏
            return
        
        # 读取位置 (8 bytes long, big-endian)
        pos = struct.unpack('>q', packet_data[offset:offset+8])[0]
        offset += 8
        
        # 解码位置
        x, y, z = decode_block_pos(pos)
        
        # 获取世界管理器
        world_manager = get_world_manager()
        
        # 获取区块
        chunk_x = x >> 4
        chunk_z = z >> 4
        chunk = world_manager.get_chunk(chunk_x, chunk_z)
        
        # 在区块内破坏方块
        local_x = x & 0xF
        local_z = z & 0xF
        
        chunk.set_block(local_x, y, local_z, BLOCK_STATE_AIR)
        chunk.is_modified = True
        
        # 保存区块
        world_manager._save_chunk(chunk)
        
        # 发送 Block Change 包给客户端确认
        if conn:
            send_block_change(conn, x, y, z, BLOCK_STATE_AIR)
        
        log_info(f"Player {username} broke block at ({x}, {y}, {z})")
        
    except Exception as e:
        log_error(f"Error handling block break for {username}: {e}")
