"""Poetry build hook: compile the cvisgraph C backend into the package.

`poetry build` / `poetry install` / `pip install` run this to compile the C
sources of the pinned `extern/cvisgraph` submodule into
`pyvisgraph/libcvisgraph.so`, a plain shared library that `pyvisgraph/_clib.py`
loads via ctypes. Building through a setuptools ``Extension`` (rather than
shelling out to the submodule's Makefile) makes Poetry mark the resulting wheel
as platform-specific, which is correct for a wheel that carries a native binary.

The extension is emitted as ``libcvisgraph.so`` (no CPython ABI tag) so ctypes
finds it by name; see ``CTypesBuildExt`` below.

If the submodule is missing (e.g. a checkout without
``git submodule update --init``), the build fails with an actionable message
rather than producing a wheel with no backend.
"""
from __future__ import annotations

import os
import sysconfig
from glob import glob

from setuptools import Extension
from setuptools.command.build_ext import build_ext

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSRC = os.path.join(_HERE, "extern", "cvisgraph")


class CTypesBuildExt(build_ext):
    """Build the C sources as a ctypes library, not a CPython extension.

    Overrides the two setuptools assumptions that only hold for real
    extension modules: that the shared object exports ``PyInit_<name>`` and
    that its filename carries the interpreter's ABI tag.
    """

    def get_export_symbols(self, ext):  # noqa: D102 - no PyInit_ symbol
        return ext.export_symbols

    def get_ext_filename(self, fullname):
        # Default is e.g. pyvisgraph/libcvisgraph.cpython-312-x86_64-linux-gnu.so;
        # strip the ABI suffix down to a plain ".so" that ctypes loads by name.
        filename = super().get_ext_filename(fullname)
        ext_suffix = sysconfig.get_config_var("EXT_SUFFIX")
        if ext_suffix and filename.endswith(ext_suffix):
            filename = filename[: -len(ext_suffix)] + ".so"
        return filename


def _extension() -> Extension:
    sources = sorted(glob(os.path.join(_CSRC, "src", "*.c")))
    if not sources:
        raise RuntimeError(
            "cvisgraph C sources not found under extern/cvisgraph/src. The "
            "submodule is not checked out; run `git submodule update --init "
            "--recursive` (or clone with `--recurse-submodules`) and rebuild."
        )
    return Extension(
        name="pyvisgraph.libcvisgraph",
        sources=sources,
        include_dirs=[os.path.join(_CSRC, "include")],
        libraries=["m", "pthread"],
        extra_compile_args=["-O3", "-std=gnu11", "-Wall", "-Wextra"],
    )


def build(setup_kwargs: dict) -> None:
    """Entry point Poetry calls with the setuptools keyword arguments."""
    setup_kwargs.update(
        ext_modules=[_extension()],
        cmdclass={"build_ext": CTypesBuildExt},
    )
