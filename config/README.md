# config

This folder holds operator data files that later phases add: patterns, built-in columns, file types and the scoring rubric. The Graph allow-list is deliberately not here. It is packaged inside `src/recover_assess/core` and is not operator-editable (decision D-08), so the read-only promise cannot be loosened by editing a data file.
