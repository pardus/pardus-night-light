#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
import os, subprocess

def create_mo_files():
    podir = "po"
    mo = []
    for po in os.listdir(podir):
        if po.endswith(".po"):
            os.makedirs("{}/{}/LC_MESSAGES".format(podir, po.split(".po")[0]), exist_ok=True)
            mo_file = "{}/{}/LC_MESSAGES/{}".format(podir, po.split(".po")[0], "pardus-night-light.mo")
            msgfmt_cmd = 'msgfmt {} -o {}'.format(podir + "/" + po, mo_file)
            subprocess.call(msgfmt_cmd, shell=True)
            mo.append(("/usr/share/locale/" + po.split(".po")[0] + "/LC_MESSAGES",
                       ["po/" + po.split(".po")[0] + "/LC_MESSAGES/pardus-night-light.mo"]))
    return mo


changelog = "debian/changelog"
if os.path.exists(changelog):
    head = open(changelog).readline()
    try:
        version = head.split("(")[1].split(")")[0]
    except:
        print("debian/changelog format is wrong for get version")
        version = "0.0.0"
    f = open("src/__version__", "w")
    f.write(version)
    f.close()

data_files = [
    ("/usr/bin", ["pardus-night-light"]),
    ("/usr/share/applications",
     ["data/tr.org.pardus.night-light.desktop"]),
    ("/usr/share/pardus-night-light/ui",
     ["ui/MainWindow.glade"]),
    ("/usr/share/pardus-night-light/src",
     ["src/Main.py",
      "src/MainWindow.py",
      "src/UserSettings.py",
      "src/__version__"]),
    ("/usr/share/pardus-night-light/data",
     ["data/style.css",
      "data/tr.org.pardus.night-light-autostart.desktop",
      "data/pardus-night-light.svg",
      "data/pardus-night-light-enabled-symbolic.svg",
      "data/pardus-night-light-disabled-symbolic.svg"]),
    ("/usr/share/icons/hicolor/scalable/apps/",
     ["data/pardus-night-light.svg",
      "data/pardus-night-light-enabled-symbolic.svg",
      "data/pardus-night-light-disabled-symbolic.svg"])
] + create_mo_files()

setup(
    name="pardus-night-light",
    version=version,
    packages=find_packages(),
    scripts=["pardus-night-light"],
    install_requires=["PyGObject"],
    data_files=data_files,
    author="Fatih Altun",
    author_email="fatih.altun@pardus.org.tr",
    description="Redshift based night light application",
    license="GPLv3",
    keywords="pardus-night-light, redshift, color, temperature",
    url="https://github.com/pardus/pardus-night-light",
)
