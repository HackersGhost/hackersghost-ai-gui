# Simple first-time installation (Linux)

HackersGhost AI GUI supports Parrot OS, Kali Linux, and Debian desktops.

This is a **one-command guided installer**, not yet a graphical Debian package. It is separate from the existing CLI.

## After the installer has been published

Download **HackersGhost-AI-Install.py** from the official HackersGhost GUI download page via HTTPS:

https://hackersghost.com/downloads/hackersghost-ai-gui/HackersGhost-AI-Install.py

Open a terminal and run (adjust Downloads for your language/desktop):

    python3 ~/Downloads/HackersGhost-AI-Install.py

Review the description and type INSTALL when asked. It will:

1. Create a private Python environment in ~/.local/share/hackersghost-ai-gui/runtime/.
2. Download GUI Python dependencies from the official PyPI index.
3. Fetch the published latest.json and versioned GUI ZIP from HackersGhost.com without accepting redirects.
4. Verify the Ed25519 publisher signature, product identifier, signed URL, manifest expiry, SHA-256 checksum and ZIP safety constraints.
5. Stage the verified GUI in a private versioned folder and perform a bounded Python startup-import check.
6. Install a Linux application-menu shortcut, not a system-wide package.
7. Leave the CLI, shared encrypted memory and credential keyring unchanged.

No sudo is required. **Do not run it with sudo.** The installer does not execute downloaded shell scripts, install future updates unattended, or upload local data.

Once installed, open HackersGhost AI in the Linux application menu. Future signed GUI versions can be installed using the in-app **Install** button. Close and reopen the GUI after each update.

## Requirements

- A Linux desktop running Parrot OS, Kali Linux, or Debian (other distributions untested).
- Python 3.10+ with python3-venv and python3-pip / ensurepip.
- Internet connection to official HackersGhost HTTPS downloads and PyPI.
- Qt system libraries for PySide6 (distribution-dependent).
- No existing HackersGhost AI GUI menu shortcut.

If Python environment creation fails, install the distribution's venv package.
If GUI startup fails due to missing Qt libraries, Debian-family systems typically
require libegl1, libxcb-cursor0, and libxkbcommon-x11-0. System package installation
requires separate user administrator approval; the GUI installer never installs them.

If HackersGhost AI GUI is already installed, **do not use this first-time installer** over it. Use the GUI's update feature instead. Existing unrelated desktop shortcuts are never silently overwritten.

## Verification-only test

Use a Python environment with cryptography installed:

    python installer/install_gui.py --verify-only

This verifies the live signed release without installing it. The optional --manifest
and --archive arguments can verify a local pair of files without network access.

## Publisher checklist

- Confirm the pinned Ed25519 public key matches the production GUI.
- Publish HackersGhost-AI-Install.py as an exact reviewed copy of installer/install_gui.py.
- Upload the signed versioned ZIP and latest.json first; this installer never signs.
- Then publish the installer to the HTTPS location above.
- Test clean Parrot, Kali and Debian first installs, menu launch, a subsequent signed update and rollback.
- Retain existing ZIP releases for earlier users.

This is not a native .deb package yet. Linux file managers differ in how they run
Python scripts; a terminal command is the supported first-install route.
