-- SynapseOS session extras. Loaded after Caelestia keybinds.

hl.bind("SUPER + S", hl.dsp.exec_cmd("synapseos-overlay"))
hl.bind("SUPER + SPACE", hl.dsp.exec_cmd("synapseos menu"))
hl.bind("SUPER + Return", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + SHIFT + Return", hl.dsp.exec_cmd("firefox"))
hl.bind("SUPER + SHIFT + B", hl.dsp.exec_cmd("firefox"))
hl.bind("SUPER + SHIFT + F", hl.dsp.exec_cmd("thunar"))
hl.bind("SUPER + SHIFT + N", hl.dsp.exec_cmd("code"))
hl.bind("SUPER + SHIFT + K", hl.dsp.exec_cmd("synapseos keybindings"))
hl.bind("SUPER + SHIFT + D", hl.dsp.exec_cmd("synapseos launch tui lazydocker"))
hl.bind("SUPER + CTRL + T", hl.dsp.exec_cmd("synapseos launch tui btop"))
hl.bind("SUPER + Escape", hl.dsp.exec_cmd("synapseos menu system"))
hl.bind("CTRL + ALT + S", hl.dsp.exec_cmd("synapseos-overlay --pause"))
hl.bind("CTRL + ALT + T", hl.dsp.exec_cmd("kitty"))

hl.window_rule({
    match = { title = "^Synapse$" },
    float = true,
    pin = true,
    center = true,
    opaque = true,
})
hl.window_rule({
    match = { class = "org.synapseos.overlay" },
    float = true,
    pin = true,
    center = true,
    opaque = true,
})
hl.window_rule({
    match = { class = "org.synapseos.menu" },
    float = true,
    center = true,
})

hl.on("hyprland.start", function()
    hl.exec_cmd("dbus-update-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE HYPRLAND_INSTANCE_SIGNATURE")
    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE HYPRLAND_INSTANCE_SIGNATURE DISPLAY")
    hl.exec_cmd("systemctl --user start graphical-session.target")
    hl.exec_cmd("systemctl --user start synapse-core.service")
    hl.exec_cmd("sh -c 'test -f \"${XDG_STATE_HOME:-$HOME/.local/state}/caelestia/scheme.json\" || caelestia scheme set -n caelestia'")
    hl.exec_cmd("caelestia wallpaper -f /usr/share/backgrounds/synapseos/desktop.png")
    if os.getenv("SYNAPSEOS_SESSION_AUTOSTART") then
        hl.exec_cmd("synapseos-installer --autostart")
    end
end)
