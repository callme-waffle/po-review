# Repository instructions

## Authorized workflow

- Remote: https://github.com/callme-waffle/po-review
- Work from a specific GitHub issue. One dedicated managing session owns that issue, its implementation sessions, integration, verification and PR.
- After the initial baseline import, do not implement directly on main. Create an issue branch from the appropriate reviewed base.
- Branch format is TAG/BRIEF with a single slash. Allowed tags: feat, fix, refactor, docs, chore, test, ci, perf, build. Use a short kebab-case brief, preferably including the issue number. Do not use codex/ branches.
- Create a PR with the issue reference (Closes #N), concrete behavior changes, validation evidence, limitations and migration/rollback notes when relevant. Request the user's review. Never merge or close the issue as completed before reviewed integration.
- Public repository: never commit credentials, access.json, output/, private keys, production databases, backup data or generated runtime artifacts.

## Managing and implementation sessions

- The user explicitly requests a dedicated managing session per issue and child implementation sessions. Delegate independent work to child agents with isolated worktrees or non-overlapping file ownership.
- Use a user-visible chat for the manager when create_thread is available. Otherwise report that limitation; never describe a subagent as a newly created sidebar chat.
- Manager default: gpt-6-astra / high. Architecture, authorization boundaries and final complex review: gpt-6-astra / xhigh.
- Scoped backend implementation: gpt-6-sol / high. UI or routine implementation with fixed contracts: gpt-6-sol / medium. Mechanical documentation or inventory extraction: gpt-6-luna / medium.
- These are explicit model/effort assignments for child agents where the runtime supports them. If unavailable, report the actual model and fallback instead of claiming a requested setting was used.
- Maintain at most three simultaneous implementation agents plus the manager. Do not delegate the same work twice. Escalate effort only for unresolved ambiguity or failures.
- Establish interfaces, owned files and acceptance criteria before parallel implementation. Record child task identifiers, actual model/effort, outcomes and blockers in the issue/PR without disclosing secrets or private transcripts.
- The manager verifies behavior independently, integrates changes, handles conflicts, checks scope and prepares the PR. A child agent's success statement alone is not sufficient validation.

## Product decisions

- Default user workflow: browser translation review only. No browser terminal or full desktop in the initial scope.
- Users may optionally enable SSH/SFTP to their own Ubuntu container for direct file control.
- Users can register new repositories/projects. The first review adapter targets Sphinx/RST and gettext PO; arbitrary formats require separate adapters.
- Workspaces isolate repository copies, working PO files, baseline snapshots, build caches and persistent volumes. Users may own multiple workspaces.
- Keep account/permission management, approval/audit data and remote publication credentials outside user-controlled containers.
- Direct SSH edits must invalidate stale approvals and trigger validation before approval/upload. Compare baseline, local and remote revisions before remote publication.
- Do not modify the live service or upload translations as a side effect of development tests.

## Baseline limitations

The imported source uses absolute deployment paths and runtime inputs omitted from Git. Start with source inspection and synthetic fixtures; report missing dependencies and unexecuted tests accurately. Preserve existing changes and unrelated local output files.
