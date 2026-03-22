"""
Nebula Minecraft Server - 客户端连接处理模块
Copyright (C) 2026 BlackHoleEra-Team

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import select
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
    set_player_gamemode, read_var_int, pack_var_int
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
    send_join_game(conn, entity_id, gamemode=0, dimension=0)  # 生存模式，主世界
    
    # 2. 注册玩家
    player = player_manager.add_player(username, entity_id, conn)
    player.gamemode = 0  # 默认生存模式
    
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
        player.gamemode = player_data.get('gamemode', 0)  # 恢复游戏模式
        log_info(f"Loaded player position for {username}: ({player.x}, {player.y}, {player.z}), flying={player.is_flying}, gamemode={player.gamemode}")
    else:
        log_info(f"No saved data for {username}, using default position")
    
    # 4. 发送出生点
    send_spawn_position(conn, x=0, y=64, z=0)
    
    # 5. 发送玩家能力（根据游戏模式）
    if player.gamemode == 0:  # 生存模式
        send_player_abilities(conn, creative_mode=False, flying=False, allow_flying=False, invulnerable=False)
    elif player.gamemode == 1:  # 创造模式
        send_player_abilities(conn, creative_mode=True, flying=player.is_flying, allow_flying=True, invulnerable=True)
    elif player.gamemode == 2:  # 冒险模式
        send_player_abilities(conn, creative_mode=False, flying=False, allow_flying=False, invulnerable=False)
    elif player.gamemode == 3:  # 旁观模式
        send_player_abilities(conn, creative_mode=False, flying=True, allow_flying=True, invulnerable=True)
    
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
    
    # 9. 发送周围的区块（视距 16 = 33x33 区域，共 1089 个区块）
    VIEW_DISTANCE = 16
    SYNC_LOAD_DISTANCE = 1  # 只同步加载最近的 3x3 = 9 个区块（减少阻塞）
    
    # 计算玩家当前所在的区块坐标
    player_chunk_x = int(player.x) // 16
    player_chunk_z = int(player.z) // 16
    
    log_info(f"Loading chunks for {username} at chunk ({player_chunk_x}, {player_chunk_z}) "
             f"(view distance: {VIEW_DISTANCE}, sync load first {SYNC_LOAD_DISTANCE*2+1}x{SYNC_LOAD_DISTANCE*2+1})...")
    
    # 记录已发送的区块
    sent_chunks = set()
    pending_chunks = []  # 待后续加载的区块
    
    # 按距离排序，先发送近的区块
    chunks_to_load = []
    for dx in range(-VIEW_DISTANCE, VIEW_DISTANCE + 1):
        for dz in range(-VIEW_DISTANCE, VIEW_DISTANCE + 1):
            distance = math.sqrt(dx * dx + dz * dz)
            chunk_x = player_chunk_x + dx
            chunk_z = player_chunk_z + dz
            chunks_to_load.append((distance, chunk_x, chunk_z))
    
    # 按距离排序
    chunks_to_load.sort(key=lambda x: x[0])
    
    # 先同步加载最近的区块（确保玩家周围立即显示）
    # 使用非阻塞方式，每加载一个区块后检查是否有客户端数据
    sync_loaded = 0
    conn.setblocking(False)  # 设置为非阻塞模式
    
    for distance, chunk_x, chunk_z in chunks_to_load:
        if distance <= SYNC_LOAD_DISTANCE:
            try:
                chunk = world_manager.get_chunk(chunk_x, chunk_z)
                if chunk:
                    send_chunk_data(conn, chunk)
                    sent_chunks.add((chunk_x, chunk_z))
                    sync_loaded += 1
                    
                    # 每加载一个区块后，尝试读取客户端数据（非阻塞）
                    try:
                        packet_length = read_var_int(conn)
                        if packet_length > 0:
                            packet_data = read_exact_bytes(conn, packet_length, timeout=0.01)
                            # 这里可以处理客户端数据，如命令
                        elif packet_length == -1:
                            pass  # 没有数据，继续加载
                    except (BlockingIOError, socket.timeout):
                        pass  # 没有数据，继续加载
            except Exception as e:
                log_error(f"Error loading chunk ({chunk_x}, {chunk_z}): {e}")
        else:
            # 远处的区块加入待加载队列
            pending_chunks.append((distance, chunk_x, chunk_z))
    
    # 恢复阻塞模式
    conn.setblocking(True)
    
    log_info(f"Player {username} entered the world! Sync loaded {sync_loaded} chunks, "
             f"{len(pending_chunks)} chunks pending")
    
    # 10. 保持连接，处理Keep Alive和玩家输入（传入玩家初始区块坐标和已发送区块）
    keep_alive_loop(conn, username, player_manager, world_manager, VIEW_DISTANCE, 
                    initial_chunk_x=player_chunk_x, initial_chunk_z=player_chunk_z,
                    initial_sent_chunks=sent_chunks, pending_chunks=pending_chunks)
    
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


def keep_alive_loop(conn: socket.socket, username: str, player_manager=None, world_manager=None, view_distance=16, initial_chunk_x=0, initial_chunk_z=0, initial_sent_chunks=None, pending_chunks=None):
    """保持连接循环，包含动态区块加载"""
    last_keep_alive = time.time()
    keep_alive_id = 0
    last_physics_update = time.time()
    last_chunk_update = time.time()
    
    # 记录玩家当前所在的区块坐标（使用初始位置）
    last_chunk_x = initial_chunk_x
    last_chunk_z = initial_chunk_z
    
    # 已发送的区块集合（使用初始加载的区块）
    sent_chunks = initial_sent_chunks if initial_sent_chunks is not None else set()
    
    # 待加载的区块队列（从初始加载传递过来）
    pending_chunks_list = pending_chunks if pending_chunks is not None else []
    
    # 每 tick 加载的区块数量（增加以加快加载速度）
    CHUNKS_PER_TICK = 49
    
    # 使用 select 实现非阻塞 I/O
    conn.setblocking(False)
    
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
            
            # 区块加载（每0.05秒，更平滑的加载）
            if world_manager and current_time - last_chunk_update >= 0.05:
                last_chunk_update = current_time
                
                # 获取玩家当前位置
                if player_manager and username in player_manager.players:
                    player = player_manager.players[username]
                    player_x = getattr(player, 'x', 0)
                    player_z = getattr(player, 'z', 0)
                    
                    # 计算玩家所在的区块坐标
                    current_chunk_x = int(player_x) // 16
                    current_chunk_z = int(player_z) // 16
                    
                    # 玩家移动了，重新计算待加载区块
                    if current_chunk_x != last_chunk_x or current_chunk_z != last_chunk_z:
                        last_chunk_x = current_chunk_x
                        last_chunk_z = current_chunk_z
                        
                        # 重新计算待加载区块列表（基于新位置）
                        pending_chunks_list = []
                        for dx in range(-view_distance, view_distance + 1):
                            for dz in range(-view_distance, view_distance + 1):
                                chunk_x = current_chunk_x + dx
                                chunk_z = current_chunk_z + dz
                                chunk_key = (chunk_x, chunk_z)
                                
                                if chunk_key not in sent_chunks:
                                    dist = math.sqrt(dx * dx + dz * dz)
                                    if dist <= view_distance:
                                        pending_chunks_list.append((dist, chunk_x, chunk_z))
                        
                        # 按距离排序
                        pending_chunks_list.sort(key=lambda x: x[0])
                    
                    # 每 tick 加载固定数量的区块
                    chunks_loaded_this_tick = 0
                    new_pending = []
                    
                    for dist, chunk_x, chunk_z in pending_chunks_list:
                        if chunks_loaded_this_tick >= CHUNKS_PER_TICK:
                            # 超过本 tick 限制，保留到下一 tick
                            new_pending.append((dist, chunk_x, chunk_z))
                            continue
                        
                        chunk_key = (chunk_x, chunk_z)
                        if chunk_key in sent_chunks:
                            continue
                        
                        try:
                            chunk = world_manager.get_chunk(chunk_x, chunk_z)
                            if chunk:
                                send_chunk_data(conn, chunk)
                                sent_chunks.add(chunk_key)
                                chunks_loaded_this_tick += 1
                        except Exception as e:
                            log_error(f"Error sending chunk ({chunk_x}, {chunk_z}): {e}")
                            # 出错的区块保留到后面重试
                            new_pending.append((dist, chunk_x, chunk_z))
                    
                    # 更新待加载列表
                    pending_chunks_list = new_pending
                    
                    # 调试信息：显示加载进度
                    if chunks_loaded_this_tick > 0:
                        total_pending = len(pending_chunks_list)
                        total_sent = len(sent_chunks)
                        if total_pending > 0 and total_pending % 100 == 0:
                            log_info(f"Chunk loading progress for {username}: {total_sent} sent, {total_pending} pending")
            
            # 使用 select 检查是否有数据可读（非阻塞）
            readable, _, _ = select.select([conn], [], [], 0)  # 0秒超时，立即返回
            
            if readable:
                try:
                    packet_length = read_var_int(conn)
                    if packet_length > 0:
                        packet_data = read_exact_bytes(conn, packet_length, timeout=0.01)
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
                                try:
                                    # 解析聊天消息 (1.12.2格式: packet_id + varint长度 + UTF-8字符串)
                                    from nebula.network.packet_utils import read_var_int_from_bytes
                                    msg_length, offset = read_var_int_from_bytes(packet_data, 1)
                                    log_info(f"DEBUG: Chat packet from {username}, msg_length={msg_length}, offset={offset}, packet_len={len(packet_data)}")
                                    if msg_length > 0 and len(packet_data) >= offset + msg_length:
                                        message = packet_data[offset:offset+msg_length].decode('utf-8')
                                        log_info(f"Chat from {username}: '{message}'")
                                        
                                        # 处理命令
                                        if message.startswith('/'):
                                            log_info(f"DEBUG: Handling command '{message}' from {username}")
                                            handle_command(conn, username, message, world_manager)
                                        else:
                                            # 普通聊天消息，广播给所有玩家
                                            broadcast_chat_message(f"<{username}> {message}", username)
                                    else:
                                        log_info(f"DEBUG: Invalid chat packet, msg_length={msg_length}, available={len(packet_data)-offset}")
                                except Exception as e:
                                    log_error(f"Error parsing chat from {username}: {e}")
                                    import traceback
                                    log_error(traceback.format_exc())
                            
                            # 处理Teleport Confirm (0x00)
                            elif packet_id == 0x00:
                                # Teleport确认，暂时忽略
                                pass
                            
                            # 处理 Tab 补全 (0x14)
                            elif packet_id == 0x14:
                                handle_tab_complete(conn, packet_data)
                            
                            # 处理玩家放置方块 (0x0B)
                            elif packet_id == 0x0B:
                                handle_player_block_placement(username, packet_data, conn)
                            
                            # 处理玩家破坏方块 (0x06)
                            elif packet_id == 0x06:
                                handle_player_block_break(username, packet_data, conn)
                            
                            else:
                                log_info(f"Received packet from {username}: 0x{packet_id:02x}")
                                
                except BlockingIOError:
                    # 没有数据，继续循环
                    pass
                
        except ConnectionError:
            log_info(f"Connection lost for {username}")
            # 不要在这里移除玩家，让 finally 块处理保存和移除
            break
        except Exception as e:
            log_error(f"Error in keep alive loop for {username}: {e}")
            # 不要在这里移除玩家，让 finally 块处理保存和移除
            break


def handle_command(conn: socket.socket, username: str, message: str, world_manager):
    """
    处理玩家输入的命令
    """
    from nebula.network.protocol import pack_var_int
    
    parts = message.split()
    command = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []
    
    try:
        if command == '/time':
            if len(args) == 0:
                # 查询当前时间
                current_time = int(world_manager.world_time) if world_manager else 6000
                total_ticks = int(world_manager.world_total_time) if world_manager else 0
                send_chat_message(conn, f"当前时间: {current_time} (0=日出, 6000=正午, 12000=日落, 18000=午夜)")
                send_chat_message(conn, f"总游戏刻: {total_ticks}")
            else:
                # 设置时间
                try:
                    if args[0].lower() == 'day':
                        new_time = 1000
                    elif args[0].lower() == 'night':
                        new_time = 13000
                    elif args[0].lower() == 'noon':
                        new_time = 6000
                    elif args[0].lower() == 'midnight':
                        new_time = 18000
                    else:
                        new_time = int(args[0])
                    
                    if world_manager:
                        world_manager.world_time = new_time % 24000
                        send_chat_message(conn, f"时间设置为: {new_time}")
                        # 广播时间更新给所有玩家
                        world_manager.broadcast_time_update()
                except ValueError:
                    send_chat_message(conn, "用法: /time [day|night|noon|midnight|<数值>]")
        
        elif command == '/gamerule':
            if not world_manager:
                send_chat_message(conn, "世界未初始化")
                return
            
            if len(args) == 0:
                # 显示所有游戏规则
                send_chat_message(conn, "游戏规则:")
                for rule, value in world_manager.game_rules.items():
                    send_chat_message(conn, f"  {rule}: {value}")
            elif len(args) == 1:
                # 显示特定规则
                rule = args[0]
                if rule in world_manager.game_rules:
                    send_chat_message(conn, f"{rule}: {world_manager.game_rules[rule]}")
                else:
                    send_chat_message(conn, f"未知游戏规则: {rule}")
            else:
                # 设置规则
                rule = args[0]
                value = args[1].lower()
                
                if rule not in world_manager.game_rules:
                    send_chat_message(conn, f"未知游戏规则: {rule}")
                    return
                
                # 转换值为布尔值或保持字符串
                if value in ('true', '1', 'yes'):
                    world_manager.game_rules[rule] = True
                elif value in ('false', '0', 'no'):
                    world_manager.game_rules[rule] = False
                else:
                    world_manager.game_rules[rule] = value
                
                send_chat_message(conn, f"游戏规则 {rule} 设置为: {world_manager.game_rules[rule]}")
                # 立即广播时间更新（如果修改了 doDaylightCycle）
                if rule == "doDaylightCycle":
                    world_manager.broadcast_time_update()
        
        elif command == '/gamemode' or command == '/gm':
            if len(args) == 0:
                # 显示当前游戏模式
                player = get_player_manager().get_player(username)
                if player:
                    mode_names = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}
                    current_mode = mode_names.get(player.gamemode, "未知")
                    send_chat_message(conn, f"当前游戏模式: {current_mode} ({player.gamemode})")
                else:
                    send_chat_message(conn, "无法获取玩家信息")
            else:
                # 解析游戏模式
                mode_arg = args[0].lower()
                mode_map = {
                    '0': 0, 's': 0, 'survival': 0, '生存': 0,
                    '1': 1, 'c': 1, 'creative': 1, '创造': 1,
                    '2': 2, 'a': 2, 'adventure': 2, '冒险': 2,
                    '3': 3, 'sp': 3, 'spectator': 3, '旁观': 3,
                }
                
                if mode_arg in mode_map:
                    new_gamemode = mode_map[mode_arg]
                    player = get_player_manager().get_player(username)
                    if player:
                        player.gamemode = new_gamemode
                        set_player_gamemode(conn, new_gamemode)
                        mode_names = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}
                        send_chat_message(conn, f"游戏模式已设置为: {mode_names[new_gamemode]}")
                    else:
                        send_chat_message(conn, "无法获取玩家信息")
                else:
                    send_chat_message(conn, "用法: /gamemode <0|1|2|3|s|c|a|sp|survival|creative|adventure|spectator>")
        
        elif command == '/tp' or command == '/teleport':
            player_manager = get_player_manager()
            player = player_manager.get_player(username)
            if not player:
                send_chat_message(conn, "无法获取玩家信息")
                return
            
            if len(args) == 0:
                send_chat_message(conn, "用法: /tp <目标> 或 /tp <x> <y> <z> 或 /tp <目标> <目的地>")
            elif len(args) == 1:
                # 传送到目标（支持选择器）
                target_selector = args[0]
                targets = player_manager.resolve_selector(target_selector, username, (player.x, player.y, player.z))
                
                if targets:
                    target = targets[0]  # 取第一个目标
                    player.x = target.x
                    player.y = target.y
                    player.z = target.z
                    send_player_position_and_look(conn, player.x, player.y, player.z, player.yaw, player.pitch)
                    target_name = target.username if hasattr(target, 'username') else str(target)
                    send_chat_message(conn, f"已传送到 {target_name} 的位置")
                else:
                    send_chat_message(conn, f"找不到目标: {target_selector}")
            elif len(args) == 2:
                # 可能是: /tp <玩家> <玩家2> 或 /tp <玩家> ~ ~ ~
                # 检查第二个参数是否是数字（相对坐标）
                if args[1] in ('~', '^') or _is_number(args[1]):
                    # 这是坐标形式，需要4个参数，当前只有2个，报错
                    send_chat_message(conn, "用法: /tp <目标> <x> <y> <z> - 需要完整坐标")
                    return
                
                # 传送目标到目的地（支持选择器）
                source_selector = args[0]
                dest_selector = args[1]
                
                sources = player_manager.resolve_selector(source_selector, username, (player.x, player.y, player.z))
                dests = player_manager.resolve_selector(dest_selector, username, (player.x, player.y, player.z))
                
                if not sources:
                    send_chat_message(conn, f"找不到传送源: {source_selector}")
                    return
                if not dests:
                    send_chat_message(conn, f"找不到传送目标: {dest_selector}")
                    return
                
                dest = dests[0]
                count = 0
                for source in sources:
                    source.x = dest.x
                    source.y = dest.y
                    source.z = dest.z
                    if source.conn:
                        send_player_position_and_look(source.conn, source.x, source.y, source.z, source.yaw, source.pitch)
                    count += 1
                
                dest_name = dest.username if hasattr(dest, 'username') else str(dest)
                send_chat_message(conn, f"已将 {count} 个玩家传送到 {dest_name} 的位置")
            elif len(args) == 3:
                # 传送到指定坐标
                try:
                    x = float(args[0])
                    y = float(args[1])
                    z = float(args[2])
                    player.x = x
                    player.y = y
                    player.z = z
                    send_player_position_and_look(conn, player.x, player.y, player.z, player.yaw, player.pitch)
                    send_chat_message(conn, f"已传送到 ({x}, {y}, {z})")
                except ValueError:
                    send_chat_message(conn, "用法: /tp <x> <y> <z> - 坐标必须是数字")
            elif len(args) == 4:
                # 传送目标到指定坐标: /tp <目标> <x> <y> <z>
                target_selector = args[0]
                targets = player_manager.resolve_selector(target_selector, username, (player.x, player.y, player.z))
                
                if not targets:
                    send_chat_message(conn, f"找不到目标: {target_selector}")
                    return
                
                try:
                    x = _parse_coord(args[1], player.x)
                    y = _parse_coord(args[2], player.y)
                    z = _parse_coord(args[3], player.z)
                    
                    count = 0
                    for target in targets:
                        target.x = x
                        target.y = y
                        target.z = z
                        if target.conn:
                            send_player_position_and_look(target.conn, target.x, target.y, target.z, target.yaw, target.pitch)
                        count += 1
                    
                    send_chat_message(conn, f"已将 {count} 个玩家传送到 ({x}, {y}, {z})")
                except ValueError as e:
                    send_chat_message(conn, f"坐标格式错误: {e}")
            else:
                send_chat_message(conn, "用法: /tp [目标] <x> <y> <z> 或 /tp <目标> [目的地]")
        
        elif command == '/help':
            help_text = """可用命令:
/time - 查看当前时间
/time day - 设置为白天
/time night - 设置为夜晚
/time noon - 设置为正午
/time midnight - 设置为午夜
/time <数值> - 设置具体时间 (0-24000)
/gamerule - 查看游戏规则
/gamerule <规则> - 查看特定规则
/gamerule <规则> <值> - 设置规则
/gamemode <模式> - 切换游戏模式 (0=生存, 1=创造, 2=冒险, 3=旁观)
/tp <x> <y> <z> - 传送到指定坐标
/tp <目标> - 传送到玩家/选择器位置
/tp <目标> <目的地> - 传送玩家到玩家位置
/tp <目标> <x> <y> <z> - 传送玩家到坐标
坐标支持: ~相对坐标 (~10=当前+10, ~=当前位置)
选择器: @s=自己, @p=最近玩家, @a=所有玩家, @r=随机玩家
/help - 显示此帮助"""
            send_chat_message(conn, help_text)
        
        else:
            send_chat_message(conn, f"未知命令: {command}. 输入 /help 查看可用命令")
            
    except Exception as e:
        log_error(f"Error handling command '{command}' from {username}: {e}")
        send_chat_message(conn, f"命令执行出错: {e}")


def _is_number(s: str) -> bool:
    """检查字符串是否是数字（支持 ~ 相对坐标前缀）"""
    if s.startswith('~') or s.startswith('^'):
        s = s[1:]
    if not s:
        return True  # 只有 ~ 也是有效的
    try:
        float(s)
        return True
    except ValueError:
        return False


def _parse_coord(s: str, relative_to: float) -> float:
    """解析坐标，支持相对坐标 (~) 和局部坐标 (^)
    ~10 = relative_to + 10
    ~ = relative_to
    10 = 10 (绝对坐标)
    """
    s = s.strip()
    
    if s.startswith('~'):
        # 相对坐标
        offset_str = s[1:]
        if offset_str:
            return relative_to + float(offset_str)
        else:
            return relative_to
    elif s.startswith('^'):
        # 局部坐标（简化处理，当作相对坐标）
        offset_str = s[1:]
        if offset_str:
            return relative_to + float(offset_str)
        else:
            return relative_to
    else:
        # 绝对坐标
        return float(s)


def send_chat_message(conn: socket.socket, message: str):
    """
    发送聊天消息给客户端
    """
    from nebula.network.protocol import pack_var_int
    
    try:
        packet = bytearray()
        packet.append(0x0F)  # Chat Message 包 ID
        
        # 构建 JSON 格式的聊天消息
        json_msg = f'{{"text": "{message}"}}'
        msg_bytes = json_msg.encode('utf-8')
        
        packet.extend(pack_var_int(len(msg_bytes)))
        packet.extend(msg_bytes)
        packet.append(0x00)  # 位置: 0 = 聊天框
        
        # 发送
        conn.send(pack_var_int(len(packet)) + bytes(packet))
    except Exception as e:
        log_error(f"Error sending chat message: {e}")


def broadcast_chat_message(message: str, exclude_username: str = None):
    """
    广播聊天消息给所有在线玩家
    """
    try:
        from nebula.player.player_manager import get_player_manager
        player_manager = get_player_manager()
        if player_manager:
            for username, player in player_manager.players.items():
                if username != exclude_username and hasattr(player, 'conn') and player.conn:
                    try:
                        send_chat_message(player.conn, message)
                    except Exception as e:
                        log_error(f"Error sending chat to {username}: {e}")
    except Exception as e:
        log_error(f"Error broadcasting chat message: {e}")


def handle_tab_complete(conn: socket.socket, packet_data: bytes):
    """
    处理 Tab 补全请求 (0x14)
    CPacketTabComplete 结构: message(string), hasTargetBlock(bool), hasBlockPos(bool), targetBlock(BlockPos, optional)
    返回 SPacketTabComplete (0x0E): count(varint), suggestions[string]
    """
    try:
        from nebula.network.packet_utils import read_var_int_from_bytes
        
        offset = 1  # 跳过 packet_id
        
        # 解析 message (string)
        msg_length, offset = read_var_int_from_bytes(packet_data, offset)
        text = ""
        if msg_length > 0 and len(packet_data) >= offset + msg_length:
            text = packet_data[offset:offset+msg_length].decode('utf-8')
            offset += msg_length
        
        # 跳过 hasTargetBlock, hasBlockPos, targetBlock (我们不需要这些)
        # hasTargetBlock = packet_data[offset] if offset < len(packet_data) else 0
        # offset += 1
        # hasBlockPos = packet_data[offset] if offset < len(packet_data) else 0
        # offset += 1
        # if hasBlockPos and offset + 8 <= len(packet_data):
        #     offset += 8  # BlockPos (8 bytes)
        
        # 可用命令列表
        available_commands = [
            "time",
            "time day",
            "time night",
            "time noon",
            "time midnight",
            "help"
        ]
        
        # 根据输入过滤命令
        suggestions = []
        if text.startswith('/'):
            cmd_input = text[1:]  # 去掉开头的 /
            for cmd in available_commands:
                if cmd.startswith(cmd_input):
                    suggestions.append('/' + cmd)
        
        # 发送 Tab-Complete 响应 (0x0E) - SPacketTabComplete
        response = bytearray()
        response.append(0x0E)  # Tab-Complete 响应包 ID
        
        # 建议数量 (varint)
        response.extend(pack_var_int(len(suggestions)))
        
        # 每个建议 (string)
        for suggestion in suggestions:
            suggestion_bytes = suggestion.encode('utf-8')
            response.extend(pack_var_int(len(suggestion_bytes)))
            response.extend(suggestion_bytes)
        
        # 发送
        full_response = pack_var_int(len(response)) + bytes(response)
        total_sent = 0
        while total_sent < len(full_response):
            sent = conn.send(full_response[total_sent:])
            if sent == 0:
                raise ConnectionError("Socket connection broken")
            total_sent += sent
        
        log_info(f"Tab complete for '{text}': {suggestions}")
        
    except Exception as e:
        log_error(f"Error handling tab complete: {e}")


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
