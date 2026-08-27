(function () {
  var config = window.HT_BETS_CONFIG || {};
  var statusEl = document.getElementById("ht-status");
  var disclaimerEl = document.getElementById("ht-disclaimer");
  var liveBannerEl = document.getElementById("ht-live-banner");
  var tbody = document.querySelector("#ht-board-table tbody");
  var refreshBtn = document.getElementById("ht-refresh");
  var pollTimer = null;

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function callClass(call, liveCall) {
    var base = "ht-call";
    if (liveCall) base += " ht-call-live";
    if (call === "over") return base + " ht-call-over";
    if (call === "under") return base + " ht-call-under";
    if (call === "no_bet") return base + " ht-call-none";
    return base;
  }

  function formatEdge(edge) {
    if (edge == null || Number.isNaN(edge)) return "—";
    var sign = edge > 0 ? "+" : "";
    return sign + Number(edge).toFixed(2);
  }

  function formatPred(home, away) {
    if (home == null || away == null) return "—";
    return Number(home).toFixed(2) + "–" + Number(away).toFixed(2);
  }

  function phaseLabel(match) {
    if (match.live_call) {
      return "HALFTIME · LIVE";
    }
    return match.status_label || match.phase || "—";
  }

  function renderLiveBanner(board) {
    if (!liveBannerEl) return;
    var count = board.live_call_count || 0;
    var liveMatches = (board.matches || []).filter(function (m) {
      return m.live_call;
    });

    if (!count || !liveMatches.length) {
      liveBannerEl.hidden = true;
      liveBannerEl.innerHTML = "";
      return;
    }

    liveBannerEl.hidden = false;
    var items = liveMatches
      .map(function (m) {
        return (
          "<strong>" +
          escapeHtml(m.home_team) +
          " vs " +
          escapeHtml(m.away_team) +
          "</strong> · HT " +
          m.ht_home +
          "–" +
          m.ht_away +
          " · " +
          '<span class="' +
          callClass(m.call, true) +
          '">' +
          escapeHtml(m.call_label || "—") +
          "</span> · pred " +
          Number(m.pred_total).toFixed(2)
        );
      })
      .join("<br />");

    liveBannerEl.innerHTML =
      "<p><strong>" +
      count +
      " live call" +
      (count === 1 ? "" : "s") +
      " at halftime</strong></p>" +
      items;
  }

  function render(board) {
    if (!tbody) return;
    tbody.innerHTML = "";

    if (disclaimerEl) {
      disclaimerEl.textContent = board.disclaimer || "";
    }

    renderLiveBanner(board);

    var matches = board.matches || [];
    if (!matches.length) {
      var empty = document.createElement("tr");
      empty.innerHTML =
        '<td colspan="7" class="muted">No Premier League matches on the board right now.</td>';
      tbody.appendChild(empty);
      return;
    }

    matches.forEach(function (match) {
      var tr = document.createElement("tr");
      if (match.live_call) {
        tr.className = "ht-row-live";
      } else if (match.phase === "halftime") {
        tr.className = "ht-row-halftime";
      }

      var callLabel = match.call_label || "—";
      if (match.call_note && !match.live_call) {
        callLabel = callLabel + " *";
      }

      var ht =
        match.ht_home != null && match.ht_away != null
          ? match.ht_home + "–" + match.ht_away
          : match.score_str || "—";

      tr.innerHTML =
        "<td><strong>" +
        escapeHtml(match.home_team) +
        "</strong> vs " +
        escapeHtml(match.away_team) +
        (match.odds_matched === false
          ? ' <span class="muted">(no odds)</span>'
          : "") +
        "</td>" +
        "<td>" +
        escapeHtml(phaseLabel(match)) +
        "</td>" +
        '<td class="num">' +
        escapeHtml(String(ht)) +
        "</td>" +
        '<td class="num">' +
        escapeHtml(formatPred(match.pred_ft_home, match.pred_ft_away)) +
        "</td>" +
        '<td class="num">' +
        (match.pred_total != null ? Number(match.pred_total).toFixed(2) : "—") +
        "</td>" +
        "<td><span class=\"" +
        callClass(match.call, match.live_call) +
        '">' +
        escapeHtml(callLabel) +
        "</span></td>" +
        '<td class="num">' +
        escapeHtml(formatEdge(match.edge)) +
        "</td>";
      tbody.appendChild(tr);
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadBoard(forceRefresh) {
    var workerUrl = (config.workerUrl || "").replace(/\/+$/, "");
    setStatus("Refreshing…");

    try {
      var response;
      if (workerUrl) {
        var path = forceRefresh ? "/board?refresh=1" : "/board";
        response = await fetch(workerUrl + path, { cache: "no-store" });
      } else {
        response = await fetch("board.json", { cache: "no-store" });
      }

      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }

      var board = await response.json();
      render(board);
      var source = workerUrl ? "Cloudflare Worker" : "board.json";
      var liveCount = board.live_call_count || 0;
      var livePart =
        liveCount > 0 ? " · " + liveCount + " live HT call(s)" : "";
      setStatus(
        "Updated " +
          (board.updated || "—") +
          " · " +
          (board.matches || []).length +
          " matches · " +
          source +
          livePart
      );
    } catch (err) {
      setStatus("Failed to load board: " + (err.message || err));
    }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    var ms = Number(config.pollMs) || 60000;
    pollTimer = setInterval(function () {
      loadBoard(false);
    }, ms);
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      loadBoard(true);
    });
  }

  loadBoard(false);
  startPolling();
})();
