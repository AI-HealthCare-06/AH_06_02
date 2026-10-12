/** 공략 점수의 숫자와 게이지를 분리한다. */
export function scoreView(value) {
  const valid = typeof value === "number" && Number.isFinite(value);
  return {
    text: valid ? `${value} / 100` : "— / 100",
    fill: valid ? Math.max(0, Math.min(100, value)) : 0,
  };
}

export function kstDate(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const part = (type) => parts.find((value) => value.type === type).value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function kstTimestamp(date = new Date()) {
  return `${new Date(date.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 19)}+09:00`;
}

export function cycleView(mission, today = kstDate()) {
  const days =
    Math.floor(
      (Date.parse(`${today}T00:00:00+09:00`) -
        Date.parse(`${mission.start_date}T00:00:00+09:00`)) /
        86400000,
    ) + 1;
  const length =
    Math.floor(
      (Date.parse(`${mission.end_date}T00:00:00+09:00`) -
        Date.parse(`${mission.start_date}T00:00:00+09:00`)) /
        86400000,
    ) + 1;
  return {
    day: Math.max(0, Math.min(length, days)),
    length,
    ended: today > mission.end_date,
  };
}

export class ActivityTimer {
  constructor(clock = () => performance.now()) {
    this.clock = clock;
    this.accumulated = 0;
    this.started = null;
  }
  get running() {
    return this.started !== null;
  }
  get milliseconds() {
    return (
      this.accumulated +
      (this.running ? Math.max(0, this.clock() - this.started) : 0)
    );
  }
  get minutes() {
    return Math.floor(this.milliseconds / 6000) / 10;
  }
  start() {
    if (!this.running) this.started = this.clock();
  }
  pause() {
    this.accumulated = this.milliseconds;
    this.started = null;
  }
  ready(target) {
    return Number.isFinite(target) && target > 0 && this.minutes >= target;
  }
  get display() {
    const seconds = Math.floor(this.milliseconds / 1000);
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }
}
