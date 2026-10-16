const retryable = (error) =>
  (error.status === 404 && error.code === "PRED_NOT_FOUND") ||
  (error.status === 409 &&
    error.code === "CHLG_RECOMMENDATION_UNAVAILABLE" &&
    !error.details?.reason);
const aborted = () =>
  new DOMException("화면 또는 로그인 상태가 바뀌었어요.", "AbortError");

function waitFor(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(aborted());
    const cancel = () => {
      clearTimeout(timer);
      reject(aborted());
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", cancel);
      resolve();
    }, ms);
    signal?.addEventListener("abort", cancel, { once: true });
  });
}

/** 완료 확인은 메모리에 한 번만 보관한다. 일반 오류와 쓰기 요청에는 재시도를 확대하지 않는다. */
export class PredictionReadiness {
  #ticket = null;
  #revision = 0;
  constructor({ now = () => Date.now(), wait = waitFor } = {}) {
    this.now = now;
    this.wait = wait;
  }
  markDone(result) {
    if (
      result?.status !== "done" ||
      !Number.isInteger(result.prediction_id) ||
      result.prediction_id <= 0
    )
      return false;
    this.#ticket = { at: this.now(), revision: ++this.#revision };
    return true;
  }
  clear() {
    this.#ticket = null;
    ++this.#revision;
  }
  async request(operation, { signal } = {}) {
    const ticket = this.#ticket;
    this.#ticket = null;
    const revision = this.#revision;
    const justDone = ticket && this.now() - ticket.at <= 5000;
    for (let attempt = 0; ; attempt++) {
      if (signal?.aborted || revision !== this.#revision) throw aborted();
      try {
        return await operation();
      } catch (error) {
        if (!justDone || attempt >= 2 || !retryable(error)) throw error;
        if (signal?.aborted || revision !== this.#revision) throw aborted();
        await this.wait(1000, signal);
      }
    }
  }
}
