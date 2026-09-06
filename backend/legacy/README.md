# Legacy Migration Archive

This directory contains the old migration system that was replaced by Alembic.

## Files

- `migration.py` — Original idempotent migration functions (`_migrate_xxx`). Each startup ran ~60 functions to add columns/tables. Replaced by `alembic upgrade head`.
- `test_migrations.py` — Tests for the old migration functions. No longer needed since migrations are managed by Alembic.

## Migration History

The old system used `_column_exists()` / `_table_exists()` guards to be idempotent.
The new system uses Alembic versioned migrations (`alembic/versions/`).

Production database was stamped to Alembic head (`a9b8c7d6e5f4`) during the cutover.
