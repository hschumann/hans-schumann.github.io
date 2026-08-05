(function () {
  const params = new URLSearchParams(window.location.search);
  const usernameFromUrl = params.get("user");
  const usernameFromStorage = sessionStorage.getItem("nfl-probabilities-username");
  const username = (usernameFromUrl || usernameFromStorage || "").trim();

  if (!username) {
    window.location.replace("index.html");
    return;
  }

  sessionStorage.setItem("nfl-probabilities-username", username);
  document.getElementById("username-display").textContent = username;

  const config = window.NFL_PROBABILITIES_CONFIG || {};
  const statusEl = document.getElementById("game-status");
  const weekEl = document.getElementById("week-label");
  const gamesEl = document.getElementById("games-list");
  const submitBtn = document.getElementById("submit-predictions");
  const submitStatusEl = document.getElementById("submit-status");

  let currentWeek = null;
  let currentGames = [];

  const apiBase = (config.apiUrl || "").replace(/\/+$/, "");

  if (!apiBase) {
    showStatus(
      "setup",
      "This game is not connected yet. Deploy the Cloudflare Worker, then set apiUrl in config.js."
    );
    return;
  }

  loadGames();

  submitBtn.addEventListener("click", submitPredictions);

  async function loadGames() {
    showStatus("loading", "Loading this week\u2019s games\u2026");
    gamesEl.innerHTML = "";
    submitBtn.disabled = true;
    submitStatusEl.textContent = "";
    submitStatusEl.className = "submit-status";

    try {
      const response = await fetch(
        apiBase + "/games?user=" + encodeURIComponent(username)
      );
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || "Could not load games");
      }

      if (!data.games || !data.games.length) {
        showStatus("empty", "No games found for the latest week yet.");
        weekEl.textContent = "";
        return;
      }

      currentWeek = data.week;
      currentGames = await hydrateSavedPicks_(data.games, data.week);

      weekEl.textContent = data.weekLabel || "Week " + data.week;
      renderGames(currentGames);
      clearStatus();

      var savedCount = currentGames.filter(function (game) {
        return isFinite(Number(game.userAwayWinPct));
      }).length;
      var openCount = currentGames.filter(function (game) {
        return !game.locked;
      }).length;

      submitBtn.disabled = openCount === 0;
      submitBtn.textContent =
        savedCount > 0 ? "Update predictions" : "Submit predictions";

      if (openCount === 0) {
        submitStatusEl.textContent = "All games are locked for this week.";
      } else if (savedCount > 0) {
        submitStatusEl.textContent =
          "Welcome back — your saved picks are loaded. Edit and update anytime before games lock.";
        submitStatusEl.className = "submit-status";
      }
    } catch (err) {
      showStatus("error", err.message || "Could not load games. Try again later.");
      weekEl.textContent = "";
    }
  }

  function matchupKey_(away, home) {
    return (
      String(away || "").trim().toLowerCase() +
      "|" +
      String(home || "").trim().toLowerCase()
    );
  }

  function localPicksKey_(week) {
    return (
      "nfl-probabilities-picks:" +
      username.toLowerCase() +
      ":week:" +
      String(week)
    );
  }

  function savePicksLocally_(week, predictions) {
    try {
      localStorage.setItem(
        localPicksKey_(week),
        JSON.stringify({
          savedAt: Date.now(),
          predictions: predictions,
        })
      );
    } catch (err) {
      /* ignore quota / private mode */
    }
  }

  function loadPicksLocally_(week) {
    try {
      var raw = localStorage.getItem(localPicksKey_(week));
      if (!raw) {
        return [];
      }
      var parsed = JSON.parse(raw);
      return parsed && parsed.predictions ? parsed.predictions : [];
    } catch (err) {
      return [];
    }
  }

  async function hydrateSavedPicks_(games, week) {
    var byMatchup = {};

    // 1) Values already attached by /games?user=
    games.forEach(function (game) {
      if (isFinite(Number(game.userAwayWinPct))) {
        byMatchup[matchupKey_(game.away, game.home)] = Number(game.userAwayWinPct);
      }
    });

    // 2) Explicit user-predictions endpoint (server sheet)
    try {
      const response = await fetch(
        apiBase +
          "/user-predictions?user=" +
          encodeURIComponent(username) +
          "&week=" +
          encodeURIComponent(String(week))
      );
      const data = await response.json();
      if (response.ok && data && Array.isArray(data.predictions)) {
        data.predictions.forEach(function (pick) {
          var key = matchupKey_(pick.away, pick.home);
          if (byMatchup[key] === undefined && isFinite(Number(pick.awayWinPct))) {
            byMatchup[key] = Number(pick.awayWinPct);
          }
        });
      }
    } catch (err) {
      /* server may not have this action yet */
    }

    // 3) Browser backup from last successful submit
    loadPicksLocally_(week).forEach(function (pick) {
      var key = matchupKey_(pick.away, pick.home);
      if (byMatchup[key] === undefined && isFinite(Number(pick.awayWinPct))) {
        byMatchup[key] = Number(pick.awayWinPct);
      }
    });

    return games.map(function (game) {
      var key = matchupKey_(game.away, game.home);
      if (byMatchup[key] !== undefined) {
        game.userAwayWinPct = byMatchup[key];
      }
      return game;
    });
  }

  function renderGames(games) {
    gamesEl.innerHTML = "";

    games.forEach(function (game, index) {
      const card = document.createElement("article");
      card.className =
        "prob-game-card" + (game.locked ? " prob-game-card-locked" : "");
      card.dataset.index = String(index);

      // Slider value = home win % (dot on the right favors home / Seattle).
      var initialAwayPct = 50;
      if (isFinite(Number(game.userAwayWinPct))) {
        initialAwayPct = Math.max(
          1,
          Math.min(99, Math.round(Number(game.userAwayWinPct)))
        );
      }
      var initialHomePct = 100 - initialAwayPct;

      card.innerHTML =
        '<div class="prob-scale">' +
        '<div class="prob-side prob-side-away">' +
        '<span class="prob-team">' +
        escapeHtml(game.away) +
        "</span>" +
        '<output class="prob-pct" for="prob-slider-' +
        index +
        '">' +
        initialAwayPct +
        "%</output>" +
        "</div>" +
        '<div class="prob-side prob-side-home">' +
        '<span class="prob-team">' +
        escapeHtml(game.home) +
        "</span>" +
        '<output class="prob-pct" for="prob-slider-' +
        index +
        '">' +
        initialHomePct +
        "%</output>" +
        "</div>" +
        "</div>" +
        (game.locked
          ? '<p class="prob-locked-badge">Final &mdash; predictions locked</p>'
          : "") +
        '<label class="visually-hidden" for="prob-slider-' +
        index +
        '">Drag toward ' +
        escapeHtml(game.away) +
        " or " +
        escapeHtml(game.home) +
        "</label>" +
        '<div class="prob-slider-wrap">' +
        '<div class="prob-vegas" hidden>' +
        '<div class="prob-vegas-marker" aria-hidden="true"></div>' +
        '<p class="prob-vegas-label"></p>' +
        "</div>" +
        '<input class="prob-slider" type="range" min="1" max="99" step="1" value="' +
        initialHomePct +
        '" id="prob-slider-' +
        index +
        '" aria-valuemin="1" aria-valuemax="99" aria-valuenow="' +
        initialHomePct +
        '"' +
        (game.locked ? " disabled" : "") +
        " />" +
        '<div class="prob-ticks" aria-hidden="true">' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick prob-tick-mid"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        '<span class="prob-tick"></span>' +
        "</div>" +
        "</div>" +
        '<div class="prob-points">' +
        '<p class="prob-points-win"></p>' +
        '<p class="prob-points-loss"></p>' +
        "</div>";

      gamesEl.appendChild(card);

      const slider = card.querySelector(".prob-slider");
      renderVegasMarker(card, game);
      updatePredictionUI(card, game, Number(slider.value));

      if (!game.locked) {
        slider.addEventListener("input", function () {
          updatePredictionUI(card, game, Number(slider.value));
        });
      }
    });
  }

  function renderVegasMarker(card, game) {
    const vegasEl = card.querySelector(".prob-vegas");
    const labelEl = card.querySelector(".prob-vegas-label");
    const vegas = getVegasFavorite(game);

    if (!vegas) {
      vegasEl.hidden = true;
      return;
    }

    // Track is home-win % left→right, so marker uses home probability.
    vegasEl.style.setProperty("--vegas-pos", vegas.homePct + "%");
    labelEl.innerHTML =
      "Vegas<br>" +
      escapeHtml(vegas.team) +
      "<br>" +
      formatPct(vegas.favoritePct) +
      "%";
    vegasEl.hidden = false;
  }

  function getVegasFavorite(game) {
    const awayPct = Number(game.vegasAwayPct);
    const homePct = Number(game.vegasHomePct);

    if (!isFinite(awayPct) && !isFinite(homePct)) {
      return null;
    }

    var resolvedAway = isFinite(awayPct)
      ? awayPct
      : isFinite(homePct)
        ? 100 - homePct
        : null;
    var resolvedHome = isFinite(homePct)
      ? homePct
      : isFinite(awayPct)
        ? 100 - awayPct
        : null;

    if (resolvedAway === null || resolvedHome === null) {
      return null;
    }

    if (resolvedAway >= resolvedHome) {
      return {
        team: game.away,
        favoritePct: resolvedAway,
        homePct: resolvedHome,
      };
    }

    return {
      team: game.home,
      favoritePct: resolvedHome,
      homePct: resolvedHome,
    };
  }

  function formatPct(value) {
    return Number.isInteger(value)
      ? String(value)
      : String(Math.round(value * 10) / 10);
  }

  /** sliderValue is home win % (dot toward the right favors home). */
  function updatePredictionUI(card, game, homePct) {
    const awayPct = 100 - homePct;
    const favoriteIsAway = awayPct >= homePct;
    const team = favoriteIsAway ? game.away : game.home;
    const prob = (favoriteIsAway ? awayPct : homePct) / 100;
    const winPts = scoreWin(prob);
    const lossPts = scoreLoss(prob);

    const slider = card.querySelector(".prob-slider");
    const awayPctEl = card.querySelector(".prob-side-away .prob-pct");
    const homePctEl = card.querySelector(".prob-side-home .prob-pct");
    const winEl = card.querySelector(".prob-points-win");
    const lossEl = card.querySelector(".prob-points-loss");

    awayPctEl.textContent = awayPct + "%";
    homePctEl.textContent = homePct + "%";
    slider.setAttribute("aria-valuenow", String(homePct));
    winEl.textContent = formatPointsLine(winPts, team, "win");
    lossEl.textContent = formatPointsLine(lossPts, team, "loss");
  }

  /** win: round(100 * (0.25 - (1 - prob)^2), 1) */
  function scoreWin(prob) {
    return round1(100 * (0.25 - Math.pow(1 - prob, 2)));
  }

  /** loss: round(100 * (0.25 - prob^2), 1) */
  function scoreLoss(prob) {
    return round1(100 * (0.25 - Math.pow(prob, 2)));
  }

  function round1(value) {
    return Math.round(value * 10) / 10;
  }

  function formatPointsLine(points, team, outcome) {
    const signed = points > 0 ? "+" + points : String(points);
    return signed + " points for " + team + " " + outcome;
  }

  async function submitPredictions() {
    submitStatusEl.textContent = "";
    submitStatusEl.className = "submit-status";
    submitBtn.disabled = true;

    const predictions = currentGames
      .map(function (game, index) {
        if (game.locked) {
          return null;
        }
        const slider = document.getElementById("prob-slider-" + index);
        return {
          away: game.away,
          home: game.home,
          awayWinPct: 100 - Number(slider.value),
        };
      })
      .filter(Boolean);

    if (!predictions.length) {
      submitStatusEl.textContent = "No open games to submit.";
      submitStatusEl.className = "submit-status submit-status-error";
      submitBtn.disabled = false;
      return;
    }

    try {
      const response = await fetch(apiBase + "/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username,
          week: currentWeek,
          predictions: predictions,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || "Could not save predictions");
      }

      savePicksLocally_(currentWeek, predictions);

      window.location.href =
        "thanks.html?user=" +
        encodeURIComponent(username) +
        "&week=" +
        encodeURIComponent(String(currentWeek || ""));
    } catch (err) {
      submitStatusEl.textContent = err.message || "Could not save predictions.";
      submitStatusEl.className = "submit-status submit-status-error";
      var openCount = currentGames.filter(function (game) {
        return !game.locked;
      }).length;
      submitBtn.disabled = openCount === 0;
    }
  }

  function showStatus(kind, message) {
    statusEl.hidden = false;
    statusEl.className = "game-status game-status-" + kind;
    statusEl.textContent = message;
  }

  function clearStatus() {
    statusEl.hidden = true;
    statusEl.textContent = "";
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();
