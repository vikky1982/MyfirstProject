(function () {
  var data = window.WORDQUEST_DATA;
  var quest = window.WordQuest;
  var words = data.words;
  var levels = data.levels;
  var decoys = data.decoys;
  var KEY = "wordquest-browser-v1";
  var state = load();
  var view = "";
  var note = "";
  var wrong = false;

  function load() {
    try {
      var saved = JSON.parse(localStorage.getItem(KEY) || "null");
      if (saved && Array.isArray(saved.learned)) return Object.assign(quest.blankState(), saved);
    } catch (err) {}
    return quest.blankState();
  }

  function save() {
    localStorage.setItem(KEY, JSON.stringify(state));
  }

  function today() {
    return quest.dateKey(new Date());
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function clock(seconds) {
    seconds = Math.max(0, seconds | 0);
    return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  }

  function remaining() {
    if (state.usageDate !== today()) return quest.LIMIT;
    return Math.max(0, quest.LIMIT - (state.secondsUsed || 0));
  }

  function burst(x, y) {
    var layer = document.getElementById("sparkles");
    if (!layer) return;
    var pop = document.createElement("span");
    pop.className = "sparkie-pop";
    pop.textContent = "+1 ✦";
    pop.style.left = x + "px";
    pop.style.top = y + "px";
    layer.appendChild(pop);
    setTimeout(function () { pop.remove(); }, 1100);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var glyphs = ["✦", "✧", "✸", "★", "✶"];
    var colors = ["#f0b429", "#e36a45", "#2f7d4a", "#fff4c2", "#7eb6d9"];
    for (var i = 0; i < 32; i++) {
      var spark = document.createElement("span");
      spark.className = "spark";
      spark.textContent = glyphs[i % glyphs.length];
      spark.style.left = x + "px";
      spark.style.top = y + "px";
      spark.style.color = colors[i % colors.length];
      var angle = Math.random() * Math.PI * 2;
      var dist = 60 + Math.random() * 160;
      spark.style.setProperty("--dx", Math.cos(angle) * dist + "px");
      spark.style.setProperty("--dy", Math.sin(angle) * dist - 40 + "px");
      layer.appendChild(spark);
      setTimeout(function (node) { node.remove(); }, 1100, spark);
    }
  }

  function giveSparkie(x, y) {
    state.sparkies = (state.sparkies || 0) + 1;
    save();
    burst(x, y);
    var badge = document.getElementById("sparkie-count");
    if (badge) {
      badge.textContent = "✦ " + state.sparkies;
      badge.classList.remove("pop");
      void badge.offsetWidth;
      badge.classList.add("pop");
    }
  }

  function levelMeta(level) {
    return levels[String(level)] || levels[level];
  }

  function currentLevelNumber() {
    var learned = {};
    state.learned.forEach(function (item) { learned[item.text] = true; });
    var next = words.filter(function (word) { return !learned[word.text]; })
      .sort(function (a, b) { return a.level - b.level || a.sequence - b.sequence; })[0];
    if (quest.quizDue(state)) {
      var last = state.learned[state.learned.length - 1];
      var found = words.filter(function (word) { return last && word.text === last.text; })[0];
      return found ? found.level : 1;
    }
    return next ? next.level : 6;
  }

  function renderNav(locked) {
    var nav = document.getElementById("nav");
    var timer = document.getElementById("timer");
    var who = document.getElementById("who");
    if (!state.name || locked) {
      nav.hidden = true;
      timer.hidden = true;
      var hiddenBadge = document.getElementById("sparkie-count");
      if (hiddenBadge) hiddenBadge.hidden = true;
      who.textContent = state.name ? "✦ " + (state.sparkies || 0) + " sparkies" : "";
      return;
    }
    nav.hidden = false;
    nav.innerHTML = '<button type="button" data-go="home">Today</button><button type="button" data-go="review">Review</button><button type="button" data-go="progress">Progress</button>';
    timer.hidden = false;
    var badge = document.getElementById("sparkie-count");
    if (!badge) {
      badge = document.createElement("div");
      badge.id = "sparkie-count";
      badge.className = "sparkie-count";
      timer.parentNode.insertBefore(badge, timer);
    }
    badge.hidden = false;
    badge.textContent = "✦ " + (state.sparkies || 0);
    var left = remaining();
    timer.classList.toggle("is-low", left <= 120);
    timer.querySelector("[data-clock]").textContent = clock(left);
    timer.querySelector("[data-bar]").style.width = (left / quest.LIMIT) * 100 + "%";
    who.innerHTML = "Playing as " + esc(state.name) + ' · <button class="linkish" type="button" data-go="switch">Switch player</button>';
  }

  function dots(items, current) {
    return '<ol class="dots">' + items.map(function (item, index) {
      var cls = item.learned ? "done" : (current && item.word.text === current.text ? "now" : "");
      return '<li class="' + cls + '">' + (index + 1) + "</li>";
    }).join("") + "</ol>";
  }

  function banner() {
    if (!note) return "";
    var kind = note.kind || "good";
    return '<p class="banner ' + kind + '">' + esc(note.text) + "</p>";
  }

  function homeHtml() {
    var day = today();
    var items = quest.board(state, words, day);
    var current = quest.currentWord(state, words, day);
    var mode = quest.screen(state, words, day);
    var level = levelMeta(currentLevelNumber());
    var title = "Five words are waiting.";
    var body = "<p>Today's level: " + level.emoji + " " + esc(level.name) + ". " + esc(level.blurb) + "</p>" +
      dots(items, current) +
      '<button class="primary" type="button" data-go="learn">' + (items.some(function (item) { return item.learned; }) ? "Continue today's words" : "Start today's words") + "</button>";
    if (mode === "quiz") {
      title = "Quiz time.";
      body = "<p>You have learned " + state.learned.length + " words. Show what you remember with 10 questions.</p>" +
        '<button class="primary" type="button" data-go="quiz">Start the quiz</button>';
    } else if (mode === "done") {
      title = "You did it for today.";
      body = "<p>Come back tomorrow. The next five words will be a step harder.</p>" +
        '<button class="secondary" type="button" data-go="review">Review what you know</button>';
    } else if (mode === "champion") {
      title = "You learned the whole path.";
      body = '<button class="primary" type="button" data-go="review">Review your words</button>';
    }
    var learned = state.learned.length;
    var into = learned % quest.QUIZ_EVERY;
    var until = quest.quizDue(state) ? 0 : (into === 0 ? quest.QUIZ_EVERY : quest.QUIZ_EVERY - into);
    var shownStreak = (function () {
      var message = quest.streakMessage(state, day);
      var found = message.match(/(\d+)-day/);
      return found ? found[1] : "0";
    })();
    var here = currentLevelNumber();
    var path = "";
    for (var levelNo = 1; levelNo <= 6; levelNo++) {
      var meta = levelMeta(levelNo);
      var count = state.learned.filter(function (item) {
        return words.some(function (word) { return word.text === item.text && word.level === levelNo; });
      }).length;
      var cls = count >= 30 ? "done" : (levelNo === here ? "current" : (levelNo > here ? "locked" : "done"));
      path += '<li class="' + cls + '"><b>' + meta.emoji + " " + esc(meta.name) + "</b><span>" + count + "/30</span></li>";
    }
    return '<section class="hero-card"><p class="kicker">Hi, ' + esc(state.name) + "</p><h1>" + title + "</h1><p class=\"streak\">" +
      esc(quest.streakMessage(state, day)) + "</p>" + banner() + '<div class="mission">' + body + "</div></section>" +
      '<section class="stat-row"><article><strong>' + learned + '</strong><span>words learned</span></article><article><strong>' +
      until + "</strong><span>" + (until ? "words until a quiz" : "quiz is ready") + "</span></article><article><strong>" +
      shownStreak + '</strong><span>day streak</span></article></section>' +
      '<section class="card"><h2>Your path gets harder</h2><p class="muted">Each level is tougher than the one before.</p><ol class="path">' + path + "</ol></section>";
  }

  function learnHtml() {
    var day = today();
    if (quest.screen(state, words, day) === "quiz") return quizHtml();
    var items = quest.board(state, words, day);
    var word = quest.currentWord(state, words, day);
    if (!word) return homeHtml();
    var meta = levelMeta(word.level);
    var options = quest.choicesFor(state, word, words, decoys, day);
    var pips = "";
    for (var i = 1; i <= 6; i++) pips += '<i class="' + (i <= word.level ? "on" : "") + '"></i>';
    return banner() + dots(items, word) +
      '<article class="word-card"><p class="kicker">Level ' + word.level + " of 6 · " + esc(meta.name) + "</p>" +
      '<p class="pips" aria-label="Difficulty ' + word.level + ' of 6">' + pips + "</p>" +
      '<h1 class="word">' + esc(word.text) + "</h1>" +
      '<p class="pron">' + esc(word.pronunciation) + " · " + esc(word.part_of_speech) + "</p>" +
      '<button class="hear" type="button" data-speak="' + esc(word.text + ". " + word.example) + '">Hear it</button>' +
      "<blockquote>" + esc(word.example) + "</blockquote>" +
      '<details class="peek"' + (wrong ? " open" : "") + "><summary>Need a peek at the meaning?</summary><p>" +
      esc(word.meaning) + "</p><p><b>" + esc(word.tip) + "</b></p></details></article>" +
      '<form class="stack" data-answer="learn"><h2>What does it mean?</h2><div class="choices">' +
      options.map(function (choice) {
        return '<button class="choice" type="submit" name="choice" value="' + esc(choice) + '">' + esc(choice) + "</button>";
      }).join("") + "</div></form>";
  }

  function quizHtml() {
    var quiz = quest.startQuiz(state, words);
    save();
    if (!quiz) return homeHtml();
    var question = null;
    var index = 0;
    quiz.questions.forEach(function (item, i) {
      if (!question && !item.selected) {
        question = item;
        index = i;
      }
    });
    if (!question) return resultHtml();
    var word = words.filter(function (item) { return item.text === question.text; })[0];
    var marks = quiz.questions.map(function (item, i) {
      var cls = item.selected ? "done" : (i === index ? "now" : "");
      return '<li class="' + cls + '">' + (i + 1) + "</li>";
    }).join("");
    return banner() + '<p class="kicker">Question ' + (index + 1) + " of " + quiz.questions.length + "</p><ol class=\"dots\">" + marks + "</ol>" +
      '<article class="word-card"><h1 class="word">' + esc(word.text) + "</h1><p class=\"pron\">" + esc(word.pronunciation) +
      " · " + esc(word.part_of_speech) + '</p><button class="hear" type="button" data-speak="' + esc(word.text) +
      '">Hear it</button><p class="streak">What does this word mean?</p></article>' +
      '<form class="stack" data-answer="quiz" data-index="' + index + '"><div class="choices">' +
      question.choices.map(function (choice) {
        return '<button class="choice" type="submit" value="' + esc(choice) + '">' + esc(choice) + "</button>";
      }).join("") + "</div></form>";
  }

  function resultHtml() {
    var quiz = state.quiz;
    if (!quiz) return homeHtml();
    var score = quiz.score || 0;
    var total = quiz.questions.length;
    var lead = score === total ? "Perfect. Olive is doing a happy spin." :
      score >= 8 ? "Wonderful. Those words really stuck." :
      score >= 6 ? "Good work. A little more practice and they will stick." :
      "Brave try. Let's look at the tricky ones together.";
    var details = quiz.questions.map(function (question) {
      var word = words.filter(function (item) { return item.text === question.text; })[0];
      var ok = question.selected === question.correct;
      if (ok) return '<details class="result ok"><summary>' + esc(word.text) + " — correct</summary><p>" + esc(word.meaning) + "</p></details>";
      return '<article class="result miss"><h3>' + esc(word.text) + "</h3><p><b>Meaning:</b> " + esc(question.correct) +
        "</p><p class=\"muted\">You picked: " + esc(question.selected) + "</p><p class=\"example\">" + esc(word.example) + "</p></article>";
    }).join("");
    return '<section class="hero-card"><p class="kicker">Quiz</p><h1>' + score + " / " + total + "</h1><p class=\"lead\">" + lead +
      '</p><button class="primary" type="button" data-go="finish-quiz">Back to today</button></section><section class="card"><h2>Let\'s check the answers</h2>' +
      details + "</section>";
  }

  function progressHtml() {
    var day = today();
    var here = currentLevelNumber();
    var blocks = "";
    for (var levelNo = 1; levelNo <= 6; levelNo++) {
      var meta = levelMeta(levelNo);
      var known = words.filter(function (word) {
        return word.level === levelNo && state.learned.some(function (item) { return item.text === word.text; });
      });
      var cls = known.length >= 30 ? "done" : (levelNo === here ? "current" : (levelNo > here ? "locked" : ""));
      blocks += '<article class="' + cls + '"><h3>' + meta.emoji + " " + esc(meta.name) + " · " + known.length +
        '/30</h3><div class="track"><div class="bar" style="width:' + (known.length / 30 * 100) + '%"></div></div><p>' +
        esc(meta.blurb) + "</p>" + (levelNo > here ? "<p class=\"muted\">Still ahead.</p>" :
        '<ul class="chips">' + known.map(function (word) { return "<li>" + esc(word.text) + "</li>"; }).join("") + "</ul>") + "</article>";
    }
    var quizzes = Object.keys(state.quizzes).sort(function (a, b) { return a - b; }).map(function (key) {
      var quiz = state.quizzes[key];
      return "<li>After " + key + " words: <b>" + quiz.score + "/" + quiz.total + "</b></li>";
    }).join("");
    return '<section class="hero-card"><p class="kicker">' + esc(state.name) + '\'s progress</p><h1>' + state.learned.length +
      " words learned</h1><p>" + esc(quest.streakMessage(state, day)) + "</p></section><section class=\"card\"><h2>Levels</h2>" +
      blocks + "</section><section class=\"card\"><h2>Quizzes</h2>" + (quizzes ? "<ul>" + quizzes + "</ul>" : "<p>Your first quiz unlocks after 30 words.</p>") + "</section>";
  }

  function reviewHtml() {
    if (!state.learned.length) {
      return '<section class="hero-card"><h1>Words you already know</h1><p>Learn today\'s words first.</p><button class="primary" type="button" data-go="learn">Start learning</button></section>';
    }
    var html = '<section class="hero-card"><h1>Words you already know</h1><label for="filter">Find a word</label><input id="filter" type="search" placeholder="Try brave or ancient"></section>';
    for (var levelNo = 1; levelNo <= 6; levelNo++) {
      var known = words.filter(function (word) {
        return word.level === levelNo && state.learned.some(function (item) { return item.text === word.text; });
      });
      if (!known.length) continue;
      var meta = levelMeta(levelNo);
      html += '<section class="card"><h2>' + meta.emoji + " " + esc(meta.name) + "</h2>" + known.map(function (word) {
        return '<details class="review" data-word="' + esc(word.text.toLowerCase()) + '" data-meaning="' + esc(word.meaning.toLowerCase()) +
          '"><summary>' + esc(word.text) + "</summary><p class=\"pron\">" + esc(word.pronunciation) + "</p><p>" + esc(word.meaning) +
          "</p><p class=\"example\">" + esc(word.example) + '</p><button class="hear" type="button" data-speak="' +
          esc(word.text + ". " + word.meaning) + '">Hear it</button></details>';
      }).join("") + "</section>";
    }
    return html;
  }

  function welcomeHtml() {
    return '<section class="hero-card"><p class="kicker">Olive the owl says hello</p><h1>Five new words a day.</h1>' +
      '<p class="lead">Every correct answer gives a sparkie. Words start friendly and get harder. Progress stays on this computer.</p>' +
      (note ? banner() : "") +
      '<form class="stack" data-answer="welcome"><label for="name">What should Olive call you?</label>' +
      '<input id="name" name="name" maxlength="20" autocomplete="nickname" placeholder="Your name" autofocus>' +
      '<button class="primary" type="submit">Let\'s go</button></form></section>';
  }

  function timeupHtml() {
    return '<section class="hero-card"><p class="kicker">Olive is tucking the words in</p><h1>That\'s 15 minutes.</h1>' +
      "<p class=\"lead\">Your words are saved on this computer. Word Quest opens again tomorrow.</p><p class=\"streak\">" +
      state.learned.length + " words learned · " + esc(quest.streakMessage(state, today())) + "</p></section>";
  }

  function draw(nextView, sparkleAt) {
    var day = today();
    var locked = state.name && state.usageDate === day && state.secondsUsed >= quest.LIMIT;
    if (locked) nextView = "timeup";
    else if (!state.name) nextView = "welcome";
    else if (!nextView || nextView === "home" || nextView === "learn" || nextView === "quiz") {
      var mode = quest.screen(state, words, day);
      if (!nextView || nextView === "home") {
        if (mode === "result") nextView = "result";
        else nextView = "home";
      } else if (nextView === "learn" && (mode === "quiz" || mode === "result" || mode === "done" || mode === "champion" || mode === "timeup")) {
        nextView = mode === "quiz" ? "quiz" : (mode === "result" ? "result" : "home");
      }
    }
    view = nextView;
    var html = view === "welcome" ? welcomeHtml() :
      view === "timeup" ? timeupHtml() :
      view === "learn" ? learnHtml() :
      view === "quiz" ? quizHtml() :
      view === "result" ? resultHtml() :
      view === "progress" ? progressHtml() :
      view === "review" ? reviewHtml() : homeHtml();
    document.getElementById("app").innerHTML = html;
    renderNav(locked || view === "welcome");
    if (sparkleAt) burst(sparkleAt.x, sparkleAt.y);
    var field = document.getElementById("name") || document.getElementById("filter");
    if (field) field.focus();
  }

  document.body.addEventListener("click", function (event) {
    var speak = event.target.closest("[data-speak]");
    if (speak && window.speechSynthesis) {
      var utterance = new SpeechSynthesisUtterance(speak.getAttribute("data-speak"));
      utterance.rate = 0.9;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    }
    var go = event.target.closest("[data-go]");
    if (!go) return;
    var target = go.getAttribute("data-go");
    note = null;
    wrong = false;
    if (target === "switch") {
      state.name = "";
      save();
      draw("welcome");
      return;
    }
    if (target === "finish-quiz") {
      if (state.quiz && state.quiz.score >= 8) burst(window.innerWidth / 2, 180);
      state.quiz = null;
      quest.ensurePlan(state, words, today());
      save();
      draw("home");
      return;
    }
    if (target === "quiz") {
      quest.startQuiz(state, words);
      save();
      draw("quiz");
      return;
    }
    draw(target);
  });

  document.body.addEventListener("submit", function (event) {
    var form = event.target.closest("form");
    if (!form) return;
    event.preventDefault();
    var kind = form.getAttribute("data-answer");
    if (kind === "welcome") {
      var name = quest.cleanName(form.name.value);
      if (!name) {
        note = { kind: "bad", text: "Use a name with letters, like Maya or Jo." };
        draw("welcome");
        return;
      }
      state.name = name;
      note = { kind: "level", text: "We'll start with Seedling words. They will get harder as you grow." };
      save();
      draw("home");
      return;
    }
    var button = event.submitter;
    var choice = button ? button.value : "";
    var day = today();
    if (kind === "learn") {
      var word = quest.currentWord(state, words, day);
      if (!word) return draw("home");
      if (choice !== word.meaning) {
        wrong = true;
        note = { kind: "bad", text: "Not quite. Peek at the meaning, then try again." };
        draw("learn");
        var shaken = document.querySelector('button.choice[value="' + choice.replace(/"/g, '\\"') + '"]');
        if (shaken) shaken.classList.add("shake");
        return;
      }
      var result = quest.markCorrect(state, words, word.text, day);
      var point = button.getBoundingClientRect();
      note = { kind: "good", text: "Yes! “" + word.text + "” is yours." };
      if (result.kind === "up" && result.word) {
        var meta = levelMeta(result.word.level);
        note = { kind: "level", text: "New level: " + meta.emoji + " " + meta.name + ". " + meta.blurb };
      }
      if (quest.quizDue(state)) note = { kind: "level", text: "You have learned " + state.learned.length + " words. Quiz time!" };
      else if (quest.wordsFinished(state, day)) note = { kind: "good", text: "Those are your words for today. Come back tomorrow for five more." };
      if (result.fresh) giveSparkie(point.left + point.width / 2, point.top + point.height / 2);
      save();
      setTimeout(function () {
        draw(quest.wordsFinished(state, day) || quest.quizDue(state) ? "home" : "learn");
      }, 900);
      return;
    }
    if (kind === "quiz") {
      var index = Number(form.getAttribute("data-index"));
      var before = state.quiz.questions[index];
      var correct = before && !before.selected && choice === before.correct;
      quest.answerQuiz(state, index, choice, day);
      if (correct && button) {
        var rect = button.getBoundingClientRect();
        giveSparkie(rect.left + rect.width / 2, rect.top + rect.height / 2);
      }
      save();
      setTimeout(function () {
        draw(state.quiz && state.quiz.done ? "result" : "quiz");
      }, correct ? 900 : 0);
    }
  });

  document.body.addEventListener("input", function (event) {
    if (event.target.id !== "filter") return;
    var query = event.target.value.trim().toLowerCase();
    document.querySelectorAll("[data-word]").forEach(function (item) {
      var hay = (item.getAttribute("data-word") || "") + " " + (item.getAttribute("data-meaning") || "");
      item.hidden = query.length > 0 && hay.indexOf(query) === -1;
    });
  });

  setInterval(function () {
    if (!state.name || document.hidden) return;
    var day = today();
    var before = remaining();
    quest.tick(state, day, true);
    save();
    if (before > 0 && remaining() === 0) draw("timeup");
    else if (view !== "timeup") renderNav(false);
  }, 1000);

  draw(state.name ? "home" : "welcome");
})();
