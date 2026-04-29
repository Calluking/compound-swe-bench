# Compound SWE-Bench

Minimal clean harness for SWE-bench Lite task preparation and testing.

## Layout

- `repo/`
  Cached upstream repositories and prepared task workspaces.
- `scripts/`
  Small utilities to prepare a task and run its tests.

## Main commands

Prepare one task:

```bash
python3 scripts/prepare_task.py sympy__sympy-15345
```

Prepare every SWE-bench Lite task for one repo:

```bash
python3 scripts/prepare_repo.py django/django
```

Run the task's `FAIL_TO_PASS` tests:

```bash
python3 scripts/test_task.py sympy__sympy-15345
```

Both commands write their outputs under:

```bash
repo/<repo_slug>/tasks/<task_id>/
```
