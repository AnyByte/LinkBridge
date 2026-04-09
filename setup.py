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
    "iconfile": "assets/LinkBridge.icns",
    "plist": {
        "CFBundleName": "LinkBridge",
        "CFBundleDisplayName": "LinkBridge",
        "CFBundleIdentifier": "com.linkbridge.app",
        "CFBundleVersion": "2.0.0",
        "CFBundleShortVersionString": "2.0.0",
        "LSUIElement": True,
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
        "NSLocalNetworkUsageDescription": (
            "LinkBridge uses the local network to discover Ableton Link peers "
            "(such as Rekordbox, djay Pro, or other Link-enabled apps) so it "
            "can forward their tempo to your MIDI output."
        ),
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
