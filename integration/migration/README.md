# Staged persistence migration

The order is fixed and is not a preference:

1. a non-default provider, in tests only;
2. Kilix Land;
3. Kilix TUI;
4. Kilix Cap;
5. **Kilix 95 last**, because it is the default desktop.

The legacy store stays authoritative until a `kilix.desktop.migration.v1`
record completes. The mixed window is the real test: an unmigrated Kilix 95 and
a migrated Cap must agree on which store is authoritative, and a
default-provider change made from either must be observed by both. A provider
that cannot resolve the store fails closed with a diagnostic; it does not guess.

Rollback moves authority back to the legacy store. New state is retained but
inert — it is not merged, and it is not deleted.

Measured at this revision: 4/4 dry runs, 4/4 migrations, 1/1 rollback, 7/7
observations and 1/1 cleanup, all against local roots. Live authority flips are
**0/1**: no installed machine has been migrated by this candidate.
