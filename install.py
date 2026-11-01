#!/usr/bin/env python3
"""Install per-user launcher and desktop entry; no administrator access."""
from pathlib import Path
import shlex

root=Path(__file__).resolve().parent
bin_dir=Path.home()/'.local/bin'
apps=Path.home()/'.local/share/applications'
bin_dir.mkdir(parents=True,exist_ok=True)
apps.mkdir(parents=True,exist_ok=True)
launcher=bin_dir/'lyra-control'
content=f'#!/bin/sh\n# Lyra Control launcher\nexec /usr/bin/python3 {shlex.quote(str(root/"app.py"))} "$@"\n'
if launcher.exists() and not any(marker in launcher.read_text() for marker in
                                ('# Lyra Control launcher', 'lyra-control/app.py')):
    raise SystemExit(f'Refusing to replace unrelated launcher: {launcher}')
launcher.write_text(content)
launcher.chmod(0o755)
desktop=apps/'lyra-control.desktop'
desktop.write_text(f'''[Desktop Entry]
Type=Application
Name=Lyra Control
Comment=Integrated Lyra camera viewer and native controls
Exec={launcher}
Icon={root/'assets/icon.svg'}
Terminal=false
Categories=AudioVideo;Video;Settings;
Keywords=Lyra;Hollyland;camera;zoom;
StartupWMClass=lyra-control
''')
print(f'Installed: {launcher}\nDesktop entry: {desktop}')
