# Evaluator calibration only

{
  "kind": "evaluator calibration only, not a useful selection PoC",
  "source_commit": "610aaed3c51b80f7a068866a52454673f685d597",
  "rows": 528,
  "counts": {
    "fixed-v1": {
      "pass": 183,
      "false_alarm": 64,
      "unknown": 17
    },
    "relative-v1": {
      "pass": 183,
      "false_alarm": 64,
      "unknown": 17
    }
  },
  "changed_statuses": [],
  "known_false_alarm_became_pass": [],
  "elapsed_seconds": 1024.149215909,
  "policies": {
    "fixed-v1": "0.2s reference and subject/wrapper calls",
    "relative-v1": "2s reference; max(.2,2*t_ref) canonical/original; max(.2,3*t_ref) wrapped fault"
  },
  "outer_limits": "25 CPU seconds / 35 wall seconds; remaining resource failures stay unknown"
}
