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

Run Claude on multiple tasks in parallel:

```bash
python3 scripts/run_claude_tasks.py scikit-learn__scikit-learn-10297 scikit-learn__scikit-learn-10508
```

Run Claude on multiple tasks in one resumed session:

```bash
python3 scripts/run_claude_tasks_same_session.py scikit-learn__scikit-learn-10297 scikit-learn__scikit-learn-10508 scikit-learn__scikit-learn-10949 scikit-learn__scikit-learn-11281 scikit-learn__scikit-learn-12471
```

Run the oG-memory variants:

```bash
python3 scripts/run_claude_tasks_og.py scikit-learn__scikit-learn-10297 scikit-learn__scikit-learn-10508
python3 scripts/run_claude_tasks_same_session_og.py scikit-learn__scikit-learn-10297 scikit-learn__scikit-learn-10508 scikit-learn__scikit-learn-10949 scikit-learn__scikit-learn-11281 scikit-learn__scikit-learn-12471
```

Both commands write their outputs under:

```bash
repo/<repo_slug>/tasks/<task_id>/
```
