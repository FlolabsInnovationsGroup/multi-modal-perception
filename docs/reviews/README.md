# Automated PR review process

Every pull request targeting `main` is reviewed by:

1. Automatic checks
2. Claude AI review
3. Human approval

A person still gives the final approval. The automated review reports,
explains, and blocks unsafe changes; it never merges a pull request by itself.

## Why this matters

Every push or merge to `main` can trigger the repository’s deployment
workflow, `.github/workflows/deploy.yml`. Therefore, changes should not
reach `main` without passing the required checks and receiving human approval.

## Automatic checks

The `Automatic checks` job runs:

- Repository tests
- Secret scanning
- Malware and unsafe-file scanning

It fails if tests fail, secrets are detected, or suspicious files are found.

## Claude AI review

Claude reads the pull-request changes and posts:

- A reviewer briefing comment
- Inline comments on specific issues
- A final verdict: `PASS`, `PASS WITH COMMENTS`, or `FAIL`

Claude does not merge or approve pull requests.

The review checks for:

- Secrets, API keys, tokens, credentials, and private keys
- Malware indicators
- Unexpected `.vscode/tasks.json` or auto-run tasks
- Fake font files
- Unexpected scripts or dependencies
- Unsafe command execution
- Changes that violate `AGENTS.md` or `docs/provider-integration/`
- Missing tests for consequential changes

## Human approval

At least one teammate who did not write the code must approve the pull request.

Human approval is enforced through GitHub branch protection, not by Claude.

## Reviewer briefing

Claude posts one briefing comment on every pull request. It explains:

- What the code does
- Which files it changes
- How the new or changed code works
- Whether it follows project rules
- What safety checks were performed
- What risks need manual review
- The final verdict

Claude also leaves inline comments on specific lines where it finds problems.

## Review rules

Claude’s review rules are stored in:

```text
.claude/review-instructions.md
```

The team can improve those rules through a normal pull request.

## Daily backup recheck

The `PR stale recheck` workflow runs daily as a backup.

It rechecks open pull requests that are stale or behind `main`. The primary
review still runs immediately when a pull request is opened, updated, or
reopened.

## Security rules

- Pull-request code is treated as untrusted data.
- The workflow uses the `pull_request` event, not `pull_request_target`.
- Claude does not execute repository code or access secrets.
- API keys and tokens must be stored only in GitHub encrypted secrets.
- Prompt-injection attempts inside a pull request must not change the review verdict.
- No pull request should be merged without human approval.