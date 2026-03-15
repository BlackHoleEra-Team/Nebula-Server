"""
区块数据结构
基于 Minecraft 1.12.2 源代码实现正确的 1.12.2 区块格式
"""

import struct
import math
from typing import Optional, Dict, List, Tuple
from nebula.logging import log_info, log_error

# 区块常量
CHUNK_WIDTH = 16
CHUNK_HEIGHT = 1024  # 提升到 1024 格
SECTION_HEIGHT = 16
SECTION_COUNT = 64  # 1024 / 16

# 方块ID (1.12.2 全局方块状态 ID)
# 从 Minecraft 1.12.2 的 Block.registerBlocks() 获取
# 方块状态 ID = (方块注册 ID << 4) | 元数据
BLOCK_STATE_AIR = 0      # air: (0 << 4) | 0 = 0
BLOCK_STATE_STONE = 16   # stone: (1 << 4) | 0 = 16
BLOCK_STATE_GRASS = 32   # grass: (2 << 4) | 0 = 32
BLOCK_STATE_DIRT = 48    # dirt: (3 << 4) | 0 = 48


class BitArray:
    """
    位数组实现，使用无缝位打包（seamless bit packing）
    参考 Minecraft 1.12.2 区块数据格式
    """
    
    def __init__(self, bits_per_entry: int, array_size: int):
        self.bits_per_entry = bits_per_entry
        self.array_size = array_size
        self.max_entry_value = (1 << bits_per_entry) - 1
        # 计算需要的 long 数量
        self.long_array = [0] * ((array_size * bits_per_entry + 63) // 64)
    
    def set_at(self, index: int, value: int):
        """设置指定索引的值"""
        if index < 0 or index >= self.array_size:
            return
        if value < 0 or value > self.max_entry_value:
            value = value & self.max_entry_value
        
        bit_index = index * self.bits_per_entry
        long_index = bit_index // 64
        bit_offset = bit_index % 64
        
        # 清除旧值并设置新值（处理跨 long 边界）
        remaining_bits = self.bits_per_entry
        value_to_write = value & self.max_entry_value
        
        while remaining_bits > 0:
            available_bits = 64 - bit_offset
            bits_to_write = min(remaining_bits, available_bits)
            
            # 创建掩码
            mask = ((1 << bits_to_write) - 1) << bit_offset
            
            # 写入值
            self.long_array[long_index] = (
                (self.long_array[long_index] & ~mask) |
                ((value_to_write & ((1 << bits_to_write) - 1)) << bit_offset)
            )
            
            # 准备写入剩余位
            remaining_bits -= bits_to_write
            value_to_write >>= bits_to_write
            
            # 移动到下一个 long
            long_index += 1
            bit_offset = 0
    
    def get_at(self, index: int) -> int:
        """获取指定索引的值"""
        if index < 0 or index >= self.array_size:
            return 0
        
        bit_index = index * self.bits_per_entry
        long_index = bit_index // 64
        bit_offset = bit_index % 64
        
        result = 0
        bits_read = 0
        
        while bits_read < self.bits_per_entry:
            available_bits = 64 - bit_offset
            bits_to_read = min(self.bits_per_entry - bits_read, available_bits)
            
            # 读取值
            mask = (1 << bits_to_read) - 1
            value = (self.long_array[long_index] >> bit_offset) & mask
            
            # 合并到结果
            result |= value << bits_read
            bits_read += bits_to_read
            
            # 移动到下一个 long
            long_index += 1
            bit_offset = 0
        
        return int(result & self.max_entry_value)
    
    def get_backing_array(self) -> List[int]:
        """获取底层 long 数组"""
        return self.long_array
    
    def from_long_array(self, long_array: List[int]):
        """从 long 数组加载数据"""
        # 确保数组大小足够
        min_size = (self.array_size * self.bits_per_entry + 63) // 64
        for i in range(min(min_size, len(long_array))):
            self.long_array[i] = long_array[i]
    
    def size(self) -> int:
        """获取数组大小"""
        return len(self.long_array)


class PaletteLinear:
    """
    线性调色板 (bits <= 4)
    参考 Minecraft 1.12.2 的 BlockStatePaletteLinear
    """
    
    def __init__(self, bits: int):
        self.bits = bits
        self.states: List[int] = []
        self.max_size = 1 << bits
    
    def id_for(self, state: int) -> int:
        """获取状态的 ID，如果不存在则添加"""
        # 查找现有状态
        for i, s in enumerate(self.states):
            if s == state:
                return i
        
        # 添加新状态
        if len(self.states) < self.max_size:
            self.states.append(state)
            return len(self.states) - 1
        else:
            # 调色板已满，需要扩容
            return -1  # 表示需要扩容
    
    def get_state(self, index: int) -> int:
        """通过 ID 获取状态"""
        if 0 <= index < len(self.states):
            return self.states[index]
        return BLOCK_STATE_AIR
    
    def write(self) -> bytes:
        """序列化调色板"""
        result = bytearray()
        # Palette length (VarInt)
        result.extend(self._pack_var_int(len(self.states)))
        # 每个状态 (VarInt)
        for state in self.states:
            result.extend(self._pack_var_int(state))
        return bytes(result)
    
    def get_serialized_size(self) -> int:
        """获取序列化后的大小"""
        size = len(self._pack_var_int(len(self.states)))
        for state in self.states:
            size += len(self._pack_var_int(state))
        return size
    
    @staticmethod
    def _pack_var_int(value: int) -> bytes:
        """打包 VarInt"""
        result = bytearray()
        while True:
            if value & ~0x7F == 0:
                result.append(value)
                return bytes(result)
            result.append((value & 0x7F) | 0x80)
            value >>= 7


class ChunkSection:
    """
    区块段（16x16x16的方块区域）
    基于 Minecraft 1.12.2 的 ExtendedBlockStorage 实现
    """
    
    def __init__(self, y_index: int):
        self.y_index = y_index
        
        # 方块状态数组 (4096 个方块)
        self.block_states = [BLOCK_STATE_AIR] * 4096
        
        # 光照数据
        self.block_light = [0] * 2048  # 4 bits per block
        self.sky_light = [0xFF] * 2048  # 4 bits per block, 默认全亮
        
        # 非空气方块计数
        self.non_air_count = 0
    
    def _get_index(self, x: int, y: int, z: int) -> int:
        """将坐标转换为数组索引"""
        return (y << 8) | (z << 4) | x
    
    def set_block(self, x: int, y: int, z: int, block_state: int):
        """设置方块状态"""
        if not (0 <= x < 16 and 0 <= y < 16 and 0 <= z < 16):
            return
        
        index = self._get_index(x, y, z)
        old_state = self.block_states[index]
        self.block_states[index] = block_state
        
        # 更新非空气方块计数
        if old_state == BLOCK_STATE_AIR and block_state != BLOCK_STATE_AIR:
            self.non_air_count += 1
        elif old_state != BLOCK_STATE_AIR and block_state == BLOCK_STATE_AIR:
            self.non_air_count -= 1
    
    def get_block(self, x: int, y: int, z: int) -> int:
        """获取方块状态"""
        if not (0 <= x < 16 and 0 <= y < 16 and 0 <= z < 16):
            return BLOCK_STATE_AIR
        return self.block_states[self._get_index(x, y, z)]
    
    def is_empty(self) -> bool:
        """检查区块段是否为空（全是空气）"""
        return self.non_air_count == 0
    
    def get_block_data(self) -> bytes:
        """
        获取区块段的方块数据，用于发送给客户端
        1.12.2 格式: BitsPerEntry(1) + Palette(VarInt[]) + DataArrayLength(VarInt) + DataArray(long[])
        参考 Minecraft 1.12.2 的 BlockStateContainer.write()
        """
        # 始终使用全局调色板（13 bits）以确保兼容性
        return self._get_global_palette_data()
    
    def _get_global_palette_data(self) -> bytes:
        """使用全局调色板获取数据（bits = 13）"""
        bits_per_entry = 13
        result = bytearray()
        
        # 1. Bits per entry
        result.append(bits_per_entry)
        
        # 2. Palette length = 0 (表示使用全局调色板)
        result.append(0)
        
        # 3. 构建 BitArray
        bit_array = BitArray(bits_per_entry, 4096)
        for i, state in enumerate(self.block_states):
            bit_array.set_at(i, state & 0x1FFF)  # 13位掩码
        
        # 4. 数据数组长度 (VarInt)
        long_array = bit_array.get_backing_array()
        result.extend(self._pack_var_int(len(long_array)))
        
        # 5. 数据数组 (long[])
        for value in long_array:
            # 确保值在有符号64位整数范围内
            signed_value = value if value < 2**63 else value - 2**64
            result.extend(struct.pack('>q', signed_value))
        
        return bytes(result)
    
    def get_light_data(self, has_sky_light: bool = True) -> bytes:
        """获取光照数据"""
        result = bytearray()
        
        # Block light (2048 bytes)
        result.extend(bytes(self.block_light))
        
        # Sky light (2048 bytes) - 只在主世界
        if has_sky_light:
            result.extend(bytes(self.sky_light))
        
        return bytes(result)
    
    @staticmethod
    def _pack_var_int(value: int) -> bytes:
        """打包 VarInt"""
        result = bytearray()
        while True:
            if value & ~0x7F == 0:
                result.append(value)
                return bytes(result)
            result.append((value & 0x7F) | 0x80)
            value >>= 7


class Chunk:
    """
    完整的区块（16x256x16）
    """
    
    def __init__(self, chunk_x: int, chunk_z: int):
        self.chunk_x = chunk_x
        self.chunk_z = chunk_z
        self.sections: Dict[int, ChunkSection] = {}
        self.biomes = [1] * 256  # 16x16 biome数据，1=草原
        self.is_modified = False
        
        # 初始化所有区块段
        for i in range(SECTION_COUNT):
            self.sections[i] = ChunkSection(i)
    
    def set_block(self, x: int, y: int, z: int, block_state: int):
        """设置方块状态"""
        if not (0 <= x < 16 and 0 <= y < CHUNK_HEIGHT and 0 <= z < 16):
            return
        
        section_index = y // SECTION_HEIGHT
        local_y = y % SECTION_HEIGHT
        
        self.sections[section_index].set_block(x, local_y, z, block_state)
        self.is_modified = True
    
    def get_block(self, x: int, y: int, z: int) -> int:
        """获取方块状态"""
        if not (0 <= x < 16 and 0 <= y < CHUNK_HEIGHT and 0 <= z < 16):
            return BLOCK_STATE_AIR
        
        section_index = y // SECTION_HEIGHT
        local_y = y % SECTION_HEIGHT
        
        return self.sections[section_index].get_block(x, local_y, z)
    
    def get_section_mask(self) -> int:
        """获取存在的区块段位掩码"""
        mask = 0
        for i, section in self.sections.items():
            if not section.is_empty():
                mask |= (1 << i)
        return mask
    
    def get_chunk_data(self, has_sky_light: bool = True) -> bytes:
        """
        获取完整的区块数据，用于发送给客户端
        参考 Minecraft 1.12.2 的 SPacketChunkData
        """
        result = bytearray()
        
        section_mask = self.get_section_mask()
        
        # 写入每个存在的区块段（支持 64 sections = 1024 格高度）
        for i in range(SECTION_COUNT):
            if section_mask & (1 << i):
                if i in self.sections:
                    section = self.sections[i]
                    result.extend(section.get_block_data())
                    result.extend(section.get_light_data(has_sky_light))
        
        # 生物群系数据（只在 full chunk 时发送）
        result.extend(bytes(self.biomes))
        
        return bytes(result)
    
    def generate_flat_world(self, grass_y: int = 60):
        """
        生成标准超平坦世界
        默认 1.12.2 超平坦：y=0-2 基岩，y=3-5 泥土，y=6 草方块
        """
        # 标准超平坦地形
        for x in range(16):
            for z in range(16):
                # y=0-2: 基岩 (bedrock, block_id=7)
                for y in range(0, 3):
                    section_y = y // SECTION_HEIGHT
                    local_y = y % SECTION_HEIGHT
                    self.sections[section_y].set_block(x, local_y, z, 7 << 4)  # bedrock
                
                # y=3-5: 泥土 (dirt, block_id=3)
                for y in range(3, 6):
                    section_y = y // SECTION_HEIGHT
                    local_y = y % SECTION_HEIGHT
                    self.sections[section_y].set_block(x, local_y, z, 3 << 4)  # dirt
                
                # y=6: 草方块 (grass, block_id=2)
                y = 6
                section_y = y // SECTION_HEIGHT
                local_y = y % SECTION_HEIGHT
                self.sections[section_y].set_block(x, local_y, z, 2 << 4)  # grass
        
        self.is_modified = True
        log_info(f"Generated superflat world for chunk ({self.chunk_x}, {self.chunk_z})")
    
    def generate_realistic_terrain(self, terrain_gen):
        """
        使用真实地形生成器生成地形
        terrain_gen: TerrainGenerator 实例
        """
        from nebula.world.terrain_generator import TerrainGenerator
        
        # 生成该区块的所有方块
        blocks = terrain_gen.generate_chunk_column(self.chunk_x, self.chunk_z)
        
        # 设置方块
        for local_x, y, local_z, block_state in blocks:
            if 0 <= y < CHUNK_HEIGHT:
                section_y = y // SECTION_HEIGHT
                local_y = y % SECTION_HEIGHT
                if section_y in self.sections:
                    self.sections[section_y].set_block(local_x, local_y, local_z, block_state)
        
        # 设置生物群系
        for x in range(16):
            for z in range(16):
                world_x = self.chunk_x * 16 + x
                world_z = self.chunk_z * 16 + z
                height = terrain_gen.get_height(world_x, world_z)
                biome = terrain_gen.get_biome(world_x, world_z, height)
                # 将生物群系名称转换为 ID
                biome_id = self._biome_name_to_id(biome)
                self.biomes[z * 16 + x] = biome_id
        
        self.is_modified = True
        log_info(f"Generated realistic terrain for chunk ({self.chunk_x}, {self.chunk_z})")
    
    def _biome_name_to_id(self, biome_name: str) -> int:
        """将生物群系名称转换为 ID"""
        biome_map = {
            "ocean": 0,
            "plains": 1,
            "desert": 2,
            "mountains": 3,
            "forest": 4,
            "taiga": 5,
            "swamp": 6,
            "river": 7,
            "beach": 16,
            "jungle": 21,
            "savanna": 35,
            "snowy_tundra": 12,
            "snowy_mountains": 13,
            "snowy_taiga": 30,
        }
        return biome_map.get(biome_name, 1)  # 默认为草原
