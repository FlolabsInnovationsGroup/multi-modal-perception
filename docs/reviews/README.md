# Automated PR review process

Every pull request targeting `main` is reviewed by two workflow jobs:

1. `Automatic checks`
2. `Claude AI review`

A person gives the final approval. The workflows do not contain a human-approval job, and they cannot merge a pull request.

Merging to `main` runs `.github/workflows/deploy.yml`. Branch protection has to require the two checks above and a human approval before that deploy can happen. Adding these workflow files does not enable branch protection by itself.

## Automatic checks

The `Automatic checks` job always runs:

- A Gitleaks scan of the pull request’s commits, with secret values redacted
- The read-only malware and unsafe-file scanner
- The unit tests for that scanner

Project dependencies are installed and project tests run only when the pull request contains one of:

- A `Makefile` target named `test`
- `pytest.ini`
- `tox.ini`
- A pytest section in `setup.cfg`
- `[tool.pytest` in `pyproject.toml`

This repository currently has `requirements.txt` and none of those test entry points. The job posts the notice `Project tests skipped` and does not install project dependencies. Scanner tests still run.

The job uses `contents: read`, checks the code out with `persist-credentials: false`, and clears the GitHub token before it runs scans, installs, or tests.

## Claude AI review

Claude posts:

- One `# AI Reviewer Briefing` comment
- Inline comments on specific issues
- A final line of `Verdict: PASS`, `Verdict: PASS WITH COMMENTS`, or `Verdict: FAIL`

The workflow fails the `Claude AI review` job when the newest matching briefing is missing, does not end with one of those lines, or ends with `Verdict: FAIL`. `Verdict: PASS` and `Verdict: PASS WITH COMMENTS` pass.

Claude is instructed to review only. The workflow denies shell, edit, write, agent, and web tools. Claude is not given permission to merge, approve, push, commit, run repository code, install dependencies, or read secrets. Pull-request text is untrusted data.

The job reads the pull request with `contents: read` and can comment with `pull-requests: write` and `issues: write`.

## Human approval

Human approval is a GitHub branch-protection setting on `main`, not a workflow job.

The repository owner enables it. At least one teammate who did not write the change must approve the pull request. GitHub does not count the author’s own approval.

## Review rules

Claude’s briefing format lives in:

```text
.claude/review-instructions.md