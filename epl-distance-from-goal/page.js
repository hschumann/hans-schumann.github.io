(function () {
  var data = window.EPL_DISTANCE_DATA;
  if (!data) return;

  var sortKey = "avg_yards_from_goal";
  var sortDir = "asc";

  var columns = [
    { key: "rank", label: "#", numeric: true },
    { key: "team", label: "Team", numeric: false },
    { key: "avg_yards_from_goal", label: "Avg yards from goal", numeric: true },
    { key: "group_points", label: "Group pts", numeric: true },
    { key: "group_gd", label: "Group GD", numeric: true },
    { key: "stage", label: "Reached", numeric: false, sortKey: "stage_rank" },
    { key: "avg_resid", label: "xG residual", numeric: true },
  ];

  function formatResid(value) {
    var sign = value > 0 ? "+" : "";
    return sign + value.toFixed(3);
  }

  function formatGd(value) {
    if (value == null) return "—";
    return (value > 0 ? "+" : "") + value;
  }

  function residClass(value) {
    if (value > 0.005) return "epl-resid-pos";
    if (value < -0.005) return "epl-resid-neg";
    return "";
  }

  function compareTeams(a, b) {
    var key = sortKey === "stage" ? "stage_rank" : sortKey;
    var av = a[key];
    var bv = b[key];
    var cmp = 0;
    if (typeof av === "string" || typeof bv === "string") {
      cmp = String(av).localeCompare(String(bv));
    } else {
      cmp = av === bv ? 0 : av < bv ? -1 : 1;
    }
    return sortDir === "asc" ? cmp : -cmp;
  }

  function renderTable() {
    var table = document.getElementById("epl-team-table");
    if (!table || !data.teams) return;

    var thead = table.querySelector("thead");
    var tbody = table.querySelector("tbody");
    if (!thead || !tbody) return;

    var sorted = data.teams.slice().sort(compareTeams);

    thead.innerHTML = "";
    var headRow = document.createElement("tr");
    columns.forEach(function (col) {
      var th = document.createElement("th");
      th.scope = "col";
      if (col.numeric) th.className = "num";

      if (col.key === "rank") {
        th.textContent = col.label;
        headRow.appendChild(th);
        return;
      }

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "leaderboard-sort";
      btn.textContent = col.label;
      if (sortKey === col.key || (col.key === "stage" && sortKey === "stage_rank")) {
        btn.classList.add(sortDir === "asc" ? "is-asc" : "is-desc");
        btn.setAttribute("aria-sort", sortDir === "asc" ? "ascending" : "descending");
      } else {
        btn.setAttribute("aria-sort", "none");
      }
      btn.addEventListener("click", function () {
        var nextKey = col.key === "stage" ? "stage_rank" : col.key;
        if (sortKey === nextKey || (col.key === "stage" && sortKey === "stage_rank")) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortKey = nextKey;
          sortDir =
            nextKey === "team"
              ? "asc"
              : nextKey === "avg_yards_from_goal"
                ? "asc"
                : "desc";
        }
        renderTable();
      });
      th.appendChild(btn);
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);

    tbody.innerHTML = sorted
      .map(function (team, index) {
        return (
          "<tr>" +
          '<td class="num">' +
          (index + 1) +
          "</td>" +
          "<td>" +
          team.team +
          "</td>" +
          '<td class="num">' +
          team.avg_yards_from_goal.toFixed(1) +
          "</td>" +
          '<td class="num">' +
          (team.group_points == null ? "—" : team.group_points) +
          "</td>" +
          '<td class="num">' +
          formatGd(team.group_gd) +
          "</td>" +
          "<td>" +
          (team.stage || "—") +
          "</td>" +
          '<td class="num ' +
          residClass(team.avg_resid) +
          '">' +
          formatResid(team.avg_resid) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function renderCurve() {
    var host = document.getElementById("epl-xg-curve");
    if (!host || !data.bins || !data.curve) return;

    var width = 640;
    var height = 340;
    var margin = { top: 28, right: 18, bottom: 52, left: 58 };
    var innerW = width - margin.left - margin.right;
    var innerH = height - margin.top - margin.bottom;

    var maxYards = 105;
    var maxXg = 0;
    data.bins.forEach(function (bin) {
      if (bin.avg_xg > maxXg) maxXg = bin.avg_xg;
    });
    data.curve.forEach(function (point) {
      if (point.expected_xg > maxXg) maxXg = point.expected_xg;
    });
    maxXg = Math.ceil(maxXg * 100) / 100 + 0.01;

    var maxN = 1;
    data.bins.forEach(function (bin) {
      if (bin.n > maxN) maxN = bin.n;
    });

    function xScale(yards) {
      return margin.left + (yards / maxYards) * innerW;
    }

    function yScale(xg) {
      return margin.top + innerH - (xg / maxXg) * innerH;
    }

    function radius(n) {
      return 4 + (n / maxN) * 10;
    }

    var curvePath = data.curve
      .map(function (point, index) {
        var command = index === 0 ? "M" : "L";
        return command + " " + xScale(point.yards) + " " + yScale(point.expected_xg);
      })
      .join(" ");

    var yTickCount = 4;
    var yTicks = [];
    for (var i = 0; i <= yTickCount; i++) {
      yTicks.push((maxXg * i) / yTickCount);
    }
    var xTicks = [0, 20, 40, 60, 80, 100];

    var grid = yTicks
      .map(function (tick) {
        var y = yScale(tick);
        return (
          '<line class="epl-curve-grid" x1="' +
          margin.left +
          '" y1="' +
          y +
          '" x2="' +
          (margin.left + innerW) +
          '" y2="' +
          y +
          '" />'
        );
      })
      .join("");

    var yLabels = yTicks
      .map(function (tick) {
        return (
          '<text class="epl-curve-tick" x="' +
          (margin.left - 10) +
          '" y="' +
          (yScale(tick) + 4) +
          '" text-anchor="end">' +
          tick.toFixed(2) +
          "</text>"
        );
      })
      .join("");

    var xLabels = xTicks
      .map(function (tick) {
        return (
          '<text class="epl-curve-tick" x="' +
          xScale(tick) +
          '" y="' +
          (margin.top + innerH + 22) +
          '" text-anchor="middle">' +
          tick +
          "</text>"
        );
      })
      .join("");

    var points = data.bins
      .map(function (bin) {
        var lo = bin.yards - 2.5;
        var hi = bin.yards + 2.5;
        return (
          '<circle class="epl-curve-point" cx="' +
          xScale(bin.yards) +
          '" cy="' +
          yScale(bin.avg_xg) +
          '" r="' +
          radius(bin.n) +
          '">' +
          "<title>" +
          lo +
          "–" +
          hi +
          " yards: " +
          bin.avg_xg.toFixed(4) +
          " avg xG (" +
          bin.n +
          " possessions)</title>" +
          "</circle>"
        );
      })
      .join("");

    host.innerHTML =
      '<svg viewBox="0 0 ' +
      width +
      " " +
      height +
      '" role="img" xmlns="http://www.w3.org/2000/svg">' +
      "<title>Average expected goals by possession starting distance from goal</title>" +
      grid +
      '<line class="epl-curve-axis" x1="' +
      margin.left +
      '" y1="' +
      (margin.top + innerH) +
      '" x2="' +
      (margin.left + innerW) +
      '" y2="' +
      (margin.top + innerH) +
      '" />' +
      '<line class="epl-curve-axis" x1="' +
      margin.left +
      '" y1="' +
      margin.top +
      '" x2="' +
      margin.left +
      '" y2="' +
      (margin.top + innerH) +
      '" />' +
      yLabels +
      xLabels +
      '<text class="epl-curve-axis-label" x="' +
      (margin.left + innerW / 2) +
      '" y="' +
      (height - 8) +
      '" text-anchor="middle">Starting distance from goal (yards)</text>' +
      '<text class="epl-curve-axis-label" x="16" y="' +
      (margin.top + innerH / 2) +
      '" text-anchor="middle" transform="rotate(-90 16 ' +
      (margin.top + innerH / 2) +
      ')">Avg xG per possession</text>' +
      '<path class="epl-curve-fit" d="' +
      curvePath +
      '" fill="none" />' +
      points +
      "</svg>";
  }

  renderTable();
  renderCurve();
})();
