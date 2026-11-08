# Security

- `config.txt` combines a session Cookie, private channels and an optional prompt. Treat the entire file as a secret. Store it locally, outside shared folders when appropriate.
- Never attach a real config to public issues or screenshots. The example contains blank credentials and placeholder channels only.
- The exporter only sends the Cookie to the fixed Whop endpoint and refuses HTTP redirects. Do not modify the endpoint to a host you do not trust.
- Configuration parser errors and HTTP response bodies are not echoed, since they may contain credentials. The tool intentionally has no debug-header output.
- Clipboard and Markdown exports contain your prompt and chat data; they are not safe for public sharing just because the Cookie is omitted.
- `.gitignore` does not protect already-tracked files, forced adds, Git history or browser uploads. Review staged files before committing.
- If a Cookie was exposed, invalidate the affected session through Whop's available account/session controls; do not assume deleting the file or a normal local logout alone removes every exposed session. Clean up Git history separately if needed.
- Report security issues privately to the repository owner; never include session values in a public report.
