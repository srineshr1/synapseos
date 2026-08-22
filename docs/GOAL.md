# What SynapseOS is

SynapseOS is an Arch Linux desktop with a system assistant as a first-class
OS service. The assistant can see the session (windows, apps, processes,
battery, thermals) and act on it (launch, focus, close, throttle, kill,
notify, open files) through typed tools gated by policy you own.

The ISO is the vehicle. The assistant is the product.

## What it is not

- **Not a Linux kernel.** Linux already is the kernel. Caelestia (Hyprland +
  Quickshell) already is the desktop. Synapse is a session service
  (`synapse-core`) plus a Super+S overlay. "Baked into the OS" means enabled
  by default, on the PATH, bound to the graphical session — not compiled
  into `vmlinux`.
- **Not [AIOS](https://github.com/agiresearch/AIOS).** AIOS is a userspace
  *agent runtime* that schedules many LLM agents on one GPU. It does not
  boot a PC or kill Firefox. The only idea worth stealing is already here:
  the model never talks to `/proc` or a shell; it calls typed tools on a
  broker that enforces policy.
- **Not a unified inbox.** Telegram / Slack / Gmail connectors are Product B.
  They do not start until Product A (OS control) is a daily driver.

## Admin access

The model never gets a root shell. `sudo` / `su` / `pkexec` are refused.
Session verbs run as the user. System verbs (Wi-Fi, packages, power) will
go through a polkit helper with named methods, not `run_as_root`.

Modes: `observe` (no side effects) · `assist` (confirm destructive) · `act`
(opt-in). Ctrl+Alt+S pauses everything.

## v1 is done when a stranger can, in ten minutes

1. Ask what is running and for how long, and get the truth.
2. Kill or throttle a runaway app after a plain-language confirm.
3. Launch, focus, and close apps by name.
4. Toggle Wi-Fi / volume / brightness / sleep.
5. Pause the assistant instantly and see that it is paused.
6. Open the audit log and understand every action.

Until (4) exists, the assistant is a session copilot, not a full OS
control plane. That is still the product. Do not fill the gap with a
kernel fork.
