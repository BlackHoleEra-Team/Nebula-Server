# Nebula Minecraft Server 1.12.2

一个用 Python 编写的 Minecraft 1.12.2 服务器实现。

## 特性

- 完整的 Minecraft 1.12.2 协议支持
- 使用 OpenSimplex2 + FBM + Domain Warping 的高级地形生成
- 支持 1024 格高度上限
- 动态区块加载
- GPL-3.0 开源协议

## 安装

### 要求

- Python >= 3.8

### 安装方式

```bash
# 克隆仓库
git clone https://github.com/BlackHoleEra-Team/NebulaServer.git
cd NebulaServer

# 安装
pip install .

# 或开发模式安装
pip install -e .
```

## 使用

### 方式 1: 作为模块运行

```bash
python -m nebula.main
```

### 方式 2: 使用命令

```bash
nebula
```

### 首次运行

首次运行时会提示接受 EULA 协议。编辑生成的 `eula.txt` 文件，将 `eula=false` 改为 `eula=true`。

## 配置

服务器配置在 `server.properties` 文件中：

```properties
server-ip=0.0.0.0
server-port=25565
max-players=20
motd=Nebula Server 1.12.2
```

## 项目结构

```
nebula/
├── core/           # 核心常量
├── network/        # 网络协议
├── world/          # 世界管理
├── player/         # 玩家管理
├── logging/        # 日志系统
├── config/         # 配置管理
├── console/        # 控制台
└── main.py         # 入口点
```

## 地形生成

使用先进的地形生成算法：

1. **OpenSimplex2 噪声** - 高质量 2D/3D 噪声
2. **FBM 分形布朗运动** - 多层噪声叠加
3. **Domain Warping** - 地形扭曲增加有机感
4. **Height Curve** - 高度曲线控制地形分布

## 许可证

GPL-3.0 License - 详见 [LICENSE](LICENSE) 文件

## 团队

[BlackHoleEraTeam](https://github.com/BlackHoleEra-Team)

## 问题反馈

[GitHub Issues](https://github.com/BlackHoleEra-Team/NebulaServer/issues)
