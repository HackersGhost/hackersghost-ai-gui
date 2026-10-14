# HackersGhost AI GUI

HackersGhost AI GUI 2.0.0 is the stable Linux desktop edition of HackersGhost AI for Parrot OS, Kali Linux and Debian. It is built with Python and PySide6 and is distributed as a source ZIP with a Linux launch script rather than as a standalone executable.

HackersGhost AI is intentionally specialized in ethical hacking, cybersecurity, Linux security and authorized security labs. It is not a general-purpose chatbot. Adjacent subjects such as Linux, Bash, Python, Git, DNS, HTTP, servers, virtualization, containers, cloud systems and networking are in scope when they are directly relevant to security, hardening, privacy, forensics or a lab.

OpenAI mode sends questions and conversation context to the OpenAI Responses API and requires your own API key and access to the model you select. API usage is separate from ChatGPT. Offline demo mode works without an OpenAI API request or credential lookup. The application does not execute shell commands or browse the web.

## What is included

- OpenAI and Offline demo modes.
- Editable model selection.
- Reuse of the Linux keyring credential used by HackersGhost AI CLI.
- Optional password-masked API key for the current window only.
- Background requests so the interface stays responsive.
- Session conversation history and New chat.
- Reviewed UTF-8 text-file attachments with explicit send confirmation.
- Optional encrypted Local Memory shared with the CLI for the same Linux user.
- Separate explicit consent for automatic conversation memory.
- Searchable remembered conversation turns and optional pinned facts.
- Signed GUI update checks and verified ZIP downloads.
- Automatic update-availability checks at startup, at most once per 24 hours, without automatic installation.
- Optional Linux application-menu and desktop shortcuts.
- The same HackersGhost cybersecurity specialist policy used by the CLI.

## Install and run

Requirements: a Linux desktop session, Python 3.10 or later, and an internet connection for the initial dependency installation.

1. Transfer `HackersGhost-AI-2.0.0.zip` to your Linux computer.
2. Extract it, for example into your `Projects` folder.
3. Open a terminal inside the extracted `HackersGhost-AI-2.0.0` folder.
4. Install the system dependencies once:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv libxcb-cursor0 libsecret-tools
```

Start the application from the extracted project folder:

```bash
bash scripts/run_gui.sh
```

The launch script creates a separate Python environment in `.venv`, installs the Python dependencies and opens the GUI. The existing CLI installation is separate and is not replaced or modified.

If you use a virtual machine, transfer the ZIP through your preferred shared-folder or file-transfer method, then extract it onto the Linux filesystem before running it.

## Desktop launcher

After the first successful start, choose **App Menu > Install desktop launcher**.

This creates a HackersGhost AI entry in the Linux application menu and, when a desktop folder is available, a desktop shortcut. No administrator privileges are required for the launcher itself. Some desktop environments may ask you to trust or allow the shortcut the first time it is opened.

The shortcut points to the extracted application folder and its Python environment, so keep that folder in place. Installing a newer GUI version into a new folder does not delete the older one. You can install the launcher again from the newer version and approve replacing the old HackersGhost AI GUI shortcuts.

## Connect to OpenAI

Choose **OpenAI** and enter a model ID your API account can use. The initial model is taken from `HACKERSGHOST_MODEL` when that environment variable is set; otherwise the GUI currently defaults to `gpt-6-luna`.

Credential selection is:

1. The optional Session API key entered in the GUI.
2. `OPENAI_API_KEY` from the environment.
3. The same Linux Secret Service keyring entry used by HackersGhost AI CLI.

A Session API key is kept only in process memory for the current window. The GUI does not write it to a configuration file.

To save an API key through the CLI for later GUI reuse:

```bash
sudo apt install libsecret-tools
"$HOME/.local/bin/hackersghost-ai" api-key save
```

The GUI reads the shared credential when needed. It does not replace or delete that API-key entry.

## Encrypted Local Memory

Open **App Menu > Manage memory…** to manage encrypted memory.

HackersGhost AI 2.0 separates two choices:

- **Local Memory** controls whether existing encrypted memory can be used as context in later OpenAI requests.
- **Automatic conversation memory** controls whether new successful OpenAI conversations are saved automatically.

Turning Local Memory on does **not** automatically enable conversation saving. Automatic memory requires its own explicit confirmation.

When Automatic Memory is enabled, successful OpenAI exchanges without file attachments can be stored in encrypted local memory. File-attachment exchanges are excluded from automatic memory. Obvious passwords, API keys, access tokens and private keys are skipped on a best-effort basis, but detection is not guaranteed. Do not use Memory as a secret store.

Memory is encrypted at rest with Fernet authenticated encryption. The encryption key is stored in the Linux Secret Service keyring. The encrypted memory file is stored under the user's XDG data directory, normally:

```text
~/.local/share/hackersghost-ai/memory.enc
```

The CLI and GUI use the same memory location and keyring identity for the same Linux user. Version 2.0 keeps the on-disk schema compatible with the earlier 0.x memory envelope: older clients can still read pinned `items`, while v2 conversation turns are stored in an additional field that older clients ignore.

The current limits are:

- up to 50 pinned facts;
- up to 512 bytes per pinned fact;
- up to 8 KiB total pinned-fact storage;
- up to 60 remembered conversation turns;
- up to about 8 KiB per remembered turn;
- up to 48 KiB total remembered text.

The Memory dialog can search memory, show all remembered items, pin a fact, forget a selected pin, clear all remembered content, turn Automatic Memory off, turn Local Memory off, or erase the encrypted file and encryption key.

Turning Local Memory off also disables Automatic Memory but keeps the encrypted memory file on disk. **Clear all memory** removes remembered content while keeping Local Memory enabled and preserves the current automatic-memory setting. **Erase memory + key** removes the encrypted memory file and its encryption key and turns both memory modes off.

Remembered text is encrypted only while stored locally. When remembered text is used as context for a later OpenAI request, that text is sent to OpenAI as plaintext request content.

## File analysis

In OpenAI mode, use the folder button to select a supported UTF-8 text file such as a log, configuration file, CSV, JSON, YAML or Markdown file.

The file is shown in an editable preview before it is attached. Review it and remove any sensitive content. When you press Send, a second read-only confirmation shows what will be transmitted. Cancel leaves the question and attachment in place.

Only the reviewed text snapshot and file name are sent, not the full local path. The original file is not modified. PDF files, images, archives and binary files are not supported by this attachment flow.

Attachment exchanges are deliberately excluded from automatic long-term memory.

## GUI updates

HackersGhost AI GUI uses its own signed update channel:

```text
https://hackersghost.com/downloads/hackersghost-ai-gui/latest.json
```

When OpenAI mode is active, the GUI can check the signed update feed automatically at startup, at most once every 24 hours. If a newer version is available, the Updates area is updated and a clear popup is shown.

The automatic startup check is notification-only. It does not download, install or execute a release.

When Offline demo mode is active, the automatic startup update check is skipped. A manual **Check** action can still contact the HackersGhost update server if you explicitly choose it.

You can also press **Check** manually at any time. When a newer signed release is available, **Download** becomes available. Before saving the ZIP, the GUI validates:

- the Ed25519 signature;
- product ID and manifest schema;
- version and expiry;
- the expected trusted download URL;
- SHA-256;
- archive size and structure;
- unsafe paths and unsupported archive entries.

HTTPS redirects, CLI packages, expired manifests, invalid signatures, checksum mismatches and unsafe archives are rejected.

Installation remains manual: extract the verified ZIP into a new folder, launch its `scripts/run_gui.sh`, verify that it works, then update the desktop launcher from the new version if desired. Keep the previous folder until the new version is confirmed working.

## Privacy and security notes

OpenAI mode sends messages, current session context and any enabled remembered context to `https://api.openai.com/v1/responses`.

The request uses `store: false`. This should not be described as a guarantee of zero provider-side retention.

Offline demo mode does not make OpenAI API requests and does not load OpenAI credentials. A manual update check is separate and can contact the HackersGhost update server when explicitly requested.

The application has no automatic command execution and does not execute downloaded update code. There is no automatic installer. Update metadata is signature-verified before a release is offered for download.

## Specialist scope

HackersGhost AI is designed for cybersecurity, ethical hacking, defensive security, incident response, malware analysis, vulnerability research, web security, network security, privacy, OPSEC, authentication, credentials, security tooling and authorized security labs.

Off-topic requests receive the HackersGhost AI scope refusal. The GUI does not broaden into a general-purpose assistant.

## Subsequent launches

Use the installed application-menu or desktop shortcut, or run from the project folder:

```bash
.venv/bin/python -m hackersghost_ai
```

The desktop launcher uses the existing application folder and Python environment; it does not reinstall dependencies each time.

## Development

Activate the environment and install the project as an editable package:

```bash
source .venv/bin/activate
python -m pip install -e .
hackersghost-ai-gui
```

Run the automated test suite with:

```bash
python -m unittest discover -s tests -v
```

The tests cover the OpenAI transport, error handling, credentials, session history, attachments, offline mode, desktop-launcher behavior, encrypted memory, separate automatic-memory consent, shared CLI/GUI storage, update signature validation, startup update scheduling, update notices, archive validation and the specialist policy.

The v2 branch has also been hands-on tested on Parrot OS and Kali Linux for encrypted memory compatibility. Shared CLI/GUI memory and automatic-memory consent were tested on Parrot. Kali testing covered memory persistence, encryption at rest, permissions and the Offline demo startup-update guard. The signed stable update feeds were also verified during release preparation.

## Publishing a GUI release

The GUI update channel is separate from the CLI update channel:

```text
https://hackersghost.com/downloads/hackersghost-ai-gui/latest.json
https://hackersghost.com/downloads/hackersghost-ai-gui/HackersGhost-AI-VERSION.zip
```

The GUI trusts the same pinned publisher Ed25519 public key used by the official CLI updater, but it requires a GUI-specific signed payload with:

- `schema: 1`;
- `product: hackersghost-ai-gui`;
- version;
- trusted GUI URL;
- SHA-256;
- expiry.

The private signing key must remain outside the repository and outside the public download directory.

Example signing command for 2.0.0:

```bash
python scripts/sign_gui_release.py /path/to/HackersGhost-AI-2.0.0.zip \
  --version 2.0.0 \
  --private-key /path/to/existing-offline-signing-key \
  --output /path/to/new/latest.json
```

The helper verifies that the private key matches the public key pinned in the GUI, validates the release ZIP and refuses to overwrite an existing output manifest.

Publish the versioned ZIP first and `latest.json` last. Never upload or commit the private signing key.

## Changes in 2.0.0

Version 2.0.0 introduces automatic encrypted conversation memory with a separate explicit opt-in, while keeping Local Memory independently controllable. CLI and GUI share the same encrypted memory store for the same Linux user. Successful OpenAI conversations without attachments can be remembered automatically; attachments are excluded, secret-like content is skipped on a best-effort basis, and remembered text is included as context in later OpenAI requests.

The GUI now checks its signed update feed automatically at startup at most once per day when online mode is active. New versions are announced clearly, but downloads remain explicit and installation remains manual. Offline demo mode does not perform the automatic startup update check.

Version 2.0.0 is presented as the stable channel in the interface.
