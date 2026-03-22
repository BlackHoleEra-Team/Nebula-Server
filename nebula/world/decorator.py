"""
Nebula Minecraft Server - 世界装饰器
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

import random
from typing import List, Tuple, Optional
from nebula.logging import log_info, log_error


class WorldDecorator:
    """
    世界装饰器 - 基于原版 Minecraft 逻辑（简化版）
    """
    
    # 方块状态常量 (block_id << 4 | metadata)
    BLOCK_AIR = 0
    BLOCK_GRASS_BLOCK = 32  # grass block (id=2, meta=0)
    BLOCK_DIRT = 48   # dirt (id=3, meta=0)
    
    # 植物方块 - 草丛 (tallgrass id=31)
    BLOCK_TALLGRASS = (31 << 4) | 1  # meta=1 是草
    BLOCK_FERN = (31 << 4) | 2  # meta=2 是蕨
    
    # 花朵
    BLOCK_DANDELION = (37 << 4) | 0  # yellow_flower id=37
    BLOCK_POPPY = (38 << 4) | 0  # red_flower id=38, meta=0 罂粟
    
    # 原木和树叶
    BLOCK_LOG_OAK = (17 << 4) | 0  # log id=17, meta=0 橡木
    BLOCK_LEAVES_OAK = (18 << 4) | 0  # leaves id=18, meta=0 橡树树叶
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.rng = random.Random(seed)
        
        # 简化配置
        self.biome_decorations = {
            'plains': {'trees': 0, 'grass': 8, 'flowers': 3},
            'forest': {'trees': 8, 'grass': 5, 'flowers': 2},
            'mountains': {'trees': 1, 'grass': 3, 'flowers': 1},
            'hills': {'trees': 2, 'grass': 6, 'flowers': 2},
            'desert': {'trees': 0, 'grass': 0, 'flowers': 0},
            'beach': {'trees': 0, 'grass': 1, 'flowers': 0},
            'ocean': {'trees': 0, 'grass': 0, 'flowers': 0},
            'ice_mountains': {'trees': 0, 'grass': 0, 'flowers': 0},
        }
    
    def decorate_chunk(self, chunk, chunk_x: int, chunk_z: int, 
                       heightmap: List[Tuple[int, float, str]]):
        """装饰整个区块 - 简化版"""
        try:
            # 设置随机种子
            chunk_seed = self.seed + chunk_x * 341873128712 + chunk_z * 132897987541
            self.rng.seed(chunk_seed)
            
            # 获取主要生物群系
            biome_counts = {}
            for height, noise, biome in heightmap:
                biome_counts[biome] = biome_counts.get(biome, 0) + 1
            
            main_biome = max(biome_counts.keys(), key=lambda b: biome_counts[b])
            decor_config = self.biome_decorations.get(main_biome, self.biome_decorations['plains'])
            
            # 生成装饰
            self._gen_decorations(chunk, heightmap, decor_config)
            
        except Exception as e:
            log_error(f"Error decorating chunk ({chunk_x}, {chunk_z}): {e}")
    
    def _gen_decorations(self, chunk, heightmap: List[Tuple[int, float, str]], 
                        decor_config: dict):
        """生成装饰 - 简化版"""
        
        # 生成树木
        for _ in range(decor_config['trees']):
            x = self.rng.randint(2, 13)
            z = self.rng.randint(2, 13)
            idx = z * 16 + x
            surface_height = heightmap[idx][0]
            
            if self._can_place_tree(chunk, x, surface_height + 1, z):
                self._generate_tree(chunk, x, surface_height + 1, z)
        
        # 生成草丛
        for _ in range(decor_config['grass']):
            x = self.rng.randint(0, 15)
            z = self.rng.randint(0, 15)
            idx = z * 16 + x
            surface_height = heightmap[idx][0]
            
            if surface_height > 0 and self._can_place_plant(chunk, x, surface_height + 1, z):
                self._place_grass(chunk, x, surface_height + 1, z)
        
        # 生成花朵
        for _ in range(decor_config['flowers']):
            x = self.rng.randint(0, 15)
            z = self.rng.randint(0, 15)
            idx = z * 16 + x
            surface_height = heightmap[idx][0]
            
            if surface_height > 0 and self._can_place_plant(chunk, x, surface_height + 1, z):
                self._place_flower(chunk, x, surface_height + 1, z)
    
    def _can_place_tree(self, chunk, x: int, y: int, z: int) -> bool:
        """检查是否可以放置树"""
        if y + 6 > 250:
            return False
        
        ground = chunk.get_block(x, y - 1, z)
        if ground != self.BLOCK_GRASS_BLOCK:
            return False
        
        for dy in range(6):
            if chunk.get_block(x, y + dy, z) != self.BLOCK_AIR:
                return False
        
        return True
    
    def _can_place_plant(self, chunk, x: int, y: int, z: int) -> bool:
        """检查是否可以放置植物"""
        if chunk.get_block(x, y, z) != self.BLOCK_AIR:
            return False
        
        ground = chunk.get_block(x, y - 1, z)
        if ground not in (self.BLOCK_GRASS_BLOCK, self.BLOCK_DIRT):
            return False
        
        return True
    
    def _place_grass(self, chunk, x: int, y: int, z: int):
        """放置草丛"""
        if self.rng.random() < 0.8:
            chunk.set_block(x, y, z, self.BLOCK_TALLGRASS)
        else:
            chunk.set_block(x, y, z, self.BLOCK_FERN)
    
    def _place_flower(self, chunk, x: int, y: int, z: int):
        """放置花朵"""
        if self.rng.random() < 0.7:
            chunk.set_block(x, y, z, self.BLOCK_DANDELION)
        else:
            chunk.set_block(x, y, z, self.BLOCK_POPPY)
    
    def _generate_tree(self, chunk, x: int, y: int, z: int):
        """生成橡树"""
        tree_height = self.rng.randint(4, 6)
        
        # 树干
        for dy in range(tree_height):
            chunk.set_block(x, y + dy, z, self.BLOCK_LOG_OAK)
        
        # 树叶
        leaf_bottom = y + tree_height - 3
        
        for dy in range(4):
            leaf_y = leaf_bottom + dy
            
            if dy == 0:
                radius = 1
            elif dy == 1 or dy == 2:
                radius = 2
            else:
                radius = 0
            
            for dx in range(-radius, radius + 1):
                for dz in range(-radius, radius + 1):
                    if dx == 0 and dz == 0 and dy < 3:
                        continue
                    
                    leaf_x = x + dx
                    leaf_z = z + dz
                    
                    if 0 <= leaf_x < 16 and 0 <= leaf_z < 16:
                        if chunk.get_block(leaf_x, leaf_y, leaf_z) == self.BLOCK_AIR:
                            chunk.set_block(leaf_x, leaf_y, leaf_z, self.BLOCK_LEAVES_OAK)
        
        # 树顶
        top_y = y + tree_height
        if chunk.get_block(x, top_y, z) == self.BLOCK_AIR:
            chunk.set_block(x, top_y, z, self.BLOCK_LEAVES_OAK)
