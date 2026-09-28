# B 산출물 검증 기록

2026-09-28 기준. 이 기록은 코드·명세 검증이며 KNHANES 실데이터 학습 완료 보고가 아니다.

| 검사 | 결과 |
|---|---|
| Python 3.13 계약 단위 테스트 | 9개 통과 |
| 저장소 전체 Ruff lint | 통과 |
| 저장소 전체 Ruff format | 전체 파일 통과 |
| API 명세 JSON 예시 | 7개 파싱 통과 |
| 합성자료 실행 | 360개 가상 행, 4가지 입력 조합 × 두 질환 × seed 42 통과 |
| 최종 평가 옵션 실행 | sitting 선택 시 두 질환의 2024 역할 테스트 경로 통과 |
| 누락·비유효 y 제외 | 질환별 3행 제외 확인; 음성 변환 없음 |
| test 사용 제한 | 기본 실행에서는 test 미평가, final-variant 선택 시에만 평가 |
| SHAP | 확률 공간 가산성, one-hot→factor signed 합산, 전역 중요도 합 1 확인 |
| HP 입력 | 스파이크 제외, 소디는 고혈압만, 좌식 분리, scale 누락 시 미산출 |
| 원본 API 시트 대조 | success/data 또는 success/error, 검증 422, PRED 오류 명명, X-Request-Id 응답 헤더, 내부 함수 배열 반환 반영 |

단위 테스트 명령은 저장소 루트에서 실행한다.

```bash
python -m unittest discover -s tests/model_contract -v
ruff check .
ruff format --check .
```

합성자료와 그 성능 수치는 코드 실행 확인에만 사용했다. 실제 참가자 자료, 실제 AUROC, 실제 HP calibration, 배포 모델은 이 산출물에 포함하지 않는다. 합성 결과를 실데이터 실험 결과로 인용하지 않는다.

실제 1회전 전에 연도별 공식 코드북의 라벨 코드·특수코드·단위를 확인하고 canonical CSV를 준비해야 한다. 현재 y 매핑은 팀 기획서 v9의 정의를 구현한 것이며 공식 코드북 대조 완료를 뜻하지 않는다. 전체 FastAPI/DB 통합 테스트와 예측 라우트 구현은 이번 계약·오프라인 실험 코드 검증 범위 밖이다.
