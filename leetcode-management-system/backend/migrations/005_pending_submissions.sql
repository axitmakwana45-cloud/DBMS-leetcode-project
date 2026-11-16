BEGIN;

ALTER TABLE submission DROP CONSTRAINT IF EXISTS submission_status_check;
ALTER TABLE submission
    ADD CONSTRAINT submission_status_check
    CHECK (
        status IN (
            'ACCEPTED',
            'WRONG_ANSWER',
            'TIME_LIMIT_EXCEEDED',
            'MEMORY_LIMIT_EXCEEDED',
            'RUNTIME_ERROR',
            'COMPILE_ERROR',
            'PENDING'
        )
    );

COMMIT;
