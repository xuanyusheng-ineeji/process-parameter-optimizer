# Project Summary — Process Parameter Optimizer

> 食品工厂填充工艺参数优化系统

---

## 一、项目定位

本项目是一套**离线式工艺参数推荐系统**，面向食品工厂填充生产线。

**工作流程：**
```
历史生产数据（参数 + 实测重量）
        ↓
   AI 模型分析
        ↓
  发现重量偏差根因
        ↓
  推荐新设备 Set Point
        ↓
  工程师确认后手动输入 PLC/HMI
        ↓
     下一批产品
```

系统**不控制**设备，只输出建议值供工程师判断。

---

## 二、目录结构

```
process-parameter-optimizer/
│
├── src/
│   ├── filling/                  # 填充工艺核心模块（主要开发方向）
│   │   ├── config.py             # 16个产品配置 + 参数边界
│   │   ├── data_loader.py        # 历史数据加载与清洗
│   │   ├── synthetic_data.py     # 合成数据生成（无真实数据时使用）
│   │   ├── predictor.py          # 多模型训练与自动选优
│   │   ├── analyzer.py           # 根因分析（参数重要性 + 方向）
│   │   └── recommender.py        # Set Point 优化推荐
│   │
│   └── core/                     # 通用优化算法（原注塑项目遗留）
│       ├── bayesian_optimizer.py  # 贝叶斯优化（GP + EI 采集函数）
│       └── injection_molding.py   # 注塑机虚拟仿真器
│
├── scripts/
│   └── demo_filling.py           # 端到端演示脚本（4步完整流程）
│
├── tests/
│   └── filling/
│       ├── test_config.py        # 产品配置测试（6项）
│       ├── test_data_loader.py   # 数据加载测试（6项）
│       ├── test_predictor.py     # 预测模型测试（6项）
│       ├── test_recommender.py   # 推荐器测试（6项）
│       └── test_analyzer.py     # 根因分析测试（7项）
│
├── data/
│   └── raw/
│       └── MST_ITEM_202606231336.csv  # 原始产品主数据（Target/LCL/UCL）
│
├── docs/
│   ├── machine_parameters.txt         # 填充设备参数清单（韩文）
│   └── WRK_WEIGHT_SUMMARY_ORDER_품목목록.md  # 16个目标产品列表
│
├── pyproject.toml                # 项目依赖与构建配置
└── PROJECT_SUMMARY.md            # 本文件
```

---

## 三、填充模块详解（src/filling/）

### 3.1 config.py — 产品与参数配置

定义了 16 个填充产品的完整配置，以及 5 个设备参数。

**产品规格（ProductConfig）：**

| 字段 | 说明 |
|------|------|
| `item_cd` | 产品编码 |
| `item_nm` | 产品名称（韩文） |
| `target_g` | 标准重量（g） |
| `lcl_g` | 下控制线 = target_g（食品法规：不允许少装） |
| `ucl_g` | 上控制线（部分出口产品无限制，设为 None） |
| `nominal_params` | 正常工况下的参数值 |

**16 个产品：**
- 小包装（200–300g）：10 款奶油、蒜蓉酱、蛋黄酱类产品
- 大包装（3kg）：6 款奶油、草莓酱、番茄奶酪类产品

**5 个设备参数（PARAM_NAMES）：**

| 参数 | 单位 | 小包装范围 | 大包装范围 |
|------|------|-----------|-----------|
| `fill_time_s` | 秒 | 1.2 – 2.5 | 3.0 – 5.5 |
| `fill_pressure_bar` | bar | 1.2 – 2.5 | 1.8 – 3.2 |
| `product_temp_c` | °C | 8 – 28 | 8 – 28 |
| `nozzle_opening_pct` | % | 50 – 90 | 55 – 95 |
| `line_speed_bpm` | 包/分 | 25 – 55 | 12 – 28 |

> **注意：** 当前参数名称是通用假设值。实际设备参数（泵 INV 速度、校正输出等，见 `docs/machine_parameters.txt`）需在获取真实数据后替换。

---

### 3.2 data_loader.py — 数据加载

支持三种输入方式：

```python
from src.filling import data_loader

df = data_loader.from_csv("production.csv", item_cd="285104")
df = data_loader.from_excel("production.xlsx", item_cd="285104")
df = data_loader.from_dataframe(raw_df, item_cd="285104")
```

**清洗规则（自动执行）：**
- 删除含空值的行
- 删除重量 ≤ 0 的记录（传感器故障）
- 将参数值 clip 到物理合理范围（如温度 0–50°C）
- 若所有行均被清洗掉，抛出 `ValueError`

**必须包含的列：**
```
fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g, item_cd
```

---

### 3.3 synthetic_data.py — 合成数据

在没有真实历史数据时，用物理模型生成测试数据。

**物理模型（重量计算公式）：**
```
weight_ratio = fill_time^0.85 × pressure^0.30 × nozzle^0.20 × (1/speed)^0.10 × temp_factor
fill_weight  = target_g × weight_ratio + 噪声（±0.3% 小包装，±0.15% 大包装）
```

```python
from src.filling import synthetic_data

df = synthetic_data.generate("285104", n_batches=300, seed=42)
df_all = synthetic_data.generate_all(n_batches=200)
```

---

### 3.4 predictor.py — 多模型预测

同时训练 15 个候选模型，按 5-fold 交叉验证 R² 自动选优。

**候选模型（15 个）：**

| 类别 | 模型 |
|------|------|
| 线性 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 核函数 | SVR_RBF, SVR_Poly |
| 实例 | KNeighbors_5, KNeighbors_10 |
| 树/森林 | DecisionTree, ExtraTrees, RandomForest |
| 集成提升 | GradientBoosting, HistGradientBoosting |

**所有模型均包含 StandardScaler 预处理。**

**典型输出（合成数据场景，300批次）：**
```
Model                     CV R²      ±  Train σ (g)
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  ...（共15行）
Selected: HuberRegressor  |  n=300 batches
```

**API：**
```python
predictor = FillWeightPredictor()
predictor.train(df, product)          # 训练并选优
predictor.predict(params_dict)        # 单次预测 → float
predictor.feature_importances()       # 参数重要性 → Dict
predictor.print_summary()             # 打印对比表
```

---

### 3.5 analyzer.py — 根因分析

识别哪个参数最影响填充重量，以及影响方向。

**输出示例：**
```
[Parameter Influence on Fill Weight]
  fill_time_s         59.2%  ███████████  ↑ increases weight
  fill_pressure_bar   19.2%  ███          ↑ increases weight
  nozzle_opening_pct   9.6%  █            ↑ increases weight
  line_speed_bpm       6.9%  █            ↓ decreases weight
  product_temp_c       5.1%  █            ↑ increases weight

[Top Cause]  fill_time_s
```

**方法：** 对每个参数施加 ±5% 扰动，观察预测重量变化方向（自动 clip 到参数边界）。

```python
analyzer = RootCauseAnalyzer(predictor, product)
result = analyzer.analyze(df)    # 返回结构化字典
analyzer.print_report(df)        # 打印报告
```

---

### 3.6 recommender.py — Set Point 推荐

在参数可调范围内，找出使填充重量最接近目标且在 LCL–UCL 区间的设备参数。

**优化目标：**
```
最小化：(预测重量 - 目标重量)²
        + 变化惩罚（重要性低的参数，惩罚更重）
        + 硬约束违反惩罚（重量 < LCL × 1000）
        + 软约束违反惩罚（重量 > UCL × 500）
```

**约束：**
- 每个参数变化量不超过其操作范围的 ±15%（`max_change_pct`）
- 参数值保持在绝对边界内（`get_param_bounds()`）

**算法：** L-BFGS-B 多起点优化（10 个随机起点，取最优解）

```python
recommender = SetPointRecommender(predictor, product)
rec = recommender.recommend(current_params, max_change_pct=0.15)
recommender.print_report(rec)
```

**输出示例：**
```
[Recommended Set Points]
  Parameter               Current   Recommended   Change
  fill_time_s               1.750         1.832   +0.082
  fill_pressure_bar         1.700         1.717   +0.017
  ...

[Expected Outcome]
  Predicted fill weight: 300.0g
  Status: OK ✓
  Improvement: +12.10g closer to target
```

---

## 四、核心模块（src/core/）

这是项目的**原始框架**，用于注塑成型工艺，目前与填充模块独立。

| 文件 | 说明 |
|------|------|
| `bayesian_optimizer.py` | 通用贝叶斯优化器（GP + EI + 多目标），适用于实验次数少、参数空间大的场景 |
| `injection_molding.py` | 注塑机数字仿真器（30+ 参数，含质量/周期时间/能耗预测） |

> **注意：** `bayesian_optimizer.py` 中的 GP 预测部分使用了简化的距离加权插值，而非真正的 Gaussian Process，仅作框架参考。

---

## 五、快速开始

### 环境安装（仅需一次）

```powershell
conda activate venv
pip install -e .
```

### 运行演示

```powershell
python scripts/demo_filling.py
```

### 运行测试

```powershell
python -m pytest tests/filling/ -v
```

当前测试：**30 项，全部通过**

---

## 六、接入真实数据

当有真实 CSV 数据时，替换演示脚本中的合成数据部分：

```python
# 替换此行：
raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
df = data_loader.from_dataframe(raw_df, item_cd=item_cd)

# 改为：
df = data_loader.from_csv("你的数据文件.csv", item_cd="285104")
```

**CSV 必须包含以下列：**
```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

---

## 七、模型重训建议

| 情况 | 建议重训频率 |
|------|------------|
| 同一班内物性缓慢变化 | 每 1–2 小时，用最新 50–100 批数据重训 |
| 每天换原料批次 | 每天开机前，用前一天数据重训 |
| 原料突然换批 | 丢弃旧数据，从新批次重新积累 ≥ 100 条再训练 |
| 粘度有仪器实测 | 将粘度值加入 PARAM_NAMES，精度可大幅提升 |

---

## 八、已知局限与待办

| 项目 | 状态 | 说明 |
|------|------|------|
| 参数名称与实际设备对应 | ⚠️ 待完善 | 当前用通用英文名，实际设备参数见 `docs/machine_parameters.txt` |
| 产品配置从 CSV 动态加载 | ⚠️ 待完善 | 目前 16 个产品硬编码在 `config.py`，需与 `data/raw/MST_ITEM_*.csv` 保持同步 |
| 核心 GP 模型 | ⚠️ 简化版 | `bayesian_optimizer.py` 使用距离加权插值替代真实 GP |
| 时序/物性漂移建模 | ❌ 未实现 | 当前模型为静态映射，需配合定期重训应对物性变化 |
| 预测置信区间 | ❌ 未实现 | 当前只输出点估计，无不确定性范围 |
| Web API | ❌ 未实现 | pyproject.toml 已包含 FastAPI 依赖，接口层尚未开发 |

---

## 九、依赖概览

```
scikit-learn   — 15 个候选模型 + Pipeline + 交叉验证
scipy          — L-BFGS-B 约束优化
numpy / pandas — 数值计算与数据处理
fastapi        — （预留）REST API 接口
torch          — （预留）深度学习扩展
plotly         — （预留）可视化
```

---

*生成时间：2026-07-03*
