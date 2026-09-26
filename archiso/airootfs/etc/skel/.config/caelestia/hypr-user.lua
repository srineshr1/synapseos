-- SynapseOS session extras. Loaded after Caelestia keybinds.

-- virtio-vga (no 3D) and virgl both choke on blur/hw cursors. Keep the
-- compositor painting a desktop instead of a black frame.
if os.getenv("SYNAPSEOS_VM") == "1" or os.getenv("LIBGL_ALWAYS_SOFTWARE") == "1" then
    hl.config({
        decoration = {
            blur = { enabled = false },
            shadow = { enabled = false },
        },
        cursor = {
            no_hardware_cursors = true,
        },
    })
end

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
    hl.exec_cmd("synapseos-start-desktop")
    if os.getenv("SYNAPSEOS_SESSION_AUTOSTART") then
        hl.exec_cmd("synapseos-installer --autostart")
    end
end)
