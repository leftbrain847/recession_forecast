import { test } from 'node:test';
import assert from 'node:assert';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { dayIn, isRealDate, makePublic, makePrivate, snapshot, PUBLIC_META } from '../scripts/snapshot.mjs';

const PAGE = '<html><head><title>x</title></head><body><header>h</header>hi</body></html>';
const setup = (html = PAGE) => {
  const root = mkdtempSync(join(tmpdir(), 'snap-'));
  const page = join(root, 'page.html');
  writeFileSync(page, html);
  return { root, page };
};
const base = (o) => ({ project: 'Demo', isPublic: false, date: '2026-11-08', today: '2026-11-08', ...o });

test('dates in the configured time zone, not UTC', () => {
  assert.equal(dayIn('America/New_York', new Date('2026-11-09T03:00:00Z')), '2026-11-08');
  assert.throws(() => dayIn('Not/AZone'), /valid time zone/);
  assert.throws(() => dayIn(undefined), /timeZone/);
});

test('real dates only', () => {
  assert.ok(isRealDate('2026-11-08'));
  assert.ok(!isRealDate('2026-02-30'));
});

test('writes a dated snapshot, private by default', () => {
  const { root, page } = setup();
  const out = snapshot(base({ page, root }));
  assert.ok(out.endsWith('snapshots/2026-11-08 - Demo.html'));
  assert.ok(!readFileSync(out, 'utf8').includes('sprint-public'));
});

test('private refuses a page that already carries the tag', () => {
  assert.throws(() => makePrivate(`<html><head>${PUBLIC_META}</head></html>`), /cannot carry/);
});

test('private refuses a page mentioning the tag elsewhere', () => {
  assert.throws(() => makePrivate(`<html><head></head><script>x='${PUBLIC_META}'</script></html>`), /cannot carry/);
});

test('public adds the tag once, inside <head> not <header>', () => {
  const html = makePublic(makePublic(PAGE));
  assert.equal(html.split(PUBLIC_META).length, 2);
  assert.ok(html.indexOf(PUBLIC_META) < html.indexOf('<title>'));
});

test('public refuses a conflicting tag or a page without <head>', () => {
  assert.throws(() => makePublic('<html><head><meta name="sprint-public" content="no"></head></html>'), /not "yes"/);
  assert.throws(() => makePublic('<body>hi</body>'), /no <head>/);
});

test('earlier days are frozen; backfill only adds missing days', () => {
  const { root, page } = setup();
  assert.throws(() => snapshot(base({ page, root, date: '2026-11-07' })), /frozen/);
  snapshot(base({ page, root, date: '2026-11-07', backfill: true }));
  assert.throws(() => snapshot(base({ page, root, date: '2026-11-07', backfill: true })), /frozen record/);
  assert.throws(() => snapshot(base({ page, root, date: '2026-11-06', backfill: true, mainHas: () => true })), /frozen record/);
});

test('refuses bad names and future days', () => {
  const { root, page } = setup();
  for (const project of ['PROJECT_NAME', ' Demo ', '   ', '..', '--public', 'a/b']) {
    assert.throws(() => snapshot(base({ page, root, project })), /project/, project);
  }
  assert.throws(() => snapshot(base({ page, root, date: '2026-11-09' })), /future/);
  assert.ok(!existsSync(join(root, 'snapshots', '2026-11-09 - Demo.html')));
});
