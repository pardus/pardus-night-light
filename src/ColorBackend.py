#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-desktop night light backend.

Automatically selects:
GNOME (GSettings), KDE (D-Bus), Wayland (gammastep), or redshift as fallback.

Public API:
- apply(kelvin)
- reset()
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


class ColorBackend:
    """
    Automatically choose a color temperature backend

    1. GNOME GSettings  --  GNOME / Unity / Budgie
    2. KDE D-Bus        --  KDE / Plasma
    3. gammastep        --  Wayland and neither above matched
    4. redshift         --  fallback (X11 or when nothing else is available)
    """

    def __init__(self):
        # Default to redshift; will be overwritten by init_* methods as needed.
        self.apply_func = self.apply_redshift
        self.reset_func = self.reset_redshift
        self.backend_name = "redshift"

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

    def init_gnome_backend(self):
        if Gio is None:
            return
        try:
            source = Gio.SettingsSchemaSource.get_default()
            schema_id = 'org.gnome.settings-daemon.plugins.color'
            schema = source.lookup(schema_id, True) if source else None
            if schema is None:
                return
            settings = Gio.Settings.new(schema_id)

            def apply_gnome(temp):
                settings.set_boolean('night-light-enabled', True)
                settings.set_uint('night-light-temperature', temp)
                settings.set_boolean('night-light-schedule-automatic', False)
                settings.set_double('night-light-schedule-from', 0.0)
                settings.set_double('night-light-schedule-to', 24.0)
                settings.apply()

            def reset_gnome():
                settings.set_boolean('night-light-enabled', False)
                settings.apply()

            self.apply_func = apply_gnome
            self.reset_func = reset_gnome
            self.backend_name = "gnome"
        except Exception as exc:
            print("Failed to initialise GNOME backend: {}".format(exc))

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
