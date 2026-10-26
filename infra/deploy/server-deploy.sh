#!/bin/bash
# GitHub Actions 배포 전용. 배포 키는 authorized_keys 의 command= 로 이 스크립트에만 묶여 있다.
# 받는 명령은 "deploy vX.Y.Z" 한 줄뿐이다. 다른 입력은 실행하지 않는다.
# 서버에는 /home/ubuntu/deploy.sh 로 직접 설치한다. 이 파일을 고치면 서버 사본도 같이 바꾼다.
# authorized_keys: restrict,command="/home/ubuntu/deploy.sh" ssh-ed25519 ... dangokiller-github-deploy
set -euo pipefail

request="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$request" =~ ^deploy\ (v[0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
  echo "허용되지 않은 명령입니다: deploy vX.Y.Z 형식만 받습니다." >&2
  exit 2
fi
version="${BASH_REMATCH[1]}"

cd /home/ubuntu/project
exec 9>/home/ubuntu/deploy.lock
flock -n 9 || { echo "다른 배포가 진행 중입니다." >&2; exit 3; }
exec > >(tee -a /home/ubuntu/deploy.log) 2>&1
echo "=== $(date '+%F %T %Z') ${version} 배포 시작"

previous_app=$(grep '^APP_VERSION=' .env | cut -d= -f2)
previous_ai=$(grep '^AI_WORKER_VERSION=' .env | cut -d= -f2)

set_versions() {
  sed -i -E "s/^APP_VERSION=.*/APP_VERSION=$1/; s/^AI_WORKER_VERSION=.*/AI_WORKER_VERSION=$2/" .env
}

# nginx 는 켤 때 찾아 둔 앱 컨테이너 IP 를 계속 쓴다. 앱을 새로 만들면 IP 가 바뀔 수 있어 다시 읽게 한다
reload_nginx() {
  docker exec nginx nginx -s reload
}

# 사용자와 같은 길(nginx 80번)로 확인한다. 앱 포트만 보면 nginx 연결이 끊긴 걸 놓친다
healthy() {
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://127.0.0.1/api/v1/auth/check-email?email=deploy-check@dangokiller.com" \
      && curl -fsS -o /dev/null "http://127.0.0.1/frontend/" \
      && [ "$(docker inspect -f '{{.State.Running}}' ai-worker)" = true ] \
      && docker logs ai-worker 2>&1 | grep -c "예측 큐 대기" >/dev/null; then
      return 0
    fi
    sleep 3
  done
  return 1
}

rollback() {
  echo "!!! 배포 실패, ${previous_app}/${previous_ai} 로 되돌립니다"
  set_versions "$previous_app" "$previous_ai"
  docker compose up -d --no-deps fastapi ai-worker
  reload_nginx || true
  exit 1
}

set_versions "$version" "$version"
docker compose pull fastapi ai-worker || rollback
# 새 코드가 뜨기 전에 새 이미지로 마이그레이션부터 한다. 기존 서버는 그동안 계속 응답한다
docker compose run --rm --no-deps -T fastapi uv run --no-sync aerich upgrade || rollback
docker compose up -d --no-deps fastapi ai-worker || rollback
reload_nginx || rollback
healthy || rollback
for seed in seed_monsters seed_challenges seed_rewards; do
  docker compose exec -T fastapi uv run --no-sync python -m "scripts.seed.${seed}" || rollback
done
docker image prune -f >/dev/null
echo "=== $(date '+%F %T %Z') ${version} 배포 완료"
