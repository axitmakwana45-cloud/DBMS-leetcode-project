BEGIN;

CREATE SEQUENCE IF NOT EXISTS developer_developer_id_seq;
ALTER SEQUENCE developer_developer_id_seq OWNED BY developer.developer_id;
LOCK TABLE developer IN ACCESS EXCLUSIVE MODE;
SELECT setval(
    'developer_developer_id_seq',
    GREATEST(COALESCE((SELECT MAX(developer_id) FROM developer), 1), 1),
    EXISTS (SELECT 1 FROM developer)
);
ALTER TABLE developer ALTER COLUMN developer_id SET DEFAULT nextval('developer_developer_id_seq');
ALTER TABLE developer ALTER COLUMN email DROP NOT NULL;

CREATE SEQUENCE IF NOT EXISTS submission_submission_id_seq;
ALTER SEQUENCE submission_submission_id_seq OWNED BY submission.submission_id;
LOCK TABLE submission IN ACCESS EXCLUSIVE MODE;
SELECT setval(
    'submission_submission_id_seq',
    GREATEST(COALESCE((SELECT MAX(submission_id) FROM submission), 1), 1),
    EXISTS (SELECT 1 FROM submission)
);
ALTER TABLE submission ALTER COLUMN submission_id SET DEFAULT nextval('submission_submission_id_seq');
ALTER TABLE submission ADD COLUMN IF NOT EXISTS problem_id INTEGER;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'submission_problem_id_fkey'
          AND conrelid = 'submission'::regclass
    ) THEN
        ALTER TABLE submission
            ADD CONSTRAINT submission_problem_id_fkey
            FOREIGN KEY (problem_id) REFERENCES programming_problem(problem_id) ON DELETE SET NULL;
    END IF;
END
$$;

CREATE SEQUENCE IF NOT EXISTS contest_participant_participant_id_seq;
ALTER SEQUENCE contest_participant_participant_id_seq OWNED BY contest_participant.participant_id;
LOCK TABLE contest_participant IN ACCESS EXCLUSIVE MODE;
SELECT setval(
    'contest_participant_participant_id_seq',
    GREATEST(COALESCE((SELECT MAX(participant_id) FROM contest_participant), 1), 1),
    EXISTS (SELECT 1 FROM contest_participant)
);
ALTER TABLE contest_participant ALTER COLUMN participant_id SET DEFAULT nextval('contest_participant_participant_id_seq');

ALTER TABLE developer_auth_accounts ADD COLUMN IF NOT EXISTS developer_id INTEGER;
UPDATE developer_auth_accounts AS account
SET developer_id = (
    SELECT developer.developer_id
    FROM developer
    WHERE lower(developer.email) = lower(account.username)
       OR lower(developer.username) = lower(account.username)
    ORDER BY CASE WHEN lower(developer.email) = lower(account.username) THEN 0 ELSE 1 END,
             developer.developer_id
    LIMIT 1
)
WHERE account.developer_id IS NULL
  AND EXISTS (
      SELECT 1
      FROM developer
      WHERE lower(developer.email) = lower(account.username)
         OR lower(developer.username) = lower(account.username)
  );

WITH unlinked AS (
    SELECT id, username, password_hash
    FROM developer_auth_accounts
    WHERE developer_id IS NULL
),
created AS (
    INSERT INTO developer (
        developer_id, username, full_name, email, password_hash, country, joined_on
    )
    SELECT
        nextval('developer_developer_id_seq'),
        left(
            coalesce(nullif(regexp_replace(split_part(username, '@', 1), '[^a-zA-Z0-9_.-]', '', 'g'), ''), 'developer'),
            39 - length(id::text)
        ) || '_' || id::text,
        left(split_part(username, '@', 1), 100),
        CASE
            WHEN username ~* '^[^@[:space:]]+@[^@[:space:]]+[.][^@[:space:]]+$' THEN username
            ELSE NULL
        END,
        password_hash,
        'Not specified',
        CURRENT_DATE
    FROM unlinked
    RETURNING developer_id, password_hash
)
UPDATE developer_auth_accounts AS account
SET developer_id = created.developer_id
FROM created
WHERE account.developer_id IS NULL
  AND account.password_hash = created.password_hash;

ALTER TABLE developer_auth_accounts
    ADD CONSTRAINT developer_auth_accounts_developer_id_fkey
    FOREIGN KEY (developer_id) REFERENCES developer(developer_id) ON DELETE CASCADE;
ALTER TABLE developer_auth_accounts
    ALTER COLUMN developer_id SET NOT NULL;
ALTER TABLE developer_auth_accounts
    ADD CONSTRAINT developer_auth_accounts_developer_id_key UNIQUE (developer_id);

COMMIT;
