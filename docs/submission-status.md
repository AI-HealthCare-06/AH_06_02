# 홍서윤 B 제출 상태

## 준비한 내용

| 항목 | 산출물 | 상태 |
|---|---|---|
| API 3개 | api-predictions.md | 지정 시트 양식 대조·작성본 준비 완료, 온라인 반영 대기 |
| X/y와 누수 이유 | model.md | 계약 작성·raw 단위 및 코드북 검증 대기 |
| 진단자 source_prediction_id | model.md 1절 | NULL 확인 완료(ERD SQL 근거) |
| 좌식 독립 여부 | model.md 1절 | 독립 factor 확정 반영 |
| 모델 1회전 | experiment.md + run_baseline.py | 실제 데이터 미확보로 실행 대기 |
| B→D, global importance | model.md 7절 | 최신 명칭·버전 계약 반영 |
| 코드 검증 | verification.md | 단위 테스트 9개·린트·합성 실행 통과 |

## 확인된 원본

- 기획서 v9 PDF, 요구사항 v8 XLSX, 9/24 첨부 ERD_2.sql, factor_key v0, B 연결 확인 요청, D Mapping Table v0.
- 9/28 13:38 API/HP 스레드와 13:44까지 ERD·mapping 답변.
- 사용자가 지정한 API명세서_v1-1의 공통 규칙·쓰기 권한·모듈 간 호출 및 B 탭을 직접 읽었다. 응답 형식·오류 명명·추적 헤더와 내부 함수의 배열 반환 계약을 대조해 수정했다.
- GitHub main c0caba5와 develop a09552e. 저장소는 회원·인증 템플릿과 빈 ai_worker이며 학습자료·모델·예측 ORM/API는 없다.
- 최신 ERD는 스레드에서 185컬럼으로 변경됐다고 확인했다. 실제 확보한 SQL은 이전 첨부본이므로 최신 전체 SQL을 확보한 것으로 표시하지 않는다. 새 hp_source/last_health_record_id 등은 스레드 변경사항으로 반영했다.

## 아직 완료가 아닌 것

1. HN22/23/24 원시자료와 공식 변수설명서가 필요하다. 성능·SHAP 안정성·HP scale·global importance를 실제 계산해야 한다.
2. 제출 대상은 사용자가 새로 지정한 API명세서_v1-1이다. Google 로그인 후 원본 양식은 읽었으나 파일이 소유자의 휴지통에 있어 온라인 편집은 진행하지 않았다. B 탭 6~8행에 들어갈 작성본은 준비했다. 원본 복원 또는 사용자가 선택한 사본으로 반영해야 한다.
3. Notion 결정/SHARE DOCUMENTS 페이지는 연결 계정에서 404다. 링크 등록과 완료 체크를 하지 않았다. 완료 체크는 공지대로 본인이 한다.
4. Slack 전송은 아직 하지 않았다. 아래 메시지는 실제 완료 범위를 반영한 초안이다.

## 팀에 보낼 답변 초안

최신 API/ERD 의견 확인했습니다. B는 예측+기여도 저장 커밋 후 `refresh_hp_from_prediction(user_id, prediction_id)`를 호출하고, `get_top_contributions()`와 모델 버전이 포함된 `get_global_importance()`를 제공하는 계약으로 문서를 맞췄습니다. `user_monsters`는 직접 수정하지 않습니다.

진단자는 예측을 만들지 않으므로 `user_challenges.source_prediction_id=NULL`이 맞고, global importance+생활패턴 경로로 분리하겠습니다. `sedentary_time_high`는 독립 factor/비세라 연결을 유지합니다. 실제 sitting_minutes 채택과 SHAP 안정성, 채소 후보·소디 안정성은 원시자료 1회전 결과로 별도 공유하겠습니다. 아직 실험 완료 수치는 없습니다.

API 3개의 요청·응답·예외는 지정 API명세서_v1-1의 공통 규칙과 대조했고 B 탭 작성본을 준비했습니다. 온라인 시트 반영 및 model.md 링크 등록은 접근 가능한 원본에서 마무리해야 합니다. 확정이 필요한 부분은 HP 고정 스케일 세부 방식과 global factor_score의 0~100 변환, 등급 경계값입니다.
