/**
 * NFL Probabilities — Google Apps Script backend
 *
 * Sheet setup (nfl_guessing_game_2026):
 *   - Tabs "Week 1", "Week 2", … with columns including:
 *       Away | Home | Normalized Odds Away | Normalized Odds Home | AwayWin
 *   - AwayWin empty  → game still open for predictions
 *   - AwayWin filled → game locked (TRUE/1/away = away won; FALSE/0/home = home won)
 *   - Predictions are stored on tabs like "Week 1 Predictions"
 *
 * Deploy as web app (Execute as: Me, Who has access: Anyone), then put the
 * /exec URL + API_TOKEN into Cloudflare Worker secrets.
 */

const SPREADSHEET_NAME = "nfl_guessing_game_2026";
const API_TOKEN = "rjnaCRvi842uKVn2avri23ua"; // must match Cloudflare APPS_SCRIPT_TOKEN

function doGet(e) {
  if (!authorized_(e)) {
    return jsonResponse_({ error: "Unauthorized" });
  }

  const action = (e.parameter.action || "games").toLowerCase();

  if (action === "games") {
    var username = String(e.parameter.user || "").trim();
    return jsonResponse_(getLatestWeekGames_(username));
  }

  if (action === "userpredictions" || action === "user-predictions") {
    var user = String(e.parameter.user || "").trim();
    var weekNum = parseInt(e.parameter.week, 10);
    if (!user) {
      return jsonResponse_({ error: "Username is required" });
    }
    if (!weekNum) {
      return jsonResponse_({ error: "Week is required" });
    }
    var ss = openGameSpreadsheet_();
    var savedMap = loadUserPredictions_(ss, weekNum, user);
    var list = [];
    var keys = Object.keys(savedMap);
    for (var i = 0; i < keys.length; i++) {
      var parts = keys[i].split("|");
      list.push({
        away: parts[0],
        home: parts[1],
        awayWinPct: savedMap[keys[i]],
      });
    }
    return jsonResponse_({
      username: user,
      week: weekNum,
      predictions: list,
    });
  }

  if (
    action === "weekpredictions" ||
    action === "week-predictions" ||
    action === "others"
  ) {
    var boardWeek = parseInt(e.parameter.week, 10);
    return jsonResponse_(getWeekPredictionsBoard_(boardWeek || null));
  }

  return jsonResponse_({ error: "Unknown action" });
}

function doPost(e) {
  if (!authorized_(e)) {
    return jsonResponse_({ error: "Unauthorized" });
  }

  try {
    const payload = JSON.parse(e.postData.contents);
    var result = savePredictions_(payload);
    return jsonResponse_(result);
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

function predictionsSheetName_(week) {
  return "Week " + week + " Predictions";
}

function getLatestWeekGames_(username) {
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

  var gamesOut = readGamesFromSheet_(latestSheet);

  if (username) {
    var saved = loadUserPredictions_(ss, latestWeek, username);
    for (var g = 0; g < gamesOut.length; g++) {
      var key = predictionKey_(gamesOut[g].away, gamesOut[g].home);
      if (saved[key] !== undefined) {
        gamesOut[g].userAwayWinPct = saved[key];
      }
    }
  }

  return {
    week: latestWeek,
    weekLabel: latestSheet.getName(),
    games: gamesOut,
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
  var awayWinIdx = findColumnIndex_(headers, [
    "awaywin",
    "away win",
    "away_win",
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

    var awayWinInfo = parseAwayWin_(
      awayWinIdx === -1 ? null : data[row][awayWinIdx]
    );
    game.locked = awayWinInfo.locked;
    game.awayWin = awayWinInfo.awayWin;

    games.push(game);
  }

  return games;
}

/**
 * Empty → unlocked.
 * Any value → locked.
 * TRUE/1/away/yes → awayWin true; FALSE/0/home/no → awayWin false.
 */
function parseAwayWin_(value) {
  if (value === null || value === undefined) {
    return { locked: false, awayWin: null };
  }

  if (typeof value === "string" && value.trim() === "") {
    return { locked: false, awayWin: null };
  }

  if (typeof value === "boolean") {
    return { locked: true, awayWin: value };
  }

  if (typeof value === "number") {
    if (isNaN(value)) {
      return { locked: false, awayWin: null };
    }
    return { locked: true, awayWin: value !== 0 };
  }

  var text = String(value).trim().toLowerCase();
  if (text === "") {
    return { locked: false, awayWin: null };
  }

  if (
    text === "true" ||
    text === "1" ||
    text === "yes" ||
    text === "y" ||
    text === "away" ||
    text === "w"
  ) {
    return { locked: true, awayWin: true };
  }

  if (
    text === "false" ||
    text === "0" ||
    text === "no" ||
    text === "n" ||
    text === "home" ||
    text === "l"
  ) {
    return { locked: true, awayWin: false };
  }

  // Any other non-empty value still locks the game.
  return { locked: true, awayWin: null };
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

function predictionKey_(away, home) {
  return String(away).trim().toLowerCase() + "|" + String(home).trim().toLowerCase();
}

function getOrCreatePredictionsSheet_(ss, week) {
  var name = predictionsSheetName_(week);
  var sheet = ss.getSheetByName(name);

  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow([
      "Submitted At",
      "Username",
      "Away",
      "Home",
      "Away Win %",
      "Home Win %",
    ]);
  }

  return sheet;
}

/**
 * Board for Others' Predictions:
 * rows = games, columns = participants, cells = favored team + %.
 */
function getWeekPredictionsBoard_(weekOpt) {
  var ss = openGameSpreadsheet_();
  var week = weekOpt;
  var weekSheet = null;

  if (week) {
    weekSheet = ss.getSheetByName("Week " + week);
  }

  if (!weekSheet) {
    var sheets = ss.getSheets();
    var latestWeek = 0;
    for (var i = 0; i < sheets.length; i++) {
      var match = sheets[i].getName().match(/^Week\s+(\d+)$/i);
      if (!match) {
        continue;
      }
      var weekNum = parseInt(match[1], 10);
      var gamesCheck = readGamesFromSheet_(sheets[i]);
      if (gamesCheck.length > 0 && weekNum >= latestWeek) {
        latestWeek = weekNum;
        weekSheet = sheets[i];
      }
    }
    week = latestWeek || null;
  }

  if (!weekSheet || !week) {
    return { week: null, weekLabel: null, participants: [], games: [] };
  }

  var games = readGamesFromSheet_(weekSheet);
  var allPicks = loadAllPredictionsForWeek_(ss, week); // { displayName: { key: awayWinPct } }
  var participants = Object.keys(allPicks).sort(function (a, b) {
    return a.toLowerCase().localeCompare(b.toLowerCase());
  });

  var boardGames = [];
  for (var g = 0; g < games.length; g++) {
    var game = games[g];
    var key = predictionKey_(game.away, game.home);
    var picks = {};

    for (var p = 0; p < participants.length; p++) {
      var name = participants[p];
      var awayPct = allPicks[name][key];
      if (awayPct === undefined || awayPct === null) {
        picks[name] = null;
        continue;
      }
      picks[name] = formatFavoredPick_(game.away, game.home, awayPct);
    }

    boardGames.push({
      away: game.away,
      home: game.home,
      label: game.away + " @" + game.home,
      picks: picks,
    });
  }

  return {
    week: week,
    weekLabel: weekSheet.getName(),
    participants: participants,
    games: boardGames,
  };
}

function formatFavoredPick_(away, home, awayWinPct) {
  var awayPct = Math.max(0, Math.min(100, Math.round(Number(awayWinPct))));
  var homePct = 100 - awayPct;
  if (awayPct >= homePct) {
    return { team: away, pct: awayPct, awayWinPct: awayPct };
  }
  return { team: home, pct: homePct, awayWinPct: awayPct };
}

/** All users' away-win % by matchup key for a week. */
function loadAllPredictionsForWeek_(ss, week) {
  var byUser = {}; // displayName -> { matchupKey: awayWinPct }

  function ensureUser_(displayName) {
    var existing = null;
    var lower = displayName.toLowerCase();
    var names = Object.keys(byUser);
    for (var i = 0; i < names.length; i++) {
      if (names[i].toLowerCase() === lower) {
        existing = names[i];
        break;
      }
    }
    if (existing) {
      return existing;
    }
    byUser[displayName] = {};
    return displayName;
  }

  function ingest_(displayName, away, home, pctValue, onlyIfMissing) {
    var awayName = String(away || "").trim();
    var homeName = String(home || "").trim();
    var awayPct = parseProbability_(pctValue);
    if (!displayName || !awayName || !homeName || awayPct === null) {
      return;
    }
    var userKey = ensureUser_(String(displayName).trim());
    var key = predictionKey_(awayName, homeName);
    if (onlyIfMissing && byUser[userKey][key] !== undefined) {
      return;
    }
    byUser[userKey][key] = Math.max(0, Math.min(100, Math.round(awayPct)));
  }

  function readSheetRows_(sheet, hasWeekColumn, onlyIfMissing) {
    if (!sheet || sheet.getLastRow() < 2) {
      return;
    }
    var data = sheet.getDataRange().getValues();
    var headers = data[0].map(function (cell) {
      return String(cell).trim().toLowerCase();
    });
    var userIdx = findColumnIndex_(headers, ["username", "user", "name"]);
    var weekIdx = findColumnIndex_(headers, ["week"]);
    var awayIdx = findColumnIndex_(headers, ["away", "away team"]);
    var homeIdx = findColumnIndex_(headers, ["home", "home team"]);
    var pctIdx = findColumnIndex_(headers, [
      "away win %",
      "away win pct",
      "awaywinpct",
      "away_win_%",
    ]);

    if (userIdx === -1) userIdx = 1;
    if (awayIdx === -1) awayIdx = hasWeekColumn || weekIdx !== -1 ? 3 : 2;
    if (homeIdx === -1) homeIdx = hasWeekColumn || weekIdx !== -1 ? 4 : 3;
    if (pctIdx === -1) pctIdx = hasWeekColumn || weekIdx !== -1 ? 5 : 4;

    for (var row = 1; row < data.length; row++) {
      if (weekIdx !== -1) {
        var rowWeek = Number(data[row][weekIdx]);
        if (rowWeek !== Number(week)) {
          continue;
        }
      }
      ingest_(
        data[row][userIdx],
        data[row][awayIdx],
        data[row][homeIdx],
        data[row][pctIdx],
        onlyIfMissing
      );
    }
  }

  readSheetRows_(ss.getSheetByName(predictionsSheetName_(week)), false, false);
  readSheetRows_(ss.getSheetByName("Predictions"), true, true);

  return byUser;
}

function loadUserPredictions_(ss, week, username) {
  var map = {};
  var wantUser = username.toLowerCase();

  function ingestRow_(away, home, pctValue) {
    var awayName = String(away || "").trim();
    var homeName = String(home || "").trim();
    var awayPct = parseProbability_(pctValue);
    if (!awayName || !homeName || awayPct === null) {
      return;
    }
    map[predictionKey_(awayName, homeName)] = Math.max(
      0,
      Math.min(100, Math.round(awayPct))
    );
  }

  // Preferred: "Week N Predictions"
  var weekSheet = ss.getSheetByName(predictionsSheetName_(week));
  if (weekSheet && weekSheet.getLastRow() >= 2) {
    var data = weekSheet.getDataRange().getValues();
    var headers = data[0].map(function (cell) {
      return String(cell).trim().toLowerCase();
    });
    var userIdx = findColumnIndex_(headers, ["username", "user", "name"]);
    var awayIdx = findColumnIndex_(headers, ["away", "away team"]);
    var homeIdx = findColumnIndex_(headers, ["home", "home team"]);
    var pctIdx = findColumnIndex_(headers, [
      "away win %",
      "away win pct",
      "awaywinpct",
      "away_win_%",
    ]);

    if (userIdx === -1) userIdx = 1;
    if (awayIdx === -1) awayIdx = 2;
    if (homeIdx === -1) homeIdx = 3;
    if (pctIdx === -1) pctIdx = 4;

    for (var row = 1; row < data.length; row++) {
      var rowUser = String(data[row][userIdx] || "").trim().toLowerCase();
      if (rowUser !== wantUser) {
        continue;
      }
      ingestRow_(data[row][awayIdx], data[row][homeIdx], data[row][pctIdx]);
    }
  }

  // Fallback: legacy "Predictions" tab
  var legacy = ss.getSheetByName("Predictions");
  if (legacy && legacy.getLastRow() >= 2) {
    var legacyData = legacy.getDataRange().getValues();
    var legacyHeaders = legacyData[0].map(function (cell) {
      return String(cell).trim().toLowerCase();
    });
    var lUserIdx = findColumnIndex_(legacyHeaders, ["username", "user", "name"]);
    var lWeekIdx = findColumnIndex_(legacyHeaders, ["week"]);
    var lAwayIdx = findColumnIndex_(legacyHeaders, ["away", "away team"]);
    var lHomeIdx = findColumnIndex_(legacyHeaders, ["home", "home team"]);
    var lPctIdx = findColumnIndex_(legacyHeaders, [
      "away win %",
      "away win pct",
      "awaywinpct",
      "away_win_%",
    ]);

    if (lUserIdx === -1) lUserIdx = 1;
    if (lAwayIdx === -1) lAwayIdx = lWeekIdx === -1 ? 2 : 3;
    if (lHomeIdx === -1) lHomeIdx = lWeekIdx === -1 ? 3 : 4;
    if (lPctIdx === -1) lPctIdx = lWeekIdx === -1 ? 4 : 5;

    for (var r = 1; r < legacyData.length; r++) {
      var legacyUser = String(legacyData[r][lUserIdx] || "")
        .trim()
        .toLowerCase();
      if (legacyUser !== wantUser) {
        continue;
      }
      if (lWeekIdx !== -1) {
        var legacyWeek = Number(legacyData[r][lWeekIdx]);
        if (legacyWeek !== Number(week)) {
          continue;
        }
      }
      var key = predictionKey_(legacyData[r][lAwayIdx], legacyData[r][lHomeIdx]);
      if (map[key] === undefined) {
        ingestRow_(
          legacyData[r][lAwayIdx],
          legacyData[r][lHomeIdx],
          legacyData[r][lPctIdx]
        );
      }
    }
  }

  return map;
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
  var weekSheet = ss.getSheetByName("Week " + week);
  if (!weekSheet) {
    throw new Error('Week sheet "Week ' + week + '" not found');
  }

  var games = readGamesFromSheet_(weekSheet);
  var lockByMatchup = {};
  for (var g = 0; g < games.length; g++) {
    lockByMatchup[predictionKey_(games[g].away, games[g].home)] = !!games[g].locked;
  }

  var sheet = getOrCreatePredictionsSheet_(ss, week);
  var data = sheet.getDataRange().getValues();
  var existingRows = {}; // key -> 1-based sheet row index

  for (var row = 1; row < data.length; row++) {
    var rowUser = String(data[row][1] || "").trim().toLowerCase();
    if (rowUser !== username.toLowerCase()) {
      continue;
    }
    var key = predictionKey_(data[row][2], data[row][3]);
    existingRows[key] = row + 1; // convert to 1-based
  }

  var timestamp = new Date();
  var saved = 0;
  var skippedLocked = 0;
  var updated = 0;

  for (var i = 0; i < predictions.length; i++) {
    var pick = predictions[i];
    var away = String(pick.away || "").trim();
    var home = String(pick.home || "").trim();
    var key = predictionKey_(away, home);
    var awayPct = Number(pick.awayWinPct);

    if (!away || !home || isNaN(awayPct)) {
      continue;
    }

    if (lockByMatchup[key]) {
      skippedLocked += 1;
      continue;
    }

    awayPct = Math.max(0, Math.min(100, Math.round(awayPct)));
    var homePct = 100 - awayPct;
    var rowValues = [timestamp, username, away, home, awayPct, homePct];

    if (existingRows[key]) {
      sheet.getRange(existingRows[key], 1, existingRows[key], 6).setValues([rowValues]);
      updated += 1;
    } else {
      sheet.appendRow(rowValues);
      saved += 1;
    }
  }

  if (saved === 0 && updated === 0 && skippedLocked > 0) {
    throw new Error("All selected games are locked and cannot be updated");
  }

  return {
    success: true,
    saved: saved,
    updated: updated,
    skippedLocked: skippedLocked,
  };
}

function jsonResponse_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
