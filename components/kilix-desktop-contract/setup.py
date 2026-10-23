"""Include canonical protocol documents in both source and wheel distributions."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class BuildPy(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / "kilix_desktop_contract" / "_resources"
        for name in ("schemas", "contracts"):
            for source in sorted((ROOT / name).glob("*.json")):
                self.mkpath(str(target / name))
                self.copy_file(str(source), str(target / name / source.name))


setup(cmdclass={"build_py": BuildPy})
