# Rules for this repo
- Daily ship = adds one new input, transformation or output, runs end to end from a clean clone, with a passing test.
- Every change keeps tests passing; add a test for every new behavior. CI must run them.
- Never commit secrets. Keys live in env vars / GitHub secrets; `.env.example` holds placeholders only.
- Keep settings in config objects, not hard-coded literals.
- Day snapshots are named `YYYY-MM-DD - Project` and are frozen records: never edit or republish one after its day.
- Every sprint day commits its snapshot with `node scripts/snapshot.mjs <page.html>` (see README), so the index logs the day without a manual entry. Private unless J says the day is public.
- `main` is the source of truth, changed only through merged PRs. Push the session branch and open a PR before ending a session, so no work is lost.
- Update README Run/Test/Deployed when they change.
- Keep `project.yml` (theme, tags, what, next, active) current; the index reads it nightly.

## Working rules for agents (shared across J's repos)

- **Public-safe by default.** Write everything as if this repo will be public tomorrow. No secrets or real personal data in code, config or history (keys go in env vars and GitHub secrets). No security through hidden code: anything that would be unsafe if the repo went public is a bug, so flag it.
- **PRs, never pushes to `main`.** Every change goes through a pull request. Claude merges it once CI is green and, for high-risk PRs, an independent review has passed; J gets a short summary instead of a review queue. Hold a PR for J only when it needs a decision or a look CI can't give (visuals, money, anything irreversible).
- **Every PR opens with a risk tier and a 60-second check.** First line: `Risk: low | medium | high`. Then what could break and the exact lines worth reading.
- **High risk = these paths, or anything that publishes or touches auth:** `.github/`, secrets and tokens, auth and host code, `wrangler.toml` or other deploy config, anything that makes something public. High-risk PRs get an independent review (a fresh agent that hasn't seen the work) before J is asked to merge.
- **No generated files in PRs.** Outputs that a workflow rebuilds stay out of PRs, so they can't collide with that workflow.
- **Small PRs.** One purpose each. Split anything J can't check from a phone in about a minute.
- **Check before explaining.** Read the log, run the test, open the file. A guess is labeled as a guess.
- **Include a ready-to-paste Claude Code prompt** in each PR, as the alternative to merging.
