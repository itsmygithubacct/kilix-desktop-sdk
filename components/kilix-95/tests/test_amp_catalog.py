"""Amp preserves the complete catalog build identity and selected app root."""
import configparser
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import mock

import harness as H
import games

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    source=root/'source';source.mkdir()
    # A real local source whose build accepts only the selected native flag.
    (source/'Makefile').write_text('all:\n\ttest "$(ENCODEC)" = 1\n\tprintf "#!/bin/sh\\nexit 0\\n" > kilix-amp\n\tchmod 755 kilix-amp\n')
    for args in (('init','-q'),('config','user.name','Kilix Test'),
                 ('config','user.email','test@example.invalid'),('add','.'),('commit','-qm','fixture')):
        subprocess.run(['git','-C',str(source),*args],check=True,capture_output=True)
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    spec=replace(games.CONTENT_CATALOG.require('kilix-amp'),repository=str(source),ref=commit,
                 build=('make','ENCODEC=1','all'))
    catalog=mock.Mock();catalog.require.return_value=spec
    config=configparser.ConfigParser()
    with mock.patch.object(games,'CONTENT_CATALOG',catalog), \
         mock.patch.object(games,'APPS_DIR',str(root/'apps')), \
         mock.patch.dict(os.environ,{'GIT_ALLOW_PROTOCOL':'file'}):
        assert games.amp_ready(config) is None
        executable=games.ensure_amp(config,lambda _message:None)
        assert executable==str(root/'apps/kilix-amp/kilix-amp')
        assert games.amp_ready(config)==executable
        # Configured external executables retain the existing explicit trust.
        external=root/'external';external.mkdir()
        (external/'kilix-amp').write_text('#!/bin/sh\nexit 0\n')
        (external/'kilix-amp').chmod(0o755)
        config.add_section('kilix-amp');config.set('kilix-amp','dir',str(external))
        assert games.amp_ready(config)==str(external/'kilix-amp')
        assert games.ensure_amp(config,lambda _message:None)==str(external/'kilix-amp')
        config.remove_section('kilix-amp')
        # The wrapper must pass the actual full spec, without synthesizing
        # ref/binary-only metadata. Generic Installer cache semantics are owned
        # by the content package, not changed by this provider correction.
        changed=replace(spec,build=('make','ENCODEC=0','all'))
        catalog.require.return_value=changed
        with mock.patch.object(games.kilix_content.Installer,'ready',return_value=None) as inspect:
            assert games.amp_ready(config) is None
            assert inspect.call_args.args[0] is changed
print('ok: full Amp catalog recipe, root, readiness delegation and explicit fallback')
