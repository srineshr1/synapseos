// SynapseOS Hyprland mode.
// Off (default): normal Plasma floating windows.
// On: dwindle-tile like Hyprland. Off again: every window goes back
// to the geometry it had before the switch (or at first map).
var GAP = 8;
var DESKTOPS = 10;
var tiling = false;
var applying = false;
var saved = {};
var floated = {};
var order = {};

function keyOf(win) {
    if (!win) {
        return "";
    }
    if (win.internalId) {
        return String(win.internalId);
    }
    return String(win.pid) + ":" + String(win.resourceClass) + ":" + String(win.caption);
}

function windows() {
    if (typeof workspace.windowList === "function") {
        try {
            var listed = workspace.windowList();
            if (listed) {
                return listed;
            }
        } catch (err) {
        }
    }
    return workspace.stackingOrder || [];
}

function isTileable(win) {
    if (!win || win.deleted || !win.normalWindow || win.specialWindow) {
        return false;
    }
    if (win.desktopWindow || win.dock || win.toolbar || win.menu || win.dialog) {
        return false;
    }
    if (win.splash || win.utility || win.dropdownMenu || win.popupMenu) {
        return false;
    }
    if (win.tooltip || win.notification || win.criticalNotification) {
        return false;
    }
    if (win.appletPopup || win.onScreenDisplay || win.comboBox || win.popupWindow) {
        return false;
    }
    if (win.fullScreen || win.minimized || win.hidden || !win.managed) {
        return false;
    }
    if (win.skipTaskbar && win.skipPager) {
        return false;
    }
    var klass = String(win.resourceClass || "").toLowerCase();
    var role = String(win.windowRole || "").toLowerCase();
    if (klass.indexOf("krunner") !== -1 || klass.indexOf("plasmashell") !== -1) {
        return false;
    }
    if (klass === "org.synapseos.menu" || role === "org.synapseos.menu") {
        return false;
    }
    return true;
}

function desktopId(desktop) {
    if (!desktop) {
        return "";
    }
    if (desktop.id) {
        return String(desktop.id);
    }
    return String(desktop.x11DesktopNumber || desktop);
}

function onDesktop(win, desktop) {
    if (!win || !desktop) {
        return false;
    }
    if (win.onAllDesktops) {
        return true;
    }
    var ds = win.desktops || [];
    if (!ds.length) {
        return false;
    }
    var want = desktopId(desktop);
    for (var i = 0; i < ds.length; i++) {
        if (ds[i] === desktop || desktopId(ds[i]) === want) {
            return true;
        }
    }
    return false;
}

function sameOutput(win, output) {
    if (!output) {
        return true;
    }
    if (!win.output) {
        return true;
    }
    if (win.output === output) {
        return true;
    }
    return String(win.output.name || "") === String(output.name || "");
}

function snapshot(win) {
    var key = keyOf(win);
    if (!key || saved[key]) {
        return;
    }
    var geo = win.frameGeometry;
    saved[key] = {
        x: geo.x,
        y: geo.y,
        width: geo.width,
        height: geo.height
    };
}

function snapshotAll() {
    var list = windows();
    for (var i = 0; i < list.length; i++) {
        if (isTileable(list[i]) || (list[i] && list[i].normalWindow && !list[i].specialWindow)) {
            snapshot(list[i]);
        }
    }
}

function restoreAll() {
    applying = true;
    var list = windows();
    for (var i = 0; i < list.length; i++) {
        var win = list[i];
        var keep = saved[keyOf(win)];
        if (!keep || !win || win.deleted) {
            continue;
        }
        if (win.fullScreen) {
            continue;
        }
        try {
            win.setMaximize(false, false);
        } catch (err) {
        }
        placeRaw(win, keep.x, keep.y, keep.width, keep.height);
    }
    applying = false;
}

function placeRaw(win, x, y, width, height) {
    var next = {
        x: Math.round(x),
        y: Math.round(y),
        width: Math.max(80, Math.round(width)),
        height: Math.max(60, Math.round(height))
    };
    try {
        win.frameGeometry = next;
    } catch (err) {
        try {
            win.frameGeometry = Qt.rect(next.x, next.y, next.width, next.height);
        } catch (err2) {
        }
    }
}

function place(win, area) {
    placeRaw(
        win,
        area.x + GAP,
        area.y + GAP,
        area.width - GAP * 2,
        area.height - GAP * 2
    );
}

function orderKey(output, desktop) {
    return String(output && output.name ? output.name : "screen") + "@" + desktopId(desktop);
}

function rememberOrder(output, desktop, wins) {
    var ids = [];
    for (var i = 0; i < wins.length; i++) {
        ids.push(keyOf(wins[i]));
    }
    order[orderKey(output, desktop)] = ids;
}

function sortByOrder(output, desktop, wins) {
    var prev = order[orderKey(output, desktop)] || [];
    var rank = {};
    for (var i = 0; i < prev.length; i++) {
        rank[prev[i]] = i;
    }
    wins.sort(function (a, b) {
        var ka = keyOf(a);
        var kb = keyOf(b);
        var ia = rank.hasOwnProperty(ka) ? rank[ka] : 1000;
        var ib = rank.hasOwnProperty(kb) ? rank[kb] : 1000;
        if (ia !== ib) {
            return ia - ib;
        }
        return 0;
    });
    return wins;
}

function tiledOn(output, desktop) {
    var found = [];
    var list = windows();
    for (var i = 0; i < list.length; i++) {
        var win = list[i];
        if (!isTileable(win)) {
            continue;
        }
        if (floated[keyOf(win)]) {
            continue;
        }
        if (!onDesktop(win, desktop)) {
            continue;
        }
        if (!sameOutput(win, output)) {
            continue;
        }
        found.push(win);
    }
    return sortByOrder(output, desktop, found);
}

function dwindle(wins, area, splitVertical) {
    if (!wins.length) {
        return;
    }
    if (wins.length === 1) {
        place(wins[0], area);
        return;
    }
    var rest = wins.slice(1);
    if (splitVertical) {
        var halfH = Math.floor(area.height / 2);
        place(wins[0], { x: area.x, y: area.y, width: area.width, height: halfH });
        dwindle(rest, {
            x: area.x,
            y: area.y + halfH,
            width: area.width,
            height: area.height - halfH
        }, false);
    } else {
        var halfW = Math.floor(area.width / 2);
        place(wins[0], { x: area.x, y: area.y, width: halfW, height: area.height });
        dwindle(rest, {
            x: area.x + halfW,
            y: area.y,
            width: area.width - halfW,
            height: area.height
        }, true);
    }
}

function areaFor(output, desktop, sample) {
    try {
        if (output && desktop) {
            return workspace.clientArea(KWin.MaximizeArea, output, desktop);
        }
    } catch (err) {
    }
    if (sample) {
        try {
            return workspace.clientArea(KWin.MaximizeArea, sample);
        } catch (err2) {
        }
    }
    return { x: 0, y: 0, width: 1920, height: 1080 };
}

function retile() {
    if (!tiling || applying) {
        return;
    }
    applying = true;
    var desktops = workspace.desktops || [];
    var screens = workspace.screens || [];
    if (!screens.length) {
        screens = [workspace.activeScreen];
    }
    for (var s = 0; s < screens.length; s++) {
        var output = screens[s];
        for (var d = 0; d < desktops.length; d++) {
            var desktop = desktops[d];
            var wins = tiledOn(output, desktop);
            rememberOrder(output, desktop, wins);
            if (!wins.length) {
                continue;
            }
            dwindle(wins, areaFor(output, desktop, wins[0]), false);
        }
    }
    applying = false;
}

function notify(title, body) {
    try {
        callDBus(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            "SynapseOS",
            0,
            "preferences-system-windows",
            title,
            body,
            [],
            {},
            1800
        );
    } catch (err) {
        print("synapseostile: " + title + " — " + body);
    }
}

function setTiling(on) {
    if (on && !tiling) {
        snapshotAll();
        floated = {};
        tiling = true;
        retile();
        notify("Hyprland mode", "Windows are tiling. Super+Shift+Space restores them.");
    } else if (!on && tiling) {
        tiling = false;
        restoreAll();
        floated = {};
        notify("Plasma mode", "Windows are back where they were.");
    }
}

function toggle() {
    setTiling(!tiling);
}

function ensureDesktops() {
    try {
        while (workspace.desktops.length < DESKTOPS) {
            workspace.createDesktop(workspace.desktops.length, String(workspace.desktops.length + 1));
        }
    } catch (err) {
        print("synapseostile: could not create desktops: " + err);
    }
}

function desktopAt(index) {
    var ds = workspace.desktops || [];
    if (index < 1 || index > ds.length) {
        return null;
    }
    return ds[index - 1];
}

function switchDesktop(index) {
    var desktop = desktopAt(index);
    if (desktop) {
        workspace.currentDesktop = desktop;
    }
}

function moveToDesktop(index) {
    var desktop = desktopAt(index);
    var win = workspace.activeWindow;
    if (!desktop || !win) {
        return;
    }
    try {
        win.desktops = [desktop];
    } catch (err) {
    }
    workspace.currentDesktop = desktop;
    if (tiling) {
        retile();
    }
}

function cycleDesktop(delta) {
    var ds = workspace.desktops || [];
    if (!ds.length) {
        return;
    }
    var cur = workspace.currentDesktop;
    var idx = 0;
    for (var i = 0; i < ds.length; i++) {
        if (ds[i] === cur || desktopId(ds[i]) === desktopId(cur)) {
            idx = i;
            break;
        }
    }
    workspace.currentDesktop = ds[(idx + delta + ds.length) % ds.length];
}

function centerOf(win) {
    var geo = win.frameGeometry;
    return { x: geo.x + geo.width / 2, y: geo.y + geo.height / 2 };
}

function candidates() {
    var win = workspace.activeWindow;
    var desktop = workspace.currentDesktop;
    var output = win && win.output ? win.output : workspace.activeScreen;
    var found = [];
    var list = windows();
    for (var i = 0; i < list.length; i++) {
        var other = list[i];
        if (!isTileable(other) && !(other && other.normalWindow && !other.specialWindow && !other.minimized)) {
            continue;
        }
        if (other.minimized || other.fullScreen) {
            continue;
        }
        if (desktop && !onDesktop(other, desktop) && !other.onAllDesktops) {
            continue;
        }
        if (output && !sameOutput(other, output)) {
            continue;
        }
        found.push(other);
    }
    return found;
}

function focusDir(dx, dy) {
    var active = workspace.activeWindow;
    if (!active) {
        return;
    }
    var origin = centerOf(active);
    var best = null;
    var bestScore = 1e12;
    var list = candidates();
    for (var i = 0; i < list.length; i++) {
        var win = list[i];
        if (win === active) {
            continue;
        }
        var mid = centerOf(win);
        var vx = mid.x - origin.x;
        var vy = mid.y - origin.y;
        if (dx && vx * dx <= 4) {
            continue;
        }
        if (dy && vy * dy <= 4) {
            continue;
        }
        if (dx && Math.abs(vx) < Math.abs(vy) * 0.35) {
            continue;
        }
        if (dy && Math.abs(vy) < Math.abs(vx) * 0.35) {
            continue;
        }
        var score = Math.abs(vx) + Math.abs(vy);
        if (score < bestScore) {
            bestScore = score;
            best = win;
        }
    }
    if (best) {
        workspace.activeWindow = best;
        try {
            workspace.raiseWindow(best);
        } catch (err) {
        }
    }
}

function swapDir(dx, dy) {
    var active = workspace.activeWindow;
    if (!active || !tiling) {
        focusDir(dx, dy);
        return;
    }
    var origin = centerOf(active);
    var best = null;
    var bestScore = 1e12;
    var list = candidates();
    for (var i = 0; i < list.length; i++) {
        var win = list[i];
        if (win === active || floated[keyOf(win)]) {
            continue;
        }
        var mid = centerOf(win);
        var vx = mid.x - origin.x;
        var vy = mid.y - origin.y;
        if (dx && vx * dx <= 4) {
            continue;
        }
        if (dy && vy * dy <= 4) {
            continue;
        }
        var score = Math.abs(vx) + Math.abs(vy);
        if (score < bestScore) {
            bestScore = score;
            best = win;
        }
    }
    if (!best) {
        return;
    }
    var output = active.output || workspace.activeScreen;
    var desktop = workspace.currentDesktop;
    var wins = tiledOn(output, desktop);
    var ids = [];
    for (var j = 0; j < wins.length; j++) {
        ids.push(keyOf(wins[j]));
    }
    var a = ids.indexOf(keyOf(active));
    var b = ids.indexOf(keyOf(best));
    if (a < 0 || b < 0) {
        return;
    }
    var tmp = ids[a];
    ids[a] = ids[b];
    ids[b] = tmp;
    order[orderKey(output, desktop)] = ids;
    retile();
    workspace.activeWindow = active;
}

function toggleFloat() {
    var win = workspace.activeWindow;
    if (!win || !tiling) {
        return;
    }
    if (!isTileable(win) && !floated[keyOf(win)]) {
        return;
    }
    var key = keyOf(win);
    if (floated[key]) {
        delete floated[key];
    } else {
        floated[key] = true;
    }
    retile();
}

function onAdded(win) {
    if (!win) {
        return;
    }
    snapshot(win);
    if (tiling) {
        retile();
    }
}

function onRemoved() {
    if (tiling) {
        retile();
    }
}

workspace.windowAdded.connect(onAdded);
workspace.windowRemoved.connect(onRemoved);
workspace.windowActivated.connect(function () {
    if (tiling) {
        // Keep the layout; just raise.
    }
});
try {
    workspace.screensChanged.connect(function () {
        if (tiling) {
            retile();
        }
    });
} catch (err) {
}
try {
    workspace.currentDesktopChanged.connect(function () {
        if (tiling) {
            retile();
        }
    });
} catch (err2) {
}

registerShortcut(
    "Toggle SynapseOS Hyprland mode",
    "Toggle Hyprland-style tiling (restore positions when off)",
    "Meta+Shift+Space",
    toggle
);
registerShortcut("SynapseOS float window", "Float or retile the active window", "Meta+T", toggleFloat);
registerShortcut("SynapseOS close window", "Close the active window", "Meta+W", function () {
    workspace.slotWindowClose();
});
registerShortcut("SynapseOS fullscreen", "Toggle fullscreen", "Meta+F", function () {
    workspace.slotWindowFullScreen();
    if (tiling) {
        retile();
    }
});
registerShortcut("SynapseOS focus left", "Focus window to the left", "Meta+Left", function () { focusDir(-1, 0); });
registerShortcut("SynapseOS focus right", "Focus window to the right", "Meta+Right", function () { focusDir(1, 0); });
registerShortcut("SynapseOS focus up", "Focus window above", "Meta+Up", function () { focusDir(0, -1); });
registerShortcut("SynapseOS focus down", "Focus window below", "Meta+Down", function () { focusDir(0, 1); });
registerShortcut("SynapseOS swap left", "Swap window to the left", "Meta+Shift+Left", function () { swapDir(-1, 0); });
registerShortcut("SynapseOS swap right", "Swap window to the right", "Meta+Shift+Right", function () { swapDir(1, 0); });
registerShortcut("SynapseOS swap up", "Swap window up", "Meta+Shift+Up", function () { swapDir(0, -1); });
registerShortcut("SynapseOS swap down", "Swap window down", "Meta+Shift+Down", function () { swapDir(0, 1); });
registerShortcut("SynapseOS next desktop", "Next desktop", "Meta+Tab", function () { cycleDesktop(1); });
registerShortcut("SynapseOS previous desktop", "Previous desktop", "Meta+Shift+Tab", function () { cycleDesktop(-1); });

var desktopKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
for (var n = 0; n < desktopKeys.length; n++) {
    (function (index, key) {
        registerShortcut(
            "SynapseOS desktop " + index,
            "Switch to desktop " + index,
            "Meta+" + key,
            function () { switchDesktop(index); }
        );
        registerShortcut(
            "SynapseOS move to desktop " + index,
            "Move window to desktop " + index,
            "Meta+Shift+" + key,
            function () { moveToDesktop(index); }
        );
    })(n + 1, desktopKeys[n]);
}

registerUserActionsMenu(function () {
    return {
        title: tiling ? "Hyprland mode (on)" : "Hyprland mode",
        checkable: true,
        checked: tiling,
        triggered: function () { toggle(); }
    };
});

ensureDesktops();
print("synapseostile loaded");
