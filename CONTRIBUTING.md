# Contributing

Thanks for helping improve mcp-freesound!

1. Fork the repository and create a branch: `git checkout -b feature/my-change`.
2. Keep the runtime **dependency-free**: only the Python standard library may be imported in `src/`.
3. Run the server locally against your own Freesound API key:
   ```bash
   python mcp-freesound.py check
   npx @modelcontextprotocol/inspector python mcp-freesound.py
   ```
4. Run the tests and linters as described in [test/README.md](test/README.md). Keep all test
   files, virtualenvs and outputs inside `test/`.
5. Update `CHANGELOG.md` and both `README.md` and `README-it.md` when behaviour changes.
6. Open a pull request describing what changed and why.
