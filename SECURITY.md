# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Use GitHub's private reporting:
<https://github.com/peteyagmin/localnotebook/security/advisories/new>.

Include what you found, how to reproduce it, and the version (Settings, or `GET /api/v1/health`).
You can expect an acknowledgement, and a fix or an explanation, as time allows: this is a
single-maintainer hobby project.

## Supported versions

Only the latest release receives fixes.

## How the app protects you

- The server listens on `127.0.0.1` only. Every request to `/api` needs a random token created at
  each launch (compared in constant time), and requests from other origins are rejected.
- Documents, web pages and videos are treated as untrusted: parsers run in a separate process with a
  timeout (and a memory limit on Linux), and instructions inside documents are quoted data, not
  commands.
- Web fetches accept only `http` and `https`, check every resolved address, pin the connection to the
  checked address, re-check redirects, and refuse localhost and private networks. Responses are
  limited to 20 MB.
- Imported notebook files are checked for unsafe paths, links, oversized or suspicious archives, and
  damaged or newer databases before anything is unpacked into place.
- There is no telemetry, analytics or update check. The only network traffic is to your configured
  model server and to actions you start (web import, Discover, model downloads); each can be switched
  off in Settings.

## Things to know

- Your data folder, exported `.lnb` files and the optional model-server API key are **not encrypted**.
  The API key is stored in plain text in `app.db` and is shown in Settings. Use your operating
  system's disk encryption and file permissions.
- If you point the app at a model server that is not on your computer, your questions and passages
  from your documents are sent there. The app shows a banner when this is the case.
- Anyone who can run programs as you on your computer can read your data folder.
