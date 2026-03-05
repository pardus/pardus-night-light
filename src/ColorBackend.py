#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-desktop night light backend.

Automatically selects:
GNOME (GSettings), KDE (D-Bus), Wayland (gammastep), or redshift as fallback.

Public API:
- apply(kelvin)
- reset()
- sync_init(app)                    [GNOME only — bidirectional GSettings sync]
- sync_schedule(sh, sm, eh, em)     [GNOME only]
- sync_disconnect()                 [GNOME only — cleanup]
"""

import os
import shutil
import subprocess

try:
    import gi
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import Gio, GLib
except (ImportError, ValueError):
    Gio = None
    GLib = None


# GNOME hour conversion helpers
def gnome_to_hm(fractional_hour):
    """
    GNOME stores schedule as fractional double (20.5 = 20:30)
    App stores as integer hour + integer minute
    """
    fractional_hour = max(0.0, min(fractional_hour, 24.0))
    h = int(fractional_hour)
    m = int(round((fractional_hour - h) * 60))
    if m == 60:
        h += 1
        m = 0
    if h >= 24:
        h, m = 0, 0
    return h, m


def hm_to_gnome(hour, minute):
    return float(hour) + float(minute) / 60.0


class ColorBackend:
    """
    Automatically choose a color temperature backend

    1. GNOME GSettings  --  GNOME / Unity / Budgie
    2. KDE D-Bus        --  KDE / Plasma
    3. gammastep        --  Wayland and neither above matched
    4. redshift         --  fallback (X11 or when nothing else is available)
    """

    def __init__(self):
        self.apply_func = self.apply_redshift
        self.reset_func = self.reset_redshift
        self.backend_name = "redshift"

        # GNOME sync state
        self.settings = None
        self.sync_handler_ids = []
        self.syncing = False

        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        session = os.environ.get('XDG_SESSION_TYPE', '').lower()

        if any(d in desktop for d in ('gnome', 'unity', 'budgie')):
            self.init_gnome_backend()
        elif any(d in desktop for d in ('kde', 'plasma')):
            self.init_kde_backend()
        elif session == 'wayland':
            self.init_gammastep_backend()

        print("Selected backend: {} (session={}, desktop={})".format(
            self.backend_name, session or "unknown", desktop or "unknown"))

    # GNOME
    def init_gnome_backend(self):
        if Gio is None:
            return
        try:
            source = Gio.SettingsSchemaSource.get_default()
            schema_id = 'org.gnome.settings-daemon.plugins.color'
            schema = source.lookup(schema_id, True) if source else None
            if schema is None:
                return
            self.settings = Gio.Settings.new(schema_id)
            settings = self.settings

            def apply_gnome(temp):
                settings.set_boolean('night-light-enabled', True)
                settings.set_uint('night-light-temperature', temp)
                settings.apply()

            def reset_gnome():
                settings.set_boolean('night-light-enabled', False)
                settings.apply()

            self.apply_func = apply_gnome
            self.reset_func = reset_gnome
            self.backend_name = "gnome"
        except Exception as exc:
            print("Failed to initialise GNOME backend: {}".format(exc))

    # GNOME bidirectional sync
    def sync_init(self, app):
        if self.settings is None:
            return
        self.sync_app = app

        self.pull_all()

        for key in ('night-light-enabled', 'night-light-temperature',
                    'night-light-schedule-from', 'night-light-schedule-to'):
            hid = self.settings.connect('changed::' + key, self.on_gnome_changed)
            self.sync_handler_ids.append(hid)

        print("GNOME sync: active.")

    def clear_syncing(self):
        """Reset sync guard flag"""
        self.syncing = False
        return False  # GLib.SOURCE_REMOVE

    def on_gnome_changed(self, settings, key):
        """GNOME → App: react to dconf changes."""
        if self.syncing:
            return
        self.syncing = True
        try:
            app = self.sync_app
            if key == 'night-light-enabled':
                app.night_switch.set_state(settings.get_boolean(key))

            elif key == 'night-light-temperature':
                temp = max(1500, min(settings.get_uint(key), 5500))
                if not app.etap:
                    app.temp_adjusment.set_value(temp)

            elif key in ('night-light-schedule-from', 'night-light-schedule-to'):
                app.schedule_init = True
                try:
                    fh, fm = gnome_to_hm(settings.get_double('night-light-schedule-from'))
                    th, tm = gnome_to_hm(settings.get_double('night-light-schedule-to'))
                    app.start_hour_adj.set_value(fh)
                    app.start_minute_adj.set_value(fm)
                    app.end_hour_adj.set_value(th)
                    app.end_minute_adj.set_value(tm)
                finally:
                    app.schedule_init = False
                app.update_schedule_info()
                app.save_schedule_config()
                if app.UserSettings.config_schedule:
                    app.start_schedule()
        finally:
            GLib.idle_add(self.clear_syncing)

    def pull_all(self):
        """One-time GNOME -> app sync on startup."""
        s = self.settings
        app = self.sync_app
        self.syncing = True
        app.schedule_init = True
        try:
            # temperature first — switch handler uses config_temp via apply()
            temp = max(1500, min(s.get_uint('night-light-temperature'), 5500))
            if not app.etap:
                app.temp_adjusment.set_value(temp)

            app.night_switch.set_state(s.get_boolean('night-light-enabled'))

            h, m = gnome_to_hm(s.get_double('night-light-schedule-from'))
            app.start_hour_adj.set_value(h)
            app.start_minute_adj.set_value(m)

            h, m = gnome_to_hm(s.get_double('night-light-schedule-to'))
            app.end_hour_adj.set_value(h)
            app.end_minute_adj.set_value(m)

            app.update_schedule_info()
        finally:
            app.schedule_init = False
            GLib.idle_add(self.clear_syncing)

        app.save_schedule_config()
        if app.UserSettings.config_schedule:
            app.start_schedule()

    def sync_schedule(self, start_h, start_m, end_h, end_m):
        """App -> GNOME: schedule times changed."""
        if self.settings is None or self.syncing:
            return
        self.syncing = True
        try:
            self.settings.set_boolean('night-light-schedule-automatic', False)
            self.settings.set_double('night-light-schedule-from',
                                     hm_to_gnome(start_h, start_m))
            self.settings.set_double('night-light-schedule-to',
                                     hm_to_gnome(end_h, end_m))
            self.settings.apply()
        finally:
            GLib.idle_add(self.clear_syncing)

    def sync_disconnect(self):
        if self.settings is None:
            return
        for hid in self.sync_handler_ids:
            self.settings.disconnect(hid)
        self.sync_handler_ids.clear()
        self.sync_app = None

    # KDE
    def init_kde_backend(self):
        if Gio is None or GLib is None:
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                'org.kde.KWin',
                '/ColorCorrect',
                'org.kde.kwin.ColorCorrect',
                None,
            )
            if proxy.call_sync('nightColorInfo', None,
                               Gio.DBusCallFlags.NONE, 3000, None) is None:
                return

            def apply_kde(temp):
                config = {
                    'Mode': GLib.Variant('u', 3),
                    'NightTemperature': GLib.Variant('u', temp),
                    'Active': GLib.Variant('b', True),
                }
                try:
                    proxy.call_sync(
                        'setNightColorConfig',
                        GLib.Variant('(a{sv})', (config,)),
                        Gio.DBusCallFlags.NONE, -1, None,
                    )
                except Exception as err:
                    print("KDE backend apply error: {}".format(err))

            def reset_kde():
                config = {
                    'Mode': GLib.Variant('u', 3),
                    'Active': GLib.Variant('b', False),
                }
                try:
                    proxy.call_sync(
                        'setNightColorConfig',
                        GLib.Variant('(a{sv})', (config,)),
                        Gio.DBusCallFlags.NONE, -1, None,
                    )
                except Exception as err:
                    print("KDE backend reset error: {}".format(err))

            self.apply_func = apply_kde
            self.reset_func = reset_kde
            self.backend_name = "kde"
        except Exception as exc:
            print("Failed to initialise KDE backend: {}".format(exc))

    # Gammastep
    def init_gammastep_backend(self):
        if shutil.which('gammastep'):
            self.apply_func = self.apply_gammastep
            self.reset_func = self.reset_gammastep
            self.backend_name = "gammastep"
        else:
            print(
                "Wayland session detected but gammastep is not installed. "
                "Falling back to redshift (may not work on Wayland)."
            )

    def apply_gammastep(self, temp):
        try:
            subprocess.run(['gammastep', '-P', '-O', str(temp)])
        except Exception as exc:
            print("gammastep set error: {}".format(exc))

    def reset_gammastep(self):
        try:
            subprocess.run(['gammastep', '-x'])
        except Exception as exc:
            print("gammastep reset error: {}".format(exc))

    # Redshift (fallback)
    def apply_redshift(self, temp):
        try:
            subprocess.run(['redshift', '-P', '-O', str(temp)])
        except Exception as exc:
            print("redshift set error: {}".format(exc))

    def reset_redshift(self):
        try:
            subprocess.run(['redshift', '-x'])
        except Exception as exc:
            print("redshift reset error: {}".format(exc))

    def apply(self, temp):
        """Apply the given colour temperature (Kelvin)."""
        self.apply_func(int(temp))

    def reset(self):
        """Disable any colour filter and restore default colours."""
        self.reset_func()
