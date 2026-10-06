import importlib.util

# 학습 전처리 테스트는 앱 의존성에 없는 pandas·pyreadstat 가 필요하다.
# CI 는 uv run --with 로 unittest 를 따로 돌리고(.github/workflows/checks.yml), unittest 는 이 파일을 읽지 않는다.
# 로컬 uv run pytest 에서 의존성이 없을 때만 그 파일을 수집에서 뺀다.
collect_ignore = [] if importlib.util.find_spec("pandas") else ["test_knhanes_preprocess.py"]
