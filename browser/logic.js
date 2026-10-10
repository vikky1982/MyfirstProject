(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.WordQuest = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  var PER_DAY = 10;
  var QUIZ_EVERY = 30;
  var QUIZ_LENGTH = 10;
  var LIMIT = 15 * 60;

  function dateKey(date) {
    var y = date.getFullYear();
    var m = String(date.getMonth() + 1).padStart(2, "0");
    var d = String(date.getDate()).padStart(2, "0");
    return y + "-" + m + "-" + d;
  }

  function shiftDate(key, days) {
    var parts = key.split("-").map(Number);
    var date = new Date(parts[0], parts[1] - 1, parts[2]);
    date.setDate(date.getDate() + days);
    return dateKey(date);
  }

  function hash(text) {
    var h = 2166136261;
    for (var i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function shuffle(list, random) {
    var copy = list.slice();
    for (var i = copy.length - 1; i > 0; i--) {
      var j = Math.floor(random() * (i + 1));
      var tmp = copy[i];
      copy[i] = copy[j];
      copy[j] = tmp;
    }
    return copy;
  }

  function blankState() {
    return {
      name: "",
      learned: [],
      assigned: [],
      planDate: "",
      planWords: [],
      waitingQuiz: false,
      usageDate: "",
      secondsUsed: 0,
      streak: 0,
      lastCompleted: "",
      quizzes: {},
      quiz: null,
      round: 1
    };
  }

  function byText(words) {
    var map = {};
    words.forEach(function (word) {
      map[word.text] = word;
    });
    return map;
  }

  function learnedSet(state) {
    var set = {};
    state.learned.forEach(function (item) {
      set[item.text] = item;
    });
    return set;
  }

  function assignedSet(state) {
    var set = {};
    state.assigned.forEach(function (item) {
      set[item.text] = item;
    });
    return set;
  }

  function lastMilestone(state) {
    var best = 0;
    Object.keys(state.quizzes).forEach(function (key) {
      var milestone = Number(key);
      if (state.quizzes[key] && state.quizzes[key].done && milestone > best) best = milestone;
    });
    return best;
  }

  function quizDue(state) {
    var learned = state.learned.length;
    var due = Math.floor(learned / QUIZ_EVERY) * QUIZ_EVERY;
    return due > lastMilestone(state);
  }

  function unfinished(state) {
    var learned = learnedSet(state);
    return state.assigned.filter(function (item) {
      return !learned[item.text];
    });
  }

  function orderedWords(words) {
    return words.slice().sort(function (a, b) {
      return a.level - b.level || a.sequence - b.sequence;
    });
  }

  function nextWords(state, words, count) {
    var have = assignedSet(state);
    return orderedWords(words).filter(function (word) {
      return !have[word.text];
    }).slice(0, count);
  }

  function beginNextRound(state) {
    var fresh = blankState();
    fresh.name = state.name;
    fresh.sparkies = state.sparkies || 0;
    fresh.streak = state.streak || 0;
    fresh.lastCompleted = state.lastCompleted || "";
    fresh.usageDate = state.usageDate || "";
    fresh.secondsUsed = state.secondsUsed || 0;
    fresh.round = (state.round || 1) + 1;
    Object.keys(state).forEach(function (key) { delete state[key]; });
    Object.keys(fresh).forEach(function (key) { state[key] = fresh[key]; });
  }

  function fillPlan(state, words, today) {
    var carry = unfinished(state).filter(function (item) {
      return item.on !== today;
    });
    var alreadyNew = state.assigned.filter(function (item) {
      return item.on === today;
    }).length;
    if (quizDue(state) && carry.length === 0 && alreadyNew === 0) {
      state.planDate = today;
      state.planWords = [];
      state.waitingQuiz = true;
      return;
    }
    var room = Math.max(0, lastMilestone(state) + QUIZ_EVERY - state.assigned.length);
    var openSlots = Math.max(0, PER_DAY - carry.length - alreadyNew);
    var need = Math.min(room, openSlots);
    var picked = nextWords(state, words, need);
    if (!picked.length && need > 0 && carry.length === 0 && alreadyNew === 0 && state.assigned.length) {
      beginNextRound(state);
      fillPlan(state, words, today);
      return;
    }
    picked.forEach(function (word) {
      state.assigned.push({ text: word.text, on: today });
    });
    var learned = learnedSet(state);
    state.planDate = today;
    state.waitingQuiz = false;
    state.planWords = carry.map(function (item) { return item.text; }).concat(
      state.assigned.filter(function (item) {
        return item.on === today;
      }).map(function (item) { return item.text; })
    );
    state.planWords = state.planWords.filter(function (text, index, list) {
      return list.indexOf(text) === index && (!learned[text] || learned[text].on === today);
    });
  }

  function topUp(state, words, today) {
    if (state.waitingQuiz || quizDue(state)) return;
    if (!state.planWords || state.planWords.length === 0 || state.planWords.length >= PER_DAY) return;
    var room = Math.max(0, lastMilestone(state) + QUIZ_EVERY - state.assigned.length);
    var need = Math.min(room, PER_DAY - state.planWords.length);
    nextWords(state, words, need).forEach(function (word) {
      state.assigned.push({ text: word.text, on: today });
      state.planWords.push(word.text);
    });
  }

  function ensurePlan(state, words, today) {
    if (state.planDate !== today) {
      fillPlan(state, words, today);
      return;
    }
    if (state.waitingQuiz && !quizDue(state)) {
      fillPlan(state, words, today);
      return;
    }
    topUp(state, words, today);
  }

  function board(state, words, today) {
    ensurePlan(state, words, today);
    var learned = learnedSet(state);
    return state.planWords.map(function (text) {
      return {
        word: byText(words)[text],
        learned: !!learned[text]
      };
    }).filter(function (item) { return item.word; });
  }

  function currentWord(state, words, today) {
    var items = board(state, words, today);
    for (var i = 0; i < items.length; i++) {
      if (!items[i].learned) return items[i].word;
    }
    return null;
  }

  function choicesFor(state, word, words, decoys, today) {
    var random = rng(hash(word.text + "|" + today));
    var learned = learnedSet(state);
    var pool = [];
    state.learned.forEach(function (item) {
      var other = byText(words)[item.text];
      if (other && other.meaning !== word.meaning && pool.indexOf(other.meaning) === -1) {
        pool.push(other.meaning);
      }
    });
    pool = shuffle(pool, random);
    var options = pool.slice(0, 3);
    var extras = shuffle(decoys.filter(function (item) {
      return item !== word.meaning && options.indexOf(item) === -1;
    }), random);
    while (options.length < 3 && extras.length) options.push(extras.pop());
    options.push(word.meaning);
    return shuffle(options, random);
  }

  function dayComplete(state, today) {
    if (state.lastCompleted === today) return;
    if (state.lastCompleted === shiftDate(today, -1)) state.streak += 1;
    else state.streak = 1;
    state.lastCompleted = today;
  }

  function wordsFinished(state, today) {
    if (!state.planWords.length || state.waitingQuiz) return false;
    var learned = learnedSet(state);
    return state.planWords.every(function (text) {
      return learned[text] && learned[text].on === today;
    });
  }

  function markCorrect(state, words, text, today) {
    ensurePlan(state, words, today);
    if (state.learned.some(function (item) { return item.text === text; })) {
      return { fresh: false };
    }
    var before = 0;
    state.learned.forEach(function (item) {
      var word = byText(words)[item.text];
      if (word && word.level > before) before = word.level;
    });
    state.learned.push({ text: text, on: today });
    var word = byText(words)[text];
    var kind = null;
    if (!before) kind = "start";
    else if (word && word.level > before) kind = "up";
    if (wordsFinished(state, today)) dayComplete(state, today);
    return { fresh: true, kind: kind, word: word };
  }

  function startQuiz(state, words) {
    if (state.quiz && !state.quiz.done) return state.quiz;
    if (!quizDue(state)) return null;
    var milestone = Math.floor(state.learned.length / QUIZ_EVERY) * QUIZ_EVERY;
    var batch = state.learned.slice(milestone - QUIZ_EVERY, milestone).map(function (item) {
      return byText(words)[item.text];
    }).filter(Boolean);
    var random = rng(hash(String(milestone) + ":" + state.learned.length + ":" + Date.now()));
    var chosen = shuffle(batch, random).slice(0, QUIZ_LENGTH);
    var meanings = [];
    batch.forEach(function (word) {
      if (meanings.indexOf(word.meaning) === -1) meanings.push(word.meaning);
    });
    state.quiz = {
      milestone: milestone,
      done: false,
      questions: chosen.map(function (word) {
        var distractors = shuffle(meanings.filter(function (meaning) {
          return meaning !== word.meaning;
        }), random).slice(0, 3);
        return {
          text: word.text,
          choices: shuffle(distractors.concat([word.meaning]), random),
          correct: word.meaning,
          selected: ""
        };
      })
    };
    return state.quiz;
  }

  function answerQuiz(state, index, choice, today) {
    var quiz = state.quiz;
    if (!quiz || quiz.done) return quiz;
    var question = quiz.questions[index];
    if (!question || question.selected || question.choices.indexOf(choice) === -1) return quiz;
    question.selected = choice;
    if (quiz.questions.every(function (item) { return item.selected; })) {
      var score = quiz.questions.filter(function (item) {
        return item.selected === item.correct;
      }).length;
      quiz.done = true;
      quiz.score = score;
      var first = !state.quizzes[quiz.milestone] || !state.quizzes[quiz.milestone].done;
      state.quizzes[quiz.milestone] = { score: score, total: quiz.questions.length, done: true };
      if (first) dayComplete(state, today);
    }
    return quiz;
  }

  function streakMessage(state, today) {
    var alive = state.lastCompleted === today || state.lastCompleted === shiftDate(today, -1);
    var streak = alive ? state.streak : 0;
    if (state.lastCompleted === today && streak) return streak + "-day streak. You showed up!";
    if (state.lastCompleted === shiftDate(today, -1) && streak) {
      return "Finish today to keep your " + streak + "-day streak!";
    }
    return "Finish today's words to start a streak.";
  }

  function screen(state, words, today) {
    if (!state.name) return "welcome";
    if ((state.secondsUsed || 0) >= LIMIT && state.usageDate === today) return "timeup";
    if (quizDue(state) && unfinished(state).length === 0) return "quiz";
    if (state.quiz && !state.quiz.done) return "quiz";
    if (state.quiz && state.quiz.done) return "result";
    var items = board(state, words, today);
    var bankLeft = orderedWords(words).some(function (word) {
      return !assignedSet(state)[word.text];
    });
    if (!bankLeft && unfinished(state).length === 0 && !quizDue(state)) return "champion";
    if (wordsFinished(state, today)) return "done";
    if (!currentWord(state, words, today) && items.length === 0 && state.waitingQuiz) return "quiz";
    return "learn";
  }

  function tick(state, today, active) {
    if (state.usageDate !== today) {
      state.usageDate = today;
      state.secondsUsed = 0;
    }
    if (active && state.secondsUsed < LIMIT) state.secondsUsed += 1;
    return Math.max(0, LIMIT - state.secondsUsed);
  }

  function cleanName(raw) {
    var name = String(raw || "").replace(/\s+/g, " ").trim();
    if (!/^[A-Za-z][A-Za-z .'\-]{0,19}$/.test(name)) return "";
    return name;
  }

  return {
    PER_DAY: PER_DAY,
    QUIZ_EVERY: QUIZ_EVERY,
    QUIZ_LENGTH: QUIZ_LENGTH,
    LIMIT: LIMIT,
    dateKey: dateKey,
    blankState: blankState,
    board: board,
    currentWord: currentWord,
    choicesFor: choicesFor,
    markCorrect: markCorrect,
    quizDue: quizDue,
    startQuiz: startQuiz,
    answerQuiz: answerQuiz,
    streakMessage: streakMessage,
    screen: screen,
    tick: tick,
    cleanName: cleanName,
    wordsFinished: wordsFinished,
    ensurePlan: ensurePlan
  };
});
