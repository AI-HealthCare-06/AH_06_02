/** 체험 시안과 실제 화면이 함께 쓰는 단계별 성장 결정. */
export function growthName(stage) {
  return ["작은 별의 결정", "은하의 결정", "별빛 왕관"][stage - 1];
}

export function growthArt(stage) {
  const source = new URL(`../docs/prototype/assets/growth-crystal-stage-${stage}.webp`, import.meta.url);
  return `<img src="${source.href}" width="512" height="512" alt="" decoding="async">`;
}
