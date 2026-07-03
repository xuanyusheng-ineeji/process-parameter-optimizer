# 공정 파라미터 최적화 시스템

**언어 / Language / 语言:** [한국어](README.ko.md) · [English](README.md) · [中文](README.zh-CN.md)

---

**식품 공장 충전 라인을 위한 AI 기반 설정값 추천 시스템**

과거 생산 데이터를 분석하여 충전 중량 편차의 근본 원인을 파악하고, PLC를 건드리지 않고 설비 파라미터 조정값을 추천합니다.

---

## 문제 상황

식품 충전 라인은 5개 이상의 상호 연관된 파라미터를 동시에 운용합니다. 중량이 규격을 벗어날 때 엔지니어가 직면하는 문제:

- **미달 충전 법적 위반** — 목표값 이하는 1g도 허용되지 않음
- **수동 시행착오** — 파라미터를 하나씩 바꾸며 라인 가동 중 조정
- **경험 의존** — 최적 설정값이 소수 인원의 머릿속에만 존재
- **느린 피드백** — 문제를 인지할 때 이미 수 시간치 불량품 발생

결과: 폐기, 재작업, 미달 충전으로 인한 법적 리스크.

## 해결 방법

본 시스템은 과거 배치 데이터를 실행 가능한 설정값 추천으로 변환합니다:

```
과거 생산 데이터 (파라미터 + 실측 중량)
            ↓
       AI 모델 학습
  (15개 모델 → 자동 최적 선택)
            ↓
       근본 원인 분석
  (영향이 큰 파라미터와 조정 방향 파악)
            ↓
       설정값 추천
  (제약 최적화 — 최소한의 정밀 조정)
            ↓
  엔지니어 검토 → PLC/HMI 수동 입력
            ↓
         다음 생산 배치
```

**본 시스템은 PLC를 자동 제어하지 않습니다. 출력값은 엔지니어 검토용 추천값입니다.**

---

## 빠른 시작

```powershell
# 1. conda 환경 활성화
conda activate venv

# 2. 패키지 설치 (클론 후 1회 실행)
pip install -e .

# 3. 엔드-투-엔드 데모 실행 (합성 데이터, 품목 285104 — 300g 크림)
python scripts/demo_filling.py

# 4. 테스트 실행
python -m pytest tests/filling/ -v
```

예상 테스트 결과: **30개 전체 통과**

---

## 데모 출력

```
============================================================
충전 공정 최적화 시스템 — BK)연유크림F 300g
목표: 300g  LCL: 300g  UCL: 330.0g
============================================================

[2/4] 충전 중량 예측 모델 학습 중...
──────────────────────────────────────────────────────────────
모델                      CV R²      ±  학습 잔차σ
──────────────────────────────────────────────────────────────
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  RandomForest            0.903  0.063       2.07g
  SVR_RBF                 0.753  0.124       6.44g
  ...
──────────────────────────────────────────────────────────────
선택된 모델: HuberRegressor  |  배치 수=300

[3/4] 근본 원인 분석...
  fill_time_s         59.2%  ███████████  ↑ 증가 → 중량 증가
  fill_pressure_bar   19.2%  ███          ↑ 증가 → 중량 증가
  nozzle_opening_pct   9.6%  █            ↑ 증가 → 중량 증가

[4/4] 설정값 추천...
  파라미터                  현재값    추천값    변화량
  fill_time_s               1.750     1.832   +0.082  ← 주요 조정 항목
  fill_pressure_bar         1.700     1.717   +0.017
  ...

  예측 충전 중량: 300.0g  |  상태: OK ✓
```

---

## 모듈 참조

### config.py — 품목 및 파라미터 범위

```python
from src.filling.config import PRODUCTS, get_param_bounds, get_size_class

product = PRODUCTS["285104"]   # BK)연유크림F 300g
print(product.target_g)        # 300.0
print(product.lcl_g)           # 300.0 (항상 목표값과 동일 — 식품법 규정)
print(product.ucl_g)           # 330.0

bounds = get_param_bounds(product)
# {'fill_time_s': (1.2, 2.5), 'fill_pressure_bar': (1.2, 2.5), ...}
```

**16개 품목** 이 두 가지 크기 등급으로 구성:

| 크기 등급 | 목표 중량 범위 | 품목 코드 |
|---------|-------------|---------|
| small (소포장) | 200 – 500 g | 282113, 284023, 284047, 284059, 284535, 284760, 284961, 285101–285104 |
| medium (대포장) | > 500 g (최대 3 kg) | 284235, 284319, 284516, 284573, 374424 |

**5개 설비 파라미터 (PARAM_NAMES):**

| 파라미터 | 단위 | 소포장 범위 | 대포장 범위 |
|---------|------|-----------|-----------|
| `fill_time_s` | 초 | 1.2 – 2.5 | 3.0 – 5.5 |
| `fill_pressure_bar` | bar | 1.2 – 2.5 | 1.8 – 3.2 |
| `product_temp_c` | °C | 8 – 28 | 8 – 28 |
| `nozzle_opening_pct` | % | 50 – 90 | 55 – 95 |
| `line_speed_bpm` | 포장/분 | 25 – 55 | 12 – 28 |

> **참고:** 현재 파라미터 명칭은 임시 명칭입니다. 실제 설비 파라미터(펌퍼 INV 속도, 보정출력 등)는 `docs/machine_parameters.txt`를 참조하며, 실제 데이터 수집 후 교체해야 합니다.

---

### data_loader.py — 과거 데이터 로드

```python
from src.filling import data_loader

# CSV에서 로드
df = data_loader.from_csv("production_history.csv", item_cd="285104")

# Excel에서 로드
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")

# DataFrame에서 로드
df = data_loader.from_dataframe(raw_df, item_cd="285104")

# 데이터 요약 및 규격 적합률 출력
data_loader.summary(df, product)
```

필수 컬럼 (대소문자 무관, 자동 소문자 변환):
```
item_cd, fill_time_s, fill_pressure_bar, product_temp_c,
nozzle_opening_pct, line_speed_bpm, fill_weight_g
```

결측값, 중량 0 이하, 센서 이상값 행을 자동 제거합니다. 정제 후 유효 데이터가 없으면 `ValueError`를 발생시킵니다.

---

### predictor.py — 다중 모델 학습 및 자동 선택

15개 후보 모델을 동시에 학습하고 CV R²가 가장 높은 모델을 자동으로 선택합니다.

```python
from src.filling.predictor import FillWeightPredictor

predictor = FillWeightPredictor()
predictor.train(df, product)          # 15개 전체 학습 후 최적 모델 선택
predictor.print_summary()             # 순위별 비교표 출력

weight = predictor.predict({
    "fill_time_s": 1.80,
    "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0,
    "nozzle_opening_pct": 70.0,
    "line_speed_bpm": 40.0,
})  # → float 반환 (그램)

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**후보 모델:**

| 유형 | 모델 |
|------|------|
| 선형 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 커널 | SVR (RBF), SVR (다항식) |
| 인스턴스 기반 | KNeighbors (k=5), KNeighbors (k=10) |
| 트리 / 앙상블 | DecisionTree, ExtraTrees, RandomForest |
| 부스팅 | GradientBoosting, HistGradientBoosting |

선택 기준: 5-폴드 교차검증 R² 최고값. 식품 충전 환경에서는 선형 모델이 주로 선택됩니다(중량과 파라미터의 관계가 대체로 선형). 실제 데이터에서는 비선형 원료 특성으로 인해 트리 모델이 우수할 수 있습니다.

---

### analyzer.py — 근본 원인 분석

```python
from src.filling.analyzer import RootCauseAnalyzer

analyzer = RootCauseAnalyzer(predictor, product)

result = analyzer.analyze(df)
# result["top_cause"]         → "fill_time_s"
# result["importance"]        → [("fill_time_s", 59.2), ("fill_pressure_bar", 19.2), ...]
# result["direction"]         → {"fill_time_s": "↑ increases weight", ...}
# result["deviation_summary"] → {"mean_weight_g": 298.9, "low_pct": 51.3, ...}

analyzer.print_report(df)   # 형식화된 콘솔 출력
```

방향 판단: 각 파라미터에 ±5% 섭동을 가하여(유효 범위로 자동 클리핑) 예측 중량 변화 방향을 확인합니다.

---

### recommender.py — 설정값 최적화 추천

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

**최적화 목적 함수:**
```
최소화  (예측 중량 − 목표 중량)²
      + 변화 패널티 (중요도가 낮은 파라미터일수록 가중치 증가)
      + 1000 × max(0, LCL − 예측 중량)   ← 경질 제약
      + 500  × max(0, 예측 중량 − UCL)    ← 연질 제약
```

각 파라미터 변화량은 운용 범위의 `max_change_pct`(기본값 15%) 이내로 제한됩니다. 국소 최적해 방지를 위해 L-BFGS-B + 10개 무작위 다중 시작점을 사용합니다.

---

### synthetic_data.py — 합성 데이터 생성

실제 생산 데이터 확보 전 개발 및 테스트용으로 사용합니다.

```python
from src.filling import synthetic_data

# 단일 품목, 300 배치
df = synthetic_data.generate("285104", n_batches=300, seed=42)

# 16개 품목 전체 통합
df_all = synthetic_data.generate_all(n_batches=200, seed=42)
```

중량 시뮬레이션 물리 모델:
```
중량 = 목표중량 × (시간/표준)^0.85 × (압력/표준)^0.30
               × (노즐/표준)^0.20 × (표준속도/속도)^0.10
               × (1 + 0.003 × (온도 − 표준온도))
     + 노이즈 (소포장 ±0.3%, 대포장 ±0.15%)
```

---

## 실제 생산 데이터 연동

`scripts/demo_filling.py`에서 데이터 소스를 교체합니다:

```python
# 변경 전 (합성 데이터):
raw_df = synthetic_data.generate(item_cd, n_batches=300, seed=42)
df = data_loader.from_dataframe(raw_df, item_cd=item_cd)

# 변경 후 (실제 CSV):
df = data_loader.from_csv("path/to/production_log.csv", item_cd=item_cd)
```

권장 최소 데이터량: 품목당 **배치 100개 이상**, 300개 이상이면 모델 안정성이 향상됩니다.

---

## 최적화 실행 절차

1. **기준 데이터 수집** — 1~2교대 정상 생산 중 모든 파라미터와 실측 중량을 기록합니다.

2. **모델 학습** — `predictor.train(df, product)`으로 최적 모델을 자동 선택합니다.

3. **근본 원인 파악** — `analyzer.analyze(df)`로 파라미터 영향도를 순위화하고 조정 방향을 확인합니다.

4. **추천값 생성** — `recommender.recommend(current_params)`으로 최소 파라미터 조정량을 산출합니다.

5. **적용 및 검증** — 엔지니어가 추천값을 HMI에 입력하고, 다음 배치를 생산하여 실측 중량을 확인합니다. 필요 시 반복합니다.

6. **정기 재학습** — 점도·온도 등 물성이 시간에 따라 변화하므로 재학습 주기 권장:
   - 물성 변화가 빠른 품목: 교대(8시간)마다 재학습
   - 안정적인 품목: 전날 데이터로 매일 재학습
   - 원료 배치 교체 시: 기존 데이터 폐기, 신규 배치 100개 이상 수집 후 재학습

---

## 핵심 모듈 (범용 베이즈 최적화기)

`src/core/`는 원래 사출 성형 프로젝트용으로 개발된 범용 베이즈 최적화기로, 실험 횟수가 적고 측정 비용이 높은 상황에 활용할 수 있습니다.

```python
from src.core.bayesian_optimizer import BayesianOptimizer, ParameterSpace, ExperimentResult

optimizer = BayesianOptimizer(
    parameter_space=params_space,
    objective_weights={'quality': 0.5, 'cycle_time': 0.3, 'energy': 0.2}
)

for iteration in range(20):
    params = optimizer.suggest_next_parameters()[0]   # EI 획득 함수
    result = ExperimentResult(parameters=params, quality_score=..., ...)
    optimizer.update(result)

optimal = optimizer.get_optimal_parameters()
```

기대 향상값(EI) 획득 함수 사용:
```
EI(x) = (μ(x) − f_best) × Φ(Z) + σ(x) × φ(Z),  여기서 Z = (μ(x) − f_best) / σ(x)
```

> **참고:** 현재 GP 예측은 역거리 가중 보간을 간소화 대체제로 사용하며, 불확실성 추정은 근사값입니다.

---

## 새 품목 추가

1. `src/filling/config.py`의 `PRODUCTS`에 `ProductConfig` 항목 추가:
   ```python
   "999999": ProductConfig(
       item_cd="999999",
       item_nm="신규 품목 500g",
       target_g=500,
       lcl_g=500,       # 반드시 target_g와 동일해야 함
       ucl_g=520.0,
       nominal_params=dict(_NOMINAL_SMALL),
   ),
   ```

2. `tests/filling/test_config.py`의 `TARGET_ITEM_CDS`에 품목 코드 추가.

3. 검증: `python -m pytest tests/filling/test_config.py -v`

---

## 테스트

```powershell
# 충전 모듈 전체 테스트 실행
python -m pytest tests/filling/ -v

# 단일 테스트 파일 실행
python -m pytest tests/filling/test_predictor.py -v
```

| 테스트 파일 | 테스트 수 | 범위 |
|-----------|---------|------|
| test_config.py | 6 | 품목 설정, LCL=목표값 불변, 파라미터 범위 |
| test_data_loader.py | 6 | 로드, 정제, 경계 케이스 |
| test_predictor.py | 6 | CV R²≥0.80, 예측값, 오류 처리 |
| test_recommender.py | 6 | 규격 내 출력, 최대 변화 제약 |
| test_analyzer.py | 7 | 중요도 합계, 방향 유효성 |
| **합계** | **30** | |

---

## 알려진 한계

| 항목 | 상태 |
|------|------|
| 파라미터 명칭 | 임시 명칭; 실제 데이터 확보 후 설비 파라미터와 매핑 필요 |
| 품목 설정 소스 | 16개 품목 하드코딩; CSV 자동 로드 미구현 |
| 물성 드리프트 | 시계열 모델링 미구현; 정기 재학습으로 대응 |
| 예측 신뢰 구간 | 점 추정만 제공; 불확실성 범위 없음 |
| Web API | FastAPI 의존성 포함, 인터페이스 레이어 미구현 |

---

## 프로젝트 구조

```
src/filling/       충전 최적화 핵심 모듈
src/core/          범용 베이즈 최적화기 (사출 성형 프로젝트 기원)
scripts/           실행 가능한 데모 스크립트
tests/filling/     단위 테스트 30개
data/raw/          원시 품목 마스터 데이터 (CSV)
docs/              설비 파라미터 참조 문서, 품목 목록
```

모듈별 상세 설명은 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)를 참조하세요.

---

## 라이선스

MIT License — LICENSE 파일 참조.
