# HackersGhost AI GUI

Version 0.1.4 is an English-language desktop preview for Parrot OS, Kali Linux
and Debian, built with Python and PySide6. This download contains the application
source and a Linux launch script, rather than a standalone executable.

OpenAI mode sends questions and the current session history to the OpenAI
Responses API. It requires your own API key and model access; API usage is billed
separately from ChatGPT. Offline demo mode works without a key or API requests.
The application does not execute shell commands or browse the web.

## Included

- Chat window with Send, Enter and a New chat action.
- Editable model name, OpenAI mode and offline demo mode.
- Automatic reuse of the Linux keyring entry saved by HackersGhost AI CLI.
- Optional password-masked API key for the current window only.
- Background requests, error messages and in-memory conversation history.
- Qt-independent core modules for future CLI reuse.
- Text-file attachments with an editable preview and explicit send confirmation.
- Manual GUI update checks and signature-verified ZIP downloads.
- Optional Linux application-menu and desktop shortcuts.

## Install and run

Requirements: a Linux desktop session, Python 3.10 or later, and an internet
connection for the initial dependency download. Run the application as your
regular user.

1. Transfer `HackersGhost-AI-0.1.4.zip` to your Parrot OS or Kali Linux computer.
2. Extract it with your file manager, for example into your `Projects` folder.
3. Open a terminal inside the extracted `HackersGhost-AI-0.1.4` folder. It contains
   this README and the `scripts` folder.
4. Install the system dependencies once:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv libxcb-cursor0
```

Start the application from the extracted project folder:

```bash
bash scripts/run_gui.sh
```

The script creates a separate Python environment in `.venv`, installs PySide6 and cryptography,
and opens the window. The existing CLI installation is separate and is not modified.

If you use a virtual machine, you can transfer the ZIP through a shared folder.
Extract the project onto the Linux filesystem before running the script.

### Desktop launcher

After the first successful start, select **App > Install desktop launcher**.
This creates a **HackersGhost AI** entry in your application menu and, when your
desktop folder is enabled, a shortcut there too. It uses your configured desktop
folder, including localized names such as `Bureaublad`. No administrator access
is required. On the desktop, your environment may ask you to allow launching or
mark the shortcut as trusted the first time you open it.

Close the GUI and open the shortcut. Subsequent launches do not open a terminal,
install dependencies or check for updates. Keep the extracted project folder and
its `.venv` in place: the shortcut points to this installation, not a copied app.
No API key is stored in the shortcut. A key exported only in a terminal may not
be available in your desktop session; use the existing Linux keyring or the
session-key field instead.

After installing a new GUI version into a new folder, select the same menu item
in that version and approve replacing your old GUI shortcuts. Unrelated files
and symbolic links are never replaced. The CLI and its launcher are unchanged.
Shortcuts are not installed automatically. If your desktop cannot display icons,
use the application-menu entry. To remove the shortcuts, delete only
`hackersghost-ai-gui.desktop` from your desktop and from
`${XDG_DATA_HOME:-$HOME/.local/share}/applications`.

## Connect to AI

Select **OpenAI** and enter a model ID your API account can access. The initial
value is `HACKERSGHOST_MODEL` when set, otherwise `gpt-6-luna`, the model used in
the owner's CLI tests. Availability depends on your API account.

Leave **Session API key** blank to reuse your existing credentials. Key selection:

1. An explicitly entered session key, when provided.
2. The `OPENAI_API_KEY` environment variable.
3. The same Linux Secret Service keyring entry used by CLI 0.2.5.

For keyring access, install `libsecret-tools` and use a desktop session with an
available, unlocked Secret Service keyring. To save a key using your existing CLI:

```bash
sudo apt install libsecret-tools
"$HOME/.local/bin/hackersghost-ai" api-key save
```

The GUI only reads that saved entry; it never replaces or deletes it. A session
key is kept only in window memory and is cleared on exit. No keys are written to
configuration files. Credential lookup happens when sending a message, so the
desktop may ask you to unlock your keyring. A keyring lookup and an API request
can each wait up to 60 seconds before timing out.

Send a question, then ask a follow-up in the same window. New chat clears the local
conversation and unlocks the mode and model fields. Failed requests are shown in
the transcript but are not added to the conversation sent with the next request.
The failed question is restored to the input field for an explicit retry.

Closing the window during a request waits for that request to finish. Changing
the model, starting another chat and duplicate submissions are disabled while
waiting. Model and mode choices are kept only for the current window.

## File analysis

In OpenAI mode, use the folder icon beside the input to select a UTF-8 text file,
such as a log, configuration, CSV or JSON file. The maximum file size is 64 KiB.
PDF, images, archives and binary files are not supported. Selection alone does
not contact OpenAI or load credentials.

Review the text and remove secrets in the preview, then choose **Attach**. Edits
affect only the in-memory attachment, not your original file. The review icon
reopens the preview; the remove icon discards the pending attachment. Type your
question and press **Send**. A second, read-only confirmation shows the text that
will be sent. Cancel leaves both the question and attachment in place.

Only the reviewed snapshot and file name are sent, not the full local path. The
file is not reread during sending. It is marked as untrusted data in the request;
this is a prompt-level precaution, not a guarantee against prompt injection.
There are no command-execution tools. A failed request retains the snapshot for
an explicit retry and asks for confirmation again. After success, the attachment
leaves the input area but remains in the conversation context sent with follow-ups.
**New chat** clears that local context. The combined session request limit is 256 KiB.

## GUI updates

Choose **Check** under **Updates** to contact the GUI release channel. This does not
send your API key, chat or attached files. Checks happen only when clicked;
there is no startup check, background service or automatic installation.

When a newer signed release is available, **Download** becomes available.
Choose where to save the ZIP. The app checks its Ed25519 signature, product ID,
version, expiry, SHA-256 digest and archive structure before saving it. HTTPS
redirects, CLI packages, expired manifests and invalid signatures are rejected.
Downloads are limited to 4 MiB; the GUI stays responsive during the request.

Installation is deliberately manual in this release: extract the verified ZIP
into a new folder and launch that folder's `scripts/run_gui.sh`. Keep the old
folder as your fallback. Install the desktop launcher from the new window to
point your shortcuts to the new version. The updater does not execute downloaded code, replace
the running app, change dependencies, or modify the CLI installation. A failed
download leaves any existing destination file intact.

The GUI feed for 0.1.3 was published and verified on October 9, 2026. A new
release becomes available through the GUI only after the publisher uploads its
package and matching signed manifest. An unavailable channel is reported as
unavailable, never as proof that the installed release is current.

## Privacy and scope

OpenAI mode sends messages and session context to `https://api.openai.com/v1/responses`.
The request uses `store: false`; this does not guarantee zero provider-side retention.
See the [official Responses API guide](https://developers.openai.com/api/docs/guides/migrate-to-responses).
Conversations are not saved to disk. Offline mode does not load credentials or
make API calls. Manual update checks can still contact the publisher in offline
demo mode. There is no automatic command execution, telemetry or automatic
installer in this GUI release.

The transport and keyring lookup are adapted from the published HackersGhost AI
CLI 0.2.5. The GUI does not launch the CLI as a subprocess or modify its runtime.

## Subsequent launches

Use your installed desktop or application-menu shortcut. Alternatively, open a
terminal in the same project folder and run without downloading dependencies again:

```bash
.venv/bin/python -m hackersghost_ai
```

## Development

Activate the environment and install the project as an editable package:

```bash
source .venv/bin/activate
python -m pip install -e .
hackersghost-ai-gui
```

```text
hackersghost_ai/
  core/       Shared logic for the GUI and a future CLI
  gui/        PySide6 desktop interface
```

The AI transport, credential lookup and conversation service are separate core
modules without Qt imports. Text snapshot handling, signed GUI update downloads
and desktop-entry installation are also separate core modules. Qt only supplies
the desktop-folder location and the launcher's confirmation dialogs.

## Publishing a GUI update

The GUI feed is separate from the CLI:

```text
https://hackersghost.com/downloads/hackersghost-ai-gui/latest.json
https://hackersghost.com/downloads/hackersghost-ai-gui/HackersGhost-AI-VERSION.zip
```

The trusted public key is the existing publisher Ed25519 key from the official
CLI 0.2.5 installer. No private key is included or generated here. The payload must
identify `product: hackersghost-ai-gui` and `schema: 1`; a signed CLI manifest is
not accepted. The manifest is an envelope with base64 `payload` and `signature`.
The signed JSON payload contains `schema`, `product`, `version`, `url`, `sha256`
and a Unix-seconds `expires` value, at most 31 days ahead.

On the publisher's trusted machine, with the existing private key kept outside
this project, sign the release using the supplied helper:

```bash
python scripts/sign_gui_release.py /path/to/HackersGhost-AI-0.1.4.zip \
  --version 0.1.4 --private-key /path/to/existing-offline-signing-key \
  --output /path/to/new/latest.json
```

The helper supports raw 32-byte, hex-encoded or PEM Ed25519 keys, asks for a
password for encrypted PEM keys, checks that the key matches the pinned public
key, validates the ZIP, and never overwrites an existing output file. Never share
or upload the signing key. Upload only the versioned ZIP and signed `latest.json`,
package first and manifest last. The helper does not upload anything. Renew the
signed manifest before its default 30-day expiry, including when the version has
not changed. Do not replace the CLI feed or advertise this preview as a tested
automatic installer.

## Verification

```bash
python -m unittest discover -s tests -v
```

The tests use fake credentials and simulated API responses. They cover request
construction, error handling, keyring compatibility, conversation history,
Send/Enter, duplicate prevention, retries, offline mode and closing during a request.
File tests cover consent, redaction, cancellation, size/type limits, snapshot
reuse and retries. Update tests cover signature verification, expiry, product/URL
restrictions, archive safety, checksum failures and atomic saving. Launcher tests
cover quoted paths, localized desktop folders, explicit replacement consent,
unrelated-file protection, repeat installation and partial-failure recovery.
No real keys, website changes or paid API requests are needed. Tests render Qt
offscreen and use temporary folders instead of your real desktop.

GUI 0.1.1 startup and offline message display were manually checked on Kali with
Python 3.14.7. The owner also verified live OpenAI replies, existing Linux keyring
reuse and contextual follow-ups in GUI 0.1.2 on Kali. File analysis and a live
update check with no newer release were checked in 0.1.3. The public 0.1.3
manifest signature and downloaded package hash were also verified. The 0.1.4
desktop launcher still needs hands-on verification on Kali or Parrot; automated
Windows checks are not a substitute for Linux desktop integration. Downloading
a genuinely newer release through the GUI also remains a separate live test.

## Changes in 0.1.4

Added **App > Install desktop launcher**, with application-menu and desktop
shortcuts that start the existing Python environment without running the
dependency installer again. Replacing an older managed GUI shortcut requires
confirmation. The CLI, credentials, update channel and manual update policy are
unchanged.

## Changes in 0.1.3

Added reviewed UTF-8 file attachments, explicit permission before sending file
contents, manual signed GUI update checks/downloads and an offline publisher
signing helper. The GUI and CLI update channels remain separate. There is no
automatic installation or live GUI feed publication in this change.

## Changes in 0.1.2

Added OpenAI chat, CLI-compatible keyring lookup, model selection, a session-key
override and a responsive background request flow. Interface text remains English;
AI answers follow the user's language, as in the CLI.
