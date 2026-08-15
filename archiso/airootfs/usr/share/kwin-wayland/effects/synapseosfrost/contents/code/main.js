/*
 * Keep WindowForceBlurRole on normal windows so stock KWin blur frosts
 * them. Better Blur DX does this internally; it often fails to load in
 * a VM (virgl). Browsers stay opaque.
 */
"use strict";

const skipClass = /firefox|firefox-esr|google-chrome|chromium|brave-browser|helium|librewolf|zen|vivaldi|msedge|opera|navigator/i;

function shouldFrost(window) {
    if (!window || window.desktopWindow || window.dock || window.lockScreen) {
        return false;
    }
    const cls = (window.windowClass || "").toString();
    if (skipClass.test(cls)) {
        return false;
    }
    return window.normalWindow || window.dialog || window.popupWindow;
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
