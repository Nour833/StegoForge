# StegoForge `--json` Schemas

## encode

`{status, method, carrier, payload_size, encrypted_size, capacity, output, depth, decoy_mode, wet_paper, preserve_fingerprint, target_profile?, resized?, survival_test?}`

`survival_test = {target, survived, corrected_bits, simulation, error}`. Keyless compares raw bytes; keyed decrypts.

## decode

`{status, method, file, payload_size, output, wet_paper, wet_corrected_bits}`

## detect

`{status, report_version, tool_version, file, file_sha256, case_id, detectors_run, results[], note?}`

`results[] = {method, detected, confidence, details, has_payload}`.

## ctf

`{status, report_version, tool_version, file, file_sha256, case_id, file_size, overall_verdict, overall_confidence, results[], saved_payloads[], notes[]}`

Pass `case_id` (`--case-id`) for audit trail. Use `--no-save` for read-only triage.

## capacity

`{status, carrier, method, depth, capacity_bytes, capacity_kb, capacity_mb, stealth_score, jnd_safe_dct_capacity?, video_context?}`

## diff / batch

`diff`: `{carrier, stego, type, changed_* / differing_*, heatmap?}`.
`batch`: `{batch_dir, payload, total, passed, failed, rows[]}`.
