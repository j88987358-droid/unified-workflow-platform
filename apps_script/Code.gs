/**
 * Unified Workflow Platform - Google Sheets persistence API.
 * Configure Script Properties:
 *   UWP_SPREADSHEET_ID = target Google Spreadsheet ID
 *   UWP_API_TOKEN      = long random secret shared with GitHub Actions
 * Deploy as a Web App, execute as the deploying account, access: Anyone.
 * The API itself authenticates every POST using UWP_API_TOKEN.
 */
function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    var props = PropertiesService.getScriptProperties();
    var expectedToken = props.getProperty('UWP_API_TOKEN');
    if (!expectedToken || !constantTimeEquals_(String(body.token || ''), expectedToken)) {
      return json_({ success: false, error: 'UNAUTHORIZED' });
    }

    lock.waitLock(30000);
    var spreadsheetId = props.getProperty('UWP_SPREADSHEET_ID');
    if (!spreadsheetId) throw new Error('UWP_SPREADSHEET_ID is not configured');
    var ss = SpreadsheetApp.openById(spreadsheetId);
    var result = dispatch_(ss, body);
    return json_(result);
  } catch (err) {
    return json_({ success: false, error: safeError_(err) });
  } finally {
    try { if (lock.hasLock()) lock.releaseLock(); } catch (ignored) {}
  }
}

function dispatch_(ss, body) {
  var action = String(body.action || '');
  if (action === 'ping') return { success: true, status: 'CONNECTED' };
  if (action === 'get') return getValue_(ss, body.key);
  if (action === 'set') return setValue_(ss, body.key, body.value);
  if (action === 'delete') return deleteValue_(ss, body.key);
  if (action === 'lease_start') return leaseStart_(ss, body);
  if (action === 'lease_heartbeat') return leaseHeartbeat_(ss, body);
  if (action === 'lease_check') return leaseCheck_(ss, body);
  if (action === 'lease_inspect') return leaseInspect_(ss, body);
  if (action === 'lease_release') return leaseRelease_(ss, body);
  return { success: false, error: 'UNKNOWN_ACTION' };
}

function getValue_(ss, key) {
  requireString_(key, 'key');
  var sheet = ensureSheet_(ss, 'Persistence', ['key', 'value_json', 'updated_at']);
  var row = findRow_(sheet, 1, String(key));
  if (!row) return { success: true, found: false, value: null };
  var raw = sheet.getRange(row, 2).getValue();
  return { success: true, found: true, value: JSON.parse(String(raw)) };
}

function setValue_(ss, key, value) {
  requireString_(key, 'key');
  if (value === undefined) throw new Error('value is required');
  var sheet = ensureSheet_(ss, 'Persistence', ['key', 'value_json', 'updated_at']);
  var row = findRow_(sheet, 1, String(key));
  if (!row) row = Math.max(sheet.getLastRow() + 1, 2);
  sheet.getRange(row, 1, 1, 3).setValues([[
    String(key), JSON.stringify(value), new Date().toISOString()
  ]]);
  return { success: true, action: 'SET', key: String(key) };
}

function deleteValue_(ss, key) {
  requireString_(key, 'key');
  var sheet = ensureSheet_(ss, 'Persistence', ['key', 'value_json', 'updated_at']);
  var row = findRow_(sheet, 1, String(key));
  if (row) sheet.deleteRow(row);
  return { success: true, action: 'DELETE', key: String(key), deleted: !!row };
}

function leaseStart_(ss, body) {
  var p = leaseParams_(body);
  var sheet = leaseSheet_(ss);
  var row = findRow_(sheet, 1, p.taskId);
  var now = Date.now();
  if (row) {
    var existing = sheet.getRange(row, 2, 1, 2).getValues()[0];
    var existingOwner = String(existing[0]);
    var expiresAt = Number(existing[1]);
    if (expiresAt > now && existingOwner !== p.owner) {
      return { success: false, error: 'LEASE_ALREADY_HELD', owner: existingOwner, expires_at: expiresAt };
    }
  } else {
    row = Math.max(sheet.getLastRow() + 1, 2);
  }
  var expiry = now + p.seconds * 1000;
  sheet.getRange(row, 1, 1, 4).setValues([[p.taskId, p.owner, expiry, new Date(now).toISOString()]]);
  return { success: true, valid: true, task_id: p.taskId, owner: p.owner, expires_at: expiry };
}

function leaseHeartbeat_(ss, body) {
  var p = leaseParams_(body);
  var sheet = leaseSheet_(ss);
  var row = findRow_(sheet, 1, p.taskId);
  if (!row) return { success: false, error: 'LEASE_NOT_FOUND' };
  var values = sheet.getRange(row, 2, 1, 2).getValues()[0];
  if (String(values[0]) !== p.owner) return { success: false, error: 'LEASE_OWNER_MISMATCH' };
  if (Number(values[1]) <= Date.now()) return { success: false, error: 'LEASE_EXPIRED' };
  var now = Date.now();
  var expiry = now + p.seconds * 1000;
  sheet.getRange(row, 3, 1, 2).setValues([[expiry, new Date(now).toISOString()]]);
  return { success: true, valid: true, expires_at: expiry };
}

function leaseCheck_(ss, body) {
  var p = leaseParams_(body);
  var sheet = leaseSheet_(ss);
  var row = findRow_(sheet, 1, p.taskId);
  if (!row) return { success: true, valid: false, error: 'LEASE_NOT_FOUND' };
  var values = sheet.getRange(row, 2, 1, 2).getValues()[0];
  var valid = String(values[0]) === p.owner && Number(values[1]) > Date.now();
  return { success: true, valid: valid, expires_at: Number(values[1]) };
}

function leaseInspect_(ss, body) {
  requireString_(body.task_id, 'task_id');
  var taskId = String(body.task_id);
  var sheet = leaseSheet_(ss);
  var row = findRow_(sheet, 1, taskId);
  if (!row) return { success: true, active: false, owner: null, expires_at: null };

  var values = sheet.getRange(row, 2, 1, 2).getValues()[0];
  var owner = String(values[0]);
  var expiresAt = Number(values[1]);
  var active = expiresAt > Date.now();
  return {
    success: true,
    active: active,
    owner: active ? owner : null,
    expires_at: expiresAt
  };
}

function leaseRelease_(ss, body) {
  var p = leaseParams_(body);
  var sheet = leaseSheet_(ss);
  var row = findRow_(sheet, 1, p.taskId);
  if (!row) return { success: true, released: false, error: 'LEASE_NOT_FOUND' };
  var owner = String(sheet.getRange(row, 2).getValue());
  if (owner !== p.owner) return { success: false, error: 'LEASE_OWNER_MISMATCH' };
  sheet.deleteRow(row);
  return { success: true, released: true };
}

function leaseParams_(body) {
  requireString_(body.task_id, 'task_id');
  requireString_(body.owner, 'owner');
  var seconds = Number(body.lease_seconds || 180);
  if (!isFinite(seconds) || seconds < 30 || seconds > 86400) throw new Error('lease_seconds must be between 30 and 86400');
  return { taskId: String(body.task_id), owner: String(body.owner), seconds: Math.floor(seconds) };
}

function leaseSheet_(ss) {
  return ensureSheet_(ss, 'ExecutionLeases', ['task_id', 'owner', 'expires_at_ms', 'updated_at']);
}

function ensureSheet_(ss, name, headers) {
  var sheet = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sheet.getLastRow() === 0) sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  return sheet;
}

function findRow_(sheet, column, value) {
  var last = sheet.getLastRow();
  if (last < 2) return 0;
  var found = sheet.getRange(2, column, last - 1, 1)
    .createTextFinder(String(value)).matchEntireCell(true).findNext();
  return found ? found.getRow() : 0;
}

function requireString_(value, name) {
  if (value === undefined || value === null || String(value).trim() === '') throw new Error(name + ' is required');
}

function constantTimeEquals_(a, b) {
  if (a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function safeError_(err) {
  return String(err && err.message ? err.message : err).slice(0, 300);
}

function json_(value) {
  return ContentService.createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}
