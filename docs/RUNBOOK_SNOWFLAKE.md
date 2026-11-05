# Running this on Snowflake

Allow about an hour. You need your own Snowflake account, so nobody else can do these steps for you.

## 1. Create a trial account

Sign up at [signup.snowflake.com](https://signup.snowflake.com). A trial lasts 30 days or until its free balance runs out, and needs no payment details. Standard edition is enough. Pick AWS in a European region.

Costs stay small here: extra-small warehouses suspend after 30 seconds, and `01_database_objects.sql` adds a resource monitor with a limit of 5 credits.

## 2. Make a key pair

Password sign-in is being phased out for scripts, so the pipeline uses a key. Run this on your machine, in WSL or Git Bash if you are on Windows, and keep the files out of the repo.

```bash
mkdir -p ~/.snowflake && cd ~/.snowflake
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out commerce_svc_key.p8 -nocrypt
openssl rsa -in commerce_svc_key.p8 -pubout -out commerce_svc_key.pub
chmod 600 commerce_svc_key.p8
cat commerce_svc_key.pub
```

Never share or commit the `.p8` file.

## 3. Set up the account

In a Snowsight worksheet, using the `ACCOUNTADMIN` role, run these in order:

1. `sql/setup/01_database_objects.sql`
2. `sql/setup/02_roles_and_grants.sql`
3. `sql/setup/05_data_quality_access.sql`, first pasting the public key into `<PASTE_PUBLIC_KEY_BODY>`. Use the body only, without the `BEGIN` and `END` lines, on one line.

Skip files `03` and `04`, which need an AWS bucket.

## 4. Configure your machine

```bash
python -m venv .venv && source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

In `.env`, set `SNOWFLAKE_ACCOUNT` to your account identifier in the form `orgname-accountname`, and `SNOWFLAKE_PRIVATE_KEY_PATH` to the full path of the `.p8` file.

## 5. Run it, clean data first

```bash
python scripts/run_pipeline.py --target snowflake --mode clean
echo $?
```

Expect exit code `0`, `HEALTHY` and 28 rules passing. If a rule fails here, stop and treat it as a real finding.

```bash
python scripts/run_pipeline.py --target snowflake --mode defects
echo $?
```

Expect exit code `2`, `FAIL`, 17 rules failing and this line:

```
mode=defects planted=144 detected=144 false_positives=0 false_negatives=0
```

Exit code `2` is correct here. The critical defects were planted, and the gates and reconciliation should still pass.

## 6. Capture the evidence

Run each of the five blocks in `sql/monitoring/evidence_queries.sql` on its own in Snowsight, and screenshot each result. The last block should fail with an access error. That error is the evidence that the reporting role cannot read personal data.

Keep these:

- the screenshots, in `screenshots/snowflake/`
- `reports/dq_results.json`, which should say `"target": "snowflake"`
- `reports/rule_evaluation.json`
- a screenshot of `reports/dq_dashboard.html`

Then update the Status table in `README.md` to say what you ran, and when.

## 7. Optional: the alert

`sql/monitoring/dq_alert.sql` emails you when a critical rule fails. It needs an email address verified on your Snowflake user, and the alert has to be resumed before it runs. Suspend it afterwards, because it uses warehouse credits each time it checks.

## If something goes wrong

| Message | Likely cause |
|---|---|
| `JWT token is invalid` | Wrong account identifier, or the public key was pasted with its `BEGIN` and `END` lines or with line breaks |
| `does not exist or not authorized` | A setup file was missed or ran under the wrong role |
| Rule results differ from the DuckDB run | The two engines handled something differently. Keep the output, as it is worth investigating rather than hiding |

Sources: [Trial accounts](https://docs.snowflake.com/user-guide/admin-trial-account), [Key-pair authentication](https://docs.snowflake.com/user-guide/key-pair-auth).
