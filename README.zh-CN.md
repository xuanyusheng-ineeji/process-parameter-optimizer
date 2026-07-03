# 工艺参数优化系统

**语言 / Language / 언어:** [中文](README.zh-CN.md) · [English](README.md) · [한국어](README.ko.md)

---

**面向食品工厂填充产线的 AI 辅助设定值推荐系统**

分析历史生产数据，识别填充重量偏差的根本原因，并推荐设备参数调整值——全程不接触 PLC。

---

## 痛点

食品填充产线同时运行 5 个以上相互关联的参数。重量偏差时，工程师面临：

- **少装违法风险** — 每克低于目标值均构成违规
- **手工试凑** — 逐个参数调整，产线边跑边改
- **经验依赖** — 最佳参数设置存在少数人的脑子里
- **反馈滞后** — 发现问题时，可能已产出数小时不合格品

## 解决方案

本系统将历史批次数据转化为可执行的设定值推荐：

```
历史数据（参数 + 实测重量）
        ↓
   AI 模型训练
（15 个模型 → 自动选优）
        ↓
   根因分析
（找出影响最大的参数及调整方向）
        ↓
   设定值推荐
（约束优化 — 最小幅度、精准调整）
        ↓
   工程师审核 → 手动输入 PLC/HMI
        ↓
     下一批产品
```

**系统不自动控制 PLC，输出仅为供工程师审核的建议值。**

---

## 快速开始

```powershell
# 1. 激活 conda 环境
conda activate venv

# 2. 安装软件包（克隆后执行一次）
pip install -e .

# 3. 批次模式演示（合成数据，产品 285104 — 300g 奶油）
python scripts/demo_filling.py

# 4. 时序模式演示（1小时生产模拟，含漂移）
python scripts/demo_filling.py timeseries

# 5. 运行测试
python -m pytest tests/filling/ -v
# 预期：58 项全部通过
```

---

## 演示输出（批次模式）

```
============================================================
FILLING PROCESS OPTIMIZER — BK)연유크림F 300g
Target: 300g  LCL: 300g  UCL: 330.0g
============================================================

[2/4] 训练填充重量预测模型...
──────────────────────────────────────────────────────────────
Model                     CV R²      ±  Train σ (g)
──────────────────────────────────────────────────────────────
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  ...
──────────────────────────────────────────────────────────────
Selected: HuberRegressor  |  n=300 batches

[3/4] 根因分析...
  fill_time_s         59.2%  ███████████  ↑ 增大 → 重量增加
  fill_pressure_bar   19.2%  ███          ↑ 增大 → 重量增加
  nozzle_opening_pct   9.6%  █            ↑ 增大 → 重量增加

[4/4] 设定值推荐...
  参数                     当前值    推荐值    变化量
  fill_time_s               1.750     1.832   +0.082
  fill_pressure_bar         1.700     1.717   +0.017
  ...
  预测填充重量: 300.0g  |  状态: OK ✓
```

---

## 模块参考

### config.py — 产品与参数边界

```python
from src.filling.config import PRODUCTS, get_param_bounds

product = PRODUCTS["285104"]   # BK)연유크림F 300g
print(product.target_g)        # 300.0
print(product.lcl_g)           # 300.0（始终等于目标值 — 食品法规）
print(product.ucl_g)           # 330.0

bounds = get_param_bounds(product)
# {'fill_time_s': (1.2, 2.5), 'fill_pressure_bar': (1.2, 2.5), ...}
```

已配置 **16 个产品**，分两个规格等级：

| 规格等级 | 目标重量范围 | 产品编码 |
|---------|------------|---------|
| small（小包装） | 200 – 500 g | 282113, 284023, 284047, 284059, 284535, 284760, 284961, 285101–285104 |
| medium（大包装） | > 500 g（最大 3 kg） | 284235, 284319, 284516, 284573, 374424 |

**5 个设备参数（PARAM_NAMES）：**

| 参数 | 单位 | 小包装范围 | 大包装范围 |
|-----|------|-----------|-----------|
| `fill_time_s` | 秒 | 1.2 – 2.5 | 3.0 – 5.5 |
| `fill_pressure_bar` | bar | 1.2 – 2.5 | 1.8 – 3.2 |
| `product_temp_c` | °C | 8 – 28 | 8 – 28 |
| `nozzle_opening_pct` | % | 50 – 90 | 55 – 95 |
| `line_speed_bpm` | 包/分 | 25 – 55 | 12 – 28 |

> **注意：** 当前参数名称为占位符，真实设备参数（泵 INV 速度、校正输出等）见 `docs/machine_parameters.txt`，获取真实数据后需替换。

---

### data_loader.py — 加载历史数据

```python
from src.filling import data_loader

df = data_loader.from_csv("production_history.csv", item_cd="285104")
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")
df = data_loader.from_dataframe(raw_df, item_cd="285104")
data_loader.summary(df, product)
```

必须包含以下列（列名不区分大小写，自动转小写）：
```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

加载器自动删除含空值、重量为零及传感器异常的行。若清洗后无有效数据，抛出 `ValueError`。

---

### predictor.py — 多模型训练与自动选优

同时训练 15 个候选模型，按最高 CV R² 自动选择最优模型。

```python
from src.filling.predictor import FillWeightPredictor

predictor = FillWeightPredictor()
result = predictor.train(df, product)
predictor.print_summary()

weight = predictor.predict({
    "fill_time_s": 1.80, "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0, "nozzle_opening_pct": 70.0, "line_speed_bpm": 40.0,
})  # → float（克）

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**候选模型（15 个）：**

| 类别 | 模型 |
|------|------|
| 线性 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 核函数 | SVR_RBF, SVR_Poly |
| 实例 | KNeighbors_5, KNeighbors_10 |
| 树 / 森林 | DecisionTree, ExtraTrees, RandomForest |
| 集成提升 | GradientBoosting, HistGradientBoosting |

选优规则：5 折交叉验证 R² 最高者当选。食品填充场景下线性模型通常胜出；真实数据中树类模型可能因非线性物料交互而反超。

---

### analyzer.py — 根因分析

```python
from src.filling.analyzer import RootCauseAnalyzer

analyzer = RootCauseAnalyzer(predictor, product)
result = analyzer.analyze(df)
# result["top_cause"]         → "fill_time_s"
# result["importance"]        → [("fill_time_s", 59.2), ...]
# result["direction"]         → {"fill_time_s": "↑ increases weight", ...}
# result["deviation_summary"] → {"mean_weight_g": 298.9, "low_pct": 51.3, ...}

analyzer.print_report(df)
```

方向判断：对每个参数施加 ±5% 扰动（自动 clip 到合法边界），观察预测重量变化方向。

---

### recommender.py — 设定值优化推荐

```python
from src.filling.recommender import SetPointRecommender

recommender = SetPointRecommender(predictor, product)
rec = recommender.recommend(current_params, max_change_pct=0.15)
# rec["recommended_params"]              → {"fill_time_s": 1.832, ...}
# rec["recommended_predicted_weight_g"]  → 300.0
# rec["weight_improvement_g"]            → 12.1
# rec["in_spec"]                         → "OK ✓"

recommender.print_report(rec)
```

**优化目标：**
```
最小化  (预测重量 − 目标重量)²
      + 变化惩罚（重要性低的参数惩罚权重更高）
      + 1000 × max(0, LCL − 预测重量)   ← 硬约束
      + 500  × max(0, 预测重量 − UCL)    ← 软约束
```

每个参数的变化量不超过其操作范围的 `max_change_pct`（默认 15%）。采用 L-BFGS-B + 10 个随机多起点。

---

### synthetic_data.py — 合成数据生成

在真实生产数据到位之前，用于开发和测试。提供两种模式：

```python
from src.filling import synthetic_data

# 批次模式：每个参数设置一行
df = synthetic_data.generate("285104", n_batches=300, seed=42)
df_all = synthetic_data.generate_all(n_batches=200)

# 时序模式：每秒一行（模拟完整班次）
ts_df = synthetic_data.generate_timeseries(
    "285104",
    duration_seconds=3600,
    drift_rate_g_per_min=0.8,   # 模拟粘度漂移
    n_param_adjustments=20,
    seed=42,
)
```

重量模拟物理模型：
```
重量 = 目标重量 × (时间/标称)^0.85 × (压力/标称)^0.30
               × (喷嘴/标称)^0.20 × (标称速度/速度)^0.10
               × (1 + 0.003 × (温度 − 标称温度))
     + 噪声 + 漂移
```

---

### aggregate.py — 时序聚合（新增）

将每秒一行的原始 PLC/称重数据，聚合为稳定参数窗口（等同于"一个批次"）。

```python
from src.filling import aggregate

batches = aggregate.from_timeseries(
    ts_df,
    item_cd="285104",
    lag_seconds=2,           # PLC→称重传感器延迟（按设备实测）
    min_stable_seconds=30,   # 丢弃短于此值的过渡窗口
)
# 输出列：PARAM_NAMES 均值, fill_weight_g, weight_std_g,
#         weight_min_g, weight_max_g, n_seconds, window_start, window_end

aggregate.summary(batches)
```

核心特性：
- **滞后补偿**：将重量列向前移动 `lag_seconds` 秒，对齐产生该重量的参数
- **参数变化检测**：每个参数有独立容差，过滤测量噪声
- `lag_seconds < 0` 抛出 `ValueError`；无满足 `min_stable_seconds` 的窗口时也抛出 `ValueError`

---

### trend.py — 实时趋势监控（新增）

对时序重量数据进行实时分析，监测漂移趋势并预测何时触碰控制限。

```python
from src.filling.trend import WeightTrendMonitor

monitor = WeightTrendMonitor(product, window_seconds=300, ewma_lambda=0.2)
report = monitor.analyze(ts_df)
# report["status"]                → "OK" / "WARNING" / "CRITICAL"
# report["rolling_mean_g"]        → 最近窗口均值
# report["trend_slope_g_per_min"] → 重量漂移速率（g/分钟）
# report["seconds_until_ooc"]     → 按当前趋势触碰控制限的剩余秒数
#                                    （平坦或超过 24 小时则返回 None）
# report["alerts"]                → 告警信息列表

monitor.print_report(report)
```

告警阈值：
- **CRITICAL**：滚动均值 < LCL 或 > UCL
- **WARNING**：σ > 目标值的 3%，或斜率 > ±1 g/分钟

---

## 时序数据完整流程

当真实 PLC 数据以每秒一行的格式到来时：

```python
# 1. 实时监控趋势
monitor = WeightTrendMonitor(product, window_seconds=300)
report = monitor.analyze(ts_df)

# 2. 聚合为批次行
batches = aggregate.from_timeseries(ts_df, item_cd="285104", lag_seconds=2)

# 3. 送入标准训练流程
df = data_loader.from_dataframe(batches, item_cd="285104")
predictor.train(df, product)
analyzer.analyze(df)
recommender.recommend(current_params)
```

---

## 接入真实生产数据

**批次数据**（每批次一行）：
```python
df = data_loader.from_csv("production_log.csv", item_cd="285104")
```

**时序数据**（每秒一行）：
```python
batches = aggregate.from_timeseries(
    ts_df, item_cd="285104",
    lag_seconds=2,         # 按实际设备测定
    min_stable_seconds=30,
)
df = data_loader.from_dataframe(batches, item_cd="285104")
```

建议最小数据量：每个产品 **≥ 100 批次**，300 批次以上效果更稳定。

---

## 模型重训建议

| 情况 | 建议 |
|------|------|
| 同班内物性缓慢变化 | 每 1–2 小时，用最新 50–100 批数据重训 |
| 每天换原料批次 | 每天开机前，用前一天数据重训 |
| 原料突然换批 | 丢弃旧数据，从新批次积累 ≥ 100 条后重训 |
| 粘度有仪器实测 | 将粘度值加入 `PARAM_NAMES`，精度可大幅提升 |

---

## 测试

```powershell
python -m pytest tests/filling/ -v
```

| 测试文件 | 测试数 | 覆盖范围 |
|---------|-------|---------|
| test_config.py | 6 | 产品配置、LCL=目标值约束、参数边界 |
| test_data_loader.py | 6 | 加载、清洗、边界用例 |
| test_predictor.py | 6 | CV R²≥0.80、预测值、错误处理 |
| test_recommender.py | 5 | 在规格内输出、最大变化约束 |
| test_analyzer.py | 7 | 重要性总和、方向有效性 |
| test_aggregate.py | 11 | 窗口聚合、滞后补偿、短窗口过滤、loader 兼容性 |
| test_trend.py | 17 | CRITICAL/WARNING 告警、斜率、OOC 预测、边界用例 |
| **合计** | **58** | |

---

## 添加新产品

1. 在 `src/filling/config.py` 的 `PRODUCTS` 中添加 `ProductConfig`：
   ```python
   "999999": ProductConfig("999999", "新产品 500g", 500, 500, 520.0, dict(_NOMINAL_SMALL)),
   ```
2. 在 `tests/filling/test_config.py` 的 `TARGET_ITEM_CDS` 中添加编码。
3. 验证：`python -m pytest tests/filling/test_config.py -v`

---

## 已知局限

| 方面 | 状态 |
|------|------|
| 参数名称 | 占位符名称，待真实数据到位后与实际设备参数对应 |
| 产品配置来源 | 16 个产品硬编码，未从 CSV 动态加载 |
| 预测置信区间 | 仅点估计，无不确定性范围 |
| Web API | 已含 FastAPI 依赖，接口层尚未实现 |

---

## 项目结构

```
src/filling/       填充工艺优化核心模块（8 个文件）
src/core/          通用贝叶斯优化器（原注塑项目）
scripts/           演示脚本（批次 + 时序两种模式）
tests/filling/     58 个单元测试，7 个文件
data/raw/          原始产品主数据（CSV）
docs/              设备参数参考文档、产品清单
```

详细模块说明见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)。

---

## 许可证

MIT License — 详见 LICENSE 文件。
