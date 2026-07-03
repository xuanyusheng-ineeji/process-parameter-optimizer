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
│   ├── filling/                   # 填充工艺核心模块（主要开发方向）
│   │   ├── config.py              # 16个产品配置 + 参数边界
│   │   ├── data_loader.py         # 历史数据加载与清洗
│   │   ├── synthetic_data.py      # 合成数据生成（批次模式 + 时序模式）
│   │   ├── aggregate.py           # 1秒时序 → 稳定窗口批次行（含滞后补偿）
│   │   ├── trend.py               # 实时趋势监控（EWMA + SPC告警 + OOC预测）
│   │   ├── predictor.py           # 多模型训练与自动选优（15个候选模型）
│   │   ├── analyzer.py            # 根因分析（参数重要性 + 方向）
│   │   └── recommender.py         # Set Point 约束优化推荐
│   │
│   └── core/                      # 通用优化算法（原注塑项目遗留）
│       ├── bayesian_optimizer.py   # 贝叶斯优化（GP + EI 采集函数）
│       └── injection_molding.py    # 注塑机虚拟仿真器
│
├── scripts/
│   └── demo_filling.py            # 端到端演示（批次模式4步 / 时序模式6步）
│
├── tests/
│   └── filling/
│       ├── test_config.py         # 产品配置测试（6项）
│       ├── test_data_loader.py    # 数据加载测试（6项）
│       ├── test_predictor.py      # 预测模型测试（6项）
│       ├── test_recommender.py    # 推荐器测试（5项）
│       ├── test_analyzer.py       # 根因分析测试（7项）
│       ├── test_aggregate.py      # 时序聚合测试（11项）
│       └── test_trend.py          # 趋势监控测试（17项）
│
├── data/
│   └── raw/
│       └── MST_ITEM_202606231336.csv   # 原始产品主数据（Target/LCL/UCL）
│
├── docs/
│   ├── machine_parameters.txt          # 填充设备参数清单（韩文）
│   └── WRK_WEIGHT_SUMMARY_ORDER_품목목록.md  # 16个目标产品列表
│
├── pyproject.toml                 # 项目依赖与构建配置
├── CLAUDE.md                      # Claude Code 上下文说明
└── PROJECT_SUMMARY.md             # 本文件
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

**必须包含的列（列名大小写不敏感，自动转小写）：**
```
fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g, item_cd
```

---

### 3.3 synthetic_data.py — 合成数据

在没有真实历史数据时，用物理模型生成测试数据。提供两种模式：

#### 批次模式（每批次一行）

```python
df = synthetic_data.generate("285104", n_batches=300, seed=42)
df_all = synthetic_data.generate_all(n_batches=200)
```

#### 时序模式（每秒一行，模拟一次生产班）

```python
ts_df = synthetic_data.generate_timeseries(
    "285104",
    duration_seconds=3600,      # 1小时
    drift_rate_g_per_min=0.8,   # 模拟粘度漂移（重量逐渐偏移）
    n_param_adjustments=20,     # 班次内工程师调参次数
    seed=42,
)
```

**物理重量模型（两种模式共用）：**
```
weight_ratio = (fill_time/nom)^0.85 × (pressure/nom)^0.30
             × (nozzle/nom)^0.20 × (nom_speed/speed)^0.10
             × (1 + 0.003 × (temp − nom_temp))

fill_weight  = target_g × weight_ratio + 噪声 + 漂移
```

---

### 3.4 aggregate.py — 时序聚合（新增）

将每秒一行的原始 PLC/称重数据，聚合为参数稳定窗口（等同于"一个批次"），输出可直接送入 `data_loader` 的标准格式。

**核心功能：**
- **滞后补偿**：PLC 下发参数到称重传感器有 `lag_seconds` 秒延迟，自动补偿
- **参数变化检测**：每个参数有独立容差（如 fill_time_s 容差 5ms），微小抖动不算真实调参
- **短窗口过滤**：丢弃小于 `min_stable_seconds` 的过渡窗口

```python
from src.filling import aggregate

batches = aggregate.from_timeseries(
    ts_df,
    item_cd="285104",
    lag_seconds=2,           # PLC→称重延迟（需按设备实测）
    min_stable_seconds=30,   # 最短稳定窗口
)
# 输出列：PARAM_NAMES均值, fill_weight_g均值, weight_std_g,
#         weight_min_g, weight_max_g, n_seconds, window_start, window_end, item_cd

aggregate.summary(batches)   # 打印窗口统计
```

输出可直接传入 `data_loader.from_dataframe()` → `predictor.train()`。

---

### 3.5 trend.py — 实时趋势监控（新增）

对时序重量数据进行实时分析，监测漂移趋势并预测何时触碰控制限。

**功能：**
- 滚动均值/标准差（最近 `window_seconds` 秒）
- EWMA 平滑跟踪（`ewma_lambda` 调节响应速度）
- 线性回归斜率（g/分钟）
- OOC 预测："按当前趋势，还有多少秒触碰 LCL/UCL"（超过 24 小时则视为无意义，返回 None）
- SPC 告警：均值越限 → CRITICAL，波动过大/持续漂移 → WARNING

```python
from src.filling.trend import WeightTrendMonitor

monitor = WeightTrendMonitor(product, window_seconds=300, ewma_lambda=0.2)
report = monitor.analyze(ts_df)
# report["status"]           → "OK" / "WARNING" / "CRITICAL"
# report["trend_slope_g_per_min"] → 斜率（g/分钟）
# report["seconds_until_ooc"]    → 预计触碰控制限的剩余秒数（或 None）
# report["alerts"]               → 告警信息列表

monitor.print_report(report)
```

---

### 3.6 predictor.py — 多模型预测

同时训练 15 个候选模型，按 5-fold 交叉验证 R² 自动选优。

**关键实现细节：**
- 每次 `train()` 调用时 `clone()` 全部 Pipeline，避免多实例间的模型状态污染
- NaN CV 得分（如样本量小于 KNN 邻居数时）自动降级为 -999，不参与选优
- `feature_importances()` 统一接口：树模型用 `.feature_importances_`，线性模型用 `|coef_|` 归一化，SVR/KNN 用均等权重

**候选模型（15 个）：**

| 类别 | 模型 |
|------|------|
| 线性 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 核函数 | SVR_RBF, SVR_Poly |
| 实例 | KNeighbors_5, KNeighbors_10 |
| 树/森林 | DecisionTree, ExtraTrees, RandomForest |
| 集成提升 | GradientBoosting, HistGradientBoosting |

所有模型包含 StandardScaler 预处理。

```python
predictor = FillWeightPredictor()
result = predictor.train(df, product)   # 返回含 comparison 列表的 dict
predictor.print_summary()
weight = predictor.predict(params_dict)
importances = predictor.feature_importances()
```

---

### 3.7 analyzer.py — 根因分析

识别哪个参数最影响填充重量，以及影响方向。

**方法：** 对每个参数施加 +5% 扰动（若触碰上界则改用 -5% 并取反）。

```python
analyzer = RootCauseAnalyzer(predictor, product)
result = analyzer.analyze(df)
# result["importance"]       → 按影响度排序的 [(参数名, 百分比)] 列表
# result["direction"]        → {参数名: "↑ increases weight" / "↓ decreases weight"}
# result["top_cause"]        → 影响最大的参数名
# result["deviation_summary"]→ mean_weight_g, bias_g, ok_pct, low_pct, high_pct

analyzer.print_report(df)
```

---

### 3.8 recommender.py — Set Point 推荐

在参数可调范围内，用约束优化找出使填充重量最接近目标的设备参数。

**优化目标：**
```
最小化：(预测重量 - 目标重量)²
        + 变化惩罚（重要性低的参数惩罚更重，逆重要性加权）
        + 1000 × max(0, LCL - 预测重量)   ← 硬约束（不能少装）
        + 500  × max(0, 预测重量 - UCL)    ← 软约束（避免浪费）
```

**约束：**
- 每个参数变化量 ≤ 操作范围 × `max_change_pct`（默认 15%）
- 参数值保持在绝对边界内

**算法：** L-BFGS-B + 10 个随机多起点

```python
recommender = SetPointRecommender(predictor, product)
rec = recommender.recommend(current_params, max_change_pct=0.15)
recommender.print_report(rec)
```

---

## 四、完整数据流

### 批次模式（直接使用历史批次数据）

```
CSV/Excel/DataFrame
        ↓ data_loader.from_csv() / from_dataframe()
   清洗后的批次 DataFrame
        ↓ predictor.train()
   最优模型（15选1）
        ↓ analyzer.analyze()
   根因报告（重要性 + 方向）
        ↓ recommender.recommend()
   Set Point 推荐值
```

### 时序模式（PLC 每秒数据）

```
PLC 1秒数据 DataFrame
        ↓ trend.WeightTrendMonitor.analyze()（实时并行）
   趋势报告（告警 + OOC 预测）

        ↓ aggregate.from_timeseries()（滞后补偿 + 窗口聚合）
   稳定窗口批次 DataFrame
        ↓ data_loader.from_dataframe()
        ↓ predictor.train()
        ↓ analyzer.analyze()
        ↓ recommender.recommend()
   Set Point 推荐值
```

---

## 五、核心模块（src/core/）

这是项目的**原始框架**，用于注塑成型工艺，目前与填充模块独立。

| 文件 | 说明 |
|------|------|
| `bayesian_optimizer.py` | 通用贝叶斯优化器（GP + EI + 多目标），适用于实验次数少、参数空间大的场景 |
| `injection_molding.py` | 注塑机数字仿真器（30+ 参数，含质量/周期时间/能耗预测） |

> **注意：** `bayesian_optimizer.py` 中的 GP 预测部分使用了简化的距离加权插值，而非真正的 Gaussian Process，仅作框架参考。

---

## 六、快速开始

```powershell
# 环境安装（仅需一次）
conda activate venv
pip install -e .

# 批次模式演示（4步流程）
python scripts/demo_filling.py

# 时序模式演示（6步流程）
python scripts/demo_filling.py timeseries

# 运行全套测试
python -m pytest tests/filling/ -v
# 预期结果：58 项，全部通过
```

---

## 七、接入真实数据

### 批次数据（推荐：每批次一行）

```python
df = data_loader.from_csv("你的数据文件.csv", item_cd="285104")
# CSV 必须包含：item_cd, fill_time_s, fill_pressure_bar,
#               product_temp_c, nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

### 时序数据（每秒一行）

```python
from src.filling import aggregate, data_loader
from src.filling.trend import WeightTrendMonitor

# 实时监控
monitor = WeightTrendMonitor(product, window_seconds=300)
report = monitor.analyze(ts_df)

# 聚合为批次后训练
batches = aggregate.from_timeseries(
    ts_df, item_cd="285104",
    lag_seconds=2,           # 按实际设备测定
    min_stable_seconds=30,
)
df = data_loader.from_dataframe(batches, item_cd="285104")
predictor.train(df, product)
```

---

## 八、模型重训建议

| 情况 | 建议 |
|------|------|
| 同班内物性缓慢变化 | 每 1–2 小时，用最新 50–100 批数据重训 |
| 每天换原料批次 | 每天开机前，用前一天数据重训 |
| 原料突然换批 | 丢弃旧数据，从新批次重新积累 ≥ 100 条再训练 |
| 粘度有仪器实测 | 将粘度值加入 PARAM_NAMES，精度可大幅提升 |

---

## 九、测试覆盖（58 项）

| 文件 | 测试数 | 覆盖范围 |
|------|-------|---------|
| test_config.py | 6 | LCL=目标值约束、参数边界有效性、16个产品存在 |
| test_data_loader.py | 6 | 列校验、清洗逻辑、空数据/单行边界用例 |
| test_predictor.py | 6 | CV R²≥0.80、nominal 参数预测、缺参数 ValueError |
| test_recommender.py | 5 | 在规格内输出、最大变化约束、改善量非负 |
| test_analyzer.py | 7 | 重要性总和100%、方向有效性、ok+low+high总和100% |
| test_aggregate.py | 11 | 聚合输出、滞后补偿、短窗口过滤、data_loader 兼容性 |
| test_trend.py | 17 | CRITICAL/WARNING告警、斜率方向、OOC预测、边界用例 |

---

## 十、已知局限与待办

| 项目 | 状态 | 说明 |
|------|------|------|
| 参数名称与实际设备对应 | ⚠️ 待完善 | 当前用通用英文名，实际设备参数见 `docs/machine_parameters.txt` |
| 产品配置从 CSV 动态加载 | ⚠️ 待完善 | 目前 16 个产品硬编码在 `config.py` |
| 核心 GP 模型 | ⚠️ 简化版 | `bayesian_optimizer.py` 使用距离加权插值替代真实 GP |
| 预测置信区间 | ❌ 未实现 | 当前只输出点估计，无不确定性范围 |
| Web API | ❌ 未实现 | pyproject.toml 已包含 FastAPI 依赖，接口层尚未开发 |

---

## 十一、依赖概览

```
scikit-learn   — 15 个候选模型 + Pipeline + 交叉验证
scipy          — L-BFGS-B 约束优化 + linregress 趋势分析
numpy / pandas — 数值计算与数据处理
fastapi        — （预留）REST API 接口
torch          — （预留）深度学习扩展
plotly         — （预留）可视化
```

---

*更新时间：2026-07-03*
