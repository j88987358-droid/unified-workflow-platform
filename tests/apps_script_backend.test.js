const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Range {
  constructor(sheet, row, col, rows = 1, cols = 1) { Object.assign(this, { sheet, row, col, rows, cols }); }
  getValues() { return Array.from({ length: this.rows }, (_, r) => Array.from({ length: this.cols }, (_, c) => this.sheet.data[this.row - 1 + r]?.[this.col - 1 + c] ?? '')); }
  getValue() { return this.getValues()[0][0]; }
  setValues(values) { values.forEach((line, r) => line.forEach((v, c) => { const rr = this.row - 1 + r, cc = this.col - 1 + c; while (this.sheet.data.length <= rr) this.sheet.data.push([]); this.sheet.data[rr][cc] = v; })); return this; }
  createTextFinder(value) { return { matchEntireCell: () => ({ findNext: () => { for (let r = 1; r < this.sheet.data.length; r++) if (String(this.sheet.data[r]?.[this.col - 1] ?? '') === String(value)) return { getRow: () => r + 1 }; return null; } }) }; }
}
class Sheet {
  constructor(name) { this.name = name; this.data = []; }
  getLastRow() { let n = this.data.length; while (n && this.data[n - 1].every(v => v === '' || v === undefined)) n--; return n; }
  getRange(r, c, nr, nc) { return new Range(this, r, c, nr, nc); }
  deleteRow(row) { this.data.splice(row - 1, 1); }
}
class Spreadsheet {
  constructor() { this.sheets = new Map(); }
  getSheetByName(name) { return this.sheets.get(name) || null; }
  insertSheet(name) { const s = new Sheet(name); this.sheets.set(name, s); return s; }
}

const spreadsheet = new Spreadsheet();
const lockStats = { waits: 0, releases: 0 };
const context = {
  Date, JSON, String, Number, Math, isFinite,
  PropertiesService: { getScriptProperties: () => ({ getProperty: k => ({ UWP_API_TOKEN: 'test-secret', UWP_SPREADSHEET_ID: 'sheet-id' })[k] || null }) },
  SpreadsheetApp: { openById: id => { assert.equal(id, 'sheet-id'); return spreadsheet; } },
  LockService: { getScriptLock: () => ({
    waitLock() { lockStats.waits += 1; },
    hasLock: () => true,
    releaseLock() { lockStats.releases += 1; }
  }) },
  ContentService: { MimeType: { JSON: 'application/json' }, createTextOutput: text => ({ text, setMimeType() { return this; } }) }
};
vm.createContext(context);
vm.runInContext(fs.readFileSync('apps_script/Code.gs', 'utf8'), context);
function call(action, extra = {}, token = 'test-secret') {
  const out = context.doPost({ postData: { contents: JSON.stringify({ action, token, ...extra }) } });
  return JSON.parse(out.text);
}

test('rejects unauthorized requests', () => assert.equal(call('ping', {}, 'bad').error, 'UNAUTHORIZED'));
test('ping and key-value persistence', () => {
  assert.equal(call('ping').status, 'CONNECTED');
  assert.equal(call('set', { key: 'alpha', value: { count: 7 } }).success, true);
  assert.deepEqual(JSON.parse(JSON.stringify(call('get', { key: 'alpha' }).value)), { count: 7 });
  assert.equal(call('delete', { key: 'alpha' }).deleted, true);
  assert.equal(call('get', { key: 'alpha' }).found, false);
});
test('only one owner can hold an unexpired lease', () => {
  assert.equal(call('lease_start', { task_id: 't1', owner: 'runner-a', lease_seconds: 180 }).valid, true);
  const denied = call('lease_start', { task_id: 't1', owner: 'runner-b', lease_seconds: 180 });
  assert.equal(denied.success, false);
  assert.equal(denied.error, 'LEASE_ALREADY_HELD');
});
test('heartbeat, check and release enforce lease ownership', () => {
  assert.equal(call('lease_check', { task_id: 't1', owner: 'runner-a' }).valid, true);
  assert.equal(call('lease_inspect', { task_id: 't1' }).active, true);
  assert.equal(call('lease_heartbeat', { task_id: 't1', owner: 'runner-a' }).valid, true);
  assert.equal(call('lease_release', { task_id: 't1', owner: 'runner-b' }).error, 'LEASE_OWNER_MISMATCH');
  assert.equal(call('lease_release', { task_id: 't1', owner: 'runner-a' }).released, true);
  assert.equal(call('lease_check', { task_id: 't1', owner: 'runner-a' }).valid, false);
  assert.equal(call('lease_inspect', { task_id: 't1' }).active, false);
});
test('expired lease can be acquired by a new owner', () => {
  const originalNow = Date.now;
  let now = 1_700_000_000_000;
  Date.now = () => now;
  try {
    assert.equal(call('lease_start', { task_id: 't-exp', owner: 'old', lease_seconds: 30 }).valid, true);
    now += 31_000;
    assert.equal(call('lease_start', { task_id: 't-exp', owner: 'new', lease_seconds: 30 }).owner, 'new');
  } finally { Date.now = originalNow; }
});


test('serializes each request through the Apps Script project lock', () => {
  const waitsBefore = lockStats.waits;
  const releasesBefore = lockStats.releases;
  assert.equal(call('ping').status, 'CONNECTED');
  assert.equal(lockStats.waits, waitsBefore + 1);
  assert.equal(lockStats.releases, releasesBefore + 1);
});


test('versioned reads and compare-and-set reject stale revisions', () => {
  const first = call('get_versioned', { key: 'cas-key' });
  assert.equal(first.revision, 0);
  const saved = call('compare_and_set', { key: 'cas-key', expected_revision: 0, new_value: { count: 1 } });
  assert.equal(saved.updated, true);
  assert.equal(saved.revision, 1);
  const stale = call('compare_and_set', { key: 'cas-key', expected_revision: 0, new_value: { count: 99 } });
  assert.equal(stale.conflict, true);
  assert.equal(stale.revision, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(call('get_versioned', { key: 'cas-key' }).value)), { count: 1 });
});

test('compare-and-set write requires valid API token', () => {
  const denied = call('compare_and_set', { key: 'secure', expected_revision: 0, new_value: { x: 1 } }, 'bad-token');
  assert.equal(denied.success, false);
  assert.equal(denied.error, 'UNAUTHORIZED');
  assert.equal(call('get_versioned', { key: 'secure' }).found, false);
});

test('compare-and-set advances revision for each successful write', () => {
  assert.equal(call('compare_and_set', { key: 'revision-key', expected_revision: 0, new_value: 1 }).revision, 1);
  assert.equal(call('compare_and_set', { key: 'revision-key', expected_revision: 1, new_value: 2 }).revision, 2);
});
