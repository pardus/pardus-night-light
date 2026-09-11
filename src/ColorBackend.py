#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-desktop night light backend.

Automatically selects:
GNOME/Cinnamon (GSettings), KDE (D-Bus), Wayland (gammastep), or redshift as fallback.

Public API:
- apply(kelvin)
- reset()
- sync_init(app)                    [GNOME/Cinnamon only — bidirectional GSettings sync]
- sync_schedule(sh, sm, eh, em)     [GNOME/Cinnamon only]
- sync_disconnect()                 [GNOME/Cinnamon only — cleanup]
"""

import os
import shutil
import subprocess

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib


# GNOME/Cinnamon hour conversion helpers
def gnome_to_hm(fractional_hour):
    """
    GNOME and Cinnamon store schedule as fractional double (20.5 = 20:30)
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

    1. GSettings        --  GNOME / Unity / Budgie / Cinnamon
    2. KDE D-Bus        --  KDE / Plasma
    3. gammastep        --  Wayland and neither above matched
    4. redshift         --  fallback (X11 or when nothing else is available)
    """

    def __init__(self):
        self.apply_func = self.apply_redshift
        self.reset_func = self.reset_redshift
        self.backend_name = "redshift"

        # GSettings sync state (GNOME/Cinnamon)
        self.settings = None
        self.sync_handler_ids = []
        self.syncing = False

        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        session = os.environ.get('XDG_SESSION_TYPE', '').lower()

        if any(d in desktop for d in ('gnome', 'unity', 'budgie')):
            self.init_gsettings_backend(
                'org.gnome.settings-daemon.plugins.color', 'gnome')
        elif 'cinnamon' in desktop:
            self.init_gsettings_backend(
                'org.cinnamon.settings-daemon.plugins.color', 'cinnamon')
        elif any(d in desktop for d in ('kde', 'plasma')):
            self.init_kde_backend()
        elif session == 'wayland':
            self.init_gammastep_backend()

        print("Selected backend: {} (session={}, desktop={})".format(
            self.backend_name, session or "unknown", desktop or "unknown"))

    # GSettings (GNOME/Cinnamon)
    def init_gsettings_backend(self, schema_id, name):
        try:
            source = Gio.SettingsSchemaSource.get_default()
            schema = source.lookup(schema_id, True) if source else None
            if schema is None:
                print("Schema {} not found, falling back.".format(schema_id))
                return
            self.settings = Gio.Settings.new(schema_id)
            settings = self.settings

            def apply_gsettings(temp):
                settings.set_boolean('night-light-enabled', True)
                settings.set_uint('night-light-temperature', temp)
                settings.apply()

            def reset_gsettings():
                settings.set_boolean('night-light-enabled', False)
                settings.apply()

            self.apply_func = apply_gsettings
            self.reset_func = reset_gsettings
            self.backend_name = name
        except Exception as exc:
            print("Failed to initialise {} backend: {}".format(name, exc))

    # GSettings bidirectional sync (GNOME/Cinnamon)
    def sync_init(self, app):
        if self.settings is None:
            return
        self.sync_app = app

        self.pull_all()

        keys = ('night-light-enabled', 'night-light-temperature',
                'night-light-schedule-from', 'night-light-schedule-to')
        if self.backend_name == 'cinnamon':
            keys += ('night-light-schedule-mode',)
        for key in keys:
            hid = self.settings.connect('changed::' + key, self.on_gsettings_changed)
            self.sync_handler_ids.append(hid)

        print("{} sync: active.".format(self.backend_name))

    def clear_syncing(self):
        """Reset sync guard flag"""
        self.syncing = False
        return False  # GLib.SOURCE_REMOVE

    def on_gsettings_changed(self, settings, key):
        """Desktop (GNOME/Cinnamon) -> App: react to dconf changes."""
        if self.syncing:
            return
        self.syncing = True
        try:
            app = self.sync_app
            if key == 'night-light-enabled':
                app.night_switch.set_state(settings.get_boolean(key))

            elif key == 'night-light-temperature':
                temp = max(1500, min(settings.get_uint(key), 5500))
                if app.UserSettings.config_scrollbar:
                    app.temp_adjusment.set_value(temp)

            elif key in ('night-light-schedule-from', 'night-light-schedule-to'):
                if not app.UserSettings.config_schedule:
                    return
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

            elif key == 'night-light-schedule-mode':
                schedule = settings.get_enum(key) == 1  # manual
                app.schedule_init = True
                try:
                    app.schedule_switch.set_state(schedule)
                    app.schedule_box.set_sensitive(schedule)
                finally:
                    app.schedule_init = False
                app.save_schedule_config(schedule=schedule)
        finally:
            GLib.idle_add(self.clear_syncing)

    def pull_all(self):
        """One-time desktop (GNOME/Cinnamon) -> app sync on startup."""
        s = self.settings
        app = self.sync_app
        self.syncing = True
        app.schedule_init = True
        schedule = app.UserSettings.config_schedule
        try:
            # temperature first — switch handler uses config_temp via apply()
            temp = max(1500, min(s.get_uint('night-light-temperature'), 5500))
            if app.UserSettings.config_scrollbar:
                app.temp_adjusment.set_value(temp)

            app.night_switch.set_state(s.get_boolean('night-light-enabled'))

            if self.backend_name == 'cinnamon':
                schedule = s.get_enum('night-light-schedule-mode') == 1
                app.schedule_switch.set_state(schedule)
                app.schedule_box.set_sensitive(schedule)

            if schedule:
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

        app.save_schedule_config(schedule=schedule)
        if app.UserSettings.config_schedule:
            self.sync_schedule(
                int(app.start_hour_adj.get_value()),
                int(app.start_minute_adj.get_value()),
                int(app.end_hour_adj.get_value()),
                int(app.end_minute_adj.get_value()))
            app.start_schedule()
        elif app.UserSettings.config_status and self.backend_name != 'cinnamon':
            self.sync_always()

    def has_native_schedule(self):
        """
        True when the desktop (GNOME/Cinnamon) handles
        schedule transitions itself
        """
        return self.settings is not None

    def sync_schedule(self, start_h, start_m, end_h, end_m):
        """App -> desktop GNOME/Cinnamon"""
        if self.settings is None:
            return
        self.syncing = True
        try:
            # Switch the desktop to manual schedule
            schema = self.settings.props.settings_schema
            if schema.has_key('night-light-schedule-automatic'):
                # Gnome : boolean (True = sunset/sunrise)
                self.settings.set_boolean('night-light-schedule-automatic', False)
            if schema.has_key('night-light-schedule-mode'):
                # Cinnamon : enum 0=auto, 1=manual, 2=always
                self.settings.set_enum('night-light-schedule-mode', 1)
            self.settings.set_double('night-light-schedule-from',
                                     hm_to_gnome(start_h, start_m))
            self.settings.set_double('night-light-schedule-to',
                                     hm_to_gnome(end_h, end_m))
            self.settings.apply()
        finally:
            GLib.idle_add(self.clear_syncing)

    def sync_always(self):
        """
        Disable time restrictions in the native schedule.
        """
        if self.settings is None:
            return
        schema = self.settings.props.settings_schema
        has_mode = schema.has_key('night-light-schedule-mode')
        has_automatic = schema.has_key('night-light-schedule-automatic')
        if not has_mode and not has_automatic:
            return
        self.syncing = True
        try:
            if has_mode:
                # Cinnamon: dedicated always mode
                self.settings.set_enum('night-light-schedule-mode', 2)
            else:
                # GNOME: manual full-day schedule
                self.settings.set_boolean('night-light-schedule-automatic', False)
                self.settings.set_double('night-light-schedule-from', 0.0)
                self.settings.set_double('night-light-schedule-to', 24.0)
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
