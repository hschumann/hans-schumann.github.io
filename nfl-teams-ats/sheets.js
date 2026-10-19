/**
 * Load 2026 NFL picks from Google Sheets (published CSV) or local CSV fallback.
 *
 * Setup:
 * 1. Upload / keep your sheet in Google Drive (same columns as the NFL/*.csv files).
 * 2. File → Share → Anyone with the link can view.
 * 3. File → Share → Publish to web → pick each tab → CSV.
 * 4. Paste those CSV URLs into CONFIG below.
 */
(function () {
  var CONFIG = {
    // Published Google Sheet CSV tabs (pick grids start ~row 36).
    spreadsCsvUrl:
      "https://docs.google.com/spreadsheets/d/e/2PACX-1vTsrLb_M9TM8n6A47yONH0GXbNX7N11YNlpz63a2KZddClm8d2JTsMNVS8La7ZONOnJu5JgysbAbvYu/pub?gid=2005949457&single=true&output=csv",
    totalsCsvUrl:
      "https://docs.google.com/spreadsheets/d/e/2PACX-1vTsrLb_M9TM8n6A47yONH0GXbNX7N11YNlpz63a2KZddClm8d2JTsMNVS8La7ZONOnJu5JgysbAbvYu/pub?gid=306490129&single=true&output=csv",
    // Offline fallback if Sheets is unreachable.
    spreadsFallback: "../NFL/nfl_teams_ats_games_2026.csv",
    totalsFallback: "../NFL/nfl_teams_ats_games_2026_totals.csv",
  };

  var TEAM_DISPLAY = { WAS: "WSH", JAC: "JAX" };

  function normalizeAgreeTeams(agree) {
    return String(agree)
      .replace(/\bWAS\b/g, "WSH")
      .replace(/\bJAC\b/g, "JAX");
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function displayTeam(abbr) {
    var key = String(abbr || "").toUpperCase();
    return TEAM_DISPLAY[key] || key;
  }

  function parseCsv(text) {
    var rows = [];
    var row = [];
    var cell = "";
    var inQuotes = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      var next = text[i + 1];
      if (inQuotes) {
        if (ch === '"' && next === '"') {
          cell += '"';
          i++;
        } else if (ch === '"') {
          inQuotes = false;
        } else {
          cell += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(cell);
        cell = "";
      } else if (ch === "\n") {
        row.push(cell);
        rows.push(row);
        row = [];
        cell = "";
      } else if (ch !== "\r") {
        cell += ch;
      }
    }
    if (cell.length || row.length) {
      row.push(cell);
      rows.push(row);
    }
    return rows;
  }

  function isBlankRow(cols) {
    return !cols.some(function (c) {
      return String(c || "").trim() !== "";
    });
  }

  function isEmptyAgree(value) {
    var v = String(value || "").trim();
    if (!v) return true;
    var lower = v.toLowerCase();
    if (lower === "agree" || lower === "#n/a" || lower === "n/a") return true;
    // Placeholder / formula leftovers in unused week blocks
    if (v === "0" || v === "0.0" || v === "1" || v === "1.0") return true;
    return false;
  }

  function looksLikeSpreadBet(agree) {
    // e.g. "GB -3.5", "@DEN -2.5", "IND +6.5"
    return /^@?[A-Za-z]{2,4}\s*[+-]?\d/.test(String(agree).trim());
  }

  function looksLikeTotalsBet(agree) {
    // e.g. "DET/BUF u53.5", "KC @MIA u45.5", "PIT/NE o42.5"
    return /[uo]\s*\d/i.test(String(agree));
  }

  function parseCorrect(value) {
    var v = String(value == null ? "" : value).trim();
    if (!v) return "pending";
    var n = Number(v);
    if (Number.isNaN(n)) return "pending";
    if (n === 1) return "W";
    if (n === 0) return "L";
    if (n === 0.5) return "P";
    return "pending";
  }

  function headerCol(header, name, fromCol) {
    var target = String(name).trim().toLowerCase();
    for (var i = fromCol || 0; i < header.length; i++) {
      if (String(header[i] || "").trim().toLowerCase() === target) return i;
    }
    return -1;
  }

  function findWeekCol(cols) {
    for (var i = 0; i < cols.length; i++) {
      if (String(cols[i] || "").trim().toLowerCase() === "week") return i;
    }
    return -1;
  }

  function parseAgreePicks(rows, betValidator) {
    var week = null;
    var weekCol = -1;
    var agreeIndex = -1;
    var correctIndex = -1;
    var picks = [];

    rows.forEach(function (cols) {
      if (isBlankRow(cols)) return;

      var wc = findWeekCol(cols);
      if (wc >= 0) {
        weekCol = wc;
        week = Number(cols[weekCol + 1]);
        agreeIndex = headerCol(cols, "Agree", weekCol);
        correctIndex = headerCol(cols, "Correct", weekCol);
        // Prefer the first "Correct" after Agree (not "Agree Correct").
        if (agreeIndex >= 0) {
          for (var i = agreeIndex + 1; i < cols.length; i++) {
            if (String(cols[i] || "").trim().toLowerCase() === "correct") {
              correctIndex = i;
              break;
            }
          }
        }
        return;
      }

      if (week == null || weekCol < 0 || agreeIndex < 0 || Number.isNaN(week)) return;
      var agree = cols[agreeIndex];
      if (isEmptyAgree(agree)) return;
      var agreeText = String(agree).trim();
      if (betValidator && !betValidator(agreeText)) return;
      var team1 = String(cols[weekCol] || "").trim().toUpperCase();
      var team2 = String(cols[weekCol + 1] || "").trim().toUpperCase();
      if (!team1 || !team2) return;
      picks.push({
        week: week,
        team1: team1,
        team2: team2,
        agree: agreeText,
        result: parseCorrect(correctIndex >= 0 ? cols[correctIndex] : ""),
      });
    });
    return picks;
  }

  function formatSpreadLabel(pick) {
    var agree = normalizeAgreeTeams(pick.agree).replace(/^@/, "");
    var parts = agree.split(/\s+/);
    var betTeam = displayTeam(parts[0]);
    var line = parts.slice(1).join(" ");
    var t1 = displayTeam(pick.team1);
    var t2 = displayTeam(pick.team2);
    var opponent = betTeam === t1 ? t2 : t1;
    var prefix = normalizeAgreeTeams(pick.agree).trim().charAt(0) === "@" ? "@" : "";
    return prefix + betTeam + (line ? " " + line : "") + " (v " + opponent + ")";
  }

  function formatTotalsLabel(pick) {
    var raw = normalizeAgreeTeams(pick.agree).trim();
    // Examples: "DET/BUF u53.5", "CIN/PIT o42.5", "KC @MIA u45.5"
    var m = raw.match(/^(.+?)\s+([uo])\s*(\d+(?:\.\d+)?)$/i);
    if (!m) return raw;
    var side = m[2].toLowerCase() === "u" ? "Under" : "Over";
    var total = m[3];
    var matchup = m[1].trim();
    var teams;
    if (matchup.indexOf("/") >= 0) {
      teams = matchup.split("/").map(function (t) {
        return displayTeam(t.trim());
      });
      matchup = teams[0] + " @ " + teams[1];
    } else if (/@/.test(matchup)) {
      teams = matchup.split("@").map(function (t) {
        return displayTeam(t.trim());
      });
      matchup = teams[0] + " @ " + teams[1];
    }
    return side + " " + total + " (" + matchup + ")";
  }

  function resultClass(result) {
    if (result === "W") return "ats-win";
    if (result === "L") return "ats-loss";
    if (result === "P") return "ats-push";
    return "ats-pending";
  }

  function resultLabel(result) {
    if (result === "pending") return "Pending";
    return result;
  }

  function recordString(wins, losses, pushes) {
    var text = wins + "–" + losses;
    if (pushes) text += "–" + pushes;
    var decided = wins + losses;
    var pct = decided ? ((100 * wins) / decided).toFixed(1) : "0.0";
    return text + " (" + pct + "%)";
  }

  function accumulate(picks) {
    var byWeek = {};
    var wins = 0;
    var losses = 0;
    var pushes = 0;
    picks.forEach(function (p) {
      if (!byWeek[p.week]) byWeek[p.week] = [];
      byWeek[p.week].push(p);
      if (p.result === "W") wins++;
      else if (p.result === "L") losses++;
      else if (p.result === "P") pushes++;
    });
    return { byWeek: byWeek, wins: wins, losses: losses, pushes: pushes };
  }

  function renderTable(tbody, picks, labelFn) {
    if (!picks.length) {
      tbody.innerHTML =
        '<tr><td colspan="3" class="muted">No Agree picks found in the sheet yet.</td></tr>';
      return accumulate(picks);
    }

    var stats = accumulate(picks);
    var weeks = Object.keys(stats.byWeek)
      .map(Number)
      .sort(function (a, b) {
        return a - b;
      });
    var html = [];
    var w = 0;
    var l = 0;
    var p = 0;
    weeks.forEach(function (week) {
      stats.byWeek[week].forEach(function (pick) {
        var cls = resultClass(pick.result);
        html.push(
          "<tr>" +
            '<td class="num">' +
            week +
            "</td>" +
            "<td><span class=\"" +
            cls +
            '">' +
            esc(labelFn(pick)) +
            "</span></td>" +
            '<td class="num"><span class="' +
            cls +
            '">' +
            esc(resultLabel(pick.result)) +
            "</span></td>" +
            "</tr>"
        );
        if (pick.result === "W") w++;
        else if (pick.result === "L") l++;
        else if (pick.result === "P") p++;
      });
      html.push(
        '<tr class="ats-record-row"><td colspan="2" class="ats-record-label">Season record through Week ' +
          week +
          '</td><td class="num ats-record-value">' +
          esc(recordString(w, l, p).replace(/-/g, "–")) +
          "</td></tr>"
      );
    });
    tbody.innerHTML = html.join("");
    return stats;
  }

  function fetchCsv(primary, fallback) {
    var urls = [primary, fallback].filter(Boolean);
    function tryNext(i) {
      if (i >= urls.length) {
        return Promise.reject(new Error("Could not load CSV"));
      }
      return fetch(urls[i], { cache: "no-store" }).then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.text();
      }).catch(function () {
        return tryNext(i + 1);
      });
    }
    return tryNext(0);
  }

  function updateSummary(spreadStats, totalsStats) {
    var el = document.getElementById("nfl-2026-summary");
    if (!el) return;
    var s = recordString(spreadStats.wins, spreadStats.losses, spreadStats.pushes);
    var t = recordString(totalsStats.wins, totalsStats.losses, totalsStats.pushes);
    var cw = spreadStats.wins + totalsStats.wins;
    var cl = spreadStats.losses + totalsStats.losses;
    var cp = spreadStats.pushes + totalsStats.pushes;
    var combined = recordString(cw, cl, cp);
    var latestWeek = 0;
    Object.keys(spreadStats.byWeek)
      .concat(Object.keys(totalsStats.byWeek))
      .forEach(function (w) {
        latestWeek = Math.max(latestWeek, Number(w));
      });
    var through =
      latestWeek > 0 ? "Through Week " + latestWeek + ", " : "";
    el.innerHTML =
      through +
      "the record against the spread is <strong>" +
      esc(s.replace(/-/g, "–")) +
      "</strong>, and the record on totals is <strong>" +
      esc(t.replace(/-/g, "–")) +
      "</strong>. Combined, that is " +
      esc(combined.replace(/-/g, "–")) +
      ".";
  }

  function boot() {
    var spreadBody = document.getElementById("nfl-2026-spreads-body");
    var totalsBody = document.getElementById("nfl-2026-totals-body");
    if (!spreadBody || !totalsBody) return;

    Promise.all([
      fetchCsv(CONFIG.spreadsCsvUrl, CONFIG.spreadsFallback),
      fetchCsv(CONFIG.totalsCsvUrl, CONFIG.totalsFallback),
    ])
      .then(function (texts) {
        var spreadRows = parseCsv(texts[0]);
        var totalsRows = parseCsv(texts[1]);
        // Skip ranking block above; parser finds the first "Week" header (~row 36).
        var spreadPicks = parseAgreePicks(spreadRows, looksLikeSpreadBet);
        var totalsPicks = parseAgreePicks(totalsRows, looksLikeTotalsBet);
        var spreadStats = renderTable(spreadBody, spreadPicks, formatSpreadLabel);
        var totalsStats = renderTable(totalsBody, totalsPicks, formatTotalsLabel);
        updateSummary(spreadStats, totalsStats);

        var source = document.getElementById("nfl-sheet-source");
        if (source) {
          source.textContent = CONFIG.spreadsCsvUrl
            ? "Live from Google Sheets"
            : "Loaded from local NFL/*.csv";
        }
      })
      .catch(function (err) {
        spreadBody.innerHTML =
          '<tr><td colspan="3" class="muted">Failed to load picks: ' +
          esc(err.message) +
          "</td></tr>";
        totalsBody.innerHTML =
          '<tr><td colspan="3" class="muted">Failed to load picks.</td></tr>';
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
