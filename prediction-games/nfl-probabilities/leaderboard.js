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

  document.getElementById("link-others").href = "others.html" + q;
  document.getElementById("link-home").href = "index.html";
  document.getElementById("link-play").href =
    "play.html" + (user ? "?user=" + encodeURIComponent(user) : "");

  const config = window.NFL_PROBABILITIES_CONFIG || {};
  const apiBase = (config.apiUrl || "").replace(/\/+$/, "");
  const statusEl = document.getElementById("leaderboard-status");
  const theadEl = document.getElementById("leaderboard-thead");
  const tbodyEl = document.getElementById("leaderboard-tbody");

  let weeks = [];
  let players = [];
  let sortKey = "total";
  let sortDir = "desc";

  if (!apiBase) {
    showStatus("This page is not connected to a data source yet.");
    return;
  }

  loadLeaderboard();

  async function loadLeaderboard() {
    showStatus("Loading leaderboard\u2026");
    theadEl.innerHTML = "";
    tbodyEl.innerHTML = "";

    try {
      const response = await fetch(apiBase + "/leaderboard");
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error || "Could not load leaderboard");
      }

      weeks = data.weeks || [];
      players = data.players || [];

      if (!players.length) {
        showStatus("No predictions to rank yet.");
        renderEmptyHeader();
        return;
      }

      renderTable();
      clearStatus();
    } catch (err) {
      showStatus(err.message || "Could not load leaderboard.");
    }
  }

  function renderEmptyHeader() {
    var headRow = document.createElement("tr");
    ["Player", "Total Score"].forEach(function (label) {
      var th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    theadEl.appendChild(headRow);
  }

  function renderTable() {
    theadEl.innerHTML = "";
    tbodyEl.innerHTML = "";

    var sorted = players.slice().sort(comparePlayers);
    var weekOrder = weeks
      .map(function (_, index) {
        return index;
      })
      .reverse();
    var headRow = document.createElement("tr");

    var thName = sortHeader("Player", "name", false);
    thName.classList.add("leaderboard-sticky-name");
    headRow.appendChild(thName);
    var thTotal = sortHeader("Total Score", "total", true);
    thTotal.classList.add("leaderboard-sticky-total");
    headRow.appendChild(thTotal);
    weekOrder.forEach(function (index) {
      headRow.appendChild(sortHeader("Week " + weeks[index], "week:" + index, true));
    });
    theadEl.appendChild(headRow);

    sorted.forEach(function (player) {
      var tr = document.createElement("tr");
      if (user && player.name.toLowerCase() === user.toLowerCase()) {
        tr.className = "leaderboard-you";
      }

      var tdName = document.createElement("td");
      tdName.className = "leaderboard-player leaderboard-sticky-name";
      tdName.textContent = player.name;
      tr.appendChild(tdName);

      var tdTotal = document.createElement("td");
      tdTotal.className = "num leaderboard-sticky-total";
      tdTotal.textContent = formatScore(player.total);
      tr.appendChild(tdTotal);

      var weekScores = player.weekScores || [];
      weekOrder.forEach(function (index) {
        var score = weekScores[index];
        var td = document.createElement("td");
        td.className = "num";
        if (score === null || score === undefined) {
          td.classList.add("leaderboard-empty");
          td.textContent = "\u2014";
        } else {
          td.textContent = formatScore(score);
        }
        tr.appendChild(td);
      });

      tbodyEl.appendChild(tr);
    });

    updateStickyOffset();
  }

  function updateStickyOffset() {
    var nameCell = theadEl.querySelector(".leaderboard-sticky-name");
    if (nameCell) {
      document
        .getElementById("leaderboard-table")
        .style.setProperty("--leaderboard-name-width", nameCell.offsetWidth + "px");
    }
  }

  window.addEventListener("resize", updateStickyOffset);

  function sortHeader(label, key, numeric) {
    var th = document.createElement("th");
    th.scope = "col";
    if (numeric) {
      th.className = "num";
    }

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "leaderboard-sort";
    btn.textContent = label;
    if (sortKey === key) {
      btn.classList.add(sortDir === "asc" ? "is-asc" : "is-desc");
      btn.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
    } else {
      btn.setAttribute("aria-sort", "none");
    }
    btn.addEventListener("click", function () {
      if (sortKey === key) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortKey = key;
        sortDir = key === "name" ? "asc" : "desc";
      }
      renderTable();
    });

    th.appendChild(btn);
    return th;
  }

  function comparePlayers(a, b) {
    var av = sortValue(a);
    var bv = sortValue(b);
    var cmp;

    if (typeof av === "string" || typeof bv === "string") {
      cmp = String(av).toLowerCase().localeCompare(String(bv).toLowerCase());
    } else {
      var an = av === null ? -Infinity : av;
      var bn = bv === null ? -Infinity : bv;
      cmp = an === bn ? 0 : an < bn ? -1 : 1;
    }

    if (cmp === 0) {
      cmp = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    }
    return sortDir === "asc" ? cmp : -cmp;
  }

  function sortValue(player) {
    if (sortKey === "name") {
      return player.name;
    }
    if (sortKey === "total") {
      return player.total;
    }
    if (sortKey.indexOf("week:") === 0) {
      var index = Number(sortKey.slice(5));
      var score = player.weekScores ? player.weekScores[index] : null;
      return score === undefined ? null : score;
    }
    return player.total;
  }

  function formatScore(value) {
    if (value === null || value === undefined || !isFinite(Number(value))) {
      return "\u2014";
    }
    var n = Number(value);
    if (Object.is(n, -0)) {
      n = 0;
    }
    return Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10);
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
