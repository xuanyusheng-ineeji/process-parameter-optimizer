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

结果：报废、返工，以及少装产品带来的法律风险。

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

# 3. 运行端到端演示（合成数据，产品 285104 — 300g 奶油）
python scripts/demo_filling.py

# 4. 运行测试
python -m pytest tests/filling/ -v
```

预期测试结果：**30 项全部通过**

---

## 演示输出

```
============================================================
填充工艺优化系统 — BK)연유크림F 300g
目标: 300g  LCL: 300g  UCL: 330.0g
============================================================

[2/4] 训练填充重量预测模型...
──────────────────────────────────────────────────────────────
模型                      CV R²      ±  训练残差σ
──────────────────────────────────────────────────────────────
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  RandomForest            0.903  0.063       2.07g
  SVR_RBF                 0.753  0.124       6.44g
  ...
──────────────────────────────────────────────────────────────
已选择: HuberRegressor  |  批次数=300

[3/4] 根因分析...
  fill_time_s         59.2%  ███████████  ↑ 增大 → 重量增加
  fill_pressure_bar   19.2%  ███          ↑ 增大 → 重量增加
  nozzle_opening_pct   9.6%  █            ↑ 增大 → 重量增加

[4/4] 设定值推荐...
  参数                     当前值    推荐值    变化量
  fill_time_s               1.750     1.832   +0.082  ← 主要调整点
  fill_pressure_bar         1.700     1.717   +0.017
  ...

  预测填充重量: 300.0g  |  状态: OK ✓
```

---

## 模块参考

### config.py — 产品与参数边界

```python
from src.filling.config import PRODUCTS, get_param_bounds, get_size_class

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

# 从 CSV 加载
df = data_loader.from_csv("production_history.csv", item_cd="285104")

# 从 Excel 加载
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")

# 从 DataFrame 加载
df = data_loader.from_dataframe(raw_df, item_cd="285104")

# 打印数据摘要与规格符合情况
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
predictor.train(df, product)          # 训练全部 15 个，自动选优
predictor.print_summary()             # 打印排名对比表

weight = predictor.predict({
    "fill_time_s": 1.80,
    "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0,
    "nozzle_opening_pct": 70.0,
    "line_speed_bpm": 40.0,
})  # → 返回 float（克）

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**候选模型：**

| 类别 | 模型 |
|------|------|
| 线性 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 核函数 | SVR (RBF), SVR (多项式) |
| 实例 | KNeighbors (k=5), KNeighbors (k=10) |
| 树 / 森林 | DecisionTree, ExtraTrees, RandomForest |
| 集成提升 | GradientBoosting, HistGradientBoosting |

选优规则：5 折交叉验证 R² 最高者当选。食品填充场景下线性模型通常胜出（重量对参数变化近似线性）；真实数据中树类模型可能因非线性物料交互而反超。

---

### analyzer.py — 根因分析

```python
from src.filling.analyzer import RootCauseAnalyzer

analyzer = RootCauseAnalyzer(predictor, product)

result = analyzer.analyze(df)
# result["top_cause"]         → "fill_time_s"
# result["importance"]        → [("fill_time_s", 59.2), ("fill_pressure_bar", 19.2), ...]
# result["direction"]         → {"fill_time_s": "↑ increases weight", ...}
# result["deviation_summary"] → {"mean_weight_g": 298.9, "low_pct": 51.3, ...}

analyzer.print_report(df)   # 格式化控制台输出
```

方向判断：对每个参数施加 ±5% 扰动（自动 clip 到合法边界），观察预测重量变化方向。

---

### recommender.py — 设定值优化推荐

```python
from src.filling.recommender import SetPointRecommender

recommender = SetPointRecommender(predictor, product)

current_params = {
    "fill_time_s":        1.75,
    "fill_pressure_bar":  1.70,
    "product_temp_c":     22.0,
    "nozzle_opening_pct": 68.0,
    "line_speed_bpm":     42.0,
}

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

每个参数的变化量不超过其操作范围的 `max_change_pct`（默认 15%）。采用 L-BFGS-B + 10 个随机多起点以避免局部最优。

---

### synthetic_data.py — 合成数据生成

在真实生产数据到位之前，用于开发和测试。

```python
from src.filling import synthetic_data

# 单个产品，300 批次
df = synthetic_data.generate("285104", n_batches=300, seed=42)

# 全部 16 个产品合并
df_all = synthetic_data.generate_all(n_batches=200, seed=42)
```

重量模拟物理模型：
```
重量 = 目标重量 × (时间/标称)^0.85 × (压力/标称)^0.30
               × (喷嘴/标称)^0.20 × (标称速度/速度)^0.10
               × (1 + 0.003 × (温度 − 标称温度))
     + 噪声（小包装 ±0.3%，大包装 ±0.15%）
```

---

## 接入真实生产数据

在 `scripts/demo_filling.py` 中替换数据来源：

```python
# 替换前（合成数据）：
raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
df = data_loader.from_dataframe(raw_df, item_cd=item_cd)

# 替换后（真实 CSV）：
df = data_loader.from_csv("path/to/production_log.csv", item_cd=item_cd)
```

建议最小数据量：每个产品 **≥ 100 批次**，300 批次以上效果更稳定。

---

## 优化实施步骤

1. **采集基线数据** — 正常生产 1–2 班，记录所有参数与实测重量。

2. **训练模型** — `predictor.train(df, product)` 自动选出最优模型。

3. **识别根因** — `analyzer.analyze(df)` 排出参数影响度，并给出调整方向。

4. **生成推荐** — `recommender.recommend(current_params)` 计算最小参数调整量。

5. **执行与验证** — 工程师将推荐值输入 HMI，运行下一批次，测量实际重量，必要时重复。

6. **定期重训** — 物理性质（粘度、温度）随时间漂移，建议重训频率：
   - 物性变化快的产品：每班（8 小时）重训一次
   - 稳定产品：每天重训，用前一天数据
   - 换批原料：丢弃旧数据，用新批次积累 ≥ 100 条后重训

---

## 核心模块（通用贝叶斯优化器）

`src/core/` 保留了原注塑项目的通用贝叶斯优化器，适用于实验次数少、测量成本高的场景。

```python
from src.core.bayesian_optimizer import BayesianOptimizer, ParameterSpace, ExperimentResult

optimizer = BayesianOptimizer(
    parameter_space=params_space,
    objective_weights={'quality': 0.5, 'cycle_time': 0.3, 'energy': 0.2}
)

for iteration in range(20):
    params = optimizer.suggest_next_parameters()[0]   # EI 采集函数
    result = ExperimentResult(parameters=params, quality_score=..., ...)
    optimizer.update(result)

optimal = optimizer.get_optimal_parameters()
```

采用期望改进（EI）采集函数：
```
EI(x) = (μ(x) − f_best) × Φ(Z) + σ(x) × φ(Z)，其中 Z = (μ(x) − f_best) / σ(x)
```

> **注意：** 当前 GP 预测使用距离加权插值作为简化替代，不确定性估计为近似值。

---

## 添加新产品

1. 在 `src/filling/config.py` 的 `PRODUCTS` 中添加 `ProductConfig`：
   ```python
   "999999": ProductConfig(
       item_cd="999999",
       item_nm="新产品 500g",
       target_g=500,
       lcl_g=500,       # 必须等于 target_g
       ucl_g=520.0,
       nominal_params=dict(_NOMINAL_SMALL),
   ),
   ```

2. 在 `tests/filling/test_config.py` 的 `TARGET_ITEM_CDS` 中添加编码。

3. 验证：`python -m pytest tests/filling/test_config.py -v`

---

## 测试

```powershell
# 运行全部填充模块测试
python -m pytest tests/filling/ -v

# 运行单个测试文件
python -m pytest tests/filling/test_predictor.py -v
```

| 测试文件 | 测试数 | 覆盖范围 |
|---------|-------|---------|
| test_config.py | 6 | 产品配置、LCL=目标值约束、参数边界 |
| test_data_loader.py | 6 | 加载、清洗、边界用例 |
| test_predictor.py | 6 | CV R²≥0.80、预测值、错误处理 |
| test_recommender.py | 6 | 在规格内输出、最大变化约束 |
| test_analyzer.py | 7 | 重要性总和、方向有效性 |
| **合计** | **30** | |

---

## 已知局限

| 方面 | 状态 |
|------|------|
| 参数名称 | 占位符名称，待真实数据到位后与实际设备参数对应 |
| 产品配置来源 | 16 个产品硬编码，未从 CSV 动态加载 |
| 物性漂移 | 无时序建模，通过定期重训来应对 |
| 预测置信区间 | 仅点估计，无不确定性范围 |
| Web API | 已含 FastAPI 依赖，接口层尚未实现 |

---

## 项目结构

```
src/filling/       填充工艺优化核心模块
src/core/          通用贝叶斯优化器（原注塑项目）
scripts/           可运行的演示脚本
tests/filling/     30 个单元测试
data/raw/          原始产品主数据（CSV）
docs/              设备参数参考文档、产品清单
```

详细的模块说明见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)。

---

## 许可证

MIT License — 详见 LICENSE 文件。
