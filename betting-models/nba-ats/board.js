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

  function signed(value) {
    var n = Number(value);
    if (Number.isNaN(n)) return "—";
    return (n > 0 ? "+" : "") + n.toFixed(1);
  }

  function slateRows(block) {
    var rows =
      block && block.slate && block.slate.length
        ? block.slate.slice()
        : ((block && block.picks) || []).slice();
    rows.sort(function (a, b) {
      var diff = Number(b.abs_diff) - Number(a.abs_diff);
      if (diff) return diff;
      return String(a.tipoff_utc || "").localeCompare(String(b.tipoff_utc || ""));
    });
    return rows;
  }

  function renderSlateTable(rows) {
    var body = document.getElementById("slate-body");
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="5" class="muted">No qualifying games.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(function (row, index) {
        var spread = formatSpread(row.bet_spread);
        var bet = esc(row.bet_team) + (spread ? " " + esc(spread) : "");
        var game = esc(row.away_team) + " @ " + esc(row.home_team);
        var pick = Number(row.rank) ? Number(row.rank) <= 3 : index < 3;
        return (
          '<tr class="' +
          (pick ? "ats-pick-row" : "") +
          '">' +
          '<td class="num">' +
          Number(row.abs_diff).toFixed(1) +
          "</td>" +
          "<td>" +
          game +
          "</td>" +
          "<td>" +
          bet +
          "</td>" +
          '<td class="num">' +
          signed(row.away_score_7d) +
          "</td>" +
          '<td class="num">' +
          signed(row.home_score_7d) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function renderToday(data) {
    var today = data.today || { picks: [], slate: [] };
    var upcoming = data.upcoming;
    var meta = document.getElementById("today-meta");
    var caption = document.getElementById("slate-caption");
    var rows = slateRows(today);

    if (rows.length) {
      meta.textContent =
        today.pick_date +
        " · " +
        rows.length +
        " games, largest |Δ| first. Highlighted rows are the top 3 bets.";
      caption.textContent = "Games on " + today.pick_date + ", sorted by |Δ|";
      renderSlateTable(rows);
      return;
    }

    var preview = slateRows(upcoming);
    if (preview.length) {
      meta.textContent =
        "No qualifying games on " +
        (today.pick_date || "today") +
        ". Next slate, " +
        upcoming.pick_date +
        ", sorted by |Δ|. Highlighted rows are the top 3 bets.";
      caption.textContent = "Games on " + upcoming.pick_date + ", sorted by |Δ|";
      renderSlateTable(preview);
      return;
    }

    meta.textContent = "No qualifying games on " + (today.pick_date || "today") + ".";
    caption.textContent = "Games sorted by absolute 7-day ATS gap";
    renderSlateTable([]);
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

  function formatRecord(bin) {
    var record = bin.wins + "–" + bin.losses;
    if (bin.pushes) record += "–" + bin.pushes;
    return record;
  }

  function formatCutoff(bin) {
    if (bin.cutoff == null) return "—";
    return "≥ " + Number(bin.cutoff).toFixed(1);
  }

  function formatAccuracy(bin) {
    if (bin.accuracy == null) return "—";
    return (Number(bin.accuracy) * 100).toFixed(1) + "%";
  }

  function formatGradeStart(iso) {
    if (!iso) return "October 27, 2026";
    try {
      var parts = iso.split("-");
      return new Date(
        Number(parts[0]),
        Number(parts[1]) - 1,
        Number(parts[2])
      ).toLocaleDateString(undefined, {
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    } catch (e) {
      return iso;
    }
  }

  function renderAccuracy(bins, gradeStart) {
    var body = document.getElementById("accuracy-body");
    var meta = document.getElementById("accuracy-meta");
    var since = formatGradeStart(gradeStart);
    if (!bins || !bins.length) {
      meta.textContent = "No graded games yet. Wins and losses count from " + since + ".";
      body.innerHTML =
        '<tr><td colspan="4" class="muted">Accuracy fills in once games finish.</td></tr>';
      return;
    }
    var games = bins.reduce(function (sum, bin) {
      return sum + Number(bin.games || 0);
    }, 0);
    meta.textContent =
      games +
      " graded games since " +
      since +
      ". Each cutoff is the |Δ| at that percentile. A game lands in the highest row it clears.";
    body.innerHTML = bins
      .map(function (bin) {
        var accuracy = formatAccuracy(bin);
        var accuracyClass = "";
        if (bin.accuracy != null && bin.accuracy > 0.5) accuracyClass = "ats-win";
        else if (bin.accuracy != null && bin.accuracy < 0.5) accuracyClass = "ats-loss";
        return (
          "<tr>" +
          "<td>" +
          esc(bin.label) +
          "</td>" +
          '<td class="num">' +
          formatCutoff(bin) +
          "</td>" +
          '<td class="num">' +
          (bin.games ? formatRecord(bin) : "—") +
          "</td>" +
          '<td class="num"><span class="' +
          accuracyClass +
          '">' +
          accuracy +
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
      renderAccuracy(data.accuracy_by_percentile, data.grade_start);
    })
    .catch(function (err) {
      document.getElementById("today-meta").textContent = "Could not load picks.";
      document.getElementById("slate-body").innerHTML =
        '<tr><td colspan="5" class="muted">' + esc(err.message) + "</td></tr>";
      document.getElementById("history-body").innerHTML =
        '<tr><td colspan="4" class="muted">Unavailable</td></tr>';
      document.getElementById("accuracy-body").innerHTML =
        '<tr><td colspan="4" class="muted">Unavailable</td></tr>';
    });
})();
