/*
    Windows jump up from the dock icon (or from below) with a bounce.
    Exclusive with scale/fade/glide.
*/

"use strict";

const blacklist = {
    "ksmserver ksmserver": [],
    "ksmserver-logout-greeter ksmserver-logout-greeter": [],
    "ksplashqml ksplashqml": [],
    "spectacle org.kde.spectacle": ["region-editor"],
};

class JumpEffect {
    constructor() {
        effect.configChanged.connect(this.loadConfig.bind(this));
        effect.animationEnded.connect(this.cleanupForcedRoles.bind(this));
        effects.windowAdded.connect(this.slotWindowAdded.bind(this));
        effects.windowClosed.connect(this.slotWindowClosed.bind(this));
        effects.windowDataChanged.connect(this.slotWindowDataChanged.bind(this));
        this.loadConfig();
    }

    loadConfig() {
        this.openDuration = animationTime(560);
        this.closeDuration = animationTime(280);
        this.inScale = 0.32;
        this.outScale = 0.28;
    }

    static isJumpWindow(window) {
        if (window.windowClass == "plasmashell plasmashell"
                || window.windowClass == "plasmashell org.kde.plasmashell") {
            return window.hasDecoration;
        }

        const blacklistedTags = blacklist[window.windowClass];
        if (blacklistedTags && (blacklistedTags.length === 0 || blacklistedTags.includes(window.tag))) {
            return false;
        }

        if (window.hasDecoration) {
            return true;
        }
        if (window.popupWindow) {
            return false;
        }
        if (window.lockScreen || window.outline) {
            return false;
        }
        if (!window.managed) {
            return false;
        }
        return window.normalWindow || window.dialog;
    }

    setupForcedRoles(window) {
        window.setData(Effect.WindowForceBackgroundContrastRole, true);
        window.setData(Effect.WindowForceBlurRole, true);
    }

    cleanupForcedRoles(window) {
        window.setData(Effect.WindowForceBackgroundContrastRole, null);
        window.setData(Effect.WindowForceBlurRole, null);
    }

    dockDelta(window) {
        const iconRect = window.iconGeometry;
        const windowRect = window.geometry;
        if (iconRect && iconRect.width > 0 && iconRect.height > 0) {
            return {
                value1: iconRect.x - windowRect.x - (windowRect.width - iconRect.width) / 2,
                value2: iconRect.y - windowRect.y - (windowRect.height - iconRect.height) / 2,
            };
        }
        return { value1: 0, value2: 72 };
    }

    slotWindowAdded(window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        if (!JumpEffect.isJumpWindow(window) || !window.visible) {
            return;
        }
        if (effect.isGrabbed(window, Effect.WindowAddedGrabRole)) {
            return;
        }
        this.setupForcedRoles(window);
        const fromDock = this.dockDelta(window);
        window.jumpInAnimation = animate({
            window: window,
            curve: QEasingCurve.OutBounce,
            duration: this.openDuration,
            animations: [
                {
                    type: Effect.Scale,
                    from: this.inScale,
                },
                {
                    type: Effect.Opacity,
                    from: 0,
                },
                {
                    type: Effect.Translation,
                    from: fromDock,
                    to: { value1: 0, value2: 0 },
                },
            ],
        });
    }

    slotWindowClosed(window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        if (!JumpEffect.isJumpWindow(window) || !window.visible || window.skipsCloseAnimation) {
            return;
        }
        if (effect.isGrabbed(window, Effect.WindowClosedGrabRole)) {
            return;
        }
        if (window.jumpInAnimation) {
            cancel(window.jumpInAnimation);
            delete window.jumpInAnimation;
        }
        this.setupForcedRoles(window);
        const toDock = this.dockDelta(window);
        window.jumpOutAnimation = animate({
            window: window,
            curve: QEasingCurve.InBack,
            duration: this.closeDuration,
            animations: [
                {
                    type: Effect.Scale,
                    to: this.outScale,
                },
                {
                    type: Effect.Opacity,
                    to: 0,
                },
                {
                    type: Effect.Translation,
                    from: { value1: 0, value2: 0 },
                    to: toDock,
                },
            ],
        });
    }

    slotWindowDataChanged(window, role) {
        if (role == Effect.WindowAddedGrabRole) {
            if (window.jumpInAnimation && effect.isGrabbed(window, role)) {
                cancel(window.jumpInAnimation);
                delete window.jumpInAnimation;
                this.cleanupForcedRoles(window);
            }
        } else if (role == Effect.WindowClosedGrabRole) {
            if (window.jumpOutAnimation && effect.isGrabbed(window, role)) {
                cancel(window.jumpOutAnimation);
                delete window.jumpOutAnimation;
                this.cleanupForcedRoles(window);
            }
        }
    }
}

new JumpEffect();
