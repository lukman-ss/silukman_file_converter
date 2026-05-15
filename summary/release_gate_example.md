# Release Gate Example

The release gate is deterministic and evidence-based. It does not accept manual claims without JSON evidence.

Required evidence files:

```text
output\production_qa\manual_qa_filled.json
output\production_qa\ocr_validation.json
output\production_qa\clean_windows_validation.json
output\production_qa\<timestamp>\exe_matrix.json
output\production_qa\<timestamp>\production_qa_final.json
output\production_qa\<timestamp>\production_qa_final.md
```
Strict rules:

```text
READY_FOR_PRODUCTION only if:
- automated checks pass
- EXE matrix pass
- OCR validation decision is PASS
- clean Windows validation decision is PASS
- manual QA validation passes
- no timeout is recorded
- no status is blocked
- no required evidence is missing
```

If any rule fails, the report must list the exact blocker and keep:

```text
NOT_READY_FOR_PRODUCTION
```
