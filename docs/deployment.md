# 배포

운영 주소: http://13.125.130.94

## 자동 배포

평소 배포는 자동입니다. 서버에서 도는 코드(`app/` · `ai_worker/` · `frontend/` · `scripts/` · 의존성 · 마스터 CSV)가 바뀐 PR이 main에 머지되면 GitHub Actions(`.github/workflows/deploy.yml`)가 앱·워커 이미지를 `v1.1.N`(N은 실행 번호)으로 빌드해 올리고, 서버에서 마이그레이션 → 재시작 → 상태 확인 → 시드까지 진행합니다. 상태 확인에 실패하면 이전 버전으로 되돌립니다. 머지부터 반영까지 5\~10분 걸립니다.

- 문서만 바뀐 머지는 배포하지 않습니다.
- 다시 배포하려면 Actions 탭 → deploy → Run workflow에서 main을 고릅니다.
- 진행 상황은 Actions 탭의 deploy에서, 서버 기록은 `~/deploy.log`에서 봅니다.
- 서버 쪽 스크립트는 `infra/deploy/server-deploy.sh`입니다. 서버에는 `/home/ubuntu/deploy.sh`로 직접 설치돼 있어서, 이 파일을 고치면 서버 사본도 같이 바꿔야 합니다.
- 배포 직후 사이트가 502를 내면 서버에서 `docker exec nginx nginx -s reload`로 복구합니다. 앱 컨테이너 주소가 바뀌었는데 nginx가 옛 주소를 쓰는 경우입니다. 지금 서버 스크립트는 재시작 뒤 이 처리를 자동으로 합니다.
- `docker-compose.prod.yml`, nginx 설정, `.prod.env`, 모델 파일은 자동 배포 대상이 아닙니다. 바뀔 때만 아래 수동 절차를 씁니다.

## 배포 후 확인과 되돌리기

자동 배포의 상태 확인(`healthy`)은 nginx 80번으로 API·프론트 응답과 AI 워커 대기 로그를 봅니다. 실패하면 직전 버전으로 자동으로 되돌립니다. 그 밖에 손으로 볼 때는 서버의 `~/project`에서 아래를 씁니다.

```bash
tail -n 30 ~/deploy.log                      # 배포 기록. "배포 완료" 또는 "배포 실패, ... 로 되돌립니다"
grep -E '^(APP|AI_WORKER)_VERSION=' .env     # 지금 도는 이미지 버전
docker compose ps                            # fastapi · ai-worker · nginx 가 Up 인지
docker logs --tail 100 fastapi               # 시작 경고·오류
curl -fsS "http://127.0.0.1/api/v1/auth/check-email?email=deploy-check@dangokiller.com"
```

자동 롤백이 지나간 뒤 문제가 보이면, `~/deploy.log`에서 직전 버전을 찾아 되돌립니다. 마이그레이션은 되돌리지 않으므로 컬럼을 지우는 변경이 있었다면 먼저 팀에 알립니다.

```bash
sed -i -E 's/^APP_VERSION=.*/APP_VERSION=v1.1.N/; s/^AI_WORKER_VERSION=.*/AI_WORKER_VERSION=v1.1.N/' .env
docker compose up -d --no-deps fastapi ai-worker
docker exec nginx nginx -s reload
```

코드로 되돌릴 때는 GitHub에서 해당 PR을 Revert하는 PR을 만들어 머지합니다. 머지되면 자동 배포가 다시 돕니다.

### 질의 챗봇 (LLM)

챗봇 설정은 운영 서버 `~/project/.env`에만 있고 자동 배포가 바꾸지 않습니다. 키가 없거나 꺼져 있으면 대화는 `off`, 선택은 규칙 추천(`rules`)으로 답하므로 배포 자체는 키 없이도 안전합니다.

```bash
# 켜기: .env 에 아래 세 줄을 넣는다 (키는 화면·로그에 남기지 않는다)
#   CHALLENGE_CHAT_ENABLED=true
#   OPENAI_API_KEY=<키>
#   OPENAI_MODEL=gpt-4o
docker compose up -d --no-deps --force-recreate fastapi   # restart 는 .env 를 다시 읽지 않는다
docker exec nginx nginx -s reload

# 확인: 설정 → gpt-4o 직접 호출(예시 문맥, 개인정보 없음). --base-url 을 주지 않으면 계정을 만들지 않는다
docker compose exec -T fastapi uv run --no-sync python -m scripts.rag.check_openai
docker logs fastapi 2>&1 | grep "질의 챗봇"    # 설정 경고, "호출 실패: HTTPStatusError 401" 같은 실패 종류
```

챗봇만 끌 때는 코드를 되돌리지 않고 `CHALLENGE_CHAT_ENABLED=false`로 바꾼 뒤 위와 같이 `fastapi`를 다시 만듭니다. 화면은 규칙 추천으로 계속 돕니다.

## 수동 배포

비상용입니다. 수동 스크립트는 로컬 `envs/.prod.env`를 서버에 덮어쓰므로, 그 전에 `APP_VERSION` · `AI_WORKER_VERSION`을 지금 운영 중인 버전과 맞춥니다.

`scripts/deploy/deployment.sh`가 이미지 빌드·푸시와 EC2의 앱·워커 컨테이너 실행을 처리하고, HTTPS는 `scripts/deploy/certbot.sh`로 Let's Encrypt 인증서를 받아 적용합니다. 둘 다 `chmod +x` 한 번 해두고 실행하면 됩니다. 자세한 절차와 검증 항목은 배포·검증 계획서를 보세요.

`deployment.sh`는 아이디와 토큰을 물어보는 대화형 스크립트라 터미널에서 직접 실행합니다. 마이그레이션과 시드는 하지 않으니 끝난 뒤 서버의 `~/project`에서 따로 돌립니다.

```bash
docker compose up -d mysql nginx    # 첫 배포 때만. 스크립트는 고른 서비스만 올립니다
docker compose exec fastapi uv run --no-sync aerich upgrade
docker compose exec fastapi uv run --no-sync python -m scripts.seed.seed_monsters   # seed_challenges · seed_rewards도 같은 방식
```

스크립트가 로컬의 `infra/nginx/prod_http.conf`에서 `server_name`을 서버 IP로 바꿔 두므로, 배포 뒤에는 `git checkout infra/nginx/prod_http.conf`로 되돌립니다.
