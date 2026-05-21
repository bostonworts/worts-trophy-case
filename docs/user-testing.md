# User Testing Script

Use this for the first small test group before opening Trophy Case more widely.

For a disposable practice run:

```sh
./bin/docker-demo up
```

The seeded demo runs at `http://localhost:8011`. Clean it up with:

```sh
./bin/docker-demo clean --yes
```

## Admin Setup

1. Log in at `/login` as an admin.
2. Open `/admin` and confirm member login email says `SMTP`.
3. Open `/members/import`.
4. Import the roster from the Google Sheets URL, or upload the exported CSV.
5. Preview first, then import.
6. Spot check at least two rows:
   - A `member=1` row has `Good standing`.
   - PayPal and list emails are visible under roster emails.

## Member Login

1. Ask a member in good standing to open `/member-login`.
2. Have them enter either their PayPal email or list email.
3. Confirm they receive a login code.
4. Confirm the code redirects them to `/me`.
5. Confirm `/me` shows their public results and leaderboard points.
6. Confirm `/members` still redirects for a non-admin member.

## Negative Checks

1. Try a roster email where `member` is blank or `0`.
2. Confirm the page shows the generic sent-code message.
3. Confirm no email is sent for that address.
4. Request too many codes for the same address and confirm the rate limit message appears.

## Data Safety

1. Download `/admin/data/backup.json`.
2. Restore it into a throwaway database or local reset environment.
3. Confirm members, PayPal emails, list emails, good-standing flags, competitions, and results came back.
4. Add a disposable result with an uploaded recipe file.
5. Archive and restore that result.
6. Use clear-results only in the throwaway environment and confirm uploaded files are removed.

## Tester Notes

Ask testers to report:

- The email address they tried.
- Whether they used PayPal email or list email.
- The time they requested the code.
- The page they expected to land on after login.
- Any missing or incorrect public result rows.
