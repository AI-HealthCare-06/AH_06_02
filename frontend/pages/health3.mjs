import { pendingPage } from "../shared/components.mjs";

/** 담당자가 공통 컨텍스트로 이 화면을 구현한다. 가상 결과나 저장 동작은 넣지 않는다. */
export function mount(context) {
  pendingPage(context);
}
