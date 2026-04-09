"""py2app build config for LinkBridge.

Usage:
    python setup.py py2app

Output:
    dist/LinkBridge.app
"""

from setuptools import setup

APP = ["linkbridge/__main__.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "LinkBridge",
        "CFBundleDisplayName": "LinkBridge",
        "CFBundleIdentifier": "com.linkbridge.app",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
    },
    "packages": ["rumps", "mido", "rtmidi", "linkbridge"],
    "includes": [
        "logging.handlers",
    ],
    "excludes": [
        "tkinter",
        "_tkinter",
        "Tkinter",
    ],
}

setup(
    name="LinkBridge",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
