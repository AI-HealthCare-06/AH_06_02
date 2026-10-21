import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const html = readFileSync(
  new URL("../../frontend/docs/prototype/당고킬러-모험시안_v5.html", import.meta.url),
  "utf8",
);

function definitions(name) {
  return [...html.matchAll(new RegExp(`function ${name}\\(`, "g"))].map((match) => {
    const start = match.index;
    const open = html.indexOf("{", start);
    let depth = 1;
    let end = open + 1;
    while (depth && end < html.length) {
      if (html[end] === "{") depth++;
      if (html[end] === "}") depth--;
      end++;
    }
    return html.slice(start, end);
  });
}

function evaluate(names, setup, expression) {
  const context = vm.createContext({});
  vm.runInContext(setup + names.flatMap(definitions).join("\n"), context);
  return vm.runInContext(expression, context);
}

test("보상함은 성장 아이템을 표시하고 정의되지 않은 문구를 출력하지 않는다", () => {
  const output = evaluate(
    ["renderInventory", "renderGrowth", "renderItemGrowth"],
    `const rewardPool=[],rewardState={inventory:new Set(),stage:1,materials:0};
     const document={querySelectorAll:()=>[],getElementById:()=>({value:'',innerHTML:''})};
     const growthTab='character';function renderCharacterGrowth(){return '';}
     function growthArt(){return '';} function growthName(){return '새싹의 결정';}`,
    "renderInventory()",
  );
  assert.match(output, /성장 아이템/);
  assert.doesNotMatch(output, /undefined/);
});

test("공략을 시작한 뒤 다른 대상으로 바꾸거나 미산정 대상을 시작할 수 없다", () => {
  const output = evaluate(
    ["isTargetable", "canEnterVillage"],
    `const villageKeys=['viscera','alde','cotinine','spike'];
     const villageState={target:'viscera',selecting:true};
     const questSelection={startedOn:'2026-10-17'};`,
    "['viscera','alde','cotinine','spike'].map(canEnterVillage).join(',')",
  );
  assert.equal(output, "true,false,false,false");
});

test("2주차에 추가한 챌린지를 중단해도 추가 투입 한도는 돌아오지 않는다", () => {
  const output = evaluate(
    ["addDaysKey", "remainingChallengeSlots", "challengeLimit"],
    `const questSelection={startedOn:'2026-10-01',titles:['걷기'],extraAddedCount:1};
     function kstToday(){return '2026-10-08';}`,
    "challengeLimit() - questSelection.titles.length",
  );
  assert.equal(output, 0);
});

test("추가 챌린지는 기존 주기 시작일을 유지하고 추가 투입 횟수를 기록한다", () => {
  const output = evaluate(
    ["addDaysKey", "weekStartKey", "rememberQuestPlan"],
    `const questSelection={startedOn:'2026-10-01',target:'viscera',titles:['걷기'],extraAddedCount:0};
     const questPlanHistory=[];const recommendationKey='viscera';
     function kstToday(){return '2026-10-08';}`,
    `rememberQuestPlan([{dataset:{title:'걷기'}},{dataset:{title:'휴식'}}]);
     JSON.stringify([questSelection.startedOn,questSelection.extraAddedCount,questSelection.titles]);`,
  );
  assert.deepEqual(JSON.parse(output), ["2026-10-01", 1, ["걷기", "휴식"]]);
});

test("식후 걷기 안내는 승인 마스터의 회당 10분 목표를 사용한다", () => {
  const steps = evaluate(["challengeInstructions"], "", "challengeInstructions({title:'식후 걷기'})");
  assert.match(steps.join(" "), /10분/);
  assert.doesNotMatch(steps.join(" "), /30분/);
});

test("생활습관 선택지는 최근 4주 코드 계약을 따르고 총콜레스테롤을 수집하지 않는다", () => {
  assert.match(html, /최근 4주 기준으로 선택해 주세요/);
  assert.doesNotMatch(html, /선택지 준비 중/);
  assert.doesNotMatch(html, /aria-label="총콜레스테롤"/);
  assert.match(html, /하루 2회 이상/);
  assert.match(html, /최근 4주 동안 마시지 않음/);
});

test("챌린지를 중단해도 수행 기록과 추가 투입 사용 횟수는 보존한다", () => {
  const output = evaluate(
    ["stopPrototypeChallenge"],
    `const questSelection={titles:['걷기','근력'],extraAddedCount:1};
     const questLog=[{challenge:'근력',xp:24,progress:10}];`,
    `stopPrototypeChallenge('근력');JSON.stringify([questSelection.titles,questSelection.extraAddedCount,questLog]);`,
  );
  assert.deepEqual(JSON.parse(output), [["걷기"], 1, [{challenge:"근력",xp:24,progress:10}]]);
});

test("같은 날 건강정보를 다시 입력해도 이전 기록을 덮어쓰지 않는다", () => {
  const output = evaluate(
    ["saveHealthEntry"],
    "const healthEntries=[{date:'2026-10-17',weight:80}];",
    "saveHealthEntry({date:'2026-10-17',weight:79});JSON.stringify(healthEntries)",
  );
  assert.deepEqual(JSON.parse(output), [{date:"2026-10-17",weight:80},{date:"2026-10-17",weight:79}]);
});

test("같은 주에 챌린지를 바꿔도 이전 선택 이력은 보존한다", () => {
  const output = evaluate(
    ["addDaysKey", "weekStartKey", "rememberQuestPlan"],
    `const questSelection={startedOn:'2026-10-17',titles:[],extraAddedCount:0};
     const questPlanHistory=[];const recommendationKey='viscera';
     function kstToday(){return '2026-10-17';}`,
    `rememberQuestPlan([{dataset:{title:'걷기'}}]);rememberQuestPlan([{dataset:{title:'근력'}}]);
     JSON.stringify(questPlanHistory.map(row=>row.titles));`,
  );
  assert.deepEqual(JSON.parse(output), [["걷기"],["근력"]]);
});

test("예정 기회는 한 번만 인정하고 0점·월요일 경계·100점 초과를 보존한다", () => {
  const output = evaluate(
    ["weekStartKey", "weeklyAttackScore", "recordScheduledOccurrence"],
    "const PROGRESS_VALUE=10;const logs=[];",
    `const entry={target:'viscera',date:'2026-10-18',challenge:'걷기',name:'점심',xp:18,progress:10,scheduled:true,recognized:true};
     const accepted=recordScheduledOccurrence(logs,entry);
     const duplicate=recordScheduledOccurrence(logs,entry);
     recordScheduledOccurrence(logs,{...entry,name:'0점',progress:0});
     recordScheduledOccurrence(logs,{...entry,name:'미예정',scheduled:false});
     const sunday=weeklyAttackScore(logs,'2026-10-18');
     const monday=weeklyAttackScore(logs,'2026-10-19');
     for(let i=0;i<11;i++)recordScheduledOccurrence(logs,{...entry,name:'새 기회 '+i,date:'2026-10-19'});
     JSON.stringify([accepted,duplicate,sunday,monday,weeklyAttackScore(logs,'2026-10-19')]);`,
  );
  assert.deepEqual(JSON.parse(output), [true,false,10,0,110]);
});

test("공통 종료일 뒤에는 빈 슬롯이 있어도 새 챌린지를 시작할 수 없다", () => {
  const output = evaluate(
    ["addDaysKey", "remainingChallengeSlots"],
    `const questSelection={startedOn:'2026-10-01',titles:[],extraAddedCount:0};
     function kstToday(){return '2026-10-29';}`,
    "remainingChallengeSlots()",
  );
  assert.equal(output, 0);
});
