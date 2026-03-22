"""
Nebula Minecraft Server - 喀斯特地貌生成器
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
6. 峰林/石林地表形态
"""

import math
import random
from typing import Tuple, List, Optional, Dict, Set
from dataclasses import dataclass, field
from nebula.logging import log_info, log_error

# 尝试导入 Numba 加速
try:
    from numba import njit, prange
    import numpy as np
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

# Numba 加速的噪声函数
if HAS_NUMBA:
    @njit(cache=True)
    def _hash3d_numba(x, y, z, perm):
        """Numba加速的3D哈希"""
        idx = ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791)) & 255
        return (perm[idx] / 255.0) * 2 - 1
    
    @njit(cache=True)
    def _sample_3d_noise(x, y, z, perm):
        """Numba加速的3D噪声采样"""
        x0, y0, z0 = int(x), int(y), int(z)
        xf, yf, zf = x - x0, y - y0, z - z0
        
        # 8个角落
        c000 = _hash3d_numba(x0, y0, z0, perm)
        c001 = _hash3d_numba(x0, y0, z0 + 1, perm)
        c010 = _hash3d_numba(x0, y0 + 1, z0, perm)
        c011 = _hash3d_numba(x0, y0 + 1, z0 + 1, perm)
        c100 = _hash3d_numba(x0 + 1, y0, z0, perm)
        c101 = _hash3d_numba(x0 + 1, y0, z0 + 1, perm)
        c110 = _hash3d_numba(x0 + 1, y0 + 1, z0, perm)
        c111 = _hash3d_numba(x0 + 1, y0 + 1, z0 + 1, perm)
        
        # 三线性插值
        u = xf * xf * (3 - 2 * xf)
        v = yf * yf * (3 - 2 * yf)
        w = zf * zf * (3 - 2 * zf)
        
        # X方向插值
        c00 = c000 + u * (c100 - c000)
        c01 = c001 + u * (c101 - c001)
        c10 = c010 + u * (c110 - c010)
        c11 = c011 + u * (c111 - c011)
        
        # Y方向插值
        c0 = c00 + v * (c10 - c00)
        c1 = c01 + v * (c11 - c01)
        
        # Z方向插值
        return c0 + w * (c1 - c0)
    
    @njit(cache=True)
    def _generate_cave_noise_batch(world_x_base, world_z_base, region_size, 
                                   min_height, max_height, perm,
                                   limestone_scale, vertical_scale, threshold_base):
        """Numba加速的批量洞穴噪声生成"""
        results = []
        
        for y in range(min_height, max_height, 2):
            threshold = threshold_base - (y / 200) * 0.2
            for z in range(region_size):
                world_z = world_z_base + z
                for x in range(region_size):
                    world_x = world_x_base + x
                    
                    # 3D噪声采样
                    noise_val = _sample_3d_noise(
                        world_x * 0.03,
                        y * 0.03,
                        world_z * 0.03,
                        perm
                    )
                    
                    if noise_val > threshold:
                        intensity = min(1.0, (noise_val - threshold) / (1 - threshold) * 1.5)
                        results.append((world_x, y, world_z, intensity))
        
        return results
    
    @njit(cache=True)
    def _batch_distance_check(points_x, points_y, points_z, max_dist_sq):
        """Numba加速的批量距离检查"""
        n = len(points_x)
        result = []
        for i in range(n):
            for j in range(i + 1, n):
                dx = points_x[i] - points_x[j]
                dy = points_y[i] - points_y[j]
                dz = points_z[i] - points_z[j]
                dist_sq = dx * dx + dy * dy + dz * dz
                if dist_sq < max_dist_sq:
                    result.append((i, j))
        return result
    



@dataclass
class CaveNode:
    """洞穴网络节点"""
    x: float
    y: float
    z: float
    radius: float
    connections: List[int] = field(default_factory=list)


@dataclass
class UndergroundRiver:
    """地下河路径"""
    path: List[Tuple[int, int, int]]  # (x, y, z) 路径点
    width: float
    depth: float
    flow_strength: float


class KarstBaseLayer:
    """
    石灰岩基底分布 (31)
    使用3D噪声定义可溶性岩石区域
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 石灰岩分布参数 - 使用更大的尺度避免所有点在同一个网格
        self.limestone_threshold = -0.1  # 阈值
        self.limestone_scale = 0.05      # 增大尺度确保跨越多个网格
        self.vertical_scale = 0.03       # 垂直方向
        
        # 可溶性等级 (0-1)
        self.solubility_scale = 0.05
    
    def get_limestone_mask(self, x: int, y: int, z: int) -> bool:
        """判断位置是否为石灰岩"""
        noise_val = self.noise.sample_3d(
            x * self.limestone_scale,
            y * self.vertical_scale,
            z * self.limestone_scale
        )
        return noise_val > self.limestone_threshold
    
    def get_solubility(self, x: int, y: int, z: int) -> float:
        """获取岩石可溶性 (0-1)"""
        noise_val = self.noise.sample_3d(
            x * self.solubility_scale + 1000,
            y * self.vertical_scale * 0.5,
            z * self.solubility_scale + 1000
        )
        # 映射到 0.1-1.0
        return 0.1 + (noise_val + 1) * 0.45


class GroundwaterSeepage:
    """
    地下水渗透算法 (32)
    基于简化Darcy定律模拟地下水流
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 水位参数
        self.water_table_level = 45  # 地下水位基准
        self.water_table_variation = 15  # 水位变化范围
        
        # 渗透参数
        self.hydraulic_conductivity = 0.1  # 水力传导系数
        self.porosity = 0.15  # 孔隙度
    
    def get_water_table_height(self, x: int, z: int) -> int:
        """获取某位置的地下水位高度"""
        # 使用更大的尺度来获得更明显的水位变化
        variation = self.noise.sample_2d(x * 0.05 + 5000, z * 0.05 + 5000)
        return int(self.water_table_level + variation * self.water_table_variation)
    
    def get_flow_direction(self, x: int, y: int, z: int, 
                          limestone_mask: callable) -> Tuple[float, float, float]:
        """
        获取地下水流动方向 (dx, dy, dz)
        水从高势能流向低势能
        """
        # 计算局部梯度
        delta = 2
        
        # 势能场（基于高度和渗透性）
        def potential(px, py, pz):
            if not limestone_mask(px, py, pz):
                return -1000  # 非石灰岩区域势能极低（不可渗透）
            
            # 势能 = 高度 + 噪声扰动
            height_potential = py
            noise_potential = self.noise.sample_3d(
                px * 0.005, py * 0.01, pz * 0.005
            ) * 5
            return height_potential + noise_potential
        
        p0 = potential(x, y, z)
        px1 = potential(x + delta, y, z)
        px2 = potential(x - delta, y, z)
        py1 = potential(x, y + delta, z)
        py2 = potential(x, y - delta, z)
        pz1 = potential(x, y, z + delta)
        pz2 = potential(x, y, z - delta)
        
        # 计算梯度（指向低势能）
        dx = (px2 - px1) / (2 * delta)
        dy = (py2 - py1) / (2 * delta)
        dz = (pz2 - pz1) / (2 * delta)
        
        # 归一化
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if length > 0:
            return (dx/length, dy/length, dz/length)
        return (0, -1, 0)  # 默认向下
    
    def trace_flow_path(self, start_x: int, start_y: int, start_z: int,
                       limestone_mask: callable,
                       max_steps: int = 100) -> List[Tuple[int, int, int]]:
        """
        追踪一条地下水流动路径
        返回路径点列表
        """
        path = [(start_x, start_y, start_z)]
        x, y, z = start_x, start_y, start_z
        
        for _ in range(max_steps):
            # 获取流动方向
            dx, dy, dz = self.get_flow_direction(x, y, z, limestone_mask)
            
            # 移动到下一个位置（步长基于传导系数）
            step_size = max(1, int(self.hydraulic_conductivity * 10))
            nx = int(x + dx * step_size)
            ny = int(y + dy * step_size)
            nz = int(z + dz * step_size)
            
            # 检查边界
            if ny < 5:  # 到达底部
                break
            
            # 检查是否还在石灰岩中
            if not limestone_mask(nx, ny, nz):
                # 尝试找到附近的石灰岩
                found = False
                for r in range(1, 4):
                    for ox in range(-r, r+1):
                        for oz in range(-r, r+1):
                            for oy in range(-r//2, r//2+1):
                                if limestone_mask(nx+ox, ny+oy, nz+oz):
                                    nx, ny, nz = nx+ox, ny+oy, nz+oz
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break
                    if found:
                        break
                if not found:
                    break
            
            # 添加路径点
            if (nx, ny, nz) != (x, y, z):
                path.append((nx, ny, nz))
                x, y, z = nx, ny, nz
            else:
                break
        
        return path


class KarstDissolution:
    """
    碳酸水溶蚀算法 (33)
    沿水流路径溶解岩石，形成通道
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 溶蚀参数 - 增强溶蚀效果
        self.base_dissolution_rate = 0.15  # 增加基础溶蚀速率
        self.co2_concentration = 0.5  # 增加CO2浓度
        self.temperature_factor = 1.2  # 增加温度因子
    
    def calculate_dissolution(self, x: int, y: int, z: int,
                             flow_strength: float,
                             solubility: float) -> float:
        """
        计算溶蚀量
        返回溶解的岩石体积比例 (0-1)
        """
        # 基础溶蚀速率
        rate = self.base_dissolution_rate * solubility
        
        # 水流强度影响（更强的水流带走更多溶解物质，促进进一步溶蚀）
        rate *= (1 + flow_strength * 2)
        
        # CO2浓度影响
        rate *= (0.5 + self.co2_concentration)
        
        # 温度影响（温度越高溶蚀越快）
        rate *= self.temperature_factor
        
        # 添加噪声变化
        noise = self.noise.sample_3d(x * 0.02, y * 0.02, z * 0.02)
        rate *= (0.8 + noise * 0.4)
        
        return min(1.0, rate)
    
    def dissolve_along_path(self, path: List[Tuple[int, int, int]],
                           solubility_fn: callable,
                           dissolution_map: Dict[Tuple[int, int, int], float]) -> Dict[Tuple[int, int, int], float]:
        """
        沿路径进行溶蚀
        返回更新的溶蚀映射
        """
        for i, (x, y, z) in enumerate(path):
            # 计算该位置的流动强度（路径中间最强）
            path_progress = i / len(path) if len(path) > 1 else 0.5
            flow_strength = math.sin(path_progress * math.pi)  # 中间最强
            
            # 获取可溶性
            solubility = solubility_fn(x, y, z)
            
            # 计算溶蚀
            dissolution = self.calculate_dissolution(x, y, z, flow_strength, solubility)
            
            # 更新溶蚀映射
            key = (x, y, z)
            if key in dissolution_map:
                dissolution_map[key] = min(1.0, dissolution_map[key] + dissolution)
            else:
                dissolution_map[key] = dissolution
            
            # 影响周围区域（溶蚀扩散）
            radius = int(1 + dissolution * 2)
            if radius < 1:
                radius = 1
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                        if dist <= radius and dist > 0:  # 避免 dist=0 导致除零
                            # 距离越远影响越小
                            factor = 1 - (dist / radius)
                            neighbor_key = (x + dx, y + dy, z + dz)
                            neighbor_dissolution = dissolution * factor * 0.5
                            
                            if neighbor_key in dissolution_map:
                                dissolution_map[neighbor_key] = min(1.0, 
                                    dissolution_map[neighbor_key] + neighbor_dissolution)
                            else:
                                dissolution_map[neighbor_key] = neighbor_dissolution
        
        return dissolution_map


class CaveNetworkGenerator:
    """
    溶洞/地下空洞生成器 (34)
    结合3D噪声和溶蚀模拟生成洞穴网络
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 洞穴参数
        self.cave_density = 0.4  # 洞穴密度
        self.min_cave_height = 15  # 最低洞穴高度
        self.max_cave_height = 80  # 最高洞穴高度
        self.cave_scale = 0.008  # 洞穴噪声尺度
        
        # 子系统
        self.base_layer = KarstBaseLayer(seed)
        self.seepage = GroundwaterSeepage(seed)
        self.dissolution = KarstDissolution(seed)
    
    def generate_cave_network(self, chunk_x: int, chunk_z: int,
                             heightmap: List[List[int]]) -> Dict[Tuple[int, int, int], float]:
        """
        生成洞穴网络
        返回: {(x, y, z): 空洞强度} 映射
        """
        # 扩展区域（包含周围区块）
        region_size = 48
        half_size = region_size // 2
        world_x_base = chunk_x * 16 - half_size + 8
        world_z_base = chunk_z * 16 - half_size + 8
        
        # 初始化溶蚀映射
        dissolution_map: Dict[Tuple[int, int, int], float] = {}
        
        # 1. 生成多条地下水流动路径
        num_sources = 20  # 水源数量
        
        for _ in range(num_sources):
            # 随机选择水源位置（地表附近）
            sx = world_x_base + random.randint(0, region_size - 1)
            sz = world_z_base + random.randint(0, region_size - 1)
            
            # 获取地表高度
            local_x = sx - world_x_base
            local_z = sz - world_z_base
            if 0 <= local_x < region_size and 0 <= local_z < region_size:
                surface_y = heightmap[local_z][local_x]
            else:
                surface_y = 64
            
            # 水源从地下水位开始
            sy = self.seepage.get_water_table_height(sx, sz)
            sy = max(self.min_cave_height, min(surface_y - 5, sy))
            
            # 检查是否为石灰岩区域
            if not self.base_layer.get_limestone_mask(sx, sy, sz):
                continue
            
            # 追踪流动路径
            path = self.seepage.trace_flow_path(
                sx, sy, sz,
                lambda x, y, z: self.base_layer.get_limestone_mask(x, y, z),
                max_steps=80
            )
            
            # 沿路径溶蚀
            if len(path) > 5:
                dissolution_map = self.dissolution.dissolve_along_path(
                    path,
                    lambda x, y, z: self.base_layer.get_solubility(x, y, z),
                    dissolution_map
                )
        
        # 2. 添加3D噪声洞穴（Perlin噪声 + 溶蚀场）
        dissolution_map = self._add_noise_caves(
            world_x_base, world_z_base, region_size, dissolution_map
        )
        
        # 3. 连接相邻的空洞（形成网络）
        dissolution_map = self._connect_caves(dissolution_map)
        
        return dissolution_map
    
    def _add_noise_caves(self, world_x_base: int, world_z_base: int,
                        region_size: int,
                        dissolution_map: Dict[Tuple[int, int, int], float]) -> Dict[Tuple[int, int, int], float]:
        """添加基于3D噪声的洞穴 - 使用Numba加速"""
        
        if HAS_NUMBA:
            # 使用Numba加速批量生成
            perm = np.array(self.noise.perm, dtype=np.int32)
            results = _generate_cave_noise_batch(
                world_x_base, world_z_base, region_size,
                self.min_cave_height, self.max_cave_height, perm,
                0.03, 0.03, 0.3
            )
            
            # 将结果合并到溶解映射
            for world_x, y, world_z, intensity in results:
                # 检查是否为石灰岩
                if not self.base_layer.get_limestone_mask(world_x, y, world_z):
                    continue
                    
                key = (world_x, y, world_z)
                if key in dissolution_map:
                    dissolution_map[key] = min(1.0, dissolution_map[key] + intensity)
                else:
                    dissolution_map[key] = intensity
        else:
            # 回退到纯Python实现
            for y in range(self.min_cave_height, self.max_cave_height, 2):
                for z in range(region_size):
                    for x in range(region_size):
                        world_x = world_x_base + x
                        world_z = world_z_base + z

                        # 检查是否为石灰岩
                        if not self.base_layer.get_limestone_mask(world_x, y, world_z):
                            continue

                        # 3D噪声采样
                        noise_val = self.noise.sample_3d(
                            world_x * 0.03,
                            y * 0.03,
                            world_z * 0.03
                        )

                        threshold = 0.3 - (y / 200) * 0.2

                        if noise_val > threshold:
                            intensity = min(1.0, (noise_val - threshold) / (1 - threshold) * 1.5)

                            key = (world_x, y, world_z)
                            if key in dissolution_map:
                                dissolution_map[key] = min(1.0, dissolution_map[key] + intensity)
                            else:
                                dissolution_map[key] = intensity

        return dissolution_map
    
    def _connect_caves(self, dissolution_map: Dict[Tuple[int, int, int], float]) -> Dict[Tuple[int, int, int], float]:
        """连接相邻的空洞形成网络 - 优化版本"""

        # 找到所有高溶蚀区域（潜在洞穴）
        high_dissolution = [(k, v) for k, v in dissolution_map.items() if v > 0.4]

        if len(high_dissolution) < 2:
            return dissolution_map

        # 限制处理数量以提高性能
        max_points = min(100, len(high_dissolution))
        high_dissolution = sorted(high_dissolution, key=lambda x: x[1], reverse=True)[:max_points]
        points = [k for k, v in high_dissolution]

        # 使用Numba加速距离检查（如果可用且点数足够多）
        if HAS_NUMBA and len(points) > 20:
            points_x = np.array([p[0] for p in points], dtype=np.float64)
            points_y = np.array([p[1] for p in points], dtype=np.float64)
            points_z = np.array([p[2] for p in points], dtype=np.float64)
            
            # Numba加速批量距离检查
            pairs = _batch_distance_check(points_x, points_y, points_z, 100.0)
            
            # 创建隧道
            for i, j in pairs:
                dissolution_map = self._create_tunnel(points[i], points[j], dissolution_map)
        else:
            # 纯Python版本
            for i, p1 in enumerate(points):
                for p2 in points[i+1:]:
                    dist_sq = (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2
                    if dist_sq < 100:  # 距离 < 10
                        dissolution_map = self._create_tunnel(p1, p2, dissolution_map)

        return dissolution_map
    
    def _create_tunnel(self, p1: Tuple[int, int, int], p2: Tuple[int, int, int],
                      dissolution_map: Dict[Tuple[int, int, int], float]) -> Dict[Tuple[int, int, int], float]:
        """在两个点之间创建通道"""
        
        # 线性插值创建路径
        steps = int(math.sqrt(
            (p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2
        ))
        
        if steps == 0:
            return dissolution_map
        
        for i in range(steps + 1):
            t = i / steps
            x = int(p1[0] + (p2[0] - p1[0]) * t)
            y = int(p1[1] + (p2[1] - p1[1]) * t)
            z = int(p1[2] + (p2[2] - p1[2]) * t)
            
            # 通道中心强度最高，向外递减
            for dx in range(-1, 2):
                for dy in range(-1, 2):
                    for dz in range(-1, 2):
                        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                        intensity = max(0, 0.6 - dist * 0.3)
                        
                        key = (x + dx, y + dy, z + dz)
                        if key in dissolution_map:
                            dissolution_map[key] = min(1.0, dissolution_map[key] + intensity)
                        else:
                            dissolution_map[key] = intensity
        
        return dissolution_map
    
    def extract_cave_nodes(self, dissolution_map: Dict[Tuple[int, int, int], float],
                          threshold: float = 0.3) -> List[CaveNode]:
        """
        从溶蚀映射中提取洞穴节点
        优化版本：限制节点数量，简化连接计算
        """
        # 批量创建节点 - 使用列表推导式
        nodes = [
            CaveNode(x, y, z, 1 + intensity * 2)
            for (x, y, z), intensity in dissolution_map.items()
            if intensity >= threshold
        ]
        
        # 优化：限制最大节点数量
        max_nodes = 200
        if len(nodes) > max_nodes:
            # 按强度排序，保留最强的节点
            nodes.sort(key=lambda n: n.radius, reverse=True)
            nodes = nodes[:max_nodes]
        
        if not nodes:
            return nodes
        
        # 简化：只计算节点位置，不建立复杂连接关系
        # 连接关系在需要时动态计算
        return nodes


class CaveCollapse:
    """
    溶洞塌陷算法 (35)
    当空洞上方岩石过薄时塌陷，形成天坑
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 塌陷参数
        self.min_roof_thickness = 3  # 最小顶板厚度
        self.collapse_threshold = 0.7  # 塌陷概率阈值
        self.collapse_radius_factor = 2.0  # 塌陷半径因子
    
    def detect_collapses(self, cave_nodes: List[CaveNode],
                        surface_height: Dict[Tuple[int, int], int]) -> List[Tuple[int, int, int, float]]:
        """
        检测可能发生塌陷的位置
        返回: [(x, y, z, 塌陷半径), ...]
        """
        collapses = []
        
        for node in cave_nodes:
            # 获取该位置的地表高度
            surface_key = (int(node.x), int(node.z))
            if surface_key not in surface_height:
                continue
            
            surface_y = surface_height[surface_key]
            cave_y = node.y
            
            # 计算顶板厚度
            roof_thickness = surface_y - cave_y - node.radius
            
            # 检查是否满足塌陷条件
            if roof_thickness < self.min_roof_thickness and cave_y < surface_y:
                # 计算塌陷概率（越薄越容易塌陷）
                collapse_prob = 1.0 - (roof_thickness / self.min_roof_thickness)
                collapse_prob = max(0, min(1, collapse_prob))
                
                # 添加噪声变化（增加随机性但保持高概率）
                noise = self.noise.sample_3d(node.x * 0.05, node.y * 0.05, node.z * 0.05)
                # 噪声范围 [-1, 1]，映射到 [0.7, 1.3] 保持高概率
                noise_factor = 1.0 + noise * 0.3
                collapse_prob *= noise_factor
                collapse_prob = min(1.0, collapse_prob)
                
                if collapse_prob > self.collapse_threshold:
                    # 计算塌陷半径
                    radius = node.radius * self.collapse_radius_factor * (1 + collapse_prob)
                    collapses.append((int(node.x), int(node.y), int(node.z), radius))
        
        return collapses
    
    def apply_collapse(self, heightmap: List[List[int]],
                      collapse: Tuple[int, int, int, float],
                      dissolution_map: Dict[Tuple[int, int, int], float]) -> List[List[int]]:
        """
        应用塌陷到高度图
        返回更新后的高度图
        """
        cx, cy, cz, radius = collapse
        
        # 影响范围
        r = int(radius)
        
        for dz in range(-r, r + 1):
            for dx in range(-r, r + 1):
                dist = math.sqrt(dx*dx + dz*dz)
                if dist > radius:
                    continue
                
                x, z = cx + dx, cz + dz
                
                # 检查边界
                if z < 0 or z >= len(heightmap) or x < 0 or x >= len(heightmap[0]):
                    continue
                
                # 计算塌陷深度（中心最深）
                depth_factor = 1 - (dist / radius)
                collapse_depth = int((cy + radius - heightmap[z][x]) * depth_factor)
                
                # 应用塌陷
                if collapse_depth > 0:
                    heightmap[z][x] = max(int(cy), heightmap[z][x] - collapse_depth)
                
                # 标记为开放空间（连接地表和洞穴）
                for y in range(heightmap[z][x], int(cy + radius)):
                    key = (x, y, z)
                    dissolution_map[key] = 1.0  # 完全溶解
        
        return heightmap


class KarstPeakForest:
    """
    桂林峰林算法 (36)
    在强烈溶蚀区形成离散石峰
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 峰林参数
        self.peak_density = 0.3
        self.min_peak_height = 15
        self.max_peak_height = 60
        self.peak_spacing = 20
        self.base_width = 8
    
    def generate_peaks(self, chunk_x: int, chunk_z: int,
                      dissolution_map: Dict[Tuple[int, int, int], float],
                      base_heightmap: List[List[int]]) -> List[Tuple[int, int, int, float, float]]:
        """
        生成峰林
        返回: [(x, y, z, 高度, 半径), ...]
        """
        peaks = []
        
        # 计算溶蚀强度场
        region_size = 48
        half_size = region_size // 2
        world_x_base = chunk_x * 16 - half_size + 8
        world_z_base = chunk_z * 16 - half_size + 8
        
        # 找到强烈溶蚀区域
        strong_dissolution = {}
        for (x, y, z), intensity in dissolution_map.items():
            if intensity > 0.5:
                key = (x, z)
                if key not in strong_dissolution or strong_dissolution[key] < intensity:
                    strong_dissolution[key] = intensity
        
        # 在强烈溶蚀区生成石峰
        for (wx, wz), dissolution in strong_dissolution.items():
            if dissolution < 0.7:
                continue
            
            # 检查间距
            too_close = False
            for px, py, pz, ph, pr in peaks:
                dist = math.sqrt((wx-px)**2 + (wz-pz)**2)
                if dist < self.peak_spacing:
                    too_close = True
                    break
            
            if too_close:
                continue
            
            # 计算峰高（基于溶蚀强度和噪声）
            local_x = wx - world_x_base
            local_z = wz - world_z_base
            if 0 <= local_x < region_size and 0 <= local_z < region_size:
                base_y = base_heightmap[local_z][local_x]
            else:
                base_y = 64
            
            noise_val = self.noise.sample_2d(wx * 0.01, wz * 0.01)
            peak_height = self.min_peak_height + (noise_val + 1) * 0.5 * (self.max_peak_height - self.min_peak_height)
            peak_height *= dissolution  # 溶蚀越强，峰越高
            
            # 计算峰底半径
            radius = self.base_width + noise_val * 3
            
            peaks.append((wx, base_y, wz, peak_height, radius))
        
        return peaks
    
    def apply_to_heightmap(self, heightmap: List[List[int]],
                          peaks: List[Tuple[int, int, int, float, float]],
                          chunk_x: int, chunk_z: int) -> List[List[int]]:
        """
        将峰林应用到高度图
        """
        world_x_base = chunk_x * 16
        world_z_base = chunk_z * 16
        
        for px, py, pz, pheight, pradius in peaks:
            # 影响范围
            r = int(pradius * 2)
            
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    dist = math.sqrt(dx*dx + dz*dz)
                    if dist > pradius * 2:
                        continue
                    
                    wx, wz = int(px + dx), int(pz + dz)
                    
                    # 转换为局部坐标
                    local_x = wx - world_x_base
                    local_z = wz - world_z_base
                    
                    if local_z < 0 or local_z >= len(heightmap) or local_x < 0 or local_x >= len(heightmap[0]):
                        continue
                    
                    # 计算锥形高度
                    if dist <= pradius:
                        # 峰顶
                        height_boost = pheight * (1 - dist / pradius)
                    else:
                        # 缓坡过渡
                        t = (dist - pradius) / pradius
                        height_boost = pheight * 0.3 * (1 - t)
                    
                    # 应用高度
                    heightmap[local_z][local_x] = max(heightmap[local_z][local_x], int(py + height_boost))
        
        return heightmap


class StoneForest:
    """
    石林算法 (37)
    在近水平岩层生成密集石柱
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        
        # 石林参数 - 增加密度
        self.pillar_density = 0.85  # 增加密度
        self.min_pillar_height = 5
        self.max_pillar_height = 25
        self.pillar_spacing = 3
        self.pillar_width = 1.5
    
    def generate_pillars(self, chunk_x: int, chunk_z: int,
                        base_heightmap: List[List[int]]) -> List[Tuple[int, int, int, float, float]]:
        """
        生成石柱
        返回: [(x, y, z, 高度, 宽度), ...]
        """
        pillars = []
        
        region_size = 48
        half_size = region_size // 2
        world_x_base = chunk_x * 16 - half_size + 8
        world_z_base = chunk_z * 16 - half_size + 8
        
        # 网格化生成（石林通常较规则）
        grid_size = 4
        
        for gz in range(0, region_size, grid_size):
            for gx in range(0, region_size, grid_size):
                # 在每个网格内随机生成石柱
                if random.random() > self.pillar_density:
                    continue
                
                # 网格内偏移
                offset_x = random.randint(0, grid_size - 1)
                offset_z = random.randint(0, grid_size - 1)
                
                wx = world_x_base + gx + offset_x
                wz = world_z_base + gz + offset_z
                
                # 获取基础高度
                local_x = gx + offset_x
                local_z = gz + offset_z
                if 0 <= local_x < region_size and 0 <= local_z < region_size:
                    base_y = base_heightmap[local_z][local_x]
                else:
                    continue
                
                # 噪声决定石柱高度 - 确保高度为正
                noise_val = self.noise.sample_2d(wx * 0.02, wz * 0.02)
                if noise_val < -0.5:  # 降低阈值
                    continue
                
                # 将噪声从[-1,1]映射到[0,1]确保高度为正
                normalized_noise = (noise_val + 1) * 0.5
                height = self.min_pillar_height + normalized_noise * (self.max_pillar_height - self.min_pillar_height)
                width = self.pillar_width + normalized_noise * 0.5
                
                pillars.append((wx, base_y, wz, height, width))
        
        return pillars
    
    def apply_to_heightmap(self, heightmap: List[List[int]],
                          pillars: List[Tuple[int, int, int, float, float]],
                          chunk_x: int, chunk_z: int) -> List[List[int]]:
        """
        将石林应用到高度图
        """
        world_x_base = chunk_x * 16
        world_z_base = chunk_z * 16
        
        for px, py, pz, pheight, pwidth in pillars:
            r = int(pwidth)
            
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    dist = math.sqrt(dx*dx + dz*dz)
                    if dist > pwidth:
                        continue
                    
                    wx, wz = int(px + dx), int(pz + dz)
                    
                    local_x = wx - world_x_base
                    local_z = wz - world_z_base
                    
                    if local_z < 0 or local_z >= len(heightmap) or local_x < 0 or local_x >= len(heightmap[0]):
                        continue
                    
                    # 石柱通常是垂直的
                    heightmap[local_z][local_x] = max(heightmap[local_z][local_x], int(py + pheight))
        
        return heightmap


class UndergroundRiverSystem:
    """
    地下河系统 (38)
    在洞穴网络中定义水流路径，可能冲出地表
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
        self.seepage = GroundwaterSeepage(seed)
    
    def generate_rivers(self, cave_nodes: List[CaveNode],
                       chunk_x: int, chunk_z: int,
                       surface_height: Dict[Tuple[int, int], int]) -> List[UndergroundRiver]:
        """
        生成地下河
        """
        rivers = []
        
        if len(cave_nodes) < 2:
            return rivers
        
        # 找到低洼的洞穴节点（水聚集处）
        sorted_nodes = sorted(cave_nodes, key=lambda n: n.y)
        
        # 选择河流起点（较高的洞穴）
        num_sources = min(3, len(sorted_nodes) // 3)
        sources = sorted_nodes[-num_sources:]
        
        for source in sources:
            # 追踪水流路径
            path = self._trace_river_path(source, cave_nodes, surface_height)
            
            if len(path) > 10:
                # 计算河流参数
                width = 2 + random.random() * 2
                depth = 2 + random.random() * 2
                flow = len(path) / 100.0
                
                river = UndergroundRiver(path, width, depth, flow)
                rivers.append(river)
        
        return rivers
    
    def _trace_river_path(self, start_node: CaveNode,
                         cave_nodes: List[CaveNode],
                         surface_height: Dict[Tuple[int, int], int]) -> List[Tuple[int, int, int]]:
        """
        追踪地下河路径
        """
        path = [(int(start_node.x), int(start_node.y), int(start_node.z))]
        
        current = start_node
        visited = {id(current)}
        
        for _ in range(100):  # 最大步数
            # 找到未访问的、更低的连接节点
            candidates = []
            for conn_idx in current.connections:
                neighbor = cave_nodes[conn_idx]
                if id(neighbor) not in visited and neighbor.y <= current.y:
                    candidates.append(neighbor)
            
            if not candidates:
                break
            
            # 选择最低的候选
            next_node = min(candidates, key=lambda n: n.y)
            
            # 添加路径点（插值）
            x1, y1, z1 = int(current.x), int(current.y), int(current.z)
            x2, y2, z2 = int(next_node.x), int(next_node.y), int(next_node.z)
            
            steps = max(abs(x2-x1), abs(y2-y1), abs(z2-z1))
            if steps > 0:
                for i in range(1, steps):
                    t = i / steps
                    px = int(x1 + (x2 - x1) * t)
                    py = int(y1 + (y2 - y1) * t)
                    pz = int(z1 + (z2 - z1) * t)
                    path.append((px, py, pz))
            
            path.append((x2, y2, z2))
            
            visited.add(id(next_node))
            current = next_node
            
            # 检查是否冲出地表
            surface_key = (int(current.x), int(current.z))
            if surface_key in surface_height:
                if current.y >= surface_height[surface_key] - 5:
                    break
        
        return path
    
    def carve_river_channels(self, heightmap: List[List[int]],
                           rivers: List[UndergroundRiver],
                           dissolution_map: Dict[Tuple[int, int, int], float],
                           chunk_x: int, chunk_z: int) -> List[List[int]]:
        """
        雕刻地下河通道
        """
        world_x_base = chunk_x * 16
        world_z_base = chunk_z * 16
        
        for river in rivers:
            for x, y, z in river.path:
                # 转换为局部坐标
                local_x = x - world_x_base
                local_z = z - world_z_base
                
                if local_z < 0 or local_z >= len(heightmap) or local_x < 0 or local_x >= len(heightmap[0]):
                    continue
                
                # 雕刻通道
                r = int(river.width)
                for dz in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        dist = math.sqrt(dx*dx + dz*dz)
                        if dist > river.width:
                            continue
                        
                        nx, nz = local_x + dx, local_z + dz
                        if nz < 0 or nz >= len(heightmap) or nx < 0 or nx >= len(heightmap[0]):
                            continue
                        
                        # 降低高度（形成河道）
                        depth = int(river.depth * (1 - dist / river.width))
                        heightmap[nz][nx] = max(int(y - river.depth), heightmap[nz][nx] - depth)
                        
                        # 标记为开放空间
                        for dy in range(int(y - river.depth), int(y + 2)):
                            key = (x + dx, dy, z + dz)
                            dissolution_map[key] = 1.0
        
        return heightmap


class NaturalBridge:
    """
    天生桥生成 (39)
    洞穴部分塌陷后残留的桥状结构
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.noise = KarstNoise3D(seed)
    
    def generate_bridges(self, cave_nodes: List[CaveNode],
                        collapse_points: List[Tuple[int, int, int, float]]) -> List[Tuple[int, int, int, int, int, int, float]]:
        """
        生成天生桥
        返回: [(x1, y1, z1, x2, y2, z2, 厚度), ...]
        使用空间哈希优化
        """
        bridges = []
        
        if len(collapse_points) < 2 or len(cave_nodes) == 0:
            return bridges
        
        # 限制塌陷点数量以提高性能
        max_collapse_points = 200
        if len(collapse_points) > max_collapse_points:
            # 确定性采样：优先选择浅层塌陷点（更可能形成桥）
            # 按y坐标排序（y越大越浅），然后均匀采样
            collapse_points = sorted(collapse_points, key=lambda p: -p[1])[:max_collapse_points]
        
        # 为洞穴节点建立空间哈希（网格大小10，因为检查范围是5）
        grid_size = 10
        cave_grid: Dict[Tuple[int, int, int], List[CaveNode]] = {}
        
        for node in cave_nodes:
            grid_x = int(node.x) // grid_size
            grid_y = int(node.y) // grid_size
            grid_z = int(node.z) // grid_size
            key = (grid_x, grid_y, grid_z)
            if key not in cave_grid:
                cave_grid[key] = []
            cave_grid[key].append(node)
        
        # 在塌陷点之间寻找可能的桥
        n = len(collapse_points)
        for i in range(n):
            x1, y1, z1, r1 = collapse_points[i]
            for j in range(i + 1, n):
                x2, y2, z2, r2 = collapse_points[j]
                dx = x1 - x2
                dy = y1 - y2
                dz = z1 - z2
                dist_sq = dx*dx + dy*dy + dz*dz
                
                # 距离适中的塌陷点之间可能形成桥 (10 < dist < 30)
                if 100 < dist_sq < 900:  # 避免sqrt计算
                    # 检查中间是否有洞穴（形成桥的空间）
                    has_cave = False
                    mid_x, mid_y, mid_z = (x1+x2)//2, (y1+y2)//2, (z1+z2)//2
                    
                    # 只检查中点附近的网格
                    mid_grid_x = mid_x // grid_size
                    mid_grid_y = mid_y // grid_size
                    mid_grid_z = mid_z // grid_size
                    
                    # 检查相邻网格（包括自身）
                    for gx in range(mid_grid_x - 1, mid_grid_x + 2):
                        for gy in range(mid_grid_y - 1, mid_grid_y + 2):
                            for gz in range(mid_grid_z - 1, mid_grid_z + 2):
                                grid_key = (gx, gy, gz)
                                if grid_key in cave_grid:
                                    for node in cave_grid[grid_key]:
                                        ndx = node.x - mid_x
                                        ndy = node.y - mid_y
                                        ndz = node.z - mid_z
                                        if ndx*ndx + ndy*ndy + ndz*ndz < 25:  # < 5
                                            has_cave = True
                                            break
                                if has_cave:
                                    break
                            if has_cave:
                                break
                        if has_cave:
                            break
                    
                    if has_cave:
                        # 计算桥厚度
                        noise = self.noise.sample_3d(mid_x * 0.1, mid_y * 0.1, mid_z * 0.1)
                        thickness = 2 + (noise + 1) * 2
                        
                        bridges.append((x1, y1, z1, x2, y2, z2, thickness))
        
        return bridges
    
    def apply_to_heightmap(self, heightmap: List[List[int]],
                          bridges: List[Tuple[int, int, int, int, int, int, float]],
                          chunk_x: int, chunk_z: int) -> List[List[int]]:
        """
        将天生桥应用到高度图
        """
        world_x_base = chunk_x * 16
        world_z_base = chunk_z * 16
        
        for x1, y1, z1, x2, y2, z2, thickness in bridges:
            # 在桥的两端之间保持高度
            steps = max(abs(x2-x1), abs(z2-z1))
            if steps == 0:
                continue
            
            for i in range(steps + 1):
                t = i / steps
                x = int(x1 + (x2 - x1) * t)
                z = int(z1 + (z2 - z1) * t)
                y = int(y1 + (y2 - y1) * t)
                
                local_x = x - world_x_base
                local_z = z - world_z_base
                
                if local_z < 0 or local_z >= len(heightmap) or local_x < 0 or local_x >= len(heightmap[0]):
                    continue
                
                # 保持桥的高度
                bridge_height = int(y + thickness)
                heightmap[local_z][local_x] = max(heightmap[local_z][local_x], bridge_height)
        
        return heightmap


class KarstNoise3D:
    """
    简化的3D噪声实现（用于喀斯特地貌）
    基于OpenSimplex2的简化版本
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        self.perm = self._init_permutation()
    
    def _init_permutation(self) -> List[int]:
        """初始化置换表"""
        rng = random.Random(self.seed)
        p = list(range(256))
        rng.shuffle(p)
        return p + p
    
    def sample_2d(self, x: float, y: float) -> float:
        """2D噪声采样"""
        # 简化的值噪声
        x0, y0 = int(x), int(y)
        xf, yf = x - x0, y - y0
        
        # 哈希获取角落值
        def hash2d(x, y):
            idx = ((x * 73856093) ^ (y * 19349663)) & 255
            return (self.perm[idx] / 255.0) * 2 - 1
        
        n00 = hash2d(x0, y0)
        n01 = hash2d(x0, y0 + 1)
        n10 = hash2d(x0 + 1, y0)
        n11 = hash2d(x0 + 1, y0 + 1)
        
        # 平滑插值
        u = xf * xf * (3 - 2 * xf)
        v = yf * yf * (3 - 2 * yf)
        
        nx0 = n00 + u * (n10 - n00)
        nx1 = n01 + u * (n11 - n01)
        
        return nx0 + v * (nx1 - nx0)
    
    def sample_3d(self, x: float, y: float, z: float) -> float:
        """3D噪声采样"""
        # 简化的3D值噪声
        x0, y0, z0 = int(x), int(y), int(z)
        xf, yf, zf = x - x0, y - y0, z - z0
        
        def hash3d(x, y, z):
            idx = ((x * 73856093) ^ (y * 19349663) ^ (z * 83492791)) & 255
            return (self.perm[idx] / 255.0) * 2 - 1
        
        # 8个角落
        c = [[[hash3d(x0+i, y0+j, z0+k) 
               for k in range(2)] 
               for j in range(2)] 
               for i in range(2)]
        
        # 三线性插值
        u = xf * xf * (3 - 2 * xf)
        v = yf * yf * (3 - 2 * yf)
        w = zf * zf * (3 - 2 * zf)
        
        # X方向插值
        c00 = c[0][0][0] + u * (c[1][0][0] - c[0][0][0])
        c01 = c[0][0][1] + u * (c[1][0][1] - c[0][0][1])
        c10 = c[0][1][0] + u * (c[1][1][0] - c[0][1][0])
        c11 = c[0][1][1] + u * (c[1][1][1] - c[0][1][1])
        
        # Y方向插值
        c0 = c00 + v * (c10 - c00)
        c1 = c01 + v * (c11 - c01)
        
        # Z方向插值
        return c0 + w * (c1 - c0)


# 主集成类
class KarstTerrainSystem:
    """
    喀斯特地貌系统集成
    整合所有喀斯特地貌算法
    """
    
    def __init__(self, seed: int = 12345):
        self.seed = seed
        
        # 初始化所有子系统
        self.cave_generator = CaveNetworkGenerator(seed)
        self.collapse_detector = CaveCollapse(seed)
        self.peak_forest = KarstPeakForest(seed)
        self.stone_forest = StoneForest(seed)
        self.river_system = UndergroundRiverSystem(seed)
        self.bridge_generator = NaturalBridge(seed)
    
    def process_chunk(self, chunk_x: int, chunk_z: int,
                     base_heightmap: List[List[int]]) -> Tuple[List[List[int]], Dict[Tuple[int, int, int], float]]:
        """
        处理一个区块，生成完整的喀斯特地貌
        
        返回: (更新后的高度图, 溶蚀映射)
        """
        log_info(f"Generating karst terrain for chunk ({chunk_x}, {chunk_z})")
        
        # 1. 生成洞穴网络
        dissolution_map = self.cave_generator.generate_cave_network(
            chunk_x, chunk_z, base_heightmap
        )
        
        # 2. 提取洞穴节点
        cave_nodes = self.cave_generator.extract_cave_nodes(dissolution_map)
        log_info(f"  Generated {len(cave_nodes)} cave nodes")
        
        # 3. 检测塌陷（天坑）
        surface_height = {}
        for z in range(len(base_heightmap)):
            for x in range(len(base_heightmap[0])):
                world_x = chunk_x * 16 + x
                world_z = chunk_z * 16 + z
                surface_height[(world_x, world_z)] = base_heightmap[z][x]
        
        collapses = self.collapse_detector.detect_collapses(cave_nodes, surface_height)
        log_info(f"  Detected {len(collapses)} potential collapses")
        
        # 应用塌陷
        heightmap = [row[:] for row in base_heightmap]  # 复制
        for collapse in collapses:
            heightmap = self.collapse_detector.apply_collapse(
                heightmap, collapse, dissolution_map
            )
        
        # 4. 生成峰林
        peaks = self.peak_forest.generate_peaks(chunk_x, chunk_z, dissolution_map, base_heightmap)
        log_info(f"  Generated {len(peaks)} karst peaks")
        heightmap = self.peak_forest.apply_to_heightmap(heightmap, peaks, chunk_x, chunk_z)
        
        # 5. 生成石林
        pillars = self.stone_forest.generate_pillars(chunk_x, chunk_z, base_heightmap)
        log_info(f"  Generated {len(pillars)} stone pillars")
        heightmap = self.stone_forest.apply_to_heightmap(heightmap, pillars, chunk_x, chunk_z)
        
        # 6. 生成地下河
        rivers = self.river_system.generate_rivers(cave_nodes, chunk_x, chunk_z, surface_height)
        log_info(f"  Generated {len(rivers)} underground rivers")
        heightmap = self.river_system.carve_river_channels(
            heightmap, rivers, dissolution_map, chunk_x, chunk_z
        )
        
        # 7. 生成天生桥
        bridges = self.bridge_generator.generate_bridges(cave_nodes, collapses)
        log_info(f"  Generated {len(bridges)} natural bridges")
        heightmap = self.bridge_generator.apply_to_heightmap(heightmap, bridges, chunk_x, chunk_z)
        
        return heightmap, dissolution_map
