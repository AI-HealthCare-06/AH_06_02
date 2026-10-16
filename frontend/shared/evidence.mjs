/** HLTH-03. 공통 인증 클라이언트로 비공개 사진 참조값을 받는다. */
export function createEvidenceUploader(request) {
  return async (file, { userChallengeId, signal } = {}) => {
    if (!Number.isSafeInteger(userChallengeId) || userChallengeId <= 0)
      throw new Error("사진을 연결할 챌린지를 확인해주세요.");
    if (
      !(file instanceof Blob) ||
      !["image/jpeg", "image/png"].includes(file.type) ||
      file.size === 0 ||
      file.size > 10 * 1024 * 1024
    )
      throw new Error("10 MiB 이하의 JPEG·PNG 사진을 선택해주세요.");
    const body = new FormData();
    body.append("photo", file);
    body.append("user_challenge_id", String(userChallengeId));
    const result = await request("/evidence/photos", {
      method: "POST",
      body,
      signal,
    });
    if (
      typeof result?.evidence_url !== "string" ||
      !result.evidence_url.trim() ||
      result.evidence_url.length > 255
    )
      throw new Error("사진 업로드 응답을 확인해주세요.");
    return result;
  };
}
