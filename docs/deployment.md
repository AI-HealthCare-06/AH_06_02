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
