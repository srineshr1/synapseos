/*
    KWin scale effect, SynapseOS overlay: bounce in like a Mac dock launch.
    Same structure as upstream scale so KWin still loads it.
*/

"use strict";

const blacklist = {
    "ksmserver ksmserver": [],
    "ksmserver-logout-greeter ksmserver-logout-greeter": [],
    "ksplashqml ksplashqml": [],
    "spectacle org.kde.spectacle": ["region-editor"],
};

class ScaleEffect {
    constructor() {
        effect.configChanged.connect(this.loadConfig.bind(this));
        effect.animationEnded.connect(this.cleanupForcedRoles.bind(this));
        effects.windowAdded.connect(this.slotWindowAdded.bind(this));
        effects.windowClosed.connect(this.slotWindowClosed.bind(this));
        effects.windowDataChanged.connect(this.slotWindowDataChanged.bind(this));

        this.loadConfig();
    }

    loadConfig() {
        const defaultDuration = 520;
        const duration = effect.readConfig("Duration", defaultDuration) || defaultDuration;
        this.duration = animationTime(duration);
        this.inScale = effect.readConfig("InScale", 0.55);
        this.outScale = effect.readConfig("OutScale", 0.55);
        this.jumpPx = effect.readConfig("JumpPx", 56);
    }

    static isScaleWindow(window) {
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

    fromDock(window) {
        try {
            const iconRect = window.iconGeometry;
            const windowRect = window.geometry;
            if (iconRect && iconRect.width > 0 && iconRect.height > 0) {
                return {
                    value1: iconRect.x - windowRect.x - (windowRect.width - iconRect.width) / 2,
                    value2: iconRect.y - windowRect.y - (windowRect.height - iconRect.height) / 2,
                };
            }
        } catch (e) {}
        return { value1: 0, value2: this.jumpPx };
    }

    slotWindowAdded(window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        if (!ScaleEffect.isScaleWindow(window)) {
            return;
        }
        if (!window.visible) {
            return;
        }
        if (effect.isGrabbed(window, Effect.WindowAddedGrabRole)) {
            return;
        }
        this.setupForcedRoles(window);
        window.scaleInAnimation = animate({
            window: window,
            curve: QEasingCurve.OutBounce,
            duration: this.duration,
            animations: [
                {
                    type: Effect.Scale,
                    from: this.inScale
                },
                {
                    type: Effect.Opacity,
                    from: 0
                },
                {
                    type: Effect.Translation,
                    from: this.fromDock(window),
                    to: { value1: 0, value2: 0 }
                }
            ]
        });
    }

    slotWindowClosed(window) {
        if (effects.hasActiveFullScreenEffect) {
            return;
        }
        if (!ScaleEffect.isScaleWindow(window)) {
            return;
        }
        if (!window.visible || window.skipsCloseAnimation) {
            return;
        }
        if (effect.isGrabbed(window, Effect.WindowClosedGrabRole)) {
            return;
        }
        if (window.scaleInAnimation) {
            cancel(window.scaleInAnimation);
            delete window.scaleInAnimation;
        }
        this.setupForcedRoles(window);
        window.scaleOutAnimation = animate({
            window: window,
            curve: QEasingCurve.InBack,
            duration: Math.max(180, this.duration * 0.55),
            animations: [
                {
                    type: Effect.Scale,
                    to: this.outScale
                },
                {
                    type: Effect.Opacity,
                    to: 0
                },
                {
                    type: Effect.Translation,
                    from: { value1: 0, value2: 0 },
                    to: this.fromDock(window)
                }
            ]
        });
    }

    slotWindowDataChanged(window, role) {
        if (role == Effect.WindowAddedGrabRole) {
            if (window.scaleInAnimation && effect.isGrabbed(window, role)) {
                cancel(window.scaleInAnimation);
                delete window.scaleInAnimation;
                this.cleanupForcedRoles(window);
            }
        } else if (role == Effect.WindowClosedGrabRole) {
            if (window.scaleOutAnimation && effect.isGrabbed(window, role)) {
                cancel(window.scaleOutAnimation);
                delete window.scaleOutAnimation;
                this.cleanupForcedRoles(window);
            }
        }
    }
}

new ScaleEffect();
