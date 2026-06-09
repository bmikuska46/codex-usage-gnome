import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const DBUS_NAME = 'com.github.bmikuska.CodexUsage';
const DBUS_PATH = '/com/github/bmikuska/CodexUsage';
const DBUS_IFACE = 'com.github.bmikuska.CodexUsage';
const REFRESH_MS = 30_000;
const USAGE_BAR_WIDTH = 236;
const USAGE_COLORS = {
    green: {fill: '#33d17a', track: '#1b5e20'},
    yellow: {fill: '#f6d32d', track: '#8a6d00'},
    orange: {fill: '#ff7800', track: '#8f3f00'},
    red: {fill: '#e01b24', track: '#7a1118'},
};

function usageColorForPercent(percent) {
    if (percent >= 50)
        return USAGE_COLORS.green;
    if (percent >= 25)
        return USAGE_COLORS.yellow;
    if (percent >= 10)
        return USAGE_COLORS.orange;
    return USAGE_COLORS.red;
}

const UsageBarMenuItem = GObject.registerClass(
class UsageBarMenuItem extends PopupMenu.PopupBaseMenuItem {
    _init(title) {
        super._init({reactive: false});

        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });

        this._title = new St.Label({text: title});
        box.add_child(this._title);

        this._track = new St.BoxLayout({
            style_class: 'codex-usage-track',
            x_expand: true,
            x_align: Clutter.ActorAlign.START,
        });
        this._fill = new St.Widget({
            style_class: 'codex-usage-fill',
            x_align: Clutter.ActorAlign.START,
        });
        this._track.add_child(this._fill);
        box.add_child(this._track);

        this._reset = new St.Label({
            text: '',
            style_class: 'codex-usage-reset',
        });
        box.add_child(this._reset);

        this.add_child(box);
    }

    setValues(remainingPercent, resetLabel) {
        const remaining = Math.max(0, Math.min(100, Number(remainingPercent) || 0));
        const color = usageColorForPercent(remaining);
        const fillWidth = Math.round(USAGE_BAR_WIDTH * remaining / 100);
        this._title.text = `${remaining}% remaining`;
        this._track.set_width(USAGE_BAR_WIDTH);
        this._track.set_style(`background-color: ${color.track};`);
        this._fill.set_width(fillWidth);
        this._fill.set_style(`background-color: ${color.fill};`);
        this._reset.text = `Resets ${resetLabel || '—'}`;
    }
});

const CodexUsageIndicator = GObject.registerClass(
class CodexUsageIndicator extends PanelMenu.Button {
    _init(iconPath) {
        super._init(0.0, 'Codex GNOME Usage');

        this._icon = new St.Icon({
            gicon: new Gio.FileIcon({file: Gio.File.new_for_path(iconPath)}),
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        this._label = new St.Label({
            text: '—',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._label);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._primaryHeader = new PopupMenu.PopupMenuItem('5h limit', {reactive: false});
        this.menu.addMenuItem(this._primaryHeader);
        this._primaryBar = new UsageBarMenuItem('—');
        this.menu.addMenuItem(this._primaryBar);

        this._secondaryHeader = new PopupMenu.PopupMenuItem('Weekly limit', {reactive: false});
        this.menu.addMenuItem(this._secondaryHeader);
        this._secondaryBar = new UsageBarMenuItem('—');
        this.menu.addMenuItem(this._secondaryBar);

        this._planItem = new PopupMenu.PopupMenuItem('Plan: —', {reactive: false});
        this._planItem.label.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this.menu.addMenuItem(this._planItem);

        this._errorItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._errorItem.hide();
        this.menu.addMenuItem(this._errorItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const refreshItem = new PopupMenu.PopupMenuItem('Refresh');
        refreshItem.connect('activate', () => this._callMethod('Refresh'));
        this.menu.addMenuItem(refreshItem);

        this._authItem = null;
        this._authenticated = null;
        this._setAuthenticated(false);

        this._proxy = null;
        this._connectDbus();
        this._timeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, REFRESH_MS, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this._refresh();
    }

    _connectDbus() {
        Gio.DBusProxy.new_for_bus(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            null,
            DBUS_NAME,
            DBUS_PATH,
            DBUS_IFACE,
            null,
            (_source, result) => {
                try {
                    this._proxy = Gio.DBusProxy.new_for_bus_finish(result);
                    this._errorItem.hide();
                    this._refresh();
                } catch (e) {
                    this._proxy = null;
                    this._showError('Backend not running — start codex-usage service');
                }
            }
        );
    }

    _callMethod(method) {
        if (!this._proxy) {
            this._showError('Backend not running');
            return;
        }
        this._proxy.call(
            method,
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (_proxy, result) => {
                try {
                    this._proxy.call_finish(result);
                } catch (e) {
                    this._showError(e.message);
                }
                this._refresh();
            }
        );
    }

    _refresh() {
        if (!this._proxy)
            return;

        this._proxy.call(
            'GetUsage',
            null,
            Gio.DBusCallFlags.NONE,
            -1,
            null,
            (_proxy, result) => {
                let json = '{}';
                try {
                    const unpacked = this._proxy.call_finish(result).deepUnpack();
                    json = Array.isArray(unpacked) ? unpacked[0] : unpacked;
                } catch (e) {
                    this._showError(e.message);
                    return;
                }
                this._applyUsage(JSON.parse(json));
            }
        );
    }

    _applyUsage(data) {
        this._setAuthenticated(Boolean(data.authenticated));

        if (data.error) {
            this._showError(data.error);
            this._label.text = '!';
            return;
        }

        this._errorItem.hide();

        const primary = data.primary || {};
        const secondary = data.secondary || {};
        const primaryLeft = primary.remaining_percent ?? '—';
        const secondaryLeft = secondary.remaining_percent ?? '—';

        this._label.text = `${primaryLeft}%`;
        this._primaryBar.setValues(primaryLeft, primary.reset_label);
        this._secondaryBar.setValues(secondaryLeft, secondary.reset_label);

        const plan = data.plan_type ? data.plan_type.toUpperCase() : '—';
        const email = data.email ? ` · ${data.email}` : '';
        this._planItem.label.text = `Plan: ${plan}${email}`;

        if (data.limit_reached)
            this._icon.add_style_class_name('codex-usage-warning');
        else
            this._icon.remove_style_class_name('codex-usage-warning');
    }

    _showError(message) {
        this._errorItem.label.text = message;
        this._errorItem.show();
    }

    _setAuthenticated(authenticated) {
        if (this._authItem && this._authenticated === authenticated)
            return;

        this._authItem?.destroy();
        this._authenticated = authenticated;

        const label = authenticated ? 'Log out' : 'Log in to Codex';
        const method = authenticated ? 'Logout' : 'Login';
        this._authItem = new PopupMenu.PopupMenuItem(label);
        this._authItem.connect('activate', () => this._callMethod(method));
        this.menu.addMenuItem(this._authItem);
    }

    destroy() {
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = null;
        }
        super.destroy();
    }
});

export default class CodexUsageExtension extends Extension {
    enable() {
        const iconFile = this.dir.get_child('icons').get_child('codex-usage-symbolic.svg');
        this._indicator = new CodexUsageIndicator(iconFile.get_path());
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
