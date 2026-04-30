# Failed Evaluation Tests

This lists the unresolved tasks from the same-session and parallel scikit-learn evaluations, plus the failed tests reported by SWE-bench.

## Same Session

Evaluation summary source:

`claude-haiku-4-5-20251001_same_session_20260430T063815Z.same_session_20260430T063815Z_modal~.json`

Unresolved tasks:

- `scikit-learn__scikit-learn-10508`
- `scikit-learn__scikit-learn-10949`
- `scikit-learn__scikit-learn-15535`

### `scikit-learn__scikit-learn-10508`

Source:

`logs/run_evaluation/same_session_20260430T063815Z_modal~/claude-haiku-4-5-20251001_same_session_20260430T063815Z/scikit-learn__scikit-learn-10508/report.json`

Failed `FAIL_TO_PASS` tests:

- `sklearn/preprocessing/tests/test_label.py::test_label_encoder_errors`
- `sklearn/preprocessing/tests/test_label.py::test_label_encoder_empty_array`

### `scikit-learn__scikit-learn-10949`

Source:

`logs/run_evaluation/same_session_20260430T063815Z_modal~/claude-haiku-4-5-20251001_same_session_20260430T063815Z/scikit-learn__scikit-learn-10949/report.json`

Failed `FAIL_TO_PASS` test:

- `sklearn/utils/tests/test_validation.py::test_check_dataframe_warns_on_dtype`

### `scikit-learn__scikit-learn-15535`

Source:

`logs/run_evaluation/same_session_20260430T063815Z_modal~/claude-haiku-4-5-20251001_same_session_20260430T063815Z/scikit-learn__scikit-learn-15535/report.json`

This task passed all `FAIL_TO_PASS` tests, but failed `PASS_TO_PASS` tests, so it is a regression.

Failed `PASS_TO_PASS` tests:

- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[adjusted_mutual_info_score-adjusted_mutual_info_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[adjusted_rand_score-adjusted_rand_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[completeness_score-completeness_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[homogeneity_score-homogeneity_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[mutual_info_score-mutual_info_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[normalized_mutual_info_score-normalized_mutual_info_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[v_measure_score-v_measure_score]`
- `sklearn/metrics/cluster/tests/test_common.py::test_inf_nan_input[fowlkes_mallows_score-fowlkes_mallows_score]`

## Parallel

Evaluation summary source:

`claude-haiku-4-5-20251001_parallel_20260430_all_cleaned.parallel_20260430_all_modal_no_empty_diff.json`

Unresolved task:

- `scikit-learn__scikit-learn-10508`

### `scikit-learn__scikit-learn-10508`

Source:

`logs/run_evaluation/parallel_20260430_all_modal_no_empty_diff/claude-haiku-4-5-20251001_parallel_20260430_all_cleaned/scikit-learn__scikit-learn-10508/report.json`

Failed `FAIL_TO_PASS` tests:

- `sklearn/preprocessing/tests/test_label.py::test_label_encoder_errors`
- `sklearn/preprocessing/tests/test_label.py::test_label_encoder_empty_array`

## How This Was Verified

The wrong tasks come from each evaluation summary file's `unresolved_ids` list.

The failed tests come from each task's SWE-bench `report.json`, specifically:

`tests_status -> FAIL_TO_PASS/PASS_TO_PASS -> failure`
