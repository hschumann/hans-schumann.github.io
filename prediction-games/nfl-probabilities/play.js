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

    try {
      const response = await fetch(apiBase + "/games");
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
      currentGames = data.games;

      weekEl.textContent = data.weekLabel || "Week " + data.week;
      renderGames(data.games);
      clearStatus();
      submitBtn.disabled = false;
    } catch (err) {
      showStatus("error", err.message || "Could not load games. Try again later.");
      weekEl.textContent = "";
    }
  }

  function renderGames(games) {
    gamesEl.innerHTML = "";

    games.forEach(function (game, index) {
      const card = document.createElement("article");
      card.className = "prob-game-card";
      card.dataset.index = String(index);

      card.innerHTML =
        '<div class="prob-scale">' +
        '<div class="prob-side prob-side-away">' +
        '<span class="prob-team" id="prob-away-name-' +
        index +
        '">' +
        escapeHtml(game.away) +
        "</span>" +
        '<output class="prob-pct" id="prob-away-pct-' +
        index +
        '" for="prob-slider-' +
        index +
        '">50%</output>' +
        "</div>" +
        '<div class="prob-side prob-side-home">' +
        '<span class="prob-team" id="prob-home-name-' +
        index +
        '">' +
        escapeHtml(game.home) +
        "</span>" +
        '<output class="prob-pct" id="prob-home-pct-' +
        index +
        '" for="prob-slider-' +
        index +
        '">50%</output>' +
        "</div>" +
        "</div>" +
        '<label class="visually-hidden" for="prob-slider-' +
        index +
        '">Win probability for ' +
        escapeHtml(game.away) +
        "</label>" +
        '<div class="prob-slider-wrap">' +
        '<div class="prob-vegas" hidden>' +
        '<div class="prob-vegas-marker" aria-hidden="true"></div>' +
        '<p class="prob-vegas-label"></p>' +
        "</div>" +
        '<input class="prob-slider" type="range" min="1" max="99" step="1" value="50" ' +
        'id="prob-slider-' +
        index +
        '" aria-valuemin="1" aria-valuemax="99" aria-valuenow="50" />' +
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
        '<div class="prob-points" id="prob-points-' +
        index +
        '">' +
        '<p class="prob-points-win" id="prob-win-' +
        index +
        '"></p>' +
        '<p class="prob-points-loss" id="prob-loss-' +
        index +
        '"></p>' +
        "</div>";

      gamesEl.appendChild(card);

      const slider = card.querySelector(".prob-slider");
      renderVegasMarker(card, game);
      updatePredictionUI(card, game, Number(slider.value));

      slider.addEventListener("input", function () {
        updatePredictionUI(card, game, Number(slider.value));
      });
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

    // Marker is positioned along the away-win axis (0% left → 100% right).
    vegasEl.style.setProperty("--vegas-away-pct", vegas.awayPct + "%");
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
        awayPct: resolvedAway,
      };
    }

    return {
      team: game.home,
      favoritePct: resolvedHome,
      awayPct: resolvedAway,
    };
  }

  function formatPct(value) {
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 10) / 10);
  }

  function updatePredictionUI(card, game, awayPct) {
    const homePct = 100 - awayPct;
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
    slider.setAttribute("aria-valuenow", String(awayPct));
    winEl.textContent = formatPointsLine(winPts, team, "win");
    lossEl.textContent = formatPointsLine(lossPts, team, "loss");
  }

  /** win: round(100 * (0.25 - (1 - prob)^2), 1) */
  function scoreWin(prob) {
    return round1(100 * (0.25 - Math.pow(1 - prob, 2)));
  }

  /** loss: round(100 * (0.25 - prob^2), 1) — larger magnitude than win when prob ≠ 0.5 */
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

    const predictions = currentGames.map(function (game, index) {
      const slider = document.getElementById("prob-slider-" + index);
      return {
        away: game.away,
        home: game.home,
        awayWinPct: Number(slider.value),
      };
    });

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

      submitStatusEl.textContent = "Predictions saved!";
      submitStatusEl.className = "submit-status submit-status-success";
    } catch (err) {
      submitStatusEl.textContent = err.message || "Could not save predictions.";
      submitStatusEl.className = "submit-status submit-status-error";
    } finally {
      submitBtn.disabled = false;
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
