/** 체험 시안과 실제 화면이 함께 쓰는 단계별 성장 결정. */
export function growthName(stage) {
  return ["새싹의 결정", "숲의 결정", "별빛의 결정"][stage - 1];
}

export function growthArt(stage) {
  const color = ["#a2d2c1", "#5bb6ad", "#e5c362"][stage - 1];
  const sparkles = stage > 1
    ? '<path d="m12 65 8 8-8 8-8-8Zm86-40 7 7-7 7-7-7Z" fill="#dfba51"/>'
    : "";
  return `<svg viewBox="0 0 110 150" aria-hidden="true"><path d="M55 8 84 41 70 111H40L26 41Z" fill="${color}" stroke="#306e68" stroke-width="3"/><path d="m55 8-8 45 8 58 8-58Z" fill="#ffffff80"/><path d="M26 41h58M40 111h30M55 111v20M38 132h34" fill="none" stroke="#306e68" stroke-width="5"/>${sparkles}</svg>`;
}
