// Recreate the Macchiato floating dock. Used by synapseos-apply-dock.
(function () {
    var existing = panels();
    for (var i = existing.length - 1; i >= 0; --i) {
        existing[i].remove();
    }

    var panel = new Panel;
    panel.location = "bottom";
    panel.height = 46;
    panel.hiding = "none";
    panel.alignment = "center";
    panel.floating = 1;
    try { panel.opacity = "translucent"; } catch (e1) {}
    try { panel.lengthMode = "fit"; } catch (e2) {}
    panel.minimumLength = 620;
    panel.maximumLength = 680;

    var clock = panel.addWidget("org.kde.plasma.digitalclock");
    clock.currentConfigGroup = ["Appearance"];
    clock.writeConfig("showSeconds", 0);
    clock.writeConfig("showDate", false);
    clock.writeConfig("use24hFormat", 0);
    clock.writeConfig("autoFontAndSize", false);
    clock.writeConfig("fontFamily", "JetBrainsMono Nerd Font Propo");
    clock.writeConfig("fontSize", 12);
    clock.writeConfig("fontWeight", 50);

    try { panel.addWidget("org.kde.plasma.weather"); } catch (e3) {}

    var kickoff = panel.addWidget("org.kde.plasma.kickoff");
    kickoff.currentConfigGroup = ["General"];
    kickoff.writeConfig("icon", "synapseos-launcher");

    var tasks = panel.addWidget("org.kde.plasma.icontasks");
    tasks.currentConfigGroup = ["General"];
    tasks.writeConfig(
        "launchers",
        "applications:org.kde.dolphin.desktop,applications:firefox.desktop,applications:org.kde.kate.desktop,applications:kitty.desktop,applications:synapseos-assistant.desktop,applications:aether.desktop,applications:systemsettings.desktop"
    );
    tasks.writeConfig("fill", false);
    tasks.writeConfig("maxStripes", 1);
    tasks.writeConfig("forceStripes", false);
    tasks.writeConfig("groupingStrategy", 0);
    tasks.writeConfig("iconSpacing", 0);
    tasks.writeConfig("showOnlyCurrentDesktop", true);
    tasks.writeConfig("launchInPlace", true);

    var tray = panel.addWidget("org.kde.plasma.systemtray");
    tray.currentConfigGroup = ["General"];
    tray.writeConfig(
        "shownItems",
        "org.kde.plasma.volume,org.kde.plasma.networkmanagement,org.kde.plasma.notifications"
    );
    tray.writeConfig(
        "hiddenItems",
        "org.kde.plasma.keyboardlayout,org.kde.plasma.keyboardindicator,org.kde.plasma.manage-inputmethod,org.kde.plasma.cameraindicator,org.kde.kscreen,org.kde.plasma.brightness,org.kde.plasma.battery,org.kde.plasma.clipboard,org.kde.plasma.devicenotifier,org.kde.plasma.weather,org.kde.plasma.mediacontroller"
    );
})();
