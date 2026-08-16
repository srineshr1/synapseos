/*
 * Force stock KWin blur (or the pre-rendered wallpaper fallback) behind
 * translucent surfaces. Better Blur DX does this internally; on virgl it
 * reports "supported" and composites nothing.
 *
 * desktopWindow stays unfrosted so the sharp wallpaper remains the desktop.
 * Docks/panels and popups are included — that is the frosted chrome.
 */
"use strict";

const skipClass = /firefox|firefox-esr|google-chrome|chromium|brave-browser|helium|librewolf|zen|vivaldi|msedge|opera|navigator/i;

function shouldFrost(window) {
    if (!window || window.desktopWindow || window.lockScreen || window.outline) {
        return false;
    }
    const cls = (window.windowClass || "").toString();
    if (skipClass.test(cls)) {
        return false;
    }
    return window.dock
        || window.normalWindow
        || window.dialog
        || window.popupWindow
        || window.dropdownMenu
        || window.popupMenu
        || window.tooltip;
}

function frost(window) {
    if (shouldFrost(window)) {
        window.setData(Effect.WindowForceBlurRole, true);
    }
}

effects.windowAdded.connect(frost);
const stacking = effects.stackingOrder;
for (let i = 0; i < stacking.length; i++) {
    frost(stacking[i]);
}
