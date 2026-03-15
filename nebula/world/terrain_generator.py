"""
高级地形生成器
使用 OpenSimplex2 + FBM + Domain Warping + Height Curve
支持 1024 格高度上限
阶段三：水力侵蚀系统
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
    将噪声值映射到最终高度范围，控制平原/山脉比例 - 优化以减少阶梯感
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
        使用更平滑的映射函数
        """
        # 使用更平滑的曲线，避免过度压缩
        # 降低幂指数，让分布更均匀
        if noise_value >= 0:
            adjusted = math.pow(noise_value, 1.2)  # 降低指数，减少压缩
        else:
            adjusted = -math.pow(-noise_value, 1.1)  # 更平滑的负值处理
        
        # 映射到高度范围
        base_height = 64
        height_range = 100  # 稍微降低范围，让地形更平缓
        
        height = base_height + adjusted * height_range
        
        # 限制范围
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
    锐化山脊，让山峰更突出 - 轻度强化以避免突变
    """
    
    def __init__(self, sharpness: float = 2.0, strength: float = 40.0):
        self.sharpness = sharpness
        self.strength = strength
    
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
        
        # 轻度强化
        return height + enhanced * self.strength * height_factor


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
    将高海拔区域压平，形成高原 - 轻度应用以避免阶梯
    """
    
    def __init__(self, plateau_height: int = 120, 
                 transition_range: int = 30,
                 blend_factor: float = 0.2):  # 混合因子降低
        self.plateau_height = plateau_height
        self.transition_range = transition_range
        self.blend_factor = blend_factor
    
    def apply(self, height: int) -> int:
        """应用高原滤波 - 轻度平滑"""
        if height < self.plateau_height - self.transition_range:
            # 低于高原起始高度，保持不变
            return height
        elif height > self.plateau_height + self.transition_range:
            # 高于高原，极轻微压平
            return self.plateau_height + (height - self.plateau_height) * self.blend_factor
        else:
            # 过渡区域，平滑插值
            t = (height - (self.plateau_height - self.transition_range)) / (self.transition_range * 2)
            smooth_t = t * t * (3 - 2 * t)  # smoothstep
            target = self.plateau_height + (height - self.plateau_height) * self.blend_factor
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
    量化高度，生成台阶 - 轻度应用以避免明显阶梯
    """
    
    def __init__(self, step_height: int = 20,
                 transition_smoothness: float = 0.5,
                 min_height: int = 100,
                 blend_factor: float = 0.15):  # 混合因子大幅降低
        self.step_height = step_height
        self.transition_smoothness = transition_smoothness
        self.min_height = min_height
        self.blend_factor = blend_factor

    def apply(self, height: float) -> int:
        """应用阶地效果 - 轻度混合，只在很高区域"""
        # 只在很高区域应用阶地效果
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
            # 极轻微调整
            return int(height + (step_base + smooth_t * remainder - height) * self.blend_factor)
        else:
            # 台阶顶部，极轻微压平
            flat_top = step_base + self.step_height
            return int(flat_top * self.blend_factor + height * (1 - self.blend_factor))


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
        self.crest_enhancer = MountainCrestEnhancement(sharpness=2.0, strength=40.0)
        
        # 6. Turbulence 扰动
        self.turbulence = Turbulence(self.turb_noise, scale=0.008, strength=15.0)
        
        # 9. Plateau Filter 高原化算法
        self.plateau_filter = PlateauFilter(plateau_height=120, transition_range=30, blend_factor=0.2)
        
        # 10. Basin Generator 盆地算法
        self.basin_gen = BasinGenerator(self.basin_noise, scale=0.003,
                                        depth=25.0, threshold=0.6)
        
        # 11. Terrace Step 阶地/台地算法
        self.terrace = TerraceStep(step_height=20, transition_smoothness=0.5, 
                                   min_height=100, blend_factor=0.15)
        
        # 12. Hill & Rolling 丘陵算法
        self.hill_rolling = HillRolling(self.hill_noise, scale=0.005, amplitude=12.0)
        
        # ===== 阶段三：水力侵蚀系统 =====
        # 13. Hydraulic Erosion 水力侵蚀
        self.hydraulic_erosion = HydraulicErosion(
            erosion_speed=0.08,
            sediment_capacity=5.0,
            max_erosion_per_step=3.0,
            num_droplets=15000
        )
        
        # 14. Thermal Erosion 热侵蚀
        self.thermal_erosion = ThermalErosion(
            talus_angle=0.6,
            erosion_speed=0.6
        )
        
        # 17. Sediment Deposition 沉积算法
        self.sediment_deposition = SedimentDeposition(
            deposition_rate=0.4,
            min_slope_for_deposition=0.15
        )
        
        # River Carver 河道雕刻
        self.river_carver = RiverCarver(
            river_depth=4.0,
            river_width=2.5
        )
        
        # 是否启用侵蚀
        self.enable_erosion = True
        
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
        
        # ===== 阶段三：水力侵蚀（后处理）=====
        # 注意：侵蚀在大尺度高度图上应用，然后插值到区块
        # 这里使用简化的局部侵蚀模拟
        
        if self.enable_erosion:
            heightmap = self._apply_local_erosion(heightmap, chunk_x, chunk_z)
        
        # 缓存结果
        self._cache_heightmap(chunk_x, chunk_z, heightmap)
        
        return heightmap
    
    def _generate_large_region(self, center_chunk_x: int, center_chunk_z: int, 
                                size: int = 48) -> List[List[float]]:
        """
        生成一个更大的区域（包含周围区块），用于保证算法连续性
        使用与 generate_heightmap 完全相同的逻辑（阶段一、二）
        size: 区域大小（必须是16的倍数，默认48x48）
        """
        half_size = size // 2
        start_chunk_x = center_chunk_x - half_size // 16
        start_chunk_z = center_chunk_z - half_size // 16
        
        region = []
        for z in range(size):
            row = []
            for x in range(size):
                # 计算对应的世界坐标
                chunk_x = start_chunk_x + x // 16
                chunk_z = start_chunk_z + z // 16
                local_x = x % 16
                local_z = z % 16
                world_x = chunk_x * 16 + local_x
                world_z = chunk_z * 16 + local_z
                
                # 使用与 generate_heightmap 完全相同的逻辑生成基础高度
                height = self._generate_single_point(world_x, world_z)
                row.append(float(height))
            region.append(row)
        
        return region
    
    def _generate_single_point(self, world_x: int, world_z: int) -> int:
        """
        生成单个点的基础高度（阶段一、二），与 generate_heightmap 完全一致
        """
        # ===== 阶段一：基础地形生成 =====
        # 6. Turbulence - 扰动（坐标扭曲版本）
        turb_x, turb_z = self.turbulence.warp_coordinates(world_x, world_z)
        
        # 3. Domain Warping - 扭曲坐标（叠加 Turbulence）
        warped_x, warped_z = self.warper.warp_2d(turb_x, turb_z, scale=0.002)
        
        # 2. FBM - 生成基础地形噪声
        base_value = self.base_fbm.sample_2d(warped_x * 0.001, warped_z * 0.001)
        detail_value = self.detail_fbm.sample_2d(world_x * 0.01, world_z * 0.01)
        combined = base_value * 0.8 + detail_value * 0.2
        
        # ===== 阶段二：大型地貌特征 =====
        # 7. Large-Scale Uplift - 超大尺度抬升
        uplift = self.uplift.get_uplift(world_x, world_z) * 1.5
        
        # 5. Ridged MultiFractal - 山脊分形
        ridge_value = self.ridged.sample(world_x * 0.0002, world_z * 0.0002)
        
        # 10. Basin Generator - 盆地算法
        basin_depth = self.basin_gen.get_basin_depth(world_x, world_z)
        
        # 4. Height Curve - 应用高度曲线
        height = self.height_curve.apply(combined)
        
        # 应用抬升和盆地
        height = int(height + uplift + basin_depth)
        
        # 8. Mountain Crest Enhancement - 山脊强化
        height = int(self.crest_enhancer.enhance(height, ridge_value))
        
        # 9. Plateau Filter - 高原化算法
        height = self.plateau_filter.apply(height)
        
        # 11. Terrace Step - 阶地/台地算法
        height = self.terrace.apply(height)
        
        # 12. Hill & Rolling - 丘陵算法
        height = int(self.hill_rolling.apply(world_x, world_z, height))
        
        # 限制高度范围
        height = max(5, min(self.MAX_HEIGHT - 10, height))
        
        return height
    
    def _apply_local_erosion(self, heightmap: List[Tuple[int, float, str]], 
                             chunk_x: int, chunk_z: int) -> List[Tuple[int, float, str]]:
        """
        应用局部侵蚀效果（阶段三、四、五）
        使用48x48大区域计算，保证区块边界连续
        """
        region_size = 48
        half_size = region_size // 2
        
        # 生成48x48大区域（包含周围区块）
        large_region = self._generate_large_region(chunk_x, chunk_z, region_size)
        
        # 应用阶段三：热侵蚀
        large_region = self.thermal_erosion.erode(large_region, iterations=3)
        
        # 应用阶段三：简化的水力侵蚀
        for z in range(region_size):
            for x in range(region_size):
                world_x = (chunk_x - 1) * 16 + x
                world_z = (chunk_z - 1) * 16 + z
                
                flow_noise = self.base_noise.noise_2d(world_x * 0.05, world_z * 0.05)
                
                if large_region[z][x] < 80 and flow_noise > 0.3:
                    erosion = (flow_noise - 0.3) * 2.0
                    large_region[z][x] -= erosion * 0.3
                
                if large_region[z][x] < 65 and flow_noise < -0.3:
                    deposition = (-flow_noise - 0.3) * 1.5
                    large_region[z][x] += deposition * 0.2
        
        # 应用阶段四和五的算法
        large_region = self._apply_phase4_phase5(large_region, chunk_x, chunk_z, region_size)
        
        # 提取中心16x16区域
        start_idx = half_size - 8
        result = []
        for z in range(16):
            for x in range(16):
                idx = z * 16 + x
                original = heightmap[idx]
                new_height = int(large_region[start_idx + z][start_idx + x])
                new_height = max(5, min(self.MAX_HEIGHT - 10, new_height))
                result.append((new_height, original[1], original[2]))
        
        return result
    
    def _apply_phase4_phase5(self, heightmap: List[List[float]], 
                             chunk_x: int, chunk_z: int,
                             size: int) -> List[List[float]]:
        """
        应用阶段四和五的算法
        """
        world_x_base = (chunk_x - 1) * 16
        world_z_base = (chunk_z - 1) * 16
        
        # ========== 阶段四：河流、湖泊与海岸 ==========
        # 1. 河流网络生成
        river_network = RiverNetwork(
            min_river_length=30,
            flow_accumulation_threshold=10
        )
        
        # 计算流向
        flow_directions = []
        for z in range(size):
            row = []
            for x in range(size):
                dx, dz = D8FlowDirection.get_flow_direction(
                    heightmap, x, z, size, size
                )
                row.append((dx, dz))
            flow_directions.append(row)
        
        heightmap = river_network.generate_river_network(heightmap, flow_directions)
        
        # 2. V 型河谷雕刻
        river_mask = [[False] * size for _ in range(size)]
        for z in range(size):
            for x in range(size):
                if heightmap[z][x] < 60:
                    river_mask[z][x] = True
        
        valley_carver = ValleyCarver(
            valley_depth=4.0,
            valley_width=3.0,
            v_shape_factor=0.5
        )
        heightmap = valley_carver.carve_valley(heightmap, river_mask)
        
        # 3. 高山湖泊填充
        mountain_lake = MountainLake(
            min_lake_size=10,
            max_lake_depth=8.0
        )
        heightmap = mountain_lake.fill_lakes(heightmap)
        
        # 4. 海岸侵蚀
        coastal_erosion = CoastalErosion(
            sea_level=62.0,
            erosion_strength=1.5,
            cliff_height=3.0
        )
        heightmap = coastal_erosion.erode_coast(heightmap)
        
        # ========== 阶段五：风成与火山地貌 ==========
        # 5. 风蚀作用
        wind_direction = 45.0 + (world_x_base * 0.01) * 360
        wind_erosion = WindErosion(
            wind_direction=wind_direction,
            erosion_strength=1.0
        )
        for z in range(size):
            for x in range(size):
                wind_erosion.erode(heightmap, x, z, size, size)
        
        # 6. 沙丘生成
        dune_formation = DuneFormation(
            dune_height=3.0,
            dune_spacing=20.0,
            aridity_threshold=0.7
        )
        heightmap = dune_formation.form_dunes(heightmap, seed=self.seed)
        
        # 7. 雅丹地貌
        yardang = YardangAlgorithm(
            wind_direction=wind_direction,
            yardang_spacing=15.0,
            ridge_height=2.5
        )
        heightmap = yardang.form_yardangs(heightmap, seed=self.seed + 1)
        
        # 8. 火山锥（基于世界坐标，不是区块坐标）
        volcano_noise = self.base_noise.noise_2d(world_x_base * 0.01, world_z_base * 0.01)
        if volcano_noise > 0.85:
            volcano = VolcanoCone(
                volcano_height=35.0,
                base_radius=25.0,
                crater_radius=5.0
            )
            # 火山中心在大区域中心
            center_x, center_z = size // 2, size // 2
            heightmap = volcano.create_volcano(
                heightmap, center_x, center_z, seed=self.seed + int(world_x_base + world_z_base)
            )
            
            caldera = CalderaCollapse(
                collapse_depth=12.0,
                collapse_radius=15.0
            )
            heightmap = caldera.collapse(heightmap, center_x, center_z)
            
            magma = MagmaFluid(
                viscosity=0.7,
                flow_distance=12,
                cooling_rate=0.15
            )
            heightmap = magma.flow(heightmap, center_x, center_z, seed=self.seed)
        
        # 9. 熔岩台地
        plateau_noise = self.base_noise.noise_2d(world_x_base * 0.02, world_z_base * 0.02)
        if plateau_noise < -0.7:
            lava_plateau = LavaPlateau(
                plateau_height=3.0,
                coverage_radius=30.0,
                flatness=0.7
            )
            center_x, center_z = size // 2, size // 2
            heightmap = lava_plateau.create_plateau(
                heightmap, center_x, center_z, seed=self.seed + 2
            )
        
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


class D8FlowDirection:
    """
    D8 流向算法 (16)
    计算每个点的水流方向（8 个方向）
    """
    
    # 8 个方向的偏移 (dx, dy)
    DIRECTIONS = [
        (-1, -1), (0, -1), (1, -1),  # 左上，上，右上
        (-1, 0),           (1, 0),   # 左，右
        (-1, 1), (0, 1), (1, 1)      # 左下，下，右下
    ]
    
    # 方向对应的距离（对角线距离更长）
    DISTANCES = [
        math.sqrt(2), 1.0, math.sqrt(2),
        1.0, 1.0,
        math.sqrt(2), 1.0, math.sqrt(2)
    ]
    
    @staticmethod
    def get_flow_direction(heightmap: List[List[float]], x: int, z: int, 
                           width: int, height: int) -> Tuple[int, int]:
        """
        获取某一点的流向
        返回：(dx, dz) 流向的偏移量，如果没有更低点则返回 (0, 0)
        """
        current_height = heightmap[x][z]
        lowest_slope = 0.0
        flow_to = (0, 0)
        
        for i, (dx, dz) in enumerate(D8FlowDirection.DIRECTIONS):
            nx, nz = x + dx, z + dz
            
            # 检查边界
            if nx < 0 or nx >= width or nz < 0 or nz >= height:
                continue
            
            neighbor_height = heightmap[nx][nz]
            
            # 计算坡度（高度差 / 距离）
            height_diff = current_height - neighbor_height
            slope = height_diff / D8FlowDirection.DISTANCES[i]
            
            # 只考虑更低的邻居，选择坡度最大的方向
            if height_diff > 0 and slope > lowest_slope:
                lowest_slope = slope
                flow_to = (dx, dz)
        
        return flow_to


class HydraulicErosion:
    """
    水力侵蚀 (13)
    核心侵蚀循环：水携带沉积物移动，侵蚀高地，沉积低地
    使用粒子追踪法模拟雨滴路径
    """
    
    def __init__(self, erosion_speed: float = 0.05, 
                 sediment_capacity: float = 4.0,
                 max_erosion_per_step: float = 2.0,
                 num_droplets: int = 10000):
        self.erosion_speed = erosion_speed
        self.sediment_capacity = sediment_capacity
        self.max_erosion_per_step = max_erosion_per_step
        self.num_droplets = num_droplets
    
    def erode(self, heightmap: List[List[float]], seed: int = None) -> List[List[float]]:
        """
        执行水力侵蚀
        heightmap: 输入高度图（会被修改）
        返回：侵蚀后的高度图
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        rng = random.Random(seed)
        
        for _ in range(self.num_droplets):
            # 随机起点
            x = rng.randint(0, width - 1)
            z = rng.randint(0, height - 1)
            
            # 水滴属性
            sediment = 0.0  # 携带的沉积物
            speed = 0.0     # 水流速度
            direction = (0, 0)
            
            # 追踪水滴路径
            for step in range(50):  # 最多 50 步
                # 获取流向
                direction = D8FlowDirection.get_flow_direction(
                    heightmap, x, z, width, height
                )
                
                # 如果没有流向（平地或洼地），沉积并停止
                if direction == (0, 0):
                    # 沉积所有沉积物
                    heightmap[x][z] += sediment
                    break
                
                dx, dz = direction
                nx, nz = x + dx, z + dz
                
                # 边界检查
                if nx < 0 or nx >= width or nz < 0 or nz >= height:
                    break
                
                # 计算高度差
                current_height = heightmap[x][z]
                next_height = heightmap[nx][nz]
                delta = current_height - next_height
                
                # 更新速度（加速或减速）
                speed = max(0.0, speed + delta * 0.1)
                
                # 计算沉积物容量
                capacity = self.sediment_capacity * speed
                
                # 侵蚀或沉积
                if sediment < capacity and delta > 0:
                    # 侵蚀：从当前点带走沉积物
                    erosion_amount = min(
                        delta * self.erosion_speed,
                        self.max_erosion_per_step,
                        (capacity - sediment) * 0.5
                    )
                    heightmap[x][z] -= erosion_amount
                    sediment += erosion_amount
                elif sediment > capacity:
                    # 沉积：放下过量的沉积物
                    deposit_amount = (sediment - capacity) * 0.3
                    heightmap[x][z] += deposit_amount
                    sediment -= deposit_amount
                
                # 移动到下一个点
                x, z = nx, nz
            
            # 到达边界或海洋，沉积所有沉积物
            heightmap[x][z] += sediment
        
        return heightmap


class ThermalErosion:
    """
    热侵蚀/土石滑落 (14)
    重力导致的物质下滑，使斜坡趋于稳定角
    """
    
    def __init__(self, talus_angle: float = 0.75,  # 休止角（弧度，约 43 度）
                 erosion_speed: float = 0.5):
        self.talus_angle = talus_angle
        self.erosion_speed = erosion_speed
    
    def erode(self, heightmap: List[List[float]], iterations: int = 5) -> List[List[float]]:
        """
        执行热侵蚀
        多次扫描高度图，让过陡的斜坡物质下滑
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        for _ in range(iterations):
            # 创建临时缓冲区
            new_heightmap = [row[:] for row in heightmap]
            
            for x in range(width):
                for z in range(height):
                    current = heightmap[x][z]
                    
                    # 检查 4 个方向（上下左右）
                    for dx, dz in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, nz = x + dx, z + dz
                        
                        if nx < 0 or nx >= width or nz < 0 or nz >= height:
                            continue
                        
                        neighbor = heightmap[nx][nz]
                        
                        # 计算高度差
                        diff = current - neighbor
                        
                        # 如果高度差超过休止角，物质下滑
                        if diff > self.talus_angle:
                            transfer = (diff - self.talus_angle) * self.erosion_speed * 0.5
                            new_heightmap[x][z] -= transfer
                            new_heightmap[nx][nz] += transfer
            
            heightmap = new_heightmap
        
        return heightmap


class FluidTransport:
    """
    流体搬运 (15)
    与侵蚀结合，模拟沉积物搬运过程
    已整合到 HydraulicErosion 中
    """
    pass  # 功能已在 HydraulicErosion 中实现


class SedimentDeposition:
    """
    沉积算法 (17)
    在流速降低处沉积物质（如冲积扇、河三角洲）
    """
    
    def __init__(self, deposition_rate: float = 0.3,
                 min_slope_for_deposition: float = 0.1):
        self.deposition_rate = deposition_rate
        self.min_slope_for_deposition = min_slope_for_deposition
    
    def deposit(self, heightmap: List[List[float]], 
                flow_map: Optional[List[List[Tuple[float, float]]]] = None) -> List[List[float]]:
        """
        在低坡度区域增强沉积
        flow_map: 可选的流速图 (speed, sediment)
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        for x in range(width):
            for z in range(height):
                # 计算局部坡度
                min_neighbor = heightmap[x][z]
                for dx, dz in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, nz = x + dx, z + dz
                    if 0 <= nx < width and 0 <= nz < height:
                        min_neighbor = min(min_neighbor, heightmap[nx][nz])
                
                slope = heightmap[x][z] - min_neighbor
                
                # 在低坡度区域增强沉积
                if slope < self.min_slope_for_deposition:
                    # 轻微抬升，模拟沉积物堆积
                    heightmap[x][z] += self.deposition_rate * 0.1
        
        return heightmap


class RiverCarver:
    """
    河道雕刻器
    沿着水流路径雕刻出河谷
    """
    
    def __init__(self, river_depth: float = 3.0,
                 river_width: float = 2.0):
        self.river_depth = river_depth
        self.river_width = river_width
    
    def carve_rivers(self, heightmap: List[List[float]], 
                     flow_directions: List[List[Tuple[int, int]]]) -> List[List[float]]:
        """
        沿着主要水流路径雕刻河道
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 追踪主要河流路径
        for x in range(width):
            for z in range(height):
                # 只在低洼区域雕刻河道
                if heightmap[x][z] > 70:
                    continue
                
                # 追踪流向
                cx, cz = x, z
                path = [(cx, cz)]
                
                for _ in range(100):
                    dx, dz = flow_directions[cx][cz]
                    if dx == 0 and dz == 0:
                        break
                    
                    cx, cz = cx + dx, cz + dz
                    if cx < 0 or cx >= width or cz < 0 or cz >= height:
                        break
                    path.append((cx, cz))
                
                # 如果路径足够长，认为是河流，雕刻河道
                if len(path) > 20:
                    for px, pz in path:
                        # 雕刻河床
                        heightmap[px][pz] -= self.river_depth * 0.1
                        
                        # 加宽河道
                        for dx in range(-1, 2):
                            for dz in range(-1, 2):
                                nx, nz = px + dx, pz + dz
                                if 0 <= nx < width and 0 <= nz < height:
                                    if abs(dx) + abs(dz) == 1:
                                        heightmap[nx][nz] -= self.river_depth * 0.05
        
        return heightmap


class RiverNetwork:
    """
    河流网络生成（26）
    从源头开始，沿流向累积流量，生成永久河床
    """
    
    def __init__(self, min_river_length: int = 50,
                 flow_accumulation_threshold: int = 10):
        self.min_river_length = min_river_length
        self.flow_accumulation_threshold = flow_accumulation_threshold
    
    def generate_river_network(self, heightmap: List[List[float]], 
                                flow_directions: List[List[Tuple[int, int]]]) -> List[List[float]]:
        """
        基于流向累积生成河流网络
        返回：修改后的高度图（包含河流路径）
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 1. 计算流量累积图
        flow_accumulation = [[0] * height for _ in range(width)]
        
        # 从每个点开始追踪流向，累积流量
        for x in range(width):
            for z in range(height):
                cx, cz = x, z
                visited = set()
                
                # 追踪到汇流点
                for _ in range(500):
                    if (cx, cz) in visited:
                        break
                    visited.add((cx, cz))
                    flow_accumulation[cx][cz] += 1
                    
                    dx, dz = flow_directions[cx][cz]
                    if dx == 0 and dz == 0:
                        break
                    
                    cx, cz = cx + dx, cz + dz
                    if cx < 0 or cx >= width or cz < 0 or cz >= height:
                        break
        
        # 2. 根据流量累积确定河流
        for x in range(width):
            for z in range(height):
                # 流量超过阈值且不在高处，认为是河流
                if (flow_accumulation[x][z] > self.flow_accumulation_threshold and 
                    heightmap[x][z] < 80):
                    # 轻微下切河床
                    heightmap[x][z] -= 0.5
        
        return heightmap


class ValleyCarver:
    """
    河谷下切（27）
    加深河道，形成 V 型谷
    """
    
    def __init__(self, valley_depth: float = 8.0,
                 valley_width: float = 6.0,
                 v_shape_factor: float = 0.5):
        self.valley_depth = valley_depth
        self.valley_width = valley_width
        self.v_shape_factor = v_shape_factor
    
    def carve_valley(self, heightmap: List[List[float]], 
                     river_mask: List[List[bool]]) -> List[List[float]]:
        """
        沿河流路径雕刻 V 型河谷
        river_mask: True 表示该位置是河流
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        for x in range(width):
            for z in range(height):
                if not river_mask[x][z]:
                    continue
                
                # 计算到最近河流的距离
                for dx in range(-int(self.valley_width), int(self.valley_width) + 1):
                    for dz in range(-int(self.valley_width), int(self.valley_width) + 1):
                        nx, nz = x + dx, z + dz
                        
                        if 0 <= nx < width and 0 <= nz < height and river_mask[nx][nz]:
                            distance = math.sqrt(dx * dx + dz * dz)
                            
                            # V 型谷：距离越远，侵蚀越弱
                            if distance < self.valley_width:
                                erosion_factor = (1.0 - distance / self.valley_width) ** self.v_shape_factor
                                erosion = self.valley_depth * erosion_factor * 0.3
                                heightmap[x][z] -= erosion
        
        return heightmap


class MountainLake:
    """
    天池算法（28）
    检测封闭洼地，填充成湖泊
    """
    
    def __init__(self, min_lake_size: int = 20,
                 max_lake_depth: float = 15.0):
        self.min_lake_size = min_lake_size
        self.max_lake_depth = max_lake_depth
    
    def fill_lakes(self, heightmap: List[List[float]]) -> List[List[float]]:
        """
        检测并填充封闭洼地为湖泊
        使用洪水填充算法
        """
        width = len(heightmap)
        height = len(heightmap[0])
        visited = [[False] * height for _ in range(width)]
        
        def flood_fill(start_x: int, start_z: int, 
                       basin_height: float) -> List[Tuple[int, int]]:
            """洪水填充，返回洼地内的所有点"""
            stack = [(start_x, start_z)]
            basin_points = []
            is_closed = True
            
            while stack:
                x, z = stack.pop()
                if visited[x][z]:
                    continue
                
                visited[x][z] = True
                
                if heightmap[x][z] > basin_height:
                    continue
                
                basin_points.append((x, z))
                
                # 检查边界
                if x == 0 or x == width - 1 or z == 0 or z == height - 1:
                    is_closed = False
                
                # 4 个邻居
                for dx, dz in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, nz = x + dx, z + dz
                    if 0 <= nx < width and 0 <= nz < height and not visited[nx][nz]:
                        stack.append((nx, nz))
            
            return basin_points if is_closed else []
        
        # 遍历所有点，寻找洼地
        for x in range(width):
            for z in range(height):
                if visited[x][z]:
                    continue
                
                # 以当前点高度作为盆地高度
                basin_height = heightmap[x][z]
                basin_points = flood_fill(x, z, basin_height)
                
                # 如果洼地足够大且封闭，填充为湖
                if len(basin_points) >= self.min_lake_size:
                    # 计算填充高度（盆地边缘的最低点）
                    edge_heights = []
                    for bx, bz in basin_points:
                        for dx, dz in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                            nx, nz = bx + dx, bz + dz
                            if 0 <= nx < width and 0 <= nz < height:
                                if heightmap[nx][nz] > basin_height:
                                    edge_heights.append(heightmap[nx][nz])
                    
                    if edge_heights:
                        fill_height = min(edge_heights) - 0.5
                        fill_height = min(fill_height, basin_height + self.max_lake_depth)
                        
                        # 填充湖泊
                        for bx, bz in basin_points:
                            heightmap[bx][bz] = fill_height
        
        return heightmap


class CoastalErosion:
    """
    海岸侵蚀（29）
    根据波浪能量修改海岸线，形成海蚀崖
    """
    
    def __init__(self, sea_level: float = 62.0,
                 erosion_strength: float = 3.0,
                 cliff_height: float = 5.0):
        self.sea_level = sea_level
        self.erosion_strength = erosion_strength
        self.cliff_height = cliff_height
    
    def erode_coast(self, heightmap: List[List[float]]) -> List[List[float]]:
        """
        侵蚀海岸线，形成海蚀崖和曲折海岸
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        for x in range(width):
            for z in range(height):
                # 检查是否是海岸区域（海平面附近）
                if abs(heightmap[x][z] - self.sea_level) > 5:
                    continue
                
                # 计算到海洋的距离
                is_coast = False
                for dx in range(-3, 4):
                    for dz in range(-3, 4):
                        nx, nz = x + dx, z + dz
                        if 0 <= nx < width and 0 <= nz < height:
                            if heightmap[nx][nz] < self.sea_level - 2:
                                is_coast = True
                                break
                
                if not is_coast:
                    continue
                
                # 海岸侵蚀：降低高度，形成海蚀平台
                heightmap[x][z] -= self.erosion_strength * 0.2
                
                # 在略高于海平面的地方形成海蚀崖
                if heightmap[x][z] > self.sea_level:
                    heightmap[x][z] += self.cliff_height * 0.3
        
        return heightmap


class CanyonGenerator:
    """
    大峡谷生成（30）
    在特定区域（如干旱区）强化下切，形成峡谷
    """
    
    def __init__(self, canyon_depth: float = 20.0,
                 canyon_width: float = 8.0,
                 arid_threshold: float = 0.7):
        self.canyon_depth = canyon_depth
        self.canyon_width = canyon_width
        self.arid_threshold = arid_threshold
    
    def carve_canyon(self, heightmap: List[List[float]], 
                     moisture_map: Optional[List[List[float]]] = None,
                     noise_seed: int = 12345) -> List[List[float]]:
        """
        在干旱区域生成峡谷
        moisture_map: 湿度图（可选），None 时使用噪声模拟
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 如果没有湿度图，使用噪声模拟
        if moisture_map is None:
            moisture_noise = OpenSimplex2(noise_seed)
        
        for x in range(width):
            for z in range(height):
                # 获取湿度
                if moisture_map:
                    moisture = moisture_map[x][z]
                else:
                    moisture = moisture_noise.noise_2d(x * 0.01, z * 0.01) * 0.5 + 0.5
                
                # 只在干旱区域生成峡谷
                if moisture > self.arid_threshold:
                    continue
                
                # 在中高海拔区域生成峡谷
                if 70 < heightmap[x][z] < 120:
                    # 使用噪声决定峡谷路径
                    canyon_noise = OpenSimplex2(noise_seed + int(heightmap[x][z]))
                    canyon_pattern = canyon_noise.noise_2d(x * 0.05, z * 0.05)
                    
                    if canyon_pattern > 0.3:
                        # 下切峡谷
                        depth_factor = (canyon_pattern - 0.3) / 0.7
                        erosion = self.canyon_depth * depth_factor * 0.4
                        heightmap[x][z] -= erosion
        
        return heightmap


# ============================================================================
# 阶段五：风成与火山地貌
# ============================================================================


class WindErosion:
    """
    风蚀算法（18）
    根据主风向和岩石硬度，侵蚀特定方向
    """
    
    def __init__(self, wind_direction: float = 45.0,
                 erosion_strength: float = 2.0,
                 rock_hardness_map: Optional[Dict[str, float]] = None):
        """
        wind_direction: 主风向（角度，0=北，90=东）
        erosion_strength: 风蚀强度
        rock_hardness_map: 岩石硬度映射（可选）
        """
        self.wind_direction = wind_direction
        self.erosion_strength = erosion_strength
        self.rock_hardness_map = rock_hardness_map or {}
        
        # 将风向转换为弧度
        self.wind_rad = math.radians(wind_direction)
    
    def erode(self, heightmap: List[List[float]], 
              x: int, z: int,
              width: int, height: int) -> float:
        """
        对指定点进行风蚀
        返回：侵蚀后的高度变化量
        """
        current_height = heightmap[x][z]
        
        # 计算风向的偏移
        wind_dx = math.sin(self.wind_rad)
        wind_dz = math.cos(self.wind_rad)
        
        # 检查上风方向的邻居
        upwind_x = int(x - wind_dx)
        upwind_z = int(z - wind_dz)
        
        if 0 <= upwind_x < width and 0 <= upwind_z < height:
            upwind_height = heightmap[upwind_x][upwind_z]
            
            # 如果上风方向更高，产生侵蚀
            if upwind_height > current_height:
                height_diff = upwind_height - current_height
                
                # 获取岩石硬度（默认 1.0）
                rock_hardness = self.rock_hardness_map.get((x, z), 1.0)
                
                # 侵蚀量 = 高度差 * 风蚀强度 / 岩石硬度
                erosion = (height_diff * self.erosion_strength) / rock_hardness
                
                # 应用侵蚀
                heightmap[x][z] -= erosion * 0.1
                return erosion
        
        return 0.0


class WindDirectionalTransport:
    """
    风沙搬运（19）
    模拟沙粒跳跃，移动沙物质
    """
    
    def __init__(self, transport_distance: int = 5,
                 saltation_factor: float = 0.3):
        """
        transport_distance: 沙粒搬运距离
        saltation_factor: 跳跃因子（搬运比例）
        """
        self.transport_distance = transport_distance
        self.saltation_factor = saltation_factor
    
    def transport(self, heightmap: List[List[float]],
                  wind_direction: float,
                  width: int, height: int) -> List[List[float]]:
        """
        沿风向搬运沙物质
        """
        wind_rad = math.radians(wind_direction)
        wind_dx = math.sin(wind_rad)
        wind_dz = math.cos(wind_rad)
        
        # 创建临时缓冲区
        new_heightmap = [row[:] for row in heightmap]
        
        for x in range(width):
            for z in range(height):
                # 计算下风方向的位置
                downwind_x = int(x + wind_dx * self.transport_distance)
                downwind_z = int(z + wind_dz * self.transport_distance)
                
                if 0 <= downwind_x < width and 0 <= downwind_z < height:
                    # 从当前位置搬运沙到下风方向
                    transport_amount = self.saltation_factor * 0.5
                    new_heightmap[x][z] -= transport_amount
                    new_heightmap[downwind_x][downwind_z] += transport_amount
        
        return new_heightmap


class DuneFormation:
    """
    沙丘生成（20）
    在沙漠区域堆积形成沙丘链
    """
    
    def __init__(self, dune_height: float = 8.0,
                 dune_spacing: float = 30.0,
                 aridity_threshold: float = 0.8):
        """
        dune_height: 沙丘高度
        dune_spacing: 沙丘间距
        aridity_threshold: 干旱阈值（湿度低于此值才生成沙丘）
        """
        self.dune_height = dune_height
        self.dune_spacing = dune_spacing
        self.aridity_threshold = aridity_threshold
    
    def form_dunes(self, heightmap: List[List[float]],
                   moisture_map: Optional[List[List[float]]] = None,
                   seed: int = 12345) -> List[List[float]]:
        """
        在沙漠区域生成沙丘链
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 使用噪声生成沙丘 pattern
        dune_noise = OpenSimplex2(seed)
        
        for x in range(width):
            for z in range(height):
                # 获取湿度
                if moisture_map:
                    moisture = moisture_map[x][z]
                else:
                    moisture = dune_noise.noise_2d(x * 0.01, z * 0.01) * 0.5 + 0.5
                
                # 只在干旱区域生成沙丘
                if moisture > self.aridity_threshold:
                    # 使用周期性噪声生成沙丘链
                    dune_pattern = dune_noise.noise_2d(
                        x * (2 * math.pi / self.dune_spacing),
                        z * (2 * math.pi / self.dune_spacing)
                    )
                    
                    if dune_pattern > 0.3:
                        # 生成沙丘
                        dune_factor = (dune_pattern - 0.3) / 0.7
                        dune_height_offset = self.dune_height * dune_factor * 0.5
                        heightmap[x][z] += dune_height_offset
        
        return heightmap


class YardangAlgorithm:
    """
    雅丹地貌（21）
    定向风侵蚀形成垄槽相间
    """
    
    def __init__(self, wind_direction: float = 45.0,
                 yardang_spacing: float = 20.0,
                 ridge_height: float = 5.0):
        """
        wind_direction: 主导风向
        yardang_spacing: 垄槽间距
        ridge_height: 垄脊高度
        """
        self.wind_direction = wind_direction
        self.yardang_spacing = yardang_spacing
        self.ridge_height = ridge_height
    
    def form_yardangs(self, heightmap: List[List[float]],
                      seed: int = 12345) -> List[List[float]]:
        """
        生成雅丹地貌（垄槽相间）
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 计算垂直于风向的方向
        perp_rad = math.radians(self.wind_direction + 90)
        perp_dx = math.sin(perp_rad)
        perp_dz = math.cos(perp_rad)
        
        yardang_noise = OpenSimplex2(seed)
        
        for x in range(width):
            for z in range(height):
                # 计算在垂直风向方向上的坐标
                coord = x * perp_dx + z * perp_dz
                
                # 生成周期性的垄槽 pattern
                yardang_pattern = math.sin(coord * (2 * math.pi / self.yardang_spacing))
                
                # 添加一些随机变化
                noise_variation = yardang_noise.noise_2d(x * 0.05, z * 0.05) * 0.3
                yardang_pattern += noise_variation
                
                if yardang_pattern > 0.3:
                    # 形成垄脊（高处）
                    ridge_factor = (yardang_pattern - 0.3) / 0.7
                    heightmap[x][z] += self.ridge_height * ridge_factor * 0.3
                elif yardang_pattern < -0.3:
                    # 形成槽沟（低处）
                    trough_factor = (-yardang_pattern - 0.3) / 0.7
                    heightmap[x][z] -= self.ridge_height * trough_factor * 0.2
        
        return heightmap


class VolcanoCone:
    """
    火山锥算法（22）
    中心点隆起 + 随机喷发物，形成火山锥
    """
    
    def __init__(self, volcano_height: float = 50.0,
                 base_radius: float = 40.0,
                 crater_radius: float = 8.0):
        """
        volcano_height: 火山高度
        base_radius: 底座半径
        crater_radius: 火山口半径
        """
        self.volcano_height = volcano_height
        self.base_radius = base_radius
        self.crater_radius = crater_radius
    
    def create_volcano(self, heightmap: List[List[float]],
                       center_x: int, center_z: int,
                       seed: int = 12345) -> List[List[float]]:
        """
        在指定位置创建火山锥
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        volcano_noise = OpenSimplex2(seed)
        
        for x in range(width):
            for z in range(height):
                # 计算到火山中心的距离
                dx = x - center_x
                dz = z - center_z
                distance = math.sqrt(dx * dx + dz * dz)
                
                if distance < self.base_radius:
                    # 计算相对距离（0=中心，1=边缘）
                    rel_distance = distance / self.base_radius
                    
                    # 使用圆锥形隆起（中间高，边缘低）
                    cone_height = self.volcano_height * (1.0 - rel_distance) ** 2
                    
                    # 添加随机喷发物（火山碎屑）
                    ejecta = volcano_noise.noise_2d(x * 0.2, z * 0.2) * 3.0
                    
                    # 在火山口附近形成环形隆起
                    if distance > self.crater_radius:
                        heightmap[x][z] += cone_height + ejecta
                    else:
                        # 火山口内部轻微隆起
                        heightmap[x][z] += cone_height * 0.3 + ejecta
        
        # 形成火山口（中心凹陷）
        for x in range(width):
            for z in range(height):
                dx = x - center_x
                dz = z - center_z
                distance = math.sqrt(dx * dx + dz * dz)
                
                if distance < self.crater_radius:
                    # 火山口凹陷
                    crater_depth = self.volcano_height * 0.3 * (1.0 - distance / self.crater_radius)
                    heightmap[x][z] -= crater_depth
        
        return heightmap


class MagmaFluid:
    """
    岩浆流体（23）
    模拟熔岩流，改变局部地形（高粘度 NS 简化）
    """
    
    def __init__(self, viscosity: float = 0.8,
                 flow_distance: int = 20,
                 cooling_rate: float = 0.1):
        """
        viscosity: 岩浆粘度（越高流动越慢）
        flow_distance: 最大流动距离
        cooling_rate: 冷却速率
        """
        self.viscosity = viscosity
        self.flow_distance = flow_distance
        self.cooling_rate = cooling_rate
    
    def flow(self, heightmap: List[List[float]],
             source_x: int, source_z: int,
             seed: int = 12345) -> List[List[float]]:
        """
        从源头开始模拟熔岩流动
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        # 使用简单的扩散模型
        magma_height = 15.0  # 初始熔岩高度
        
        # 从源头向外扩散
        for radius in range(self.flow_distance):
            for angle in range(0, 360, 10):  # 每 10 度一个方向
                rad = math.radians(angle)
                x = int(source_x + radius * math.cos(rad))
                z = int(source_z + radius * math.sin(rad))
                
                if 0 <= x < width and 0 <= z < height:
                    # 熔岩随距离冷却变薄
                    flow_factor = 1.0 - (radius / self.flow_distance)
                    flow_factor *= (1.0 - self.cooling_rate) ** radius
                    
                    # 粘度影响流动性
                    flow_factor *= (1.0 - self.viscosity)
                    
                    if flow_factor > 0.1:
                        # 添加熔岩堆积
                        lava_height = magma_height * flow_factor
                        heightmap[x][z] += lava_height
        
        return heightmap


class CalderaCollapse:
    """
    火山口塌陷（24）
    火山喷发后顶部塌陷，形成破火山口
    """
    
    def __init__(self, collapse_depth: float = 20.0,
                 collapse_radius: float = 25.0):
        """
        collapse_depth: 塌陷深度
        collapse_radius: 塌陷半径
        """
        self.collapse_depth = collapse_depth
        self.collapse_radius = collapse_radius
    
    def collapse(self, heightmap: List[List[float]],
                 center_x: int, center_z: int) -> List[List[float]]:
        """
        在火山顶部形成塌陷的破火山口
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        for x in range(width):
            for z in range(height):
                dx = x - center_x
                dz = z - center_z
                distance = math.sqrt(dx * dx + dz * dz)
                
                if distance < self.collapse_radius:
                    # 计算塌陷深度（中心最深，边缘渐浅）
                    rel_distance = distance / self.collapse_radius
                    collapse = self.collapse_depth * (1.0 - rel_distance) ** 2
                    
                    # 添加一些随机变化
                    noise = OpenSimplex2(int(center_x * 100 + center_z)).noise_2d(x * 0.1, z * 0.1)
                    collapse += noise * 2.0
                    
                    heightmap[x][z] -= collapse
        
        return heightmap


class LavaPlateau:
    """
    熔岩台地（25）
    大面积平坦熔岩覆盖
    """
    
    def __init__(self, plateau_height: float = 5.0,
                 coverage_radius: float = 60.0,
                 flatness: float = 0.8):
        """
        plateau_height: 台地高度
        coverage_radius: 覆盖半径
        flatness: 平坦度（越高越平）
        """
        self.plateau_height = plateau_height
        self.coverage_radius = coverage_radius
        self.flatness = flatness
    
    def create_plateau(self, heightmap: List[List[float]],
                       center_x: int, center_z: int,
                       seed: int = 12345) -> List[List[float]]:
        """
        创建大面积的熔岩台地
        """
        width = len(heightmap)
        height = len(heightmap[0])
        
        plateau_noise = OpenSimplex2(seed)
        
        for x in range(width):
            for z in range(height):
                dx = x - center_x
                dz = z - center_z
                distance = math.sqrt(dx * dx + dz * dz)
                
                if distance < self.coverage_radius:
                    # 计算覆盖因子（边缘渐变）
                    rel_distance = distance / self.coverage_radius
                    coverage = 1.0 - rel_distance
                    
                    # 平坦化处理
                    if coverage > 0.3:
                        # 添加轻微的地形起伏
                        noise_variation = plateau_noise.noise_2d(x * 0.03, z * 0.03) * 2.0
                        
                        # 熔岩覆盖使地形变平
                        heightmap[x][z] += (self.plateau_height - heightmap[x][z] * 0.1) * coverage * self.flatness
                        heightmap[x][z] += noise_variation * coverage
        
        return heightmap
