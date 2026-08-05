(function () {
  const params = new URLSearchParams(window.location.search);
  const user = (
    params.get("user") ||
    sessionStorage.getItem("nfl-probabilities-username") ||
    ""
  ).trim();
  const weekParam = params.get("week") || "";

  const q =
    (user ? "?user=" + encodeURIComponent(user) : "") +
    (weekParam ? (user ? "&" : "?") + "week=" + encodeURIComponent(weekParam) : "");

  document.getElementById("link-leaderboard").href = "leaderboard.html" + q;
  document.getElementById("link-home").href = "index.html";
  document.getElementById("link-play").href =
    "play.html" + (user ? "?user=" + encodeURIComponent(user) : "");

  const config = window.NFL_PROBABILITIES_CONFIG || {};
  const apiBase = (config.apiUrl || "").replace(/\/+$/, "");
  const statusEl = document.getElementById("others-status");
  const weekEl = document.getElementById("week-label");
  const captionEl = document.getElementById("others-caption");
  const theadEl = document.getElementById("others-thead");
  const tbodyEl = document.getElementById("others-tbody");

  if (!apiBase) {
    showStatus("This page is not connected to a data source yet.");
    return;
  }

  loadBoard();

  async function loadBoard() {
    showStatus("Loading predictions\u2026");
    theadEl.innerHTML = "";
    tbodyEl.innerHTML = "";

    try {
      const url =
        apiBase +
        "/others" +
        (weekParam ? "?week=" + encodeURIComponent(weekParam) : "");
      const response = await fetch(url);
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || "Could not load predictions");
      }

      if (!data.games || !data.games.length) {
        showStatus("No games found for this week yet.");
        return;
      }

      weekEl.textContent = data.weekLabel || "Week " + data.week;
      captionEl.textContent =
        (data.weekLabel || "Week " + data.week) + " participant forecasts";

      renderTable(data.participants || [], data.games);
      clearStatus();
    } catch (err) {
      showStatus(err.message || "Could not load predictions.");
    }
  }

  function renderTable(participants, games) {
    var headRow = document.createElement("tr");
    var gameTh = document.createElement("th");
    gameTh.scope = "col";
    gameTh.textContent = "Game";
    headRow.appendChild(gameTh);

    if (!participants.length) {
      var emptyTh = document.createElement("th");
      emptyTh.textContent = "No submissions yet";
      headRow.appendChild(emptyTh);
      theadEl.appendChild(headRow);

      games.forEach(function (game) {
        var tr = document.createElement("tr");
        var tdGame = document.createElement("td");
        tdGame.textContent = game.label || game.away + " @" + game.home;
        tr.appendChild(tdGame);
        var tdEmpty = document.createElement("td");
        tdEmpty.className = "others-empty";
        tdEmpty.textContent = "\u2014";
        tr.appendChild(tdEmpty);
        tbodyEl.appendChild(tr);
      });
      return;
    }

    participants.forEach(function (name) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = name;
      headRow.appendChild(th);
    });
    theadEl.appendChild(headRow);

    games.forEach(function (game) {
      var tr = document.createElement("tr");
      var tdGame = document.createElement("td");
      tdGame.className = "others-game";
      tdGame.textContent = game.label || game.away + " @" + game.home;
      tr.appendChild(tdGame);

      participants.forEach(function (name) {
        var td = document.createElement("td");
        var pick = game.picks ? game.picks[name] : null;
        if (!pick) {
          td.className = "others-empty";
          td.textContent = "\u2014";
        } else {
          td.textContent = pick.team + " " + pick.pct + "%";
        }
        tr.appendChild(td);
      });

      tbodyEl.appendChild(tr);
    });
  }

  function showStatus(message) {
    statusEl.hidden = false;
    statusEl.className = "game-status";
    statusEl.textContent = message;
  }

  function clearStatus() {
    statusEl.hidden = true;
    statusEl.textContent = "";
  }
})();
