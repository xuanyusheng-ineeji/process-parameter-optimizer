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

# 3. 배치 모드 데모 (합성 데이터, 품목 285104 — 300g 크림)
python scripts/demo_filling.py

# 4. 시계열 파이프라인 데모 (1시간 생산 시뮬레이션, 드리프트 포함)
python scripts/demo_filling.py timeseries

# 5. 테스트 실행
python -m pytest tests/filling/ -v
# 예상: 58개 전체 통과
```

---

## 데모 출력 (배치 모드)

```
============================================================
FILLING PROCESS OPTIMIZER — BK)연유크림F 300g
Target: 300g  LCL: 300g  UCL: 330.0g
============================================================

[2/4] 충전 중량 예측 모델 학습 중...
──────────────────────────────────────────────────────────────
Model                     CV R²      ±  Train σ (g)
──────────────────────────────────────────────────────────────
★ HuberRegressor          0.996  0.001       1.05g ◀
  LinearRegression        0.996  0.001       1.05g
  GradientBoosting        0.950  0.037       0.55g
  ...
──────────────────────────────────────────────────────────────
Selected: HuberRegressor  |  n=300 batches

[3/4] 근본 원인 분석...
  fill_time_s         59.2%  ███████████  ↑ 증가 → 중량 증가
  fill_pressure_bar   19.2%  ███          ↑ 증가 → 중량 증가
  nozzle_opening_pct   9.6%  █            ↑ 증가 → 중량 증가

[4/4] 설정값 추천...
  파라미터                  현재값    추천값    변화량
  fill_time_s               1.750     1.832   +0.082
  fill_pressure_bar         1.700     1.717   +0.017
  ...
  예측 충전 중량: 300.0g  |  상태: OK ✓
```

---

## 모듈 참조

### config.py — 품목 및 파라미터 범위

```python
from src.filling.config import PRODUCTS, get_param_bounds

product = PRODUCTS["285104"]   # BK)연유크림F 300g
print(product.target_g)        # 300.0
print(product.lcl_g)           # 300.0 (항상 목표값과 동일 — 식품법 규정)
print(product.ucl_g)           # 330.0

bounds = get_param_bounds(product)
# {'fill_time_s': (1.2, 2.5), 'fill_pressure_bar': (1.2, 2.5), ...}
```

**16개 품목**이 두 가지 크기 등급으로 구성:

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

> **참고:** 현재 파라미터 명칭은 임시 명칭입니다. 실제 설비 파라미터는 `docs/machine_parameters.txt`를 참조하며, 실제 데이터 수집 후 교체해야 합니다.

---

### data_loader.py — 과거 데이터 로드

```python
from src.filling import data_loader

df = data_loader.from_csv("production_history.csv", item_cd="285104")
df = data_loader.from_excel("production.xlsx", sheet="Sheet1", item_cd="285104")
df = data_loader.from_dataframe(raw_df, item_cd="285104")
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
result = predictor.train(df, product)
predictor.print_summary()

weight = predictor.predict({
    "fill_time_s": 1.80, "fill_pressure_bar": 1.75,
    "product_temp_c": 18.0, "nozzle_opening_pct": 70.0, "line_speed_bpm": 40.0,
})  # → float 반환 (그램)

importances = predictor.feature_importances()
# {'fill_time_s': 0.59, 'fill_pressure_bar': 0.19, ...}
```

**후보 모델 (15개):**

| 유형 | 모델 |
|------|------|
| 선형 | LinearRegression, Ridge, Lasso, ElasticNet, HuberRegressor, BayesianRidge |
| 커널 | SVR_RBF, SVR_Poly |
| 인스턴스 기반 | KNeighbors_5, KNeighbors_10 |
| 트리 / 앙상블 | DecisionTree, ExtraTrees, RandomForest |
| 부스팅 | GradientBoosting, HistGradientBoosting |

선택 기준: 5-폴드 교차검증 R² 최고값. 식품 충전 환경에서는 선형 모델이 주로 선택되며, 실제 데이터에서는 트리 모델이 우수할 수 있습니다.

---

### analyzer.py — 근본 원인 분석

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

방향 판단: 각 파라미터에 ±5% 섭동을 가하여(유효 범위로 자동 클리핑) 예측 중량 변화 방향을 확인합니다.

---

### recommender.py — 설정값 최적화 추천

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

**최적화 목적 함수:**
```
최소화  (예측 중량 − 목표 중량)²
      + 변화 패널티 (중요도가 낮은 파라미터일수록 가중치 증가)
      + 1000 × max(0, LCL − 예측 중량)   ← 경질 제약
      + 500  × max(0, 예측 중량 − UCL)    ← 연질 제약
```

각 파라미터 변화량은 운용 범위의 `max_change_pct`(기본값 15%) 이내로 제한됩니다. L-BFGS-B + 10개 무작위 다중 시작점 사용.

---

### synthetic_data.py — 합성 데이터 생성

실제 생산 데이터 확보 전 개발 및 테스트용으로 사용합니다. 두 가지 모드를 제공합니다:

```python
from src.filling import synthetic_data

# 배치 모드: 파라미터 설정당 1행
df = synthetic_data.generate("285104", n_batches=300, seed=42)
df_all = synthetic_data.generate_all(n_batches=200)

# 시계열 모드: 초당 1행 (전체 교대 시뮬레이션)
ts_df = synthetic_data.generate_timeseries(
    "285104",
    duration_seconds=3600,
    drift_rate_g_per_min=0.8,   # 교대 내 점도 변화 시뮬레이션
    n_param_adjustments=20,
    seed=42,
)
```

중량 시뮬레이션 물리 모델:
```
중량 = 목표중량 × (시간/표준)^0.85 × (압력/표준)^0.30
               × (노즐/표준)^0.20 × (표준속도/속도)^0.10
               × (1 + 0.003 × (온도 − 표준온도))
     + 노이즈 + 드리프트
```

---

### aggregate.py — 시계열 집계 (신규)

1초 단위 PLC/검중기 원시 데이터를 안정된 파라미터 윈도우(배치 행)로 집계합니다.

```python
from src.filling import aggregate

batches = aggregate.from_timeseries(
    ts_df,
    item_cd="285104",
    lag_seconds=2,           # PLC→검중기 지연 (설비별 실측값 사용)
    min_stable_seconds=30,   # 짧은 과도 윈도우 제거
)
# 출력 컬럼: PARAM_NAMES (평균), fill_weight_g, weight_std_g,
#            weight_min_g, weight_max_g, n_seconds, window_start, window_end

aggregate.summary(batches)
```

핵심 기능:
- **지연 보상**: 중량 컬럼을 `-lag_seconds` 행 이동하여 해당 중량을 생산한 파라미터와 정렬
- **파라미터 변화 감지**: 파라미터별 허용 오차로 측정 노이즈 필터링
- `lag_seconds < 0`이면 `ValueError`; `min_stable_seconds` 조건을 만족하는 윈도우가 없으면 `ValueError`

---

### trend.py — 실시간 중량 추세 모니터링 (신규)

시계열 중량 데이터를 실시간으로 분석하여 드리프트 추세를 추적하고 OOC 시점을 예측합니다.

```python
from src.filling.trend import WeightTrendMonitor

monitor = WeightTrendMonitor(product, window_seconds=300, ewma_lambda=0.2)
report = monitor.analyze(ts_df)
# report["status"]                → "OK" / "WARNING" / "CRITICAL"
# report["rolling_mean_g"]        → 최근 윈도우 평균
# report["trend_slope_g_per_min"] → 중량 드리프트 속도 (g/분)
# report["seconds_until_ooc"]     → 현재 추세 지속 시 LCL/UCL 도달까지 남은 초
#                                    (기울기 거의 없거나 24h 초과 시 None)
# report["alerts"]                → 경보 메시지 목록

monitor.print_report(report)
```

경보 임계값:
- **CRITICAL**: 롤링 평균 < LCL 또는 > UCL
- **WARNING**: σ > 목표값의 3%, 또는 기울기 > ±1 g/분

---

## 시계열 파이프라인

실제 PLC 데이터가 초당 1행으로 수신될 때의 전체 파이프라인:

```python
# 1. 실시간 추세 모니터링
monitor = WeightTrendMonitor(product, window_seconds=300)
report = monitor.analyze(ts_df)

# 2. 배치 수준 행으로 집계
batches = aggregate.from_timeseries(ts_df, item_cd="285104", lag_seconds=2)

# 3. 표준 학습 파이프라인에 투입
df = data_loader.from_dataframe(batches, item_cd="285104")
predictor.train(df, product)
analyzer.analyze(df)
recommender.recommend(current_params)
```

---

## 실제 생산 데이터 연동

**배치 데이터** (배치당 1행):
```python
df = data_loader.from_csv("production_log.csv", item_cd="285104")
```

**시계열 데이터** (초당 1행):
```python
batches = aggregate.from_timeseries(
    ts_df, item_cd="285104",
    lag_seconds=2,         # 실제 설비 지연에 맞게 조정
    min_stable_seconds=30,
)
df = data_loader.from_dataframe(batches, item_cd="285104")
```

권장 최소 데이터량: 품목당 **배치 100개 이상**, 300개 이상이면 안정성이 향상됩니다.

---

## 재학습 주기 권장

| 상황 | 권장 사항 |
|------|---------|
| 교대 내 점도 서서히 변화 | 1–2시간마다 최근 50–100배치로 재학습 |
| 일별 원료 교체 | 교대 시작 시 전날 데이터로 재학습 |
| 원료 배치 급격 교체 | 기존 데이터 폐기; 신규 배치 100개 이상 수집 후 재학습 |
| 점도 계측 가능 | `PARAM_NAMES`에 추가하면 정확도 대폭 향상 |

---

## 테스트

```powershell
python -m pytest tests/filling/ -v
```

| 테스트 파일 | 테스트 수 | 범위 |
|-----------|---------|------|
| test_config.py | 6 | 품목 설정, LCL=목표값 불변, 파라미터 범위 |
| test_data_loader.py | 6 | 로드, 정제, 경계 케이스 |
| test_predictor.py | 6 | CV R²≥0.80, 예측값, 오류 처리 |
| test_recommender.py | 5 | 규격 내 출력, 최대 변화 제약 |
| test_analyzer.py | 7 | 중요도 합계, 방향 유효성 |
| test_aggregate.py | 11 | 윈도우 집계, 지연 보상, 단기 윈도우 필터, loader 호환성 |
| test_trend.py | 17 | CRITICAL/WARNING 경보, 기울기, OOC 예측, 경계 케이스 |
| **합계** | **58** | |

---

## 새 품목 추가

1. `src/filling/config.py`의 `PRODUCTS`에 `ProductConfig` 항목 추가:
   ```python
   "999999": ProductConfig("999999", "신규 품목 500g", 500, 500, 520.0, dict(_NOMINAL_SMALL)),
   ```
2. `tests/filling/test_config.py`의 `TARGET_ITEM_CDS`에 품목 코드 추가.
3. 검증: `python -m pytest tests/filling/test_config.py -v`

---

## 알려진 한계

| 항목 | 상태 |
|------|------|
| 파라미터 명칭 | 임시 명칭; 실제 데이터 확보 후 설비 파라미터와 매핑 필요 |
| 품목 설정 소스 | 16개 품목 하드코딩; CSV 자동 로드 미구현 |
| 예측 신뢰 구간 | 점 추정만 제공; 불확실성 범위 없음 |
| Web API | FastAPI 의존성 포함, 인터페이스 레이어 미구현 |

---

## 프로젝트 구조

```
src/filling/       충전 최적화 핵심 모듈 (8개 파일)
src/core/          범용 베이즈 최적화기 (사출 성형 프로젝트 기원)
scripts/           실행 가능한 데모 스크립트 (배치 + 시계열)
tests/filling/     단위 테스트 58개, 7개 파일
data/raw/          원시 품목 마스터 데이터 (CSV)
docs/              설비 파라미터 참조 문서, 품목 목록
```

모듈별 상세 설명은 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)를 참조하세요.

---

## 라이선스

MIT License — LICENSE 파일 참조.
