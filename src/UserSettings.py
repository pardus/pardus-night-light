#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb 16 14:53:13 2022

@author: fatih
"""

import os
from configparser import ConfigParser
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


class UserSettings(object):
    def __init__(self):
        self.default_status = False
        self.default_temp = 5500
        self.default_autostart = False
        self.default_schedule = False
        self.default_schedule_start = "18:00"
        self.default_schedule_end = "06:00"

        self.configdir = "{}/pardus/pardus-night-light/".format(GLib.get_user_config_dir())
        self.configfile = "settings.ini"

        self.autostartdir = "{}/autostart/".format(GLib.get_user_config_dir())
        self.autostartfile = "tr.org.pardus.night-light-autostart.desktop"

        self.config = ConfigParser(strict=False)

        self.config_status = self.default_status
        self.config_temp = self.default_temp
        self.config_autostart = self.default_autostart
        self.config_schedule = self.default_schedule
        self.config_schedule_start = self.default_schedule_start
        self.config_schedule_end = self.default_schedule_end

    def createDefaultConfig(self, force=False):
        self.config['Main'] = {"status": self.default_status,
                               "temp": self.default_temp,
                               "autostart": self.default_autostart,
                               "schedule": self.default_schedule,
                               "schedule_start": self.default_schedule_start,
                               "schedule_end": self.default_schedule_end}

        if not Path.is_file(Path(self.configdir + self.configfile)) or force:
            if self.createDir(self.configdir):
                with open(self.configdir + self.configfile, "w") as cf:
                    self.config.write(cf)

    def readConfig(self):
        try:
            self.config.read(self.configdir + self.configfile)
            self.config_status = self.config.getboolean('Main', 'status')
            self.config_temp = self.config.getint('Main', 'temp')
            self.config_autostart = self.config.getboolean('Main', 'autostart')
            self.config_schedule = self.config.getboolean('Main', 'schedule',
                                                          fallback=self.default_schedule)
            self.config_schedule_start = self.config.get('Main', 'schedule_start',
                                                         fallback=self.default_schedule_start)
            self.config_schedule_end = self.config.get('Main', 'schedule_end',
                                                       fallback=self.default_schedule_end)

        except Exception as e:
            print("{}".format(e))
            print("user config read error ! Trying create defaults")
            # if not read; try to create defaults
            self.config_status = self.default_status
            self.config_temp = self.default_temp
            self.config_autostart = self.default_autostart
            self.config_schedule = self.default_schedule
            self.config_schedule_start = self.default_schedule_start
            self.config_schedule_end = self.default_schedule_end
            try:
                self.createDefaultConfig(force=True)
            except Exception as e:
                print("self.createDefaultConfig(force=True) : {}".format(e))

    def writeConfig(self, status, temp, autostart,
                    schedule=None, schedule_start=None, schedule_end=None):
        self.config['Main'] = {
            "status": status,
            "temp": temp,
            "autostart": autostart,
            "schedule": schedule if schedule is not None else self.config_schedule,
            "schedule_start": schedule_start if schedule_start is not None else self.config_schedule_start,
            "schedule_end": schedule_end if schedule_end is not None else self.config_schedule_end
        }
        if self.createDir(self.configdir):
            with open(self.configdir + self.configfile, "w") as cf:
                self.config.write(cf)
                return True
        return False

    def createDir(self, dir):
        try:
            Path(dir).mkdir(parents=True, exist_ok=True)
            return True
        except:
            print("{} : {}".format("mkdir error", dir))
            return False

    def set_autostart(self, state):
        self.createDir(self.autostartdir)
        p = Path(self.autostartdir + self.autostartfile)
        if state:
            if not p.exists():
                p.symlink_to(
                    os.path.dirname(os.path.abspath(__file__)) + "/../data/tr.org.pardus.night-light-autostart.desktop")
        else:
            if p.exists():
                p.unlink(missing_ok=True)
