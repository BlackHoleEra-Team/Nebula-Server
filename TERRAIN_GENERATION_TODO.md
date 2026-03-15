# 地形生成 TODO

## 🏔️ 阶段一：基础地形骨架
**目标**：生成大陆轮廓和基本高度场，能输出 2D 高度图或简单 3D 地形。

- [ ] OpenSimplex2 / Simplex 噪声（1）
  - [ ] 实现 2D/3D 噪声函数，作为所有后续噪声的基础
- [ ] FBM 分形布朗运动（2）
  - [ ] 叠加多层噪声，构建粗糙的地形轮廓
- [ ] Domain Warping 地形扭曲（3）
  - [ ] 用噪声场扭曲坐标，增加地形有机感
- [ ] Hard Height Curve 高度曲线（4）
  - [ ] 将高度值映射到最终范围，控制平原/山脉比例

**验证**：生成 256×256 的灰度图，肉眼观察大陆架、山脉雏形。

---

## ⛰️ 阶段二：大型地貌特征
**目标**：在基础地形上添加山脉、高原、盆地等显著特征。

- [ ] Large-Scale Uplift 超大尺度抬升（7）
  - [ ] 用低频噪声控制区域性抬升，形成主要山脉
- [ ] Ridged MultiFractal 山脊分形（5）
  - [ ] 叠加山脊噪声，增强山脊线
- [ ] Mountain Crest Enhancement 山脊强化（8）
  - [ ] 锐化山脊，让山峰更突出
- [ ] Turbulence 扰动（6）
  - [ ] 对地形施加二次扭曲，增加破碎感
- [ ] Plateau Filter 高原化算法（9）
  - [ ] 将高海拔区域压平，形成高原
- [ ] Basin Generator 盆地算法（10）
  - [ ] 制造局部凹陷，用于后续湖泊/盆地
- [ ] Terrace Step 阶地/台地算法（11）
  - [ ] 量化高度，生成台阶
- [ ] Hill & Rolling 丘陵算法（12）
  - [ ] 在低海拔区域添加平缓起伏

**验证**：此时地形已具备大型山脉、高原、盆地，可生成彩色高度图观察。

---

## 💧 阶段三：水力侵蚀（地形真实感的关键）
**目标**：模拟水流雕刻地形，形成沟壑、河谷。

- [ ] D8 Flow Direction D8 流向算法（16）
  - [ ] 计算每个点的水流方向（需要先有高度图）
- [ ] Hydraulic Erosion 水力侵蚀（13）
  - [ ] 核心侵蚀循环：水携带沉积物移动，侵蚀高地，沉积低地
- [ ] Thermal Erosion 热侵蚀/土石滑落（14）
  - [ ] 重力导致的物质下滑，使斜坡趋于稳定角
- [ ] Fluid Transport 沉积物搬运（15）
  - [ ] 与侵蚀结合，模拟搬运过程
- [ ] Fluid Sediment Deposition 沉积算法（17）
  - [ ] 在流速降低处沉积物质（如冲积扇）

**验证**：运行侵蚀迭代后，地形应出现明显的河谷、冲沟，山脚有沉积扇。

---

## 🌊 阶段四：河流、湖泊与海岸
**目标**：基于侵蚀后的地形生成河网、湖泊，并处理海岸线。

- [ ] River Network 河流网络生成（26）
  - [ ] 从源头开始，沿流向累积流量，生成永久河床
- [ ] Valley Carving 河谷下切（27）
  - [ ] 加深河道，形成 V 型谷
- [ ] Mountain Lake / Heaven Pool 天池算法（28）
  - [ ] 检测封闭洼地，填充成湖泊
- [ ] Coastal Erosion 海岸侵蚀（29）
  - [ ] 根据波浪能量修改海岸线，形成海蚀崖
- [ ] Canyon Generator 大峡谷生成（30）
  - [ ] 在特定区域（如干旱区）强化下切，形成峡谷

**验证**：生成带河流、湖泊的地形，海岸线出现曲折和悬崖。

---

## 🌪️ 阶段五：风成与火山地貌
**目标**：在干旱区添加风蚀地貌，在构造活跃区添加火山。

- [ ] Wind Erosion 风蚀算法（18）
  - [ ] 根据主风向和岩石硬度，侵蚀特定方向
- [ ] Wind Directional Transport 风沙搬运（19）
  - [ ] 模拟沙粒跳跃，移动沙物质
- [ ] Dune Formation 沙丘生成（20）
  - [ ] 在沙漠区域堆积形成沙丘链
- [ ] Yardang Algorithm 雅丹地貌（21）
  - [ ] 定向风侵蚀形成垄槽相间
- [ ] Volcano Cone 火山锥算法（22）
  - [ ] 中心点隆起 + 随机喷发物，形成火山锥
- [ ] Magma Fluid 岩浆流体（高粘度 NS 简化）（23）
  - [ ] 模拟熔岩流，改变局部地形
- [ ] Caldera Collapse 火山口塌陷（24）
  - [ ] 火山喷发后顶部塌陷，形成破火山口
- [ ] Lava Plateau 熔岩台地（25）
  - [ ] 大面积平坦熔岩覆盖

**验证**：在特定生物群系（沙漠、火山带）能看到典型地貌。

---

## 🕳️ 阶段六：喀斯特地貌与 3D 洞穴系统（核心难点）
**目标**：从 2.5D 升级到真 3D，在地下生成溶洞、地下河等结构。

- [ ] Karst Base Layer 石灰岩基底分布（31）
  - [ ] 定义可溶性岩石区域（3D 掩码）
- [ ] Groundwater Seepage 地下水渗透算法（32）
  - [ ] 模拟地下水流动路径（3D 场）
- [ ] Karst Dissolution 碳酸水溶蚀（33）
  - [ ] 沿水流路径溶解岩石，降低密度
- [ ] Cave Network 溶洞/地下空洞生成（34）
  - [ ] 核心 3D 空洞生成器（可用 3D 噪声 + 溶蚀模拟）
- [ ] Cave Collapse 溶洞塌陷 → 天坑（35）
  - [ ] 当空洞上方岩石过薄时塌陷，连通地表
- [ ] Karst Peak Forest 桂林峰林算法（36）
  - [ ] 在强烈溶蚀区形成离散石峰（修改地表）
- [ ] Stone Forest 石林算法（37）
  - [ ] 在近水平岩层生成密集石柱
- [ ] Underground River 地下河系统（38）
  - [ ] 在洞穴网络中定义水流路径，可能冲出地表
- [ ] Natural Bridge 天生桥生成（39）
  - [ ] 洞穴部分塌陷后残留的桥状结构

**验证**：生成 3D 切片图，观察地下空洞、钟乳石（可后续添加）、地下河。能进入游戏查看洞穴内部。

---

## ❄️ 阶段七：冰川、构造与特殊地表过程
**目标**：整合剩下的地质过程，丰富地貌多样性。

- [ ] Glacial Erosion 冰川侵蚀（40）
  - [ ] 在高纬度/高海拔区域雕刻 U 型谷、冰斗、角峰
- [ ] Tectonic / Fault Movement 构造断层与抬升（41）
  - [ ] 模拟断层位移，形成断层崖、地垒地堑
- [ ] Sea Level & Floodfill 海平面淹没算法（42）
  - [ ] 根据海平面确定海岸线，淹没低洼区域
- [ ] Soil Depth 土壤厚度生成（43）
  - [ ] 基于坡度、气候、母岩计算土壤覆盖
- [ ] Sun Exposure 地形日照/阴阳坡算法（44）
  - [ ] 计算坡向，影响后续植被/积雪
- [ ] Landslide 滑坡/崩塌算法（45）
  - [ ] 在陡坡处触发物质滑移
- [ ] Alluvial Fan 冲积扇/三角洲算法（46）
  - [ ] 在河流出山口或入海口堆积扇形沉积
- [ ] Island Shape & Mask 岛屿生成（47）
  - [ ] 用噪声生成岛屿轮廓，控制海岸线
- [ ] Coral Reef 珊瑚礁/滩涂算法（48）
  - [ ] 在浅海温暖水域生成珊瑚礁
- [ ] Salt Lake & Salt Marsh 盐湖、盐碱地（49）
  - [ ] 在封闭盆地蒸发形成盐壳
- [ ] Permafrost 冻土/永冻层（50）
  - [ ] 根据气候模拟永久冻土分布
- [ ] Gully Erosion 细沟/冲沟系统（51）
  - [ ] 在黄土区域添加密集冲沟网络

**验证**：地形应出现冰川地貌、断层线、盐湖等，细节极大丰富。

---

## 🌿 阶段八：气候、生物群系与方块放置
**目标**：将地形转化为 Minecraft 世界，放置不同方块和资源。

- [ ] Temperature Map 温度噪声（55）
  - [ ] 根据纬度、海拔生成温度场
- [ ] Humidity Map 湿度噪声（56）
  - [ ] 结合风向、地形雨等生成湿度
- [ ] Biome Blend 群系混合（57）
  - [ ] 根据温湿度图确定生物群系，并平滑过渡
- [ ] Snow Line 雪线算法（58）
  - [ ] 根据温度和海拔确定积雪线
- [ ] Strata Generator 地质分层（52）
  - [ ] 根据深度和区域生成岩层序列（如花岗岩、石灰岩、砂岩）
- [ ] Ore Distribution 矿石分布（54）
  - [ ] 在岩层中嵌入矿脉
- [ ] Slope-Based Block 坡度判断方块（53）
  - [ ] 根据坡度放置不同表面方块（如草、石、雪）

**验证**：进入游戏，不同生物群系有正确方块，地下有矿石，地表有植被（需额外实现）。

---

## ⚡ 阶段九：性能优化与整合（贯穿全程）
**目标**：确保生成速度满足 Minecraft 服务端实时需求。

- [ ] 初期：单线程，小范围生成测试
- [ ] 中期：引入 Numba @njit 加速热点函数（60）
- [ ] 后期：实现 Multi-threading 多线程并行（61），每个区块独立生成
- [ ] 实施 Heightmap Caching 高度图缓存（62），避免重复计算
- [ ] 实现 LOD 细节分级（63），远处用低分辨率
- [ ] 完善 Chunk-based Generation 区块生成（59），按需生成

---

## 📊 当前进度

**已完成**：
- ✅ 阶段一：基础地形骨架
  - OpenSimplex2/Simplex 噪声
  - FBM 分形布朗运动
  - Domain Warping 地形扭曲
  - Hard Height Curve 高度曲线
- ✅ 阶段二：大型地貌特征
  - Large-Scale Uplift 超大尺度抬升
  - Ridged MultiFractal 山脊分形
  - Mountain Crest Enhancement 山脊强化
  - Turbulence 扰动
  - Plateau Filter 高原化算法
  - Basin Generator 盆地算法
  - Terrace Step 阶地/台地算法
  - Hill & Rolling 丘陵算法
- ✅ 阶段三：水力侵蚀
  - D8 Flow Direction 流向算法
  - Hydraulic Erosion 水力侵蚀
  - Thermal Erosion 热侵蚀
  - Fluid Transport 流体搬运
  - Sediment Deposition 沉积算法
  - River Carver 河道雕刻器
- ✅ 阶段四：河流、湖泊与海岸
  - River Network 河流网络生成（26）✓
  - Valley Carving 河谷下切（27）✓
  - Mountain Lake / Heaven Pool 天池算法（28）✓
  - Coastal Erosion 海岸侵蚀（29）✓
  - Canyon Generator 大峡谷生成（30）✓
- ✅ 阶段五：风成与火山地貌
  - Wind Erosion 风蚀算法（18）✓
  - Wind Directional Transport 风沙搬运（19）✓
  - Dune Formation 沙丘生成（20）✓
  - Yardang Algorithm 雅丹地貌（21）✓
  - Volcano Cone 火山锥算法（22）✓
  - Magma Fluid 岩浆流体（23）✓
  - Caldera Collapse 火山口塌陷（24）✓
  - Lava Plateau 熔岩台地（25）✓
- ✅ **阶段四、五已集成到服务器地形生成** ✓

**进行中**：
- 🔄 地形生成参数优化（减少阶梯效应、提升真实感）

**待开始**：
- ⏳ 阶段六：喀斯特地貌与 3D 洞穴
- ⏳ 阶段七：冰川、构造与特殊地表
- ⏳ 阶段八：气候、生物群系与方块放置
- ⏳ 阶段九：性能优化与整合

---

## 📝 备注

- 每个阶段完成后应生成可视化结果进行验证
- 性能优化应贯穿整个开发过程
- 保持与 Minecraft 1.12.2 协议兼容性
