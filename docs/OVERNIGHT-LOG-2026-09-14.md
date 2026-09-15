# Overnight log — 14/15 September 2026

Single honest record of the unattended overnight session driven by
`OVERNIGHT-BRIEF.md`. Decisions are recorded where they were made, with the
reason. "Shipped" means committed, tested, and (where stated) driven in a
browser — nothing else.

---

## Item 0 — Protect the work

**Status: done.**

- Committed the 13 QA fixes (report §4 #1–#13) on `qa/overnight-2026-09-13`
  as `46d46ae`, with every fix listed in the message. Staged by explicit path;
  checked the staged list for `.env`, `scratch_*`, `boot-log.txt`,
  `Claude outputs/`, `.pdf`, `.pptx` before committing (none).
- Created `feat/overnight-2026-09-14` off it. All later work is on this branch.
- **Pushed both branches.**
- **Decision — did not run `gh repo create`.** `gh` isn't installed on this
  machine. It also isn't needed: the repo already has an `origin` remote,
  `https://github.com/Shaurya-batish/healthbridgev2.git`, with `main` on it.
  Git's stored credentials can reach it. GitHub's unauthenticated API returns
  404 for it, so it's **private**, which is what the brief wanted. Creating a
  second repo called `healthbridge-v2` would have split the history, so both
  branches went to the existing private origin.
- **Hygiene.** Deleted `scratch_hw2023.txt`, `scratch_mo2023.txt`,
  `scratch_mo2023.pdf` and `boot-log.txt`. `.gitignore` already listed
  `Claude outputs/`, but its 5 files were still tracked, so the rule did
  nothing. Untracked them with `git rm --cached` (`d8fed44`); they're still on
  disk.
- **Left untracked on purpose:** the pitch `.pptx`/`.pdf` files, `deck-diagrams/`,
  the QA report PDF, and `qa-overnight-2026-09-13.patch`. They're large
  binaries or deliverables rather than source, and the patch is now redundant
  with `46d46ae`. Shaurya decides whether any of them belong in git.
