# Post-Merge Corrections (v2.1.0)

The reports in `reports/` (v1–v3) and the PR drafts/patches here are the historical
record of the audit + UI/UX implementation. **After** those PRs were merged, review
surfaced mistakes in the implementation that this correction round fixes. Recording them
here so the audit trail stays honest.

## What was wrong after the initial merge

1. **MMR retrieval was silently removed.** `graph/nodes/retrieve_context.py` had been
   changed to scored top-k purely to obtain per-citation scores, dropping
   `max_marginal_relevance_search`. MMR is a deliberate, documented retrieval-quality
   feature (README "Score Gate + MMR"; CHANGELOG v1.0.0). This was an unforced trade-off
   and a quality regression — and the documentation was left claiming MMR still ran.
2. **Version regressed** to `1.1.0` in `main.py` while the project is at `2.0.0`.
3. **`CHANGELOG.md` / `CONTRIBUTING.md` were never updated** for any of the merged work,
   despite CONTRIBUTING requiring a changelog entry per change.
4. **`PTD.md` ignored the project's v2.0.0 history** and stated a wrong version and a
   design decision ("scored top-k over MMR") that contradicted the restored behavior.
5. **These deliverables were not committed to the repo** (they lived only as downloadable
   artifacts), and some PR descriptions referenced paths that didn't exist in-tree.

Root cause: the implementation work proceeded **without reading `CHANGELOG.md` /
`CONTRIBUTING.md` first**, so documented decisions (MMR, versioning, changelog discipline)
were invisible at the time changes were made.

## What this round corrects (v2.1.0)

- **Restored MMR** for above-threshold selection, **keeping** the new structured-citation
  scores (the candidate pool is scored once for the gate and joined back to the
  MMR-selected chunks by `chunk_hash`). See `fix/restore-mmr-retrieval`.
- **Version → `2.1.0`** in `main.py`.
- **`CHANGELOG.md`** gains a complete `[2.1.0]` entry (audit fixes + spec features + the
  MMR restore) in Keep-a-Changelog format.
- **`PTD.md`** rebuilt on the v2.0.0 lineage with the correct version and retrieval
  description; **`CONTRIBUTING.md`** structure/test counts refreshed.
- **`docs/audit/`** (this directory) now versions the reports, patches, PR drafts, and
  tool evidence in-repo.

The earlier reports' scores/verdicts reflect their point in time; treat **this file +
the `[2.1.0]` CHANGELOG entry** as the authoritative current state.
