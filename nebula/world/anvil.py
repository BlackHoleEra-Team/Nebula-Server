"""
Nebula Minecraft Server - Anvil区域文件格式
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

import os
import struct
import zlib
from typing import Optional, Dict, Tuple
from io import BytesIO
from nebula.logging import log_info, log_error
from nebula.network.nbt import NBTWriter, NBTReader

# Anvil格式常量
SECTOR_SIZE = 4096
REGION_SIZE = 32
CHUNKS_PER_REGION = REGION_SIZE * REGION_SIZE


class AnvilRegion:
    """
    Anvil区域文件 (.mca)
    存储32x32个区块
    """
    
    def __init__(self, region_x: int, region_z: int, world_folder: str):
        self.region_x = region_x
        self.region_z = region_z
        self.world_folder = world_folder
        # 使用绝对路径避免工作目录问题
        abs_world_folder = os.path.abspath(world_folder)
        self.file_path = os.path.join(
            abs_world_folder, "region",
            f"r.{region_x}.{region_z}.mca"
        )
        
        # 区块位置表 (每个区块4字节: 3字节偏移 + 1字节扇区数)
        self.location_table: Dict[Tuple[int, int], Tuple[int, int]] = {}
        # 区块时间戳表 (每个区块4字节)
        self.timestamp_table: Dict[Tuple[int, int], int] = {}
        
        # 加载或创建区域文件
        self._load_or_create()
    
    def _load_or_create(self):
        """加载现有区域文件或创建新文件"""
        file_exists = os.path.exists(self.file_path)
        abs_path = os.path.abspath(self.file_path)
        cwd = os.getcwd()
        log_info(f"_load_or_create: cwd={cwd}, file_path={self.file_path}, abs_path={abs_path}, exists={file_exists}")
        if file_exists:
            self._load_existing()
        else:
            self._create_new()
    
    def _create_new(self):
        """创建新的区域文件"""
        # 确保region文件夹存在
        region_folder = os.path.dirname(self.file_path)
        os.makedirs(region_folder, exist_ok=True)
        
        # 创建文件头 (8KB: 4KB位置表 + 4KB时间戳表)
        with open(self.file_path, 'wb') as f:
            # 位置表 (4096字节，初始全0)
            f.write(bytes(SECTOR_SIZE))
            # 时间戳表 (4096字节，初始全0)
            f.write(bytes(SECTOR_SIZE))
        
        log_info(f"Created new region file: {self.file_path}")
    
    def _load_existing(self):
        """加载现有的区域文件"""
        try:
            with open(self.file_path, 'rb') as f:
                # 读取位置表
                location_data = f.read(SECTOR_SIZE)
                # 读取时间戳表
                timestamp_data = f.read(SECTOR_SIZE)
                
                # 解析位置表
                # 格式: 4字节整数 = (offset << 8) | sector_count
                for i in range(CHUNKS_PER_REGION):
                    value = struct.unpack('>I', location_data[i*4:i*4+4])[0]
                    offset = value >> 8
                    sector_count = value & 255
                    
                    if offset > 0 and sector_count > 0:
                        # 使用位运算获取局部坐标 (支持负数)
                        local_x = i & (REGION_SIZE - 1)
                        local_z = i // REGION_SIZE
                        self.location_table[(local_x, local_z)] = (offset, sector_count)
                
                # 解析时间戳表
                for i in range(CHUNKS_PER_REGION):
                    timestamp = struct.unpack('>I', timestamp_data[i*4:i*4+4])[0]
                    if timestamp > 0:
                        # 使用位运算获取局部坐标 (支持负数)
                        local_x = i & (REGION_SIZE - 1)
                        local_z = i // REGION_SIZE
                        self.timestamp_table[(local_x, local_z)] = timestamp
            
            log_info(f"Loaded region file: {self.file_path}, chunks: {len(self.location_table)}")
        except Exception as e:
            log_error(f"Error loading region file {self.file_path}: {e}")
            # 如果加载失败，创建新的区域文件
            self._create_new()
    
    def read_chunk(self, chunk_x: int, chunk_z: int) -> Optional[bytes]:
        """
        读取区块的NBT数据
        返回解压后的NBT数据，如果不存在则返回None
        """
        # 使用位运算获取局部坐标 (支持负数)
        local_x = chunk_x & (REGION_SIZE - 1)
        local_z = chunk_z & (REGION_SIZE - 1)
        
        log_info(f"Reading chunk ({chunk_x}, {chunk_z}), local=({local_x}, {local_z}), location_table has {len(self.location_table)} entries")
        
        if (local_x, local_z) not in self.location_table:
            log_info(f"Chunk ({chunk_x}, {chunk_z}) not found in location table")
            return None
        
        offset, sector_count = self.location_table[(local_x, local_z)]
        log_info(f"Found chunk ({chunk_x}, {chunk_z}) at offset {offset}, sectors {sector_count}")
        
        try:
            with open(self.file_path, 'rb') as f:
                # 跳转到区块数据位置
                f.seek(offset * SECTOR_SIZE)
                
                # 读取区块头 (4字节长度 + 1字节压缩类型)
                length_data = f.read(4)
                if len(length_data) < 4:
                    log_error(f"Invalid chunk header for ({chunk_x}, {chunk_z})")
                    return None
                
                data_length = struct.unpack('>I', length_data)[0]
                compression_type = struct.unpack('B', f.read(1))[0]
                
                log_info(f"Chunk ({chunk_x}, {chunk_z}) header: length={data_length}, compression={compression_type}")
                
                # 读取压缩数据
                compressed_data = f.read(data_length - 1)
                
                log_info(f"Read {len(compressed_data)} bytes of compressed data")
                
                # 解压数据
                if compression_type == 1:  # gzip
                    import gzip
                    result = gzip.decompress(compressed_data)
                    log_info(f"Decompressed gzip data: {len(result)} bytes")
                    return result
                elif compression_type == 2:  # zlib
                    result = zlib.decompress(compressed_data)
                    log_info(f"Decompressed zlib data: {len(result)} bytes")
                    return result
                else:
                    log_error(f"Unknown compression type: {compression_type}")
                    return None
                    
        except Exception as e:
            log_error(f"Error reading chunk ({chunk_x}, {chunk_z}): {e}")
            return None
    
    def write_chunk(self, chunk_x: int, chunk_z: int, nbt_data: bytes):
        """
        写入区块的NBT数据
        """
        # 使用位运算获取局部坐标 (支持负数)
        local_x = chunk_x & (REGION_SIZE - 1)
        local_z = chunk_z & (REGION_SIZE - 1)
        
        log_info(f"Writing chunk ({chunk_x}, {chunk_z}) to region file, nbt_data size: {len(nbt_data)}")
        
        # 压缩数据
        compressed_data = zlib.compress(nbt_data)
        log_info(f"Compressed data size: {len(compressed_data)}")
        
        # 构建区块数据
        chunk_data = bytearray()
        # 长度 (包括压缩类型字节)
        chunk_data.extend(struct.pack('>I', len(compressed_data) + 1))
        # 压缩类型 (2 = zlib)
        chunk_data.append(2)
        # 压缩数据
        chunk_data.extend(compressed_data)
        
        # 填充到扇区边界
        sectors_needed = (len(chunk_data) + SECTOR_SIZE - 1) // SECTOR_SIZE
        padding = sectors_needed * SECTOR_SIZE - len(chunk_data)
        chunk_data.extend(bytes(padding))
        
        try:
            with open(self.file_path, 'r+b') as f:
                # 检查是否已有该区块
                if (local_x, local_z) in self.location_table:
                    # 复用现有位置
                    offset, old_sectors = self.location_table[(local_x, local_z)]
                    
                    # 如果新数据能放入旧位置
                    if sectors_needed <= old_sectors:
                        # 写入数据
                        f.seek(offset * SECTOR_SIZE)
                        f.write(chunk_data[:old_sectors * SECTOR_SIZE])
                    else:
                        # 需要分配新位置
                        offset = self._find_free_sectors(f, sectors_needed)
                        if offset is None:
                            # 扩展到文件末尾
                            f.seek(0, 2)  # 移动到文件末尾
                            offset = f.tell() // SECTOR_SIZE
                            f.write(chunk_data)
                        else:
                            f.seek(offset * SECTOR_SIZE)
                            f.write(chunk_data)
                        
                        # 更新位置表
                        self.location_table[(local_x, local_z)] = (offset, sectors_needed)
                        self._write_location_table(f, local_x, local_z, offset, sectors_needed)
                else:
                    # 分配新位置
                    offset = self._find_free_sectors(f, sectors_needed)
                    if offset is None:
                        # 扩展到文件末尾
                        f.seek(0, 2)
                        offset = f.tell() // SECTOR_SIZE
                        f.write(chunk_data)
                    else:
                        f.seek(offset * SECTOR_SIZE)
                        f.write(chunk_data)
                    
                    # 更新位置表
                    self.location_table[(local_x, local_z)] = (offset, sectors_needed)
                    self._write_location_table(f, local_x, local_z, offset, sectors_needed)
                
                # 更新时间戳
                import time
                timestamp = int(time.time())
                self.timestamp_table[(local_x, local_z)] = timestamp
                self._write_timestamp_table(f, local_x, local_z, timestamp)
                
                log_info(f"Successfully wrote chunk ({chunk_x}, {chunk_z}) at offset {offset}, sectors {sectors_needed}")
                
        except Exception as e:
            log_error(f"Error writing chunk ({chunk_x}, {chunk_z}): {e}")
    
    def _find_free_sectors(self, f, sectors_needed: int) -> Optional[int]:
        """查找空闲的扇区"""
        # 简单实现：返回None，让调用者扩展到文件末尾
        # 实际实现应该扫描文件查找空闲空间
        return None
    
    def _write_location_table(self, f, local_x: int, local_z: int, offset: int, sector_count: int):
        """写入位置表项
        格式: 4字节整数 = (offset << 8) | sector_count
        读取时: offset = value >> 8, sector_count = value & 255
        """
        index = local_z * REGION_SIZE + local_x
        f.seek(index * 4)
        # 组合成4字节: (offset << 8) | sector_count
        value = (offset << 8) | (sector_count & 0xFF)
        f.write(struct.pack('>I', value))
    
    def _write_timestamp_table(self, f, local_x: int, local_z: int, timestamp: int):
        """写入时间戳表项"""
        index = local_z * REGION_SIZE + local_x
        f.seek(SECTOR_SIZE + index * 4)
        f.write(struct.pack('>I', timestamp))
