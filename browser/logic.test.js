const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const quest = require("./logic.js");

const data = vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, "words.js"), "utf8") + "\nWORDQUEST_DATA;",
  { window: {} }
);
const words = data.words;
const decoys = data.decoys;

function studyDay(state, day) {
  quest.ensurePlan(state, words, day);
  const pending = quest.board(state, words, day).filter((item) => !item.learned);
  assert.ok(pending.length > 0 && pending.length <= 5);
  pending.forEach((item) => quest.markCorrect(state, words, item.word.text, day));
  return pending.map((item) => item.word);
}

const state = quest.blankState();
state.name = "Maya";
const day1 = studyDay(state, "2026-06-01");
assert.strictEqual(day1.length, 5);
assert.ok(day1.every((word) => word.level === 1));
quest.ensurePlan(state, words, "2026-06-01");
assert.strictEqual(state.assigned.length, 5);

state.learned = state.learned.slice(0, 3);
const tomorrow = "2026-06-02";
quest.ensurePlan(state, words, tomorrow);
const carried = quest.board(state, words, tomorrow).filter((item) => !item.learned);
assert.deepStrictEqual(carried.map((item) => item.word.sequence), [4, 5, 6, 7, 8]);

const fresh = quest.blankState();
fresh.name = "Maya";
let day = "2026-06-01";
for (let i = 0; i < 6; i++) {
  assert.strictEqual(quest.quizDue(fresh), false);
  studyDay(fresh, day);
  const parts = day.split("-").map(Number);
  const next = new Date(parts[0], parts[1] - 1, parts[2] + 1);
  day = quest.dateKey(next);
}
assert.strictEqual(fresh.learned.length, 30);
assert.strictEqual(quest.quizDue(fresh), true);
quest.ensurePlan(fresh, words, day);
assert.strictEqual(fresh.assigned.length, 30);
const quiz = quest.startQuiz(fresh, words);
assert.strictEqual(quiz.questions.length, 10);
quiz.questions.forEach((question, index) => {
  quest.answerQuiz(fresh, index, question.correct, day);
});
assert.strictEqual(fresh.quizzes[30].score, 10);
quest.ensurePlan(fresh, words, day);
const unlocked = quest.board(fresh, words, day).filter((item) => !item.learned);
assert.deepStrictEqual(unlocked.map((item) => item.word.level), [2, 2, 2, 2, 2]);

const first = quest.currentWord(fresh, words, "2026-01-01");
const easy = quest.blankState();
easy.name = "Sam";
const word = quest.currentWord(easy, words, "2026-01-01");
const options = quest.choicesFor(easy, word, words, decoys, "2026-01-01");
assert.ok(options.includes(word.meaning));
options.forEach((choice) => {
  if (choice !== word.meaning) assert.ok(decoys.includes(choice));
});
assert.ok(first);

let remaining = quest.tick(easy, "2026-01-01", false);
assert.strictEqual(remaining, 15 * 60);
easy.secondsUsed = 15 * 60;
assert.strictEqual(quest.screen(easy, words, "2026-01-01"), "timeup");

console.log("browser logic ok");
