#!/bin/bash
set -eo pipefail

COLOR_GREEN=$(tput setaf 2)
COLOR_BLUE=$(tput setaf 4)
COLOR_RED=$(tput setaf 1)
COLOR_NC=$(tput sgr0)

cd "$(dirname "$0")/../.."
source ./envs/.prod.env

# ---------- 도커 이미지 빌드 및 푸시 함수 ----------
build_and_push () {
  local docker_user=$1
  local docker_repo=$2
  local name=$3
  local tag=$4
  local dockerfile=$5
  local context=$6
  local tag_base=""

  if [[ "$name" == "FastAPI" ]]; then
    tag_base="app"
  else
    tag_base="ai"
  fi
  echo "${COLOR_BLUE}${name} Docker Image Build Start.${COLOR_NC}"
  docker build --platform linux/amd64 -t ${docker_user}/${docker_repo}:${tag_base}-${tag} -f ${dockerfile} ${context}

  echo "${COLOR_BLUE}${name} Docker Image Push Start.${COLOR_NC}"
  docker push ${docker_user}/${docker_repo}:${tag_base}-${tag}

  echo "${COLOR_GREEN}${name} Done.${COLOR_NC}"
  echo ""
}

# ---------- Docker login Prompt ----------
echo "${COLOR_BLUE}도커 유저네임과 비밀번호(PAT)을 입력해주세요.${COLOR_NC}"
read -p "username: " docker_user
# 토큰은 화면에 보이지 않게 받는다
read -s -p "password: " docker_pw
echo ""


# ---------- Docker Login ----------
echo "${COLOR_BLUE}Docker login${COLOR_NC}"
# 토큰을 명령줄 인자로 넘기면 프로세스 목록에 보이므로 표준 입력으로 넘긴다
if ! printf '%s' "${docker_pw}" | docker login -u "${docker_user}" --password-stdin ; then
  echo "${COLOR_RED}도커 로그인에 실패했습니다. 도커 유저네임과 비밀번호를 확인해주세요.${COLOR_NC}"
  # 실패한 채로 이미지를 10분 넘게 빌드하지 않도록 여기서 멈춘다
  exit 1
fi
echo "${COLOR_GREEN}도커 로그인 성공!${COLOR_NC}"
echo ""

# ---------- Docker Repository Input Prompt ----------
echo "${COLOR_BLUE}도커 이미지를 업로드할 레포지토리 이름을 입력해주세요.${COLOR_NC}"
read -p "Docker Repository Name: " docker_repo
echo ""

# ---------- Select Prompt ----------
echo "${COLOR_BLUE}배포 전 빌드 & 푸시할 이미지를 선택하세요(복수선택 가능, 띄어쓰기로 구분)${COLOR_NC}"
echo "1) fastapi"
echo "2) ai_worker"
read -p "선택 (예: 1 2): " selections
echo ""


# ---------- Docker Image Build & Push ----------
DEPLOY_SERVICES=()

for choice in $selections; do
  case $choice in
    1)
      echo "${COLOR_BLUE}FastAPI 앱의 배포 버젼을 입력하세요(ex. v1.0.0)${COLOR_NC}"
      read -p "FastAPI 앱 버젼: " fastapi_version
      build_and_push ${docker_user} ${docker_repo} "FastAPI" ${fastapi_version} "app/Dockerfile" "."
      DEPLOY_SERVICES+=("fastapi")
      ;;
    2)
      echo "${COLOR_BLUE}AI-worker 앱의 배포 버젼을 입력하세요(ex. v1.0.0)${COLOR_NC}"
      read -p "AI-worker 앱 버젼: " ai_version
      build_and_push ${docker_user} ${docker_repo} "AI Worker" ${ai_version} "ai_worker/Dockerfile" "."
      DEPLOY_SERVICES+=("ai-worker")
      ;;
    *)
      echo "${COLOR_RED}잘못된 선택입니다: $choice${COLOR_NC}"
      exit 1
      ;;
  esac
done

echo "${COLOR_GREEN}모든 선택된 이미지 빌드 & 푸시 완료! 🎉${COLOR_NC}"
echo "${COLOR_BLUE}배포 대상 서비스: ${DEPLOY_SERVICES[*]}${COLOR_NC}"
echo ""

# ---------- SSH 접속 정보 입력 prompt ----------
echo "${COLOR_BLUE}EC2 인스턴스 생성시 발급받은 ssh key 파일의 파일명을 입력하세요.(ex. ai_health_key.pem)${COLOR_NC}"
read -p "SSH 키 파일명: " ssh_key_file
echo ""

echo "${COLOR_BLUE}EC2 인스턴스의 IP를 입력하세요.${COLOR_NC}"
read -p "EC2-IP: " ec2_ip
echo ""

echo "${COLOR_BLUE}배포중인 서버의 https 여부를 선택하세요.${COLOR_NC}"
echo "1) http 사용중"
echo "2) https 사용중"
read -p "선택(ex. 1): " is_https
echo ""

# ---------- EC2 내에 배포 준비 파일 복사  ----------
scp -i ~/.ssh/${ssh_key_file} envs/.prod.env ubuntu@${ec2_ip}:~/project/.env
scp -i ~/.ssh/${ssh_key_file} infra/docker/docker-compose.prod.yml ubuntu@${ec2_ip}:~/project/docker-compose.yml
# 모델 아티팩트 전송 (experiment-refit/은 보안서약 대상이라 별도 전달 필요)
ssh -i ~/.ssh/${ssh_key_file} ubuntu@${ec2_ip} "mkdir -p ~/project/data"
scp -r -i ~/.ssh/${ssh_key_file} data/model ubuntu@${ec2_ip}:~/project/data/
scp -r -i ~/.ssh/${ssh_key_file} data/experiment-refit ubuntu@${ec2_ip}:~/project/data/
if [[ "$is_https" == "1" ]] ; then
  # ---------- prod_http.conf 파일의 server_name 자동 수정 ----------
  sed -i '' "s/server_name .*/server_name ${ec2_ip};/g" infra/nginx/prod_http.conf
  scp -i ~/.ssh/${ssh_key_file} infra/nginx/prod_http.conf ubuntu@${ec2_ip}:~/project/nginx/default.conf
else
  echo "${COLOR_BLUE} 사용중인 도메인을 입력하세요. (ex. api.ozcoding.site)${COLOR_NC}"
  read -p "Domain: " domain
  # ---------- prod_https.conf 파일의 server_name, ssl_certificate 자동 수정 ----------
  sed -i '' "s/server_name .*/server_name ${domain};/g" infra/nginx/prod_https.conf
  sed -i '' "s|/etc/letsencrypt/live/[^/]*|/etc/letsencrypt/live/${domain}|g" infra/nginx/prod_https.conf
  scp -i ~/.ssh/${ssh_key_file} infra/nginx/prod_https.conf ubuntu@${ec2_ip}:~/project/nginx/default.conf
fi

# ---------- EC2 배포 자동화  ----------
echo "${COLOR_BLUE}EC2 인스턴스에 SSH 접속을 시도합니다.${COLOR_NC}"
chmod 400 ~/.ssh/${ssh_key_file}
# 서버는 Docker Hub에 로그인하지 않는다. 이미지 저장소가 공개라 로그인 없이 받을 수 있고,
# 로그인하면 토큰이 서버의 ~/.docker/config.json 에 남는다. 저장소를 비공개로 바꾸면 이 전제가 깨진다
ssh -i ~/.ssh/${ssh_key_file} ubuntu@${ec2_ip} \
  "DEPLOY_SERVICES='${DEPLOY_SERVICES[*]}' \
   bash -s" << 'EOF'
  set -e
  cd project

  # valkey가 처음이면 따로 기동
  docker compose up -d valkey

  echo "Deploying services: $DEPLOY_SERVICES"
  docker compose up -d --pull always --no-deps $DEPLOY_SERVICES

  docker image prune -af
EOF

echo "✅ Deployment finished."
