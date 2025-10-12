# Temporary Directory - Files Marked for Deletion

This directory contains files that are no longer used in the codebase and can be safely deleted.

## Files:

### `folios.db` and `data/folios.db`
- **Status**: Empty (0 bytes)
- **Reason**: These were never used. The actual database is `folios_v2.db` in the root directory.
- **References**: Only found in:
  - `.env.example` (as example config)
  - Test files (which create their own temp databases)
  - Documentation (migration notes)
- **Safe to delete**: Yes

## Action:
You can delete this entire directory once you've confirmed everything is working correctly.

```bash
rm -rf tmp_for_deletion/
```
