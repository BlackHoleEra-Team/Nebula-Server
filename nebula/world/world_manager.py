"""
世界管理器
管理世界文件夹、区块加载/保存、地形生成
"""

import os
import struct
from typing import Optional, Dict, Tuple
from nebula.logging import log_info, log_error, log_warn
from nebula.config.config import WORLD_NAME
from nebula.player.player_data import init_player_data_manager
from .chunk import Chunk, CHUNK_HEIGHT
from .anvil import AnvilRegion


class WorldManager:
    """
    世界管理器
    负责管理整个世界，包括区块加载、保存和生成
    """
    
    def __init__(self, world_name: str = None):
        self.world_name = world_name or WORLD_NAME
        self.world_folder = os.path.join("world", self.world_name)
        
        # 已加载的区块缓存
        self.loaded_chunks: Dict[Tuple[int, int], Chunk] = {}
        
        # 已加载的区域文件
        self.loaded_regions: Dict[Tuple[int, int], AnvilRegion] = {}
        
        # 初始化地形生成器
        from nebula.world.terrain_generator import TerrainGenerator
        self.terrain_generator = TerrainGenerator(seed=12345)  # 使用固定种子以便测试
        
        # 初始化世界
        self._init_world()
    
    def _init_world(self):
        """初始化世界文件夹"""
        # 创建世界文件夹结构
        folders = [
            self.world_folder,
            os.path.join(self.world_folder, "region"),
            os.path.join(self.world_folder, "playerdata"),
            os.path.join(self.world_folder, "data"),
        ]
        
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
        
        # 创建level.dat
        self._create_level_dat()
        
        # 初始化玩家数据管理器
        init_player_data_manager(self.world_folder)
        
        log_info(f"World initialized: {self.world_folder}")
    
    def _create_level_dat(self):
        """创建level.dat文件"""
        level_dat_path = os.path.join(self.world_folder, "level.dat")
        
        if os.path.exists(level_dat_path):
            return
        
        # 构建level.dat NBT数据
        from nebula.network.nbt import NBTWriter
        
        level_data = {
            "Data": {
                "version": 1343,  # 1.12.2
                "LevelName": self.world_name,
                "generatorName": "flat",
                "generatorVersion": 0,
                "generatorOptions": "",
                "RandomSeed": 0,
                "MapFeatures": 0,
                "LastPlayed": 0,
                "SizeOnDisk": 0,
                "allowCommands": 1,
                "hardcore": 0,
                "initialized": 1,
                "GameType": 1,  # 创造模式
                "Difficulty": 2,  # 普通
                "DifficultyLocked": 0,
                "Time": 0,
                "DayTime": 0,
                "SpawnX": 0,
                "SpawnY": 64,
                "SpawnZ": 0,
                "raining": 0,
                "rainTime": 0,
                "thundering": 0,
                "thunderTime": 0,
                "clearWeatherTime": 0,
            }
        }
        
        try:
            from nebula.network.nbt import write_nbt
            nbt_data = write_nbt(level_data)
            
            # 写入文件 (带gzip头)
            import gzip
            with gzip.open(level_dat_path, 'wb') as f:
                f.write(nbt_data)
            
            log_info(f"Created level.dat for world: {self.world_name}")
            
        except Exception as e:
            log_error(f"Error creating level.dat: {e}")
    
    def get_region(self, chunk_x: int, chunk_z: int) -> AnvilRegion:
        """获取区块所在的区域文件"""
        region_x = chunk_x >> 5  # chunk_x // 32
        region_z = chunk_z >> 5  # chunk_z // 32
        
        if (region_x, region_z) not in self.loaded_regions:
            self.loaded_regions[(region_x, region_z)] = AnvilRegion(
                region_x, region_z, self.world_folder
            )
        
        return self.loaded_regions[(region_x, region_z)]
    
    def get_chunk(self, chunk_x: int, chunk_z: int) -> Chunk:
        """
        获取区块，如果不存在则生成
        """
        if (chunk_x, chunk_z) in self.loaded_chunks:
            return self.loaded_chunks[(chunk_x, chunk_z)]
        
        # 尝试从文件加载
        chunk = self._load_chunk(chunk_x, chunk_z)
        
        if chunk is None:
            # 生成新区块
            chunk = self._generate_chunk(chunk_x, chunk_z)
            # 保存到文件
            self._save_chunk(chunk)
        
        # 缓存区块
        self.loaded_chunks[(chunk_x, chunk_z)] = chunk
        
        return chunk
    
    def _load_chunk(self, chunk_x: int, chunk_z: int) -> Optional[Chunk]:
        """从文件加载区块"""
        region = self.get_region(chunk_x, chunk_z)
        nbt_data = region.read_chunk(chunk_x, chunk_z)
        
        if nbt_data is None:
            return None
        
        try:
            # 解析NBT数据
            from nebula.network.nbt import NBTReader
            chunk_nbt = NBTReader.read(nbt_data)
            
            # 创建区块
            chunk = Chunk(chunk_x, chunk_z)
            
            # 从NBT加载方块数据
            level = chunk_nbt.get("Level", {})
            sections = level.get("Sections", [])
            
            log_info(f"Loading chunk ({chunk_x}, {chunk_z}), found {len(sections)} sections")
            
            for section_data in sections:
                y_index = section_data.get("Y", 0)
                if y_index < 0 or y_index >= 64:  # 支持 1024 格高度 (64 sections)
                    log_warn(f"Skipping section with invalid Y: {y_index}")
                    continue
                
                # 1.12.2 格式：加载 BlockStates 数组和 Palette
                block_states = section_data.get("BlockStates", [])
                palette = section_data.get("Palette", [])
                
                log_info(f"Loading section Y={y_index}, BlockStates len={len(block_states)}, Palette len={len(palette)}")
                
                section = chunk.sections[y_index]
                
                # 如果有 Palette，使用 Palette；否则使用全局调色板（BlockStates 值直接是方块状态 ID）
                if len(palette) > 0:
                    # 使用自定义调色板
                    # 计算每个 entry 的位数
                    bits_per_entry = max(1, (len(block_states) * 64) // 4096)
                    if bits_per_entry < 1 or bits_per_entry > 13:
                        bits_per_entry = 13  # 默认使用全局调色板
                    
                    # 从 BitArray 中读取方块状态
                    from nebula.world.chunk import BitArray
                    bit_array = BitArray(bits_per_entry, 4096)
                    bit_array.from_long_array(block_states)
                    
                    for i in range(4096):
                        palette_index = bit_array.get_at(i)
                        if palette_index < len(palette):
                            block_state = palette[palette_index]
                        else:
                            block_state = 0  # 空气
                        section.set_block(i % 16, i // 256, (i // 16) % 16, block_state)
                else:
                    # 使用全局调色板（BlockStates 值直接是方块状态 ID）
                    # 计算每个 entry 的位数
                    bits_per_entry = 13  # 全局调色板使用 13 位
                    
                    from nebula.world.chunk import BitArray
                    bit_array = BitArray(bits_per_entry, 4096)
                    bit_array.from_long_array(block_states)
                    
                    for i in range(4096):
                        block_state = bit_array.get_at(i) & 0x1FFF  # 13 位掩码
                        section.set_block(i % 16, i // 256, (i // 16) % 16, block_state)
            
            # 加载biome数据
            biomes = level.get("Biomes", [])
            if len(biomes) == 256:
                chunk.biomes = list(biomes)
            
            # 标记区块为未修改（刚从文件加载）
            chunk.is_modified = False
            
            log_info(f"Loaded chunk ({chunk_x}, {chunk_z}) from file")
            return chunk
            
        except Exception as e:
            log_error(f"Error loading chunk ({chunk_x}, {chunk_z}): {e}")
            return None
    
    def _generate_chunk(self, chunk_x: int, chunk_z: int) -> Chunk:
        """生成新区块"""
        chunk = Chunk(chunk_x, chunk_z)
        
        # 使用真实地形生成器生成地形
        chunk.generate_realistic_terrain(self.terrain_generator)
        
        log_info(f"Generated chunk ({chunk_x}, {chunk_z})")
        return chunk
    
    def _save_chunk(self, chunk: Chunk):
        """保存区块到文件"""
        if not chunk.is_modified:
            return
        
        try:
            # 构建NBT数据
            sections_list = []
            
            log_info(f"Saving chunk ({chunk.chunk_x}, {chunk.chunk_z}), sections: {len([s for s in chunk.sections.values() if not s.is_empty()])}")
            
            for y_index, section in chunk.sections.items():
                if section.is_empty():
                    continue
                
                log_info(f"Saving section Y={y_index}, non_air_count={section.non_air_count}")
                
                # 1.12.2 格式：使用 BlockStates 数组（long 数组）和 Palette
                # 参考 ChunkSection.get_block_data() 的实现
                
                # 构建 BitArray
                from nebula.world.chunk import BitArray
                bits_per_entry = 13  # 使用全局调色板
                bit_array = BitArray(bits_per_entry, 4096)
                
                for i, state in enumerate(section.block_states):
                    bit_array.set_at(i, state & 0x1FFF)  # 13 位掩码
                
                # 获取 long 数组
                long_array = bit_array.get_backing_array()
                
                section_data = {
                    "Y": y_index,
                    "BlockStates": long_array,  # long 数组
                    "Palette": [],  # 空列表表示使用全局调色板
                    "SkyLight": bytes([0xFF] * 2048),  # 满天空光照
                    "BlockLight": bytes([0] * 2048),  # 无方块光照
                }
                
                sections_list.append(section_data)
            
            # 计算高度图 (HeightMap) - 支持 1024 格高度
            height_map = [0] * 256
            for x in range(16):
                for z in range(16):
                    # 从顶部向下找到第一个非空气方块
                    for y in range(CHUNK_HEIGHT - 1, -1, -1):
                        section_y = y // 16
                        local_y = y % 16
                        if section_y in chunk.sections:
                            section = chunk.sections[section_y]
                            idx = local_y * 256 + z * 16 + x
                            if section.block_states[idx] != 0:  # 非空气
                                height_map[z * 16 + x] = min(255, y + 1)  # 限制在 255 以内
                                break
            
            # 构建完整的NBT结构
            chunk_nbt = {
                "Level": {
                    "xPos": chunk.chunk_x,
                    "zPos": chunk.chunk_z,
                    "LastUpdate": 0,
                    "LightPopulated": 1,
                    "TerrainPopulated": 1,
                    "V": 1,
                    "InhabitedTime": 0,
                    "Biomes": bytes(chunk.biomes),
                    "HeightMap": height_map,
                    "Sections": sections_list,
                    "Entities": [],
                    "TileEntities": [],
                    "TileTicks": [],
                },
                "DataVersion": 1343,  # 1.12.2
            }
            
            # 写入NBT
            from nebula.network.nbt import write_nbt_to_bytes
            nbt_data = write_nbt_to_bytes(chunk_nbt)
            
            # 保存到区域文件
            region = self.get_region(chunk.chunk_x, chunk.chunk_z)
            region.write_chunk(chunk.chunk_x, chunk.chunk_z, nbt_data)
            
            chunk.is_modified = False
            log_info(f"Saved chunk ({chunk.chunk_x}, {chunk.chunk_z})")
            
        except Exception as e:
            log_error(f"Error saving chunk ({chunk.chunk_x}, {chunk.chunk_z}): {e}")
    
    def save_all(self):
        """保存所有已加载的区块"""
        for chunk in self.loaded_chunks.values():
            self._save_chunk(chunk)
        
        log_info(f"Saved {len(self.loaded_chunks)} chunks")


# 全局世界管理器实例
_world_manager: Optional[WorldManager] = None


def get_world_manager() -> WorldManager:
    """获取全局世界管理器实例"""
    global _world_manager
    if _world_manager is None:
        _world_manager = WorldManager()
    return _world_manager
