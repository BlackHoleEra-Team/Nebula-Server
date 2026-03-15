"""
高级地形生成器
使用 OpenSimplex2 + FBM + Domain Warping + Height Curve
支持 1024 格高度上限
"""

import math
import random
from typing import Tuple, List, Optional, Dict
from nebula.logging.logging_utils import log_info, log_error


class OpenSimplex2:
    """
    OpenSimplex2 噪声实现
    2D/3D 噪声函数，比 Perlin Noise 更自然，无方向性伪影
    参考: https://github.com/KdotJPG/OpenSimplex2
    """
    
    # 2D 偏斜因子
    SKEW_2D = 0.5 * (math.sqrt(3.0) - 1.0)
    UNSKEW_2D = (3.0 - math.sqrt(3.0)) / 6.0
    
    def __init__(self, seed: int = None):
        self.seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        self.perm = self._init_permutation()
        # 2D 梯度表 - 单位圆上的 24 个均匀分布点
        self.grad2 = [
            (0.130526192220052, 0.99144486137381),
            (0.38268343236509, 0.923879532511287),
            (0.608761429008721, 0.793353340144265),
            (0.793353340144265, 0.608761429008721),
            (0.923879532511287, 0.38268343236509),
            (0.99144486137381, 0.130526192220052),
            (0.99144486137381, -0.130526192220052),
            (0.923879532511287, -0.38268343236509),
            (0.793353340144265, -0.608761429008721),
            (0.608761429008721, -0.793353340144265),
            (0.38268343236509, -0.923879532511287),
            (0.130526192220052, -0.99144486137381),
            (-0.130526192220052, -0.99144486137381),
            (-0.38268343236509, -0.923879532511287),
            (-0.608761429008721, -0.793353340144265),
            (-0.793353340144265, -0.608761429008721),
            (-0.923879532511287, -0.38268343236509),
            (-0.99144486137381, -0.130526192220052),
            (-0.99144486137381, 0.130526192220052),
            (-0.923879532511287, 0.38268343236509),
            (-0.793353340144265, 0.608761429008721),
            (-0.608761429008721, 0.793353340144265),
            (-0.38268343236509, 0.923879532511287),
            (-0.130526192220052, 0.99144486137381)
        ]
    
    def _init_permutation(self) -> List[int]:
        """初始化置换表"""
        rng = random.Random(self.seed)
        p = list(range(256))
        rng.shuffle(p)
        # 扩展为 512 长度以避免取模
        return p + p
    
    def _dot2(self, g, x, y):
        """2D 点积"""
        return g[0] * x + g[1] * y
    
    def noise_2d(self, x: float, y: float) -> float:
        """
        2D OpenSimplex2 噪声
        返回值范围: [-1, 1]
        """
        # 偏斜输入坐标到 Simplex 网格
        skew = (x + y) * self.SKEW_2D
        xs = x + skew
        ys = y + skew
        
        # 确定基础网格单元
        xsb = int(math.floor(xs))
        ysb = int(math.floor(ys))
        
        # 计算单元内局部坐标
        xsi = xs - xsb
        ysi = ys - ysb
        
        # 确定我们在两个三角形中的哪一个
        # 并计算第二个顶点的坐标
        if xsi > ysi:
            # 右下三角形 (0,0) -> (1,0) -> (1,1)
            xins = xsi - ysi
            yins = 1.0 - xins
            dx2 = xsi - 1.0
            dy2 = ysi
            dx3 = xsi - 1.0
            dy3 = ysi - 1.0
        else:
            # 左上三角形 (0,0) -> (0,1) -> (1,1)
            yins = ysi - xsi
            xins = 1.0 - yins
            dx2 = xsi
            dy2 = ysi - 1.0
            dx3 = xsi - 1.0
            dy3 = ysi - 1.0
        
        # 第一个顶点 (0,0) 的偏移
        dx1 = xsi
        dy1 = ysi
        
        # 计算三个顶点的贡献
        value = 0.0
        
        # 顶点 1: (0, 0)
        attn1 = 2.0 / 3.0 - dx1 * dx1 - dy1 * dy1
        if attn1 > 0:
            attn1 *= attn1
            px = xsb & 255
            py = ysb & 255
            gi = self.perm[(px + self.perm[py]) & 511] % 24
            value += attn1 * attn1 * self._dot2(self.grad2[gi], dx1, dy1)
        
        # 顶点 2: (1, 0) 或 (0, 1)
        attn2 = 2.0 / 3.0 - dx2 * dx2 - dy2 * dy2
        if attn2 > 0:
            attn2 *= attn2
            if xsi > ysi:
                px = (xsb + 1) & 255
                py = ysb & 255
            else:
                px = xsb & 255
                py = (ysb + 1) & 255
            gi = self.perm[(px + self.perm[py]) & 511] % 24
            value += attn2 * attn2 * self._dot2(self.grad2[gi], dx2, dy2)
        
        # 顶点 3: (1, 1)
        attn3 = 2.0 / 3.0 - dx3 * dx3 - dy3 * dy3
        if attn3 > 0:
            attn3 *= attn3
            px = (xsb + 1) & 255
            py = (ysb + 1) & 255
            gi = self.perm[(px + self.perm[py]) & 511] % 24
            value += attn3 * attn3 * self._dot2(self.grad2[gi], dx3, dy3)
        
        # 归一化
        return value * 18.0


class FBM:
    """
    分形布朗运动 (Fractal Brownian Motion)
    叠加多层噪声，构建粗糙的地形轮廓
    """
    
    def __init__(self, noise_func, octaves: int = 4, 
                 persistence: float = 0.5, lacunarity: float = 2.0):
        self.noise_func = noise_func
        self.octaves = octaves
        self.persistence = persistence
        self.lacunarity = lacunarity
    
    def sample_2d(self, x: float, y: float) -> float:
        """2D FBM 采样"""
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0
        
        for _ in range(self.octaves):
            total += self.noise_func(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= self.persistence
            frequency *= self.lacunarity
        
        # 归一化到 [-1, 1]
        return total / max_value if max_value > 0 else 0
    
class DomainWarper:
    """
    地形扭曲 (Domain Warping)
    用噪声场扭曲坐标，增加地形有机感
    """
    
    def __init__(self, warp_noise: OpenSimplex2, strength: float = 20.0):
        self.warp_noise = warp_noise
        self.strength = strength
    
    def warp_2d(self, x: float, y: float, scale: float = 0.003) -> Tuple[float, float]:
        """
        2D 坐标扭曲
        返回扭曲后的坐标 (wx, wy)
        """
        # 使用两个独立的噪声场来扭曲 x 和 y
        offset_x = self.warp_noise.noise_2d(x * scale, y * scale) * self.strength
        offset_y = self.warp_noise.noise_2d(x * scale + 100, y * scale + 100) * self.strength
        
        return x + offset_x, y + offset_y


class HeightCurve:
    """
    高度曲线 (Hard Height Curve)
    将噪声值映射到最终高度范围，控制平原/山脉比例
    """
    
    def __init__(self, sea_level: int = 62, max_height: int = 256):
        self.sea_level = sea_level
        self.max_height = max_height
        
        # 地形参数
        self.ocean_threshold = -0.3      # 海洋阈值
        self.beach_threshold = -0.1      # 海滩阈值
        self.plains_threshold = 0.2      # 平原阈值
        self.hills_threshold = 0.5       # 丘陵阈值
        self.mountains_threshold = 0.7   # 山脉阈值
    
    def apply(self, noise_value: float) -> int:
        """
        应用高度曲线，将 [-1, 1] 的噪声值映射到实际高度
        """
        # 使用 S 型曲线 (sigmoid-like) 来调整分布
        # 让平原更多，极端地形更少
        
        # 首先应用一个幂函数来调整分布
        if noise_value >= 0:
            adjusted = math.pow(noise_value, 1.5)  # 压缩正值
        else:
            adjusted = -math.pow(-noise_value, 1.2)  # 稍微扩展负值
        
        # 映射到高度范围
        # 基础高度 64，范围 5 到 200
        base_height = 64
        height_range = 120  # 增加范围从100到120
        
        height = base_height + adjusted * height_range
        
        # 限制范围（提高上限）
        return max(5, min(self.max_height - 5, int(height)))
    
    def get_biome_from_height(self, height: int, noise_value: float) -> str:
        """
        根据高度和噪声值确定生物群系
        """
        if height < self.sea_level - 5:
            return "deep_ocean"
        elif height < self.sea_level:
            return "ocean"
        elif height < self.sea_level + 2:
            return "beach"
        elif noise_value < self.plains_threshold:
            return "plains"
        elif noise_value < self.hills_threshold:
            return "forest"
        elif noise_value < self.mountains_threshold:
            return "hills"
        else:
            return "mountains"


class LargeScaleUplift:
    """
    超大尺度抬升 (7)
    用低频噪声控制区域性抬升，形成主要山脉
    """
    
    def __init__(self, noise: OpenSimplex2, scale: float = 0.0005, 
                 strength: float = 80.0):
        self.noise = noise
        self.scale = scale
        self.strength = strength
    
    def get_uplift(self, x: float, z: float) -> float:
        """获取指定坐标的抬升量"""
        # 使用非常低频的噪声来创建大范围的地形抬升
        uplift = self.noise.noise_2d(x * self.scale, z * self.scale)
        # 只保留正值（抬升），负值变为0
        return max(0, uplift) * self.strength


class RidgedMultiFractal:
    """
    山脊分形 (5)
    叠加山脊噪声，增强山脊线
    """
    
    def __init__(self, noise: OpenSimplex2, octaves: int = 3,
                 persistence: float = 0.6, lacunarity: float = 2.0):
        self.noise = noise
        self.octaves = octaves
        self.persistence = persistence
        self.lacunarity = lacunarity
    
    def sample(self, x: float, z: float) -> float:
        """采样山脊噪声 - 标准山脊分形算法"""
        total = 0.0
        frequency = 1.0
        amplitude = 0.5  # 初始振幅降低
        max_value = 0.0
        
        for i in range(self.octaves):
            # 获取噪声值
            n = self.noise.noise_2d(x * frequency, z * frequency)
            # 标准山脊公式: 1 - |noise|
            ridge = 1.0 - abs(n)
            # 轻微锐化
            ridge = ridge * ridge
            
            total += ridge * amplitude
            max_value += amplitude
            
            amplitude *= self.persistence
            frequency *= self.lacunarity
        
        # 归一化
        if max_value > 0:
            return total / max_value
        return 0.5


class MountainCrestEnhancement:
    """
    山脊强化 (8)
    锐化山脊，让山峰更突出
    """
    
    def __init__(self, sharpness: float = 2.5):
        self.sharpness = sharpness
    
    def enhance(self, height: float, ridge_value: float) -> float:
        """
        强化山脊
        height: 当前高度
        ridge_value: 山脊噪声值 [0, 1]
        """
        # 只在已经有一定高度的区域强化山脊（避免平地出现柱子）
        if height < 70:
            return height
        
        # 使用幂函数锐化山脊
        enhanced = math.pow(ridge_value, self.sharpness)
        
        # 根据当前高度调整强化强度（越高越强）
        height_factor = min(1.0, (height - 70) / 50.0)
        
        # 大幅增强强化效果（从30增加到100）
        return height + enhanced * 100.0 * height_factor


class Turbulence:
    """
    扰动 (6)
    对地形施加二次扭曲，增加破碎感
    使用坐标域扭曲（Domain Warping）实现，更安全
    """
    
    def __init__(self, noise: OpenSimplex2, scale: float = 0.003,
                 strength: float = 8.0):
        self.noise = noise
        self.scale = scale
        self.strength = strength
    
    def warp_coordinates(self, x: float, z: float) -> Tuple[float, float]:
        """
        扭曲坐标 - 返回扭曲后的坐标
        这样噪声采样点被移动，而不是直接修改噪声值
        """
        # 使用两个独立的噪声来扭曲 x 和 z
        warp_x = self.noise.noise_2d(x * self.scale, z * self.scale)
        warp_z = self.noise.noise_2d(x * self.scale + 100, z * self.scale + 100)
        
        # 限制扭曲范围
        warp_x = max(-1.0, min(1.0, warp_x)) * self.strength
        warp_z = max(-1.0, min(1.0, warp_z)) * self.strength
        
        return x + warp_x, z + warp_z


class PlateauFilter:
    """
    高原化算法 (9)
    将高海拔区域压平，形成高原
    """
    
    def __init__(self, plateau_height: int = 120, 
                 transition_range: int = 20):
        self.plateau_height = plateau_height
        self.transition_range = transition_range
    
    def apply(self, height: int) -> int:
        """应用高原滤波"""
        if height < self.plateau_height - self.transition_range:
            # 低于高原起始高度，保持不变
            return height
        elif height > self.plateau_height + self.transition_range:
            # 高于高原，压平
            return self.plateau_height + (height - self.plateau_height) * 0.3
        else:
            # 过渡区域，平滑插值
            t = (height - (self.plateau_height - self.transition_range)) / (self.transition_range * 2)
            smooth_t = t * t * (3 - 2 * t)  # smoothstep
            target = self.plateau_height + (height - self.plateau_height) * 0.3
            return int(height + (target - height) * smooth_t)


class BasinGenerator:
    """
    盆地算法 (10)
    制造局部凹陷，用于后续湖泊/盆地
    """
    
    def __init__(self, noise: OpenSimplex2, scale: float = 0.003,
                 depth: float = 25.0, threshold: float = 0.6):
        self.noise = noise
        self.scale = scale
        self.depth = depth
        self.threshold = threshold
    
    def get_basin_depth(self, x: float, z: float) -> float:
        """获取盆地深度，返回负值表示凹陷"""
        n = self.noise.noise_2d(x * self.scale, z * self.scale)
        # 只有当噪声值超过阈值时才形成盆地
        if n > self.threshold:
            # 计算盆地深度
            intensity = (n - self.threshold) / (1.0 - self.threshold)
            return -intensity * self.depth
        return 0.0


class TerraceStep:
    """
    阶地/台地算法 (11)
    量化高度，生成台阶
    """
    
    def __init__(self, step_height: int = 20,
                 transition_smoothness: float = 0.9,
                 min_height: int = 80):  # 只在80以上应用
        self.step_height = step_height
        self.transition_smoothness = transition_smoothness
        self.min_height = min_height

    def apply(self, height: float) -> int:
        """应用阶地效果 - 只在高山区域"""
        # 只在一定高度以上应用阶地效果
        if height < self.min_height:
            return int(height)

        # 计算应该在哪一级台阶
        step_index = int(height / self.step_height)
        step_base = step_index * self.step_height

        # 在台阶边缘添加平滑过渡
        remainder = height - step_base
        transition_zone = self.step_height * self.transition_smoothness

        if remainder < transition_zone:
            # 过渡区域，几乎保持原高度
            t = remainder / transition_zone
            smooth_t = t * t * (3 - 2 * t)  # smoothstep
            # 轻微调整
            return int(height + (step_base + smooth_t * remainder - height) * 0.3)
        else:
            # 台阶顶部，轻微压平（保留70%原高度）
            flat_top = step_base + self.step_height
            blend = 0.3  # 只压平30%
            return int(flat_top * blend + height * (1 - blend))


class HillRolling:
    """
    丘陵算法 (12)
    在低海拔区域添加平缓起伏
    """
    
    def __init__(self, noise: OpenSimplex2, scale: float = 0.005,
                 amplitude: float = 12.0):
        self.noise = noise
        self.scale = scale
        self.amplitude = amplitude
    
    def apply(self, x: float, z: float, base_height: float) -> float:
        """添加丘陵起伏"""
        # 只在低海拔区域添加丘陵
        if base_height < 80:
            # 使用平滑的噪声创建丘陵
            hill = self.noise.noise_2d(x * self.scale, z * self.scale)
            # 使用 smoothstep 让丘陵更圆润
            hill = hill * hill * (3.0 - 2.0 * abs(hill))
            return base_height + hill * self.amplitude
        return base_height


class TerrainGenerator:
    """
    高级地形生成器
    使用 OpenSimplex2 + FBM + Domain Warping + Height Curve
    阶段二：添加大型地貌特征
    """
    
    # 高度上限
    MAX_HEIGHT = 1024
    
    # 海平面高度
    SEA_LEVEL = 62
    
    def __init__(self, seed: int = None):
        self.seed = seed if seed is not None else random.randint(0, 2**31 - 1)
        log_info(f"Initializing terrain generator with seed: {self.seed}")
        
        # 1. OpenSimplex2 噪声
        self.base_noise = OpenSimplex2(seed)
        self.detail_noise = OpenSimplex2(seed + 1)
        self.warp_noise = OpenSimplex2(seed + 2)
        self.ridge_noise = OpenSimplex2(seed + 3)
        self.uplift_noise = OpenSimplex2(seed + 4)
        self.turb_noise = OpenSimplex2(seed + 5)
        self.basin_noise = OpenSimplex2(seed + 6)
        self.hill_noise = OpenSimplex2(seed + 7)
        
        # 2. FBM 分形布朗运动
        self.base_fbm = FBM(self.base_noise.noise_2d, octaves=4, 
                            persistence=0.5, lacunarity=2.0)
        self.detail_fbm = FBM(self.detail_noise.noise_2d, octaves=2,
                              persistence=0.5, lacunarity=2.0)
        
        # 3. Domain Warping 地形扭曲
        self.warper = DomainWarper(self.warp_noise, strength=30.0)
        
        # 4. Height Curve 高度曲线
        self.height_curve = HeightCurve(sea_level=self.SEA_LEVEL, 
                                        max_height=self.MAX_HEIGHT)
        
        # ===== 阶段二：大型地貌特征 =====
        # 7. Large-Scale Uplift 超大尺度抬升
        self.uplift = LargeScaleUplift(self.uplift_noise, scale=0.0005, strength=80.0)
        
        # 5. Ridged MultiFractal 山脊分形
        self.ridged = RidgedMultiFractal(self.ridge_noise, octaves=3,
                                         persistence=0.6, lacunarity=2.0)
        
        # 8. Mountain Crest Enhancement 山脊强化
        self.crest_enhancer = MountainCrestEnhancement(sharpness=2.5)
        
        # 6. Turbulence 扰动
        self.turbulence = Turbulence(self.turb_noise, scale=0.008, strength=15.0)
        
        # 9. Plateau Filter 高原化算法
        self.plateau_filter = PlateauFilter(plateau_height=120, transition_range=20)
        
        # 10. Basin Generator 盆地算法
        self.basin_gen = BasinGenerator(self.basin_noise, scale=0.003,
                                        depth=25.0, threshold=0.6)
        
        # 11. Terrace Step 阶地/台地算法
        self.terrace = TerraceStep(step_height=8, transition_smoothness=0.3)
        
        # 12. Hill & Rolling 丘陵算法
        self.hill_rolling = HillRolling(self.hill_noise, scale=0.005, amplitude=12.0)
        
        # 高度图缓存
        self._height_cache: Dict[Tuple[int, int], List[Tuple[int, float, str]]] = {}
        self._cache_max_size = 100
        
        log_info("Terrain generator initialized with Phase 2 large-scale features")
    
    def _get_cached_heightmap(self, chunk_x: int, chunk_z: int) -> Optional[List[Tuple[int, float, str]]]:
        """获取缓存的高度图"""
        return self._height_cache.get((chunk_x, chunk_z))
    
    def _cache_heightmap(self, chunk_x: int, chunk_z: int, heightmap: List[Tuple[int, float, str]]):
        """缓存高度图"""
        if len(self._height_cache) >= self._cache_max_size:
            keys = list(self._height_cache.keys())[:self._cache_max_size // 2]
            for key in keys:
                del self._height_cache[key]
        
        self._height_cache[(chunk_x, chunk_z)] = heightmap
    
    def generate_heightmap(self, chunk_x: int, chunk_z: int) -> List[Tuple[int, float, str]]:
        """
        生成区块高度图
        返回 [(height, raw_noise, biome), ...] 列表，共 256 个元素 (16x16)
        
        阶段一：OpenSimplex2 + FBM + Domain Warping + Height Curve
        阶段二：添加大型地貌特征
        """
        # 检查缓存
        cached = self._get_cached_heightmap(chunk_x, chunk_z)
        if cached is not None:
            return cached
        
        heightmap = []
        
        for local_z in range(16):
            for local_x in range(16):
                world_x = chunk_x * 16 + local_x
                world_z = chunk_z * 16 + local_z
                
                # ===== 阶段一：基础地形生成 =====
                # 6. Turbulence - 扰动（坐标扭曲版本）
                # 先应用 Turbulence 扭曲坐标
                turb_x, turb_z = self.turbulence.warp_coordinates(world_x, world_z)
                
                # 3. Domain Warping - 扭曲坐标（叠加 Turbulence）
                warped_x, warped_z = self.warper.warp_2d(turb_x, turb_z, scale=0.002)
                
                # 2. FBM - 生成基础地形噪声
                base_value = self.base_fbm.sample_2d(warped_x * 0.001, warped_z * 0.001)
                detail_value = self.detail_fbm.sample_2d(world_x * 0.01, world_z * 0.01)
                combined = base_value * 0.8 + detail_value * 0.2
                
                # ===== 阶段二：大型地貌特征 =====
                
                # 7. Large-Scale Uplift - 超大尺度抬升（已启用，大幅增强）
                uplift = self.uplift.get_uplift(world_x, world_z) * 1.5
                
                # 5. Ridged MultiFractal - 山脊分形（已启用）
                ridge_value = self.ridged.sample(world_x * 0.0002, world_z * 0.0002)
                
                # 10. Basin Generator - 盆地算法（已启用）
                basin_depth = self.basin_gen.get_basin_depth(world_x, world_z)
                
                # 4. Height Curve - 应用高度曲线
                height = self.height_curve.apply(combined)
                
                # 应用抬升和盆地
                height = int(height + uplift + basin_depth)
                
                # 8. Mountain Crest Enhancement - 山脊强化（已启用）
                height = int(self.crest_enhancer.enhance(height, ridge_value))
                
                # 9. Plateau Filter - 高原化算法（已启用）
                height = self.plateau_filter.apply(height)
                
                # 11. Terrace Step - 阶地/台地算法（已启用）
                height = self.terrace.apply(height)
                
                # 12. Hill & Rolling - 丘陵算法（已启用）
                height = int(self.hill_rolling.apply(world_x, world_z, height))
                
                # 限制高度范围
                height = max(5, min(self.MAX_HEIGHT - 10, height))
                
                # 确定生物群系
                biome = self.height_curve.get_biome_from_height(height, combined)
                
                heightmap.append((height, combined, biome))
        
        # 缓存结果
        self._cache_heightmap(chunk_x, chunk_z, heightmap)
        
        return heightmap
    
    def generate_chunk_column(self, chunk_x: int, chunk_z: int) -> List[Tuple[int, int, int, int]]:
        """
        生成一个区块列的所有方块
        返回: [(x, y, z, block_state), ...]
        """
        blocks = []
        
        # 生成高度图
        heightmap = self.generate_heightmap(chunk_x, chunk_z)
        
        for local_z in range(16):
            for local_x in range(16):
                idx = local_z * 16 + local_x
                surface_height, noise_val, biome = heightmap[idx]
                
                # 确定这一列需要生成的最高高度
                # 如果地表低于海平面，需要生成到海平面（填充水）
                max_y = max(surface_height, self.SEA_LEVEL)
                
                # 生成该列的方块
                for y in range(min(max_y + 1, 256)):
                    block_state = self._get_block_at(y, surface_height, biome)
                    if block_state != 0:
                        blocks.append((local_x, y, local_z, block_state))
        
        return blocks
    
    def _get_block_at(self, y: int, surface_height: int, biome: str) -> int:
        """根据位置和生物群系返回方块类型"""
        
        # 基岩层
        if y == 0:
            return 7 << 4  # 基岩
        
        # 地表以上 - 检查是否需要水
        if y > surface_height:
            if y <= self.SEA_LEVEL:
                return 9 << 4  # 水
            return 0  # 空气
        
        # 深海/海洋底部
        if biome in ["deep_ocean", "ocean"]:
            depth = surface_height - y
            if y == surface_height:
                return 12 << 4  # 沙子（海底表面）
            elif depth <= 3:
                return 12 << 4  # 沙子
            else:
                return 1 << 4  # 石头
        
        # 海滩
        if biome == "beach":
            depth = surface_height - y
            if depth <= 3:
                return 12 << 4  # 沙子
            return 1 << 4  # 石头
        
        # 地表
        if y == surface_height:
            if biome == "plains":
                return 2 << 4  # 草方块
            elif biome == "forest":
                return 2 << 4  # 草方块
            elif biome == "hills":
                return 2 << 4  # 草方块
            elif biome == "mountains":
                if y > 100:
                    return 80 << 4  # 雪
                return 1 << 4  # 石头
            else:
                return 2 << 4  # 草方块
        
        # 地表以下
        depth = surface_height - y
        
        if biome == "mountains":
            return 1 << 4  # 石头
        else:
            if depth <= 3:
                return 3 << 4  # 泥土
            return 1 << 4  # 石头
    
    def get_height(self, world_x: int, world_z: int) -> int:
        """获取指定坐标的地表高度"""
        chunk_x = world_x // 16
        chunk_z = world_z // 16
        local_x = world_x % 16
        local_z = world_z % 16
        
        heightmap = self.generate_heightmap(chunk_x, chunk_z)
        return heightmap[local_z * 16 + local_x][0]
    
    def get_biome(self, world_x: int, world_z: int, height: int = None) -> str:
        """获取指定坐标的生物群系名称"""
        chunk_x = world_x // 16
        chunk_z = world_z // 16
        local_x = world_x % 16
        local_z = world_z % 16
        
        heightmap = self.generate_heightmap(chunk_x, chunk_z)
        _, _, biome = heightmap[local_z * 16 + local_x]
        return biome
    
    def get_block_at(self, world_x: int, y: int, world_z: int) -> int:
        """获取指定坐标的方块"""
        height = self.get_height(world_x, world_z)
        biome = self.get_biome(world_x, world_z)
        return self._get_block_at(y, height, biome)
