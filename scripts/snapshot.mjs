#!/usr/bin/env node
// Freeze today's build as snapshots/YYYY-MM-DD - <project>.html. The index repo's nightly refresh finds it on the
// default branch and logs the sprint day, with no index.yml edit. It goes on the public sprint site only if the page
// carries <meta name="sprint-public" content="yes"> (added only when sprint.config.json has "public": true or
// --public is passed) and it passes the nightly UAT and secret scan. A private snapshot never carries the tag.
//
//   node scripts/snapshot.mjs <page.html> [--project "Name"] [--public] [--backfill YYYY-MM-DD]
//
// Day snapshots are frozen records: today's can be rewritten; an earlier day's never is.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const SNAPSHOT_DIR = 'snapshots'; // fixed: the index only scans this folder
export const PUBLIC_META = '<meta name="sprint-public" content="yes">';
const ANY_TAG = /<meta\s+name=["']?sprint-public["']?[^>]*>/gi;
const TAG_TEXT = /sprint-public/i;
const HEAD = /<head(\s[^>]*)?>/i;
const NAME = /^[\p{L}\p{N}](?:[\p{L}\p{N} .,()'_-]{0,78}[\p{L}\p{N}).'_-])?$/u;

export function dayIn(timeZone, now = new Date()) {
  if (!timeZone) throw new Error('set "timeZone" in sprint.config.json');
  try {
    return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  } catch {
    throw new Error(`"${timeZone}" is not a valid time zone`);
  }
}

export function isRealDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(`${s}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}

export function makePublic(html) {
  const existing = html.match(ANY_TAG) ?? [];
  if (existing.some((t) => !/content=["']?yes["']?/i.test(t))) throw new Error('page has a sprint-public tag that is not "yes"; remove it first');
  if (existing.length) return html;
  if (!HEAD.test(html)) throw new Error('page has no <head>; the public tag must go in <head>');
  return html.replace(HEAD, (m) => `${m}\n${PUBLIC_META}`);
}

export function makePrivate(html) {
  // Any mention of the tag (a meta tag, or text inside a script) could be read as an opt-in by the index: refuse
  // rather than edit the page. Remove it from the source page, or snapshot with --public.
  if (TAG_TEXT.test(html)) throw new Error('page mentions "sprint-public"; a private snapshot cannot carry it (remove it, or use --public)');
  return html;
}

// Files already on the default branch, so a stale local branch can't overwrite a merged record.
export function onMain(repoRoot, path) {
  try {
    execFileSync('git', ['-C', repoRoot, 'cat-file', '-e', `origin/main:${path}`], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

export function snapshot({ page, project, isPublic, date, today, root, backfill = false, mainHas = () => false }) {
  if (!project || project === 'PROJECT_NAME') throw new Error('set "project" in sprint.config.json or pass --project');
  if (!NAME.test(project)) throw new Error('project name must start with a letter or digit, have no leading/trailing spaces, and use only letters, digits, spaces and . , ( ) \' _ -');
  if (!isRealDate(date)) throw new Error(`${date} is not a real date (YYYY-MM-DD)`);
  if (date > today) throw new Error('cannot snapshot a future day');
  if (date < today && !backfill) throw new Error('earlier days are frozen; use --backfill YYYY-MM-DD only to add a missing day');
  const rel = `${SNAPSHOT_DIR}/${date} - ${project}.html`;
  const out = join(root, rel);
  if (date < today && (existsSync(out) || mainHas(rel))) throw new Error(`${rel} is a frozen record from an earlier day; not overwriting it`);
  const html = readFileSync(page, 'utf8');
  const body = isPublic ? makePublic(html) : makePrivate(html);
  mkdirSync(join(root, SNAPSHOT_DIR), { recursive: true });
  writeFileSync(out, body);
  return out;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const args = process.argv.slice(2);
  const flag = (n) => {
    const i = args.indexOf(`--${n}`);
    if (i < 0) return undefined;
    const v = args[i + 1];
    if (v === undefined || v.startsWith('--')) throw new Error(`--${n} needs a value`);
    return v;
  };
  try {
    const cfg = JSON.parse(readFileSync(join(root, 'sprint.config.json'), 'utf8'));
    const page = args[0];
    if (!page || page.startsWith('--')) throw new Error('usage: node scripts/snapshot.mjs <page.html> [--project "Name"] [--public] [--backfill YYYY-MM-DD]');
    const today = dayIn(cfg.timeZone);
    const backfillDate = flag('backfill');
    const out = snapshot({
      page,
      project: flag('project') ?? cfg.project,
      isPublic: args.includes('--public') || cfg.public === true,
      date: backfillDate ?? today,
      today,
      root,
      backfill: Boolean(backfillDate),
      mainHas: (rel) => onMain(root, rel),
    });
    console.log(`snapshot: ${out}`);
  } catch (e) {
    console.error(`snapshot: ${e.message}`);
    process.exit(1);
  }
}
