/**
 * NFL Probabilities — Google Apps Script backend
 *
 * Setup:
 * 1. Create a Google Sheet named "nfl_guessing_game_2026".
 * 2. Add tabs "Week 1", "Week 2", … with header row: Away | Home
 * 3. Extensions → Apps Script → paste this file → Save.
 * 4. Set API_TOKEN below to a long random string.
 * 5. Deploy → New deployment → Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 6. Put the /exec URL and API_TOKEN into Cloudflare Worker secrets
 *    (APPS_SCRIPT_URL, APPS_SCRIPT_TOKEN) — never into the public site.
 */

const SPREADSHEET_NAME = "nfl_guessing_game_2026";
const API_TOKEN = "REPLACE_WITH_A_LONG_RANDOM_TOKEN"; // must match Cloudflare APPS_SCRIPT_TOKEN // must match Cloudflare APPS_SCRIPT_TOKEN
const PREDICTIONS_SHEET = "Predictions";

function doGet(e) {
  if (!authorized_(e)) {
    return jsonResponse_({ error: "Unauthorized" });
  }

  const action = (e.parameter.action || "games").toLowerCase();

  if (action === "games") {
    return jsonResponse_(getLatestWeekGames_());
  }

  return jsonResponse_({ error: "Unknown action" });
}

function doPost(e) {
  if (!authorized_(e)) {
    return jsonResponse_({ error: "Unauthorized" });
  }

  try {
    const payload = JSON.parse(e.postData.contents);
    savePredictions_(payload);
    return jsonResponse_({ success: true });
  } catch (err) {
    return jsonResponse_({ error: String(err) });
  }
}

function authorized_(e) {
  return e.parameter.token === API_TOKEN;
}

function openGameSpreadsheet_() {
  const files = DriveApp.getFilesByName(SPREADSHEET_NAME);
  if (!files.hasNext()) {
    throw new Error('Spreadsheet "' + SPREADSHEET_NAME + '" not found');
  }
  return SpreadsheetApp.open(files.next());
}

function getLatestWeekGames_() {
  const ss = openGameSpreadsheet_();
  const sheets = ss.getSheets();

  var latestWeek = 0;
  var latestSheet = null;

  for (var i = 0; i < sheets.length; i++) {
    var sheet = sheets[i];
    var match = sheet.getName().match(/^Week\s+(\d+)$/i);
    if (!match) {
      continue;
    }

    var weekNum = parseInt(match[1], 10);
    var games = readGamesFromSheet_(sheet);
    if (games.length > 0 && weekNum >= latestWeek) {
      latestWeek = weekNum;
      latestSheet = sheet;
    }
  }

  if (!latestSheet) {
    return { week: null, weekLabel: null, games: [] };
  }

  return {
    week: latestWeek,
    weekLabel: latestSheet.getName(),
    games: readGamesFromSheet_(latestSheet),
  };
}

function readGamesFromSheet_(sheet) {
  var data = sheet.getDataRange().getValues();
  if (data.length < 2) {
    return [];
  }

  var headers = data[0].map(function (cell) {
    return String(cell).trim().toLowerCase();
  });

  var awayIdx = findColumnIndex_(headers, ["away", "away team"]);
  var homeIdx = findColumnIndex_(headers, ["home", "home team"]);
  var awayOddsIdx = findColumnIndex_(headers, [
    "normalized odds away",
    "normalized_odds_away",
  ]);
  var homeOddsIdx = findColumnIndex_(headers, [
    "normalized odds home",
    "normalized_odds_home",
  ]);

  if (awayIdx === -1) {
    awayIdx = 0;
  }
  if (homeIdx === -1) {
    homeIdx = 1;
  }

  var games = [];

  for (var row = 1; row < data.length; row++) {
    var away = String(data[row][awayIdx] || "").trim();
    var home = String(data[row][homeIdx] || "").trim();
    if (!away || !home) {
      continue;
    }

    var game = { away: away, home: home };
    var awayOdds = parseProbability_(
      awayOddsIdx === -1 ? null : data[row][awayOddsIdx]
    );
    var homeOdds = parseProbability_(
      homeOddsIdx === -1 ? null : data[row][homeOddsIdx]
    );

    if (awayOdds !== null) {
      game.vegasAwayPct = awayOdds;
    }
    if (homeOdds !== null) {
      game.vegasHomePct = homeOdds;
    }

    games.push(game);
  }

  return games;
}

/** Returns a 0–100 percentage, or null if missing/invalid. */
function parseProbability_(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "string") {
    value = value.replace("%", "").trim();
    if (value === "") {
      return null;
    }
  }

  var num = Number(value);
  if (isNaN(num)) {
    return null;
  }

  // Treat fractions like 0.60 as 60%.
  if (num >= 0 && num <= 1) {
    num = num * 100;
  }

  return Math.max(0, Math.min(100, Math.round(num * 10) / 10));
}

function findColumnIndex_(headers, candidates) {
  for (var i = 0; i < candidates.length; i++) {
    var idx = headers.indexOf(candidates[i]);
    if (idx !== -1) {
      return idx;
    }
  }
  return -1;
}

function savePredictions_(payload) {
  var username = String(payload.username || "").trim();
  var week = payload.week;
  var predictions = payload.predictions || [];

  if (!username) {
    throw new Error("Username is required");
  }
  if (!week || !predictions.length) {
    throw new Error("No predictions to save");
  }

  var ss = openGameSpreadsheet_();
  var sheet = ss.getSheetByName(PREDICTIONS_SHEET);

  if (!sheet) {
    sheet = ss.insertSheet(PREDICTIONS_SHEET);
    sheet.appendRow([
      "Submitted At",
      "Username",
      "Week",
      "Away",
      "Home",
      "Away Win %",
      "Home Win %",
    ]);
  }

  var timestamp = new Date();

  for (var i = 0; i < predictions.length; i++) {
    var pick = predictions[i];
    var awayPct = Number(pick.awayWinPct);
    if (isNaN(awayPct)) {
      continue;
    }
    awayPct = Math.max(0, Math.min(100, Math.round(awayPct)));
    sheet.appendRow([
      timestamp,
      username,
      week,
      pick.away,
      pick.home,
      awayPct,
      100 - awayPct,
    ]);
  }
}

function jsonResponse_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
