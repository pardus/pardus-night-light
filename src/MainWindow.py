#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Feb  5 19:05:13 2022

@author: fatihaltun
"""

import os
import signal
import subprocess
import time
import distro
import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject, Gdk

try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as appindicator
except:
    # fall back to Ayatana
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as appindicator

from UserSettings import UserSettings

import locale
from locale import gettext as _

locale.bindtextdomain('pardus-night-light', '/usr/share/locale')
locale.textdomain('pardus-night-light')


class MainWindow(object):
    def __init__(self, application):
        self.Application = application

        self.main_window_ui_filename = os.path.dirname(os.path.abspath(__file__)) + "/../ui/MainWindow.glade"
        try:
            self.GtkBuilder = Gtk.Builder.new_from_file(self.main_window_ui_filename)
            self.GtkBuilder.connect_signals(self)
        except GObject.GError:
            print("Error reading GUI file: " + self.main_window_ui_filename)
            raise

        self.define_components()
        self.define_variables()
        self.main_window.set_application(application)

        self.user_settings()
        self.set_autostart()
        self.init_indicator()
        self.init_ui()

        self.about_dialog.set_program_name(_("Pardus Night Light"))
        if self.about_dialog.get_titlebar() is None:
            about_headerbar = Gtk.HeaderBar.new()
            about_headerbar.set_show_close_button(True)
            about_headerbar.set_title(_("About Pardus Night Light"))
            about_headerbar.pack_start(Gtk.Image.new_from_icon_name("pardus-night-light", Gtk.IconSize.LARGE_TOOLBAR))
            about_headerbar.show_all()
            self.about_dialog.set_titlebar(about_headerbar)

        # Set version
        # If not getted from __version__ file then accept version in MainWindow.glade file
        try:
            version = open(os.path.dirname(os.path.abspath(__file__)) + "/__version__").readline()
            self.about_dialog.set_version(version)
        except:
            pass

        cssProvider = Gtk.CssProvider()
        cssProvider.load_from_path(os.path.dirname(os.path.abspath(__file__)) + "/../data/style.css")
        screen = Gdk.Screen.get_default()
        styleContext = Gtk.StyleContext()
        styleContext.add_provider_for_screen(screen, cssProvider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)

        # With the others GTK_STYLE_PROVIDER_PRIORITY values get the same result.

        def sighandler(signum, frame):
            subprocess.run(["redshift", "-x"])
            if self.about_dialog.is_visible():
                self.about_dialog.hide()
            self.main_window.get_application().quit()

        signal.signal(signal.SIGINT, sighandler)
        signal.signal(signal.SIGTERM, sighandler)

        if any(key in self.Application.args for key in ["tray", "set", "color"]):
            self.main_window.set_visible(False)
        else:
            self.main_window.set_visible(True)
            self.main_window.show_all()

        self.set_indicator()
        self.control_args()

    def define_components(self):
        self.main_window = self.GtkBuilder.get_object("ui_main_window")
        self.about_dialog = self.GtkBuilder.get_object("ui_about_dialog")
        self.night_switch = self.GtkBuilder.get_object("ui_night_switch")
        self.autostart_switch = self.GtkBuilder.get_object("ui_autostart_switch")
        self.temp_scale = self.GtkBuilder.get_object("ui_temp_scale")
        self.temp_adjusment = self.GtkBuilder.get_object("ui_temp_adjusment")

        self.ui_main_box = self.GtkBuilder.get_object("ui_main_box")
        self.ui_submain_box = self.GtkBuilder.get_object("ui_submain_box")
        self.ui_mainlabels_box = self.GtkBuilder.get_object("ui_mainlabels_box")
        self.ui_mainwidgets_box = self.GtkBuilder.get_object("ui_mainwidgets_box")

        self.ui_tempcolor_stack = self.GtkBuilder.get_object("ui_tempcolor_stack")
        self.ui_temp_box = self.GtkBuilder.get_object("ui_temp_box")

    def define_variables(self):
        system_wide = "usr/share" in os.path.dirname(os.path.abspath(__file__))
        self.icon_active = "pardus-night-light-on-symbolic" if system_wide else "night-light-symbolic"
        self.icon_passive = "pardus-night-light-off-symbolic" if system_wide else "display-brightness-symbolic"
        self.make_first_sleep = True
        self.temp_color = {"low": 5500, "medium": 4000, "high": 2500}
        self.etap = False
        if "etap" in distro.name().lower() and "etap" in distro.codename():
            print("ETAP detected.")
            self.etap = True

    def control_args(self):
        if "set" in self.Application.args.keys():
            print("processing 'set' arg.")
            try:
                value = int(self.Application.args["set"])
            except Exception as e:
                print("{}".format(e))
                print("invalid arg. 0 for disable, 1 for enable")
                return
            if value == 0:
                # disable
                self.night_switch.set_state(False)

            elif value == 1:
                # enable
                self.night_switch.set_state(True)
            else:
                print("value {} not supported yet.".format(value))
        elif "color" in self.Application.args.keys():
            print("processing 'color' arg.")
            try:
                value = int(self.Application.args["color"])
                if value not in range(1500, 5501):
                    print("The value should be between 1500 and 5500. Your value is: {}".format(value))
                    return
            except Exception as e:
                print("{}".format(e))
                print("invalid arg")
                return
            if self.etap:
                self.set_color_temp(value)
            else:
                self.temp_adjusment.set_value(value)
        elif "tray" in self.Application.args.keys():
            self.main_window.set_visible(False)
        else:
            self.main_window.present()

    def user_settings(self):
        self.UserSettings = UserSettings()
        self.UserSettings.createDefaultConfig()
        self.UserSettings.readConfig()

    def init_ui(self):

        if self.etap:
            self.ui_tempcolor_stack.set_visible_child_name("button")
            self.ui_main_box.set_spacing(0)
            self.ui_mainlabels_box.set_spacing(0)
            self.ui_mainwidgets_box.set_spacing(0)
            self.ui_submain_box.set_margin_top(0)
            self.init_etap_tempcolor_buttons()
        else:
            self.ui_tempcolor_stack.set_visible_child_name("scale")

        self.night_switch.set_state(self.UserSettings.config_status)
        if self.etap:
            self.ui_temp_box.set_sensitive(self.UserSettings.config_status)
        else:
            self.temp_scale.set_sensitive(self.UserSettings.config_status)
            self.temp_adjusment.set_value(self.UserSettings.config_temp)
        self.autostart_switch.set_state(self.UserSettings.config_autostart)
        if not self.UserSettings.config_status:
            subprocess.run(["redshift", "-x"])

        system_wide = "usr/share" in os.path.dirname(os.path.abspath(__file__))
        if not system_wide:
            self.main_window.set_default_icon_from_file(
                os.path.dirname(os.path.abspath(__file__)) + "/../data/pardus-night-light.svg")
            self.about_dialog.set_logo(None)

    def init_etap_tempcolor_buttons(self):
        self.low_button = Gtk.Button.new()
        self.low_button.name = "low"
        self.low_button.connect("clicked", self.on_temp_button_clicked)
        low_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        low_box.set_homogeneous(True)
        low_box.set_margin_top(3)
        low_color_label = Gtk.Label.new()
        low_color_label.set_size_request(-1, 34)
        low_color_label.set_margin_start(13)
        low_color_label.set_margin_end(13)
        low_color_label.get_style_context().add_class("low-label")
        low_text_label = Gtk.Label.new()
        low_text_label.set_text(_("Low"))
        low_box.pack_start(low_color_label, False, True, 0)
        low_box.pack_start(low_text_label, False, True, 0)
        self.low_button.add(low_box)

        self.medium_button = Gtk.Button.new()
        self.medium_button.name = "medium"
        self.medium_button.connect("clicked", self.on_temp_button_clicked)
        medium_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        medium_box.set_homogeneous(True)
        medium_box.set_margin_top(3)
        medium_color_label = Gtk.Label.new()
        medium_color_label.set_size_request(-1, 34)
        medium_color_label.set_margin_start(13)
        medium_color_label.set_margin_end(13)
        medium_color_label.get_style_context().add_class("medium-label")
        medium_text_label = Gtk.Label.new()
        medium_text_label.set_text(_("Medium"))
        medium_box.pack_start(medium_color_label, False, True, 0)
        medium_box.pack_start(medium_text_label, False, True, 0)
        self.medium_button.add(medium_box)

        self.high_button = Gtk.Button.new()
        self.high_button.name = "high"
        self.high_button.connect("clicked", self.on_temp_button_clicked)
        high_box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
        high_box.set_homogeneous(True)
        high_box.set_margin_top(3)
        high_color_label = Gtk.Label.new()
        high_color_label.set_size_request(-1, 34)
        high_color_label.set_margin_start(13)
        high_color_label.set_margin_end(13)
        high_color_label.get_style_context().add_class("high-label")
        high_text_label = Gtk.Label.new()
        high_text_label.set_text(_("High"))
        high_box.pack_start(high_color_label, False, True, 0)
        high_box.pack_start(high_text_label, False, True, 0)
        self.high_button.add(high_box)

        self.ui_temp_box.add(self.low_button)
        self.ui_temp_box.add(self.medium_button)
        self.ui_temp_box.add(self.high_button)

        self.ui_temp_box.show_all()

    def init_indicator(self):
        if self.etap:
            return
        self.indicator = appindicator.Indicator.new(
            "pardus-night-light", self.icon_active, appindicator.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title(_("Pardus Night Light"))
        self.menu = Gtk.Menu()
        self.item_action = Gtk.MenuItem()
        self.item_action.connect("activate", self.on_menu_action)
        self.item_sh_app = Gtk.MenuItem()
        self.item_sh_app.connect("activate", self.on_menu_show_app)
        self.item_separator = Gtk.SeparatorMenuItem()
        self.item_quit = Gtk.MenuItem()
        self.item_quit.set_label(_("Quit"))
        self.item_quit.connect('activate', self.on_menu_quit_app)
        self.menu.append(self.item_sh_app)
        self.menu.append(self.item_action)
        self.menu.append(self.item_separator)
        self.menu.append(self.item_quit)
        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def set_indicator(self):
        if self.etap:
            return

        if self.UserSettings.config_status:
            self.item_action.set_label(_("Disable"))
            self.indicator.set_icon(self.icon_active)
        else:
            self.item_action.set_label(_("Enable"))
            self.indicator.set_icon(self.icon_passive)

        if self.main_window.is_visible():
            self.item_sh_app.set_label(_("Hide App"))
        else:
            self.item_sh_app.set_label(_("Show App"))

    def set_autostart(self):
        self.UserSettings.set_autostart(self.UserSettings.config_autostart)

    def on_menu_action(self, *args):
        self.night_switch.set_state(not self.UserSettings.config_status)

    def on_menu_show_app(self, *args):
        window_state = self.main_window.is_visible()
        if window_state:
            self.main_window.set_visible(False)
            self.item_sh_app.set_label(_("Show App"))
        else:
            self.main_window.set_visible(True)
            self.item_sh_app.set_label(_("Hide App"))
            self.main_window.present()

    def on_menu_quit_app(self, *args):
        subprocess.run(["redshift", "-x"])
        if self.about_dialog.is_visible():
            self.about_dialog.hide()
        self.main_window.get_application().quit()

    # Set color temp function for ETAP
    def set_color_temp(self, temperature):
        if self.UserSettings.config_status:
            subprocess.run(["redshift", "-P", "-O", "{}".format(temperature)])

        if temperature == self.temp_color["low"]:
            self.low_button.get_style_context().add_class("suggested-action")
            self.medium_button.get_style_context().remove_class("suggested-action")
            self.high_button.get_style_context().remove_class("suggested-action")
        elif temperature == self.temp_color["medium"]:
            self.low_button.get_style_context().remove_class("suggested-action")
            self.medium_button.get_style_context().add_class("suggested-action")
            self.high_button.get_style_context().remove_class("suggested-action")
        elif temperature == self.temp_color["high"]:
            self.low_button.get_style_context().remove_class("suggested-action")
            self.medium_button.get_style_context().remove_class("suggested-action")
            self.high_button.get_style_context().add_class("suggested-action")
        else:
            self.low_button.get_style_context().remove_class("suggested-action")
            self.medium_button.get_style_context().remove_class("suggested-action")
            self.high_button.get_style_context().remove_class("suggested-action")

        user_temp = self.UserSettings.config_temp
        if temperature != user_temp:
            self.UserSettings.writeConfig(self.UserSettings.config_status, temperature,
                                          self.UserSettings.config_autostart)
            self.user_settings()

    # Color temperature button clicks for ETAP
    def on_temp_button_clicked(self, button):
        if self.UserSettings.config_status:
            subprocess.run(["redshift", "-P", "-O", "{}".format(self.temp_color[button.name])])

        for row_button in self.ui_temp_box:
            row_button.get_style_context().remove_class("suggested-action")
        button.get_style_context().add_class("suggested-action")

        user_temp = self.UserSettings.config_temp
        if self.temp_color[button.name] != user_temp:
            self.UserSettings.writeConfig(self.UserSettings.config_status, self.temp_color[button.name],
                                          self.UserSettings.config_autostart)
            self.user_settings()

    def on_ui_temp_adjusment_value_changed(self, adjusment):
        value = "{:0.0f}".format(adjusment.get_value())
        print("on_ui_temp_adjusment_value_changed", value)

        if self.UserSettings.config_status:
            subprocess.run(["redshift", "-P", "-O", value])

        user_temp = self.UserSettings.config_temp
        if value != user_temp:
            self.UserSettings.writeConfig(self.UserSettings.config_status, value, self.UserSettings.config_autostart)
            self.user_settings()

    def on_ui_night_switch_state_set(self, switch, state):
        if self.etap:
            self.ui_temp_box.set_sensitive(state)
        else:
            self.temp_scale.set_sensitive(state)
        if state:
            if "tray" in self.Application.args.keys() and self.make_first_sleep:
                self.make_first_sleep = False
                time.sleep(5)
            subprocess.run(["redshift", "-P", "-O", "{:0.0f}".format(self.UserSettings.config_temp)])
            if self.etap:
                if self.UserSettings.config_temp == self.temp_color["low"]:
                    self.low_button.get_style_context().add_class("suggested-action")
                    self.medium_button.get_style_context().remove_class("suggested-action")
                    self.high_button.get_style_context().remove_class("suggested-action")
                elif self.UserSettings.config_temp == self.temp_color["medium"]:
                    self.low_button.get_style_context().remove_class("suggested-action")
                    self.medium_button.get_style_context().add_class("suggested-action")
                    self.high_button.get_style_context().remove_class("suggested-action")
                elif self.UserSettings.config_temp == self.temp_color["high"]:
                    self.low_button.get_style_context().remove_class("suggested-action")
                    self.medium_button.get_style_context().remove_class("suggested-action")
                    self.high_button.get_style_context().add_class("suggested-action")
                else:
                    self.low_button.get_style_context().remove_class("suggested-action")
                    self.medium_button.get_style_context().remove_class("suggested-action")
                    self.high_button.get_style_context().remove_class("suggested-action")
            else:
                self.temp_adjusment.set_value(self.UserSettings.config_temp)
            if not self.etap:
                self.item_action.set_label(_("Disable"))
                self.indicator.set_icon(self.icon_active)
        else:
            subprocess.run(["redshift", "-x"])
            if not self.etap:
                self.item_action.set_label(_("Enable"))
                self.indicator.set_icon(self.icon_passive)

        user_status = self.UserSettings.config_status
        if state != user_status:
            self.UserSettings.writeConfig(state, self.UserSettings.config_temp, self.UserSettings.config_autostart)
            self.user_settings()

    def on_ui_autostart_switch_state_set(self, switch, state):
        self.UserSettings.set_autostart(state)

        user_autostart = self.UserSettings.config_autostart
        if state != user_autostart:
            self.UserSettings.writeConfig(self.UserSettings.config_status, self.UserSettings.config_temp, state)
            self.user_settings()

    def on_ui_about_button_clicked(self, button):
        self.about_dialog.run()
        self.about_dialog.hide()

    def on_ui_main_window_delete_event(self, widget, event):
        self.main_window.hide()
        if not self.etap:
            self.item_sh_app.set_label(_("Show App"))
        return True

    def on_ui_main_window_destroy(self, widget, event):
        subprocess.run(["redshift", "-x"])
        if self.about_dialog.is_visible():
            self.about_dialog.hide()
        self.main_window.get_application().quit()
