# Yandex Mail cloud bridge

This service processes one authenticated request at a time per caller action. There are no scheduled jobs, IMAP IDLE connections or mailbox background polling. It stores no passwords, email contents or logs on disk.

Runtime: Python 3.12+. Build: `python3 -m py_compile bridge/server.py`. Start: `python3 bridge/server.py`. Render plan: Free. The app binds `0.0.0.0:$PORT` (10000 default). Health endpoint: `/health`.

Set a random `MAIL_BRIDGE_TOKEN` of at least 32 characters in Render and set the same value as a secret in the private chat plugin. Never commit this token. Set the plugin's `MAIL_BRIDGE_URL` to the deployed HTTPS origin. Render requires a GitHub/GitLab/Bitbucket repository accessible to the connected account.

POST `/mail`, `Authorization: Bearer <MAIL_BRIDGE_TOKEN>`, `Content-Type: application/json`. The private plugin passes credentials only over HTTPS. The bridge can contact only allowlisted Yandex IMAP hosts on port 993 with certificate verification. Only `connect`, `check`, `search`, `read` operations exist. Message reads use UIDVALIDITY and BODY.PEEK; mailboxes open read-only. Full message reads are limited to 2 MB and return at most 24,000 body characters. Attachment names are returned; attachment bytes are not downloaded separately.

Cold start may take about one minute on Render Free. The plugin allows up to two minutes; the chat host may require retrying if it applies a shorter timeout. User credentials remain encrypted in the private plugin's persistent database and do not depend on Render's temporary filesystem.

Verify: `python3 -m unittest discover -s bridge -v`.
