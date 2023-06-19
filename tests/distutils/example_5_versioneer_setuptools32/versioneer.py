#     Copyright 2023, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Python test originally created or extracted from other peoples work. The
#     parts from me are licensed as below. It is at least Free Software where
#     it's copied from other people. In these cases, that will normally be
#     indicated.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
# Version: 0.28
# Heavily truncated version of versioneer

import configparser
import json
import os
import sys
from pathlib import Path

have_tomllib = True
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        have_tomllib = False


class VersioneerConfig:
    """Container for Versioneer configuration parameters."""


def get_root():
    """Get the project root directory.

    We require that all commands are run from the project root, i.e. the
    directory that contains setup.py, setup.cfg, and versioneer.py .
    """
    root = os.path.realpath(os.path.abspath(os.getcwd()))
    setup_py = os.path.join(root, "setup.py")
    versioneer_py = os.path.join(root, "versioneer.py")
    if not (os.path.exists(setup_py) or os.path.exists(versioneer_py)):
        # allow 'python path/to/setup.py COMMAND'
        root = os.path.dirname(os.path.realpath(os.path.abspath(sys.argv[0])))
        setup_py = os.path.join(root, "setup.py")
        versioneer_py = os.path.join(root, "versioneer.py")
    if not (os.path.exists(setup_py) or os.path.exists(versioneer_py)):
        err = (
            "Versioneer was unable to run the project root directory. "
            "Versioneer requires setup.py to be executed from "
            "its immediate directory (like 'python setup.py COMMAND'), "
            "or in a way that lets it use sys.argv[0] to find the root "
            "(like 'python path/to/setup.py COMMAND')."
        )
        raise VersioneerBadRootError(err)
    return root


def get_config_from_root(root):
    """Read the project setup.cfg file to determine Versioneer config."""
    # This might raise OSError (if setup.cfg is missing)

    root = Path(root)
    pyproject_toml = root / "pyproject.toml"
    setup_cfg = root / "setup.cfg"
    section = None
    if pyproject_toml.exists() and have_tomllib:
        try:
            with open(pyproject_toml, "rb") as fobj:
                pp = tomllib.load(fobj)
            section = pp["tool"]["versioneer"]
        except (tomllib.TOMLDecodeError, KeyError):
            pass
    if not section:
        parser = configparser.ConfigParser()
        with open(setup_cfg) as cfg_file:
            parser.read_file(cfg_file)

        section = parser["versioneer"]

    cfg = VersioneerConfig()
    cfg.versionfile_source = section.get("versionfile_source")
    cfg.versionfile_build = section.get("versionfile_build")

    cfg.verbose = section.get("verbose")
    return cfg


SHORT_VERSION_PY = """
# This file was generated by 'versioneer.py' (0.28) from
# revision-control system data, or from the parent directory name of an
# unpacked source archive. Distribution tarballs contain a pre-generated copy
# of this file.

import json

version_json = '''
%s
'''  # END VERSION_JSON


def get_versions():
    return json.loads(version_json)
"""


def write_to_version_file(filename, versions):
    """Write the given version number to the given _version.py file."""
    os.unlink(filename)
    contents = json.dumps(versions, sort_keys=True, indent=1, separators=(",", ": "))
    with open(filename, "w") as f:
        f.write(SHORT_VERSION_PY % contents)

    print("set %s to '%s'" % (filename, versions["version"]))


class VersioneerBadRootError(Exception):
    """The project root directory is unknown or missing key files."""


def get_versions(verbose=False):
    """Get the project version from whatever source is available.

    Returns dict with two keys: 'version' and 'full'.
    """
    if "versioneer" in sys.modules:
        # see the discussion in cmdclass.py:get_cmdclass()
        del sys.modules["versioneer"]

    # We return a special version always for testing
    return {
        "version": "0+24601",
        "full-revisionid": None,
        "dirty": None,
        "error": "unable to compute version",
        "date": None,
    }


def get_version():
    """Get the short version string for this project."""
    return get_versions()["version"]


def get_cmdclass(cmdclass=None):
    """Get the custom setuptools subclasses used by Versioneer.

    If the package uses a different cmdclass (e.g. one from numpy), it
    should be provide as an argument.
    """
    if "versioneer" in sys.modules:
        del sys.modules["versioneer"]
        # this fixes the "python setup.py develop" case (also 'install' and
        # 'easy_install .'), in which subdependencies of the main project are
        # built (using setup.py bdist_egg) in the same python process. Assume
        # a main project A and a dependency B, which use different versions
        # of Versioneer. A's setup.py imports A's Versioneer, leaving it in
        # sys.modules by the time B's setup.py is executed, causing B to run
        # with the wrong versioneer. Setuptools wraps the sub-dep builds in a
        # sandbox that restores sys.modules to it's pre-build state, so the
        # parent is protected against the child's "import versioneer". By
        # removing ourselves from sys.modules here, before the child build
        # happens, we protect the child from the parent's versioneer too.
        # Also see https://github.com/python-versioneer/python-versioneer/issues/52

    cmds = {} if cmdclass is None else cmdclass.copy()

    # we override "build_py" in setuptools
    #
    # most invocation pathways end up running build_py:
    #  distutils/build -> build_py
    #  distutils/install -> distutils/build ->..
    #  setuptools/bdist_wheel -> distutils/install ->..
    #  setuptools/bdist_egg -> distutils/install_lib -> build_py
    #  setuptools/install -> bdist_egg ->..
    #  setuptools/develop -> ?
    #  pip install:
    #   copies source tree to a tempdir before running egg_info/etc
    #   if .git isn't copied too, 'git describe' will fail
    #   then does setup.py bdist_wheel, or sometimes setup.py install
    #  setup.py egg_info -> ?

    # pip install -e . and setuptool/editable_wheel will invoke build_py
    # but the build_py command is not expected to copy any files.

    # we override different "build_py" commands for both environments
    if "build_py" in cmds:
        _build_py = cmds["build_py"]
    else:
        from setuptools.command.build_py import build_py as _build_py

    class cmd_build_py(_build_py):
        def run(self):
            root = get_root()
            cfg = get_config_from_root(root)
            versions = get_versions()
            _build_py.run(self)
            if getattr(self, "editable_mode", False):
                # During editable installs `.py` and data files are
                # not copied to build_lib
                return
            # now locate _version.py in the new build/ directory and replace
            # it with an updated value
            if cfg.versionfile_build:
                target_versionfile = os.path.join(self.build_lib, cfg.versionfile_build)
                print("UPDATING %s" % target_versionfile)
                write_to_version_file(target_versionfile, versions)

    cmds["build_py"] = cmd_build_py

    return cmds