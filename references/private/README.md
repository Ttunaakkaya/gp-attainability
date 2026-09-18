# Local-only full texts

Place legally obtained personal research copies here. Expected first file:

```text
suenaga_et_al_ecc2025.pdf
```

After adding it, run `uv run attain-sampling doctor --strict-paper`, compute its SHA-256,
and record version, access method, date, and hash in `docs/source_manifest.md`. Never force
add this directory to Git.
