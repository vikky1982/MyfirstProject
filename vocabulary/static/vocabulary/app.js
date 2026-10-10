(function () {
  document.querySelectorAll(".tz-offset").forEach(function (input) {
    input.value = String(new Date().getTimezoneOffset());
  });

  function csrfToken() {
    var input = document.querySelector("#heartbeat-form input[name=csrfmiddlewaretoken]");
    if (input) return input.value;
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  var body = document.body;
  if (body.dataset.remaining) {
    var remaining = parseInt(body.dataset.remaining, 10);
    var limit = parseInt(body.dataset.limit, 10) || 1;
    var clock = document.querySelector("[data-clock]");
    var bar = document.querySelector("[data-bar]");
    var timer = document.getElementById("timer");

    function render() {
      var safe = Math.max(0, remaining);
      var minutes = Math.floor(safe / 60);
      var seconds = safe % 60;
      if (clock) {
        clock.textContent = minutes + ":" + String(seconds).padStart(2, "0");
      }
      if (bar) bar.style.width = Math.max(0, (safe / limit) * 100) + "%";
      if (timer) timer.classList.toggle("is-low", safe <= 120);
    }

    function heartbeat(active) {
      var payload = new URLSearchParams();
      payload.set("active", active ? "1" : "0");
      return fetch(body.dataset.heartbeat, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: payload,
        credentials: "same-origin"
      }).then(function (response) {
        if (!response.ok) return null;
        return response.json();
      }).then(function (data) {
        if (!data) return;
        remaining = data.remaining;
        render();
        if (remaining <= 0) window.location.assign(body.dataset.timeup);
      }).catch(function () {});
    }

    window.setInterval(function () {
      if (document.hidden) return;
      if (remaining > 0) remaining -= 1;
      render();
      if (remaining <= 0) heartbeat(true);
    }, 1000);

    window.setInterval(function () {
      if (!document.hidden) heartbeat(true);
    }, 10000);

    document.addEventListener("visibilitychange", function () {
      heartbeat(!document.hidden);
    });
    render();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-speak]");
    if (!button || !window.speechSynthesis) return;
    var utterance = new SpeechSynthesisUtterance(button.dataset.speak);
    utterance.rate = 0.9;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  });

  function burstSparkles(x, y) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var layer = document.getElementById("sparkles");
    if (!layer) return;
    var glyphs = ["✦", "✧", "✸", "★", "✶"];
    var colors = ["#f0b429", "#e36a45", "#2f7d4a", "#fff4c2", "#7eb6d9"];
    for (var i = 0; i < 26; i++) {
      var spark = document.createElement("span");
      spark.className = "spark";
      spark.textContent = glyphs[i % glyphs.length];
      spark.style.left = x + "px";
      spark.style.top = y + "px";
      spark.style.color = colors[i % colors.length];
      var angle = Math.random() * Math.PI * 2;
      var dist = 50 + Math.random() * 140;
      spark.style.setProperty("--dx", Math.cos(angle) * dist + "px");
      spark.style.setProperty("--dy", Math.sin(angle) * dist - 30 + "px");
      layer.appendChild(spark);
      setTimeout(function (node) { node.remove(); }, 750, spark);
    }
  }

  document.addEventListener("click", function (event) {
    var choice = event.target.closest("button.choice");
    if (!choice || !choice.form) return;
    choice.form.dataset.sparkX = String(event.clientX);
    choice.form.dataset.sparkY = String(event.clientY);
  }, true);

  if (document.querySelector(".banner.is-good, .banner.is-level, .is-celebrate")) {
    burstSparkles(window.innerWidth / 2, 170);
  }

  var filter = document.getElementById("filter");
  if (filter) {
    filter.addEventListener("input", function () {
      var query = filter.value.trim().toLowerCase();
      document.querySelectorAll("[data-word]").forEach(function (item) {
        var haystack = item.dataset.word + " " + item.dataset.meaning;
        item.hidden = query.length > 0 && haystack.indexOf(query) === -1;
      });
    });
  }
})();
