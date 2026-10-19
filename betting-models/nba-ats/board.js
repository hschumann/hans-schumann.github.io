(function () {
  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatSpread(spread) {
    if (spread == null || spread === "") return "";
    var n = Number(spread);
    if (Number.isNaN(n)) return "";
    return (n > 0 ? "+" : "") + String(n);
  }

  function resultClass(result) {
    if (result === "W") return "ats-win";
    if (result === "L") return "ats-loss";
    if (result === "P") return "ats-push";
    return "ats-pending";
  }

  function renderPickCard(pick) {
    var spread = formatSpread(pick.bet_spread);
    var title = esc(pick.bet_team) + (spread ? " " + esc(spread) : "");
    var loc = pick.bet_team === pick.home_team ? "vs" : "@";
    return (
      '<article class="subsection stack">' +
      "<h3>" +
      title +
      " " +
      loc +
      " " +
      esc(pick.against_team || (pick.bet_team === pick.home_team ? pick.away_team : pick.home_team)) +
      "</h3>" +
      '<p class="muted">7-day ATS: ' +
      esc(pick.bet_team) +
      " " +
      (pick.bet_team === pick.home_team
        ? Number(pick.home_score_7d).toFixed(1)
        : Number(pick.away_score_7d).toFixed(1)) +
      " vs " +
      esc(pick.against_team || "") +
      " " +
      (pick.bet_team === pick.home_team
        ? Number(pick.away_score_7d).toFixed(1)
        : Number(pick.home_score_7d).toFixed(1)) +
      " &middot; |Δ| " +
      Number(pick.abs_diff).toFixed(1) +
      "</p>" +
      "</article>"
    );
  }

  function renderToday(data) {
    var today = data.today || { picks: [] };
    var upcoming = data.upcoming;
    var meta = document.getElementById("today-meta");
    var box = document.getElementById("today-picks");
    var picks = today.picks || [];

    if (picks.length) {
      meta.textContent = "Slate date " + today.pick_date + " · top " + picks.length + " by |Δ|";
      box.innerHTML = picks.map(renderPickCard).join("");
      return;
    }

    if (upcoming && upcoming.picks && upcoming.picks.length) {
      meta.textContent =
        "No qualifying games on " +
        today.pick_date +
        ". Next slate preview for " +
        upcoming.pick_date +
        ":";
      box.innerHTML = upcoming.picks.map(renderPickCard).join("");
      return;
    }

    meta.textContent = "No qualifying games on " + (today.pick_date || "today") + ".";
    box.innerHTML = '<p class="muted">Check back on the next NBA slate.</p>';
  }

  function renderRecord(record) {
    var el = document.getElementById("record-line");
    if (!record) {
      el.textContent = "";
      return;
    }
    var parts = [];
    parts.push(
      "Season record: " +
        record.wins +
        "–" +
        record.losses +
        (record.pushes ? "–" + record.pushes : "")
    );
    if (record.pending) parts.push(record.pending + " pending");
    el.textContent = parts.join(" · ");
  }

  function renderHistory(history) {
    var body = document.getElementById("history-body");
    if (!history || !history.length) {
      body.innerHTML =
        '<tr><td colspan="4" class="muted">No graded picks yet — history fills in as game days complete.</td></tr>';
      return;
    }

    body.innerHTML = history
      .map(function (row) {
        var spread = formatSpread(row.bet_spread);
        var bet =
          esc(row.bet_team) +
          (spread ? " " + esc(spread) : "") +
          " (" +
          (row.bet_team === row.home_team ? "vs " : "@ ") +
          esc(row.against_team || (row.bet_team === row.home_team ? row.away_team : row.home_team)) +
          ")";
        var result = row.result || "pending";
        var resultLabel = result === "pending" ? "—" : result;
        return (
          "<tr>" +
          "<td>" +
          esc(row.pick_date) +
          "</td>" +
          "<td><span class=\"" +
          resultClass(result) +
          '">' +
          bet +
          "</span></td>" +
          '<td class="num">' +
          Number(row.abs_diff).toFixed(1) +
          "</td>" +
          '<td class="num"><span class="' +
          resultClass(result) +
          '">' +
          esc(resultLabel) +
          "</span></td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function formatUpdated(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch (e) {
      return iso;
    }
  }

  fetch("picks.json", { cache: "no-store" })
    .then(function (res) {
      if (!res.ok) throw new Error("Failed to load picks.json");
      return res.json();
    })
    .then(function (data) {
      document.getElementById("updated-at").textContent = formatUpdated(data.updated);
      renderToday(data);
      renderRecord(data.record);
      renderHistory(data.history);
    })
    .catch(function (err) {
      document.getElementById("today-meta").textContent = "Could not load picks.";
      document.getElementById("today-picks").innerHTML =
        '<p class="muted">' + esc(err.message) + "</p>";
      document.getElementById("history-body").innerHTML =
        '<tr><td colspan="4" class="muted">Unavailable</td></tr>';
    });
})();
