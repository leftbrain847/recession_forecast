# PROJECT_NAME

One line: what this does and who it's for.

## Run
```
# exact commands from a clean clone
```

## Test
```
# exact test command (CI runs the same thing)
```

## Deployed
- Live: (link)
- Day snapshot: `YYYY-MM-DD - Project` (frozen; never edited)

## Ship a sprint day
Set `project` in `sprint.config.json`, then freeze the day's page:
```
node scripts/snapshot.mjs <page.html>            # private
node scripts/snapshot.mjs <page.html> --public   # opts in to the public sprint site
```
Commit `snapshots/` to `main` (via PR). The index's nightly refresh logs the day automatically; public pages still have to pass its UAT and secret scan.
