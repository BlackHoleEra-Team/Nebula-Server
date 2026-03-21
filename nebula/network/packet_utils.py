"""
网络数据包工具模块
实现VarInt编解码、字符串打包等通用功能
"""

import socket
import struct
from typing import Tuple, Optional


def read_var_int(socket_conn: socket.socket) -> int:
    """从socket读取一个VarInt"""
    result = 0
    shift = 0
    while True:
        try:
            byte_data = socket_conn.recv(1)
            if not byte_data:
                raise ConnectionError("Connection closed while reading VarInt")
            byte = byte_data[0]
        except socket.timeout:
            continue
        except BlockingIOError:
            # 非阻塞模式下没有数据，返回 -1 表示无数据
            return -1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not (byte & 0x80):
            return result


def read_exact_bytes(socket_conn: socket.socket, length: int, timeout: float = 5.0) -> bytes:
    """从socket读取指定长度的字节，确保读取完整"""
    socket_conn.settimeout(timeout)
    data = bytearray()
    while len(data) < length:
        try:
            chunk = socket_conn.recv(length - len(data))
            if not chunk:
                raise ConnectionError("Connection closed while reading data")
            data.extend(chunk)
        except socket.timeout:
            continue
    return bytes(data)


def pack_var_int(value: int) -> bytes:
    """将整数打包成VarInt格式"""
    result = bytearray()
    while True:
        if value & ~0x7F == 0:
            result.append(value)
            return bytes(result)
        result.append((value & 0x7F) | 0x80)
        value >>= 7


def pack_string(data: str) -> bytes:
    """将字符串打包成Minecraft协议格式 (VarInt长度 + UTF-8数据)"""
    encoded = data.encode('utf-8')
    return pack_var_int(len(encoded)) + encoded


def read_string_from_bytes(data: bytes, offset: int) -> Tuple[str, int]:
    """从字节数据中读取字符串，返回(字符串, 新的偏移量)"""
    length, pos = read_var_int_from_bytes(data, offset)
    string_data = data[pos:pos + length]
    return string_data.decode('utf-8'), pos + length


def read_var_int_from_bytes(data: bytes, offset: int) -> Tuple[int, int]:
    """从字节数据中读取VarInt，返回(值, 新的偏移量)"""
    result = 0
    shift = 0
    pos = offset
    while pos < len(data):
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        shift += 7
        if not (byte & 0x80):
            return result, pos
    # 如果到达这里，说明数据不完整
    raise IndexError(f"VarInt data incomplete at offset {offset}, data length: {len(data)}")


def pack_short(value: int) -> bytes:
    """打包有符号短整型 (2字节, 大端序)"""
    return struct.pack('>h', value)


def pack_int(value: int) -> bytes:
    """打包有符号整型 (4字节, 大端序)"""
    return struct.pack('>i', value)


def pack_long(value: int) -> bytes:
    """打包有符号长整型 (8字节, 大端序)"""
    return struct.pack('>q', value)


def pack_float(value: float) -> bytes:
    """打包单精度浮点数 (4字节, 大端序)"""
    return struct.pack('>f', value)


def pack_double(value: float) -> bytes:
    """打包双精度浮点数 (8字节, 大端序)"""
    return struct.pack('>d', value)


def pack_bool(value: bool) -> bytes:
    """打包布尔值 (1字节)"""
    return b'\x01' if value else b'\x00'


def pack_byte(value: int) -> bytes:
    """打包有符号字节"""
    return struct.pack('b', value)


def pack_unsigned_byte(value: int) -> bytes:
    """打包无符号字节"""
    return struct.pack('B', value)


def pack_position(x: int, y: int, z: int) -> bytes:
    """
    打包位置数据 (1.12.2格式)
    使用64位长整型: 26位X, 12位Y, 26位Z
    """
    val = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
    return pack_long(val)


def read_position(data: bytes, offset: int) -> Tuple[int, int, int, int]:
    """
    从字节数据中读取位置
    返回: (x, y, z, 新的偏移量)
    """
    val = struct.unpack('>q', data[offset:offset + 8])[0]
    x = val >> 38
    y = (val >> 26) & 0xFFF
    z = val & 0x3FFFFFF
    
    # 符号扩展
    if x >= 2**25:
        x -= 2**26
    if y >= 2**11:
        y -= 2**12
    if z >= 2**25:
        z -= 2**26
    
    return x, y, z, offset + 8


def pack_uuid(uuid_most: int, uuid_least: int) -> bytes:
    """打包UUID (两个64位长整型)"""
    return pack_long(uuid_most) + pack_long(uuid_least)
