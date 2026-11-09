# Phase 12 session operations

Default is Stage A. Live observation does **not** start automatically.

From the project root, with `PYTHONPATH=src` and the project venv:

```text
python src/phase12/run_phase12.py --offline-validate
python src/phase12/run_phase12.py --status
python src/phase12/run_phase12.py --stop-session
python src/phase12/run_phase12.py --validate-journal
python src/phase12/run_phase12.py --summary
```

Manual Stage B (user only, later):

```text
python src/phase12/run_phase12.py --start-session
```

`--start-session` is refused during this implementation run so MT5 is not opened as a side effect of building Phase 12.

Stop: `--stop-session` releases the session lock. Only one session may run. No scheduled tasks. No hidden background process.
