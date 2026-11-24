# Security Policy

PDF Editor opens untrusted files, so security bugs matter here.

## Reporting a vulnerability

**Please don't open a public issue.** Use GitHub's private reporting instead:
**Security tab → Report a vulnerability** on this repository.

Examples of things to report:
- A crafted PDF that makes pdfeditor read or write files outside the paths it was given
- A way to get around the MCP server's allowed-folder check (`PDFEDIT_ALLOWED_DIRS`)
- Redaction that leaves the "removed" content recoverable
- Crashes or hangs caused by a malicious PDF (also report these to the upstream library if the bug is there)

You'll get a reply within 7 days.

## Supported versions

Only the latest release on `main` is supported.
