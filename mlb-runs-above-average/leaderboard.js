(function () {
  function initLeaderboard(config) {
    var PAGE_SIZE = 30;
    var rows = config.rows || [];
    var sortKey = config.defaultSortKey || "total";
    var sortDir = config.defaultSortDir || "desc";
    var pageIndex = 0;

    var rangeSelect = document.getElementById(config.rangeId);
    var theadEl = document.getElementById(config.theadId);
    var tbodyEl = document.getElementById(config.tbodyId);
    var metaEl = document.getElementById(config.metaId);

    if (!rows.length || !rangeSelect || !theadEl || !tbodyEl) {
      return;
    }

    buildRangeOptions();
    rangeSelect.addEventListener("change", function () {
      pageIndex = Number(rangeSelect.value) || 0;
      renderTable();
    });

    renderTable();

    function buildRangeOptions() {
      rangeSelect.innerHTML = "";
      var pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
      for (var i = 0; i < pages; i++) {
        var start = i * PAGE_SIZE + 1;
        var end = Math.min((i + 1) * PAGE_SIZE, rows.length);
        var opt = document.createElement("option");
        opt.value = String(i);
        opt.textContent = start + "\u2013" + end;
        rangeSelect.appendChild(opt);
      }
      rangeSelect.value = "0";
    }

    function renderTable() {
      theadEl.innerHTML = "";
      tbodyEl.innerHTML = "";

      var sorted = rows.slice().sort(compareRows);
      var pages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
      if (pageIndex >= pages) {
        pageIndex = pages - 1;
        rangeSelect.value = String(pageIndex);
      }

      var start = pageIndex * PAGE_SIZE;
      var slice = sorted.slice(start, start + PAGE_SIZE);

      var headRow = document.createElement("tr");
      config.columns.forEach(function (col) {
        headRow.appendChild(sortHeader(col.label, col.key, !!col.numeric));
      });
      theadEl.appendChild(headRow);

      slice.forEach(function (row, i) {
        var tr = document.createElement("tr");
        config.columns.forEach(function (col) {
          if (col.key === "rank") {
            tr.appendChild(numCell(start + i + 1));
            return;
          }
          var value = row[col.key];
          if (col.format === "signed") {
            tr.appendChild(numCell(formatSigned(value, col.digits)));
          } else if (col.numeric) {
            tr.appendChild(numCell(value));
          } else {
            tr.appendChild(textCell(value));
          }
        });
        tbodyEl.appendChild(tr);
      });

      if (metaEl) {
        var shownStart = sorted.length ? start + 1 : 0;
        var shownEnd = start + slice.length;
        metaEl.textContent =
          "Showing " +
          shownStart +
          "\u2013" +
          shownEnd +
          " of " +
          sorted.length +
          " " +
          config.noun +
          " (" +
          config.minLabel +
          "). Click a column header to sort.";
      }
    }

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
        btn.setAttribute(
          "aria-sort",
          sortDir === "asc" ? "ascending" : "descending"
        );
      } else {
        btn.setAttribute("aria-sort", "none");
      }
      btn.addEventListener("click", function () {
        if (sortKey === key) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortKey = key;
          if (key === "player" || key === "team") {
            sortDir = "asc";
          } else if (config.numericDefaultAsc && config.numericDefaultAsc[key]) {
            sortDir = "asc";
          } else {
            sortDir = "desc";
          }
        }
        pageIndex = 0;
        rangeSelect.value = "0";
        renderTable();
      });

      th.appendChild(btn);
      return th;
    }

    function compareRows(a, b) {
      var av = a[sortKey];
      var bv = b[sortKey];
      var cmp;

      if (typeof av === "string" || typeof bv === "string") {
        cmp = String(av).toLowerCase().localeCompare(String(bv).toLowerCase());
      } else {
        cmp = av === bv ? 0 : av < bv ? -1 : 1;
      }

      if (cmp === 0) {
        cmp = a.rank - b.rank;
      }
      return sortDir === "asc" ? cmp : -cmp;
    }

    function textCell(value) {
      var td = document.createElement("td");
      td.textContent = value;
      return td;
    }

    function numCell(value) {
      var td = document.createElement("td");
      td.className = "num";
      td.textContent = value;
      return td;
    }

    function formatSigned(value, digits) {
      var n = Number(value);
      var places = digits == null ? 2 : digits;
      var text = n.toFixed(places);
      if (n > 0) {
        return "+" + text;
      }
      return text;
    }
  }

  initLeaderboard({
    rows: window.MLB_RAA_LEADERBOARD || [],
    rangeId: "leaderboard-range",
    theadId: "mlb-leaderboard-thead",
    tbodyId: "mlb-leaderboard-tbody",
    metaId: "leaderboard-meta",
    noun: "hitters",
    minLabel: "min. 100 PA",
    defaultSortKey: "total",
    defaultSortDir: "desc",
    columns: [
      { label: "Rank", key: "rank", numeric: true },
      { label: "Player", key: "player" },
      { label: "Team", key: "team" },
      { label: "PA", key: "pa", numeric: true },
      { label: "RAA", key: "raa", numeric: true, format: "signed" },
      { label: "RE Added", key: "reAdded", numeric: true, format: "signed" },
      { label: "Total Value", key: "total", numeric: true, format: "signed" },
      {
        label: "Value / PA",
        key: "valuePerPa",
        numeric: true,
        format: "signed",
        digits: 4,
      },
    ],
  });

  initLeaderboard({
    rows: window.MLB_RAA_PITCHERS || [],
    rangeId: "pitcher-range",
    theadId: "mlb-pitcher-thead",
    tbodyId: "mlb-pitcher-tbody",
    metaId: "pitcher-meta",
    noun: "pitchers",
    minLabel: "min. 100 BF",
    defaultSortKey: "total",
    defaultSortDir: "asc",
    numericDefaultAsc: {
      total: true,
      raa: true,
      reAdded: true,
      valuePerBf: true,
      bf: false,
      rank: true,
    },
    columns: [
      { label: "Rank", key: "rank", numeric: true },
      { label: "Player", key: "player" },
      { label: "Team", key: "team" },
      { label: "BF", key: "bf", numeric: true },
      { label: "RAA", key: "raa", numeric: true, format: "signed" },
      { label: "RE Added", key: "reAdded", numeric: true, format: "signed" },
      { label: "Total Value", key: "total", numeric: true, format: "signed" },
      {
        label: "Value / BF",
        key: "valuePerBf",
        numeric: true,
        format: "signed",
        digits: 4,
      },
    ],
  });
})();
