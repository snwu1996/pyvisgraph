"""ctypes bindings for libcvisgraph, the C backend of this branch.

The shared library is looked up, in order:

1. the CVISGRAPH_LIB environment variable (a path to the .so itself),
2. this package directory (where `make cbackend` copies it),
3. $CVISGRAPH_DIR/libcvisgraph.so,
4. the local cvisgraph checkout next to this repository
   (~/Projects/VisibilityGraphs/cvisgraph) -- for now the C library is
   consumed from that local folder; eventually this will resolve against
   a cvisgraph release fetched from GitHub instead,
5. the system library path.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os

_LIB_NAME = 'libcvisgraph.so'


def _candidates():
    yield os.environ.get('CVISGRAPH_LIB')
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    yield os.path.join(pkg_dir, _LIB_NAME)
    env_dir = os.environ.get('CVISGRAPH_DIR')
    if env_dir:
        yield os.path.join(env_dir, _LIB_NAME)
    # Sibling checkout of the cvisgraph repository (local for now, see
    # module docstring).
    repo_parent = os.path.dirname(os.path.dirname(pkg_dir))
    yield os.path.join(repo_parent, 'cvisgraph', _LIB_NAME)
    yield ctypes.util.find_library('cvisgraph')


def _load() -> ctypes.CDLL:
    errors = []
    for path in _candidates():
        if not path:
            continue
        try:
            return ctypes.CDLL(path)
        except OSError as exc:
            errors.append(f'{path}: {exc}')
    raise ImportError(
        'could not load libcvisgraph.so; run `make cbackend` in the '
        'repository root (or `make` in the cvisgraph checkout), or set '
        'CVISGRAPH_LIB/CVISGRAPH_DIR. Tried:\n  ' + '\n  '.join(errors))


lib = _load()

c_double = ctypes.c_double
c_int = ctypes.c_int
c_int32 = ctypes.c_int32
c_int64 = ctypes.c_int64
c_void_p = ctypes.c_void_p
c_double_p = ctypes.POINTER(c_double)
c_int32_p = ctypes.POINTER(c_int32)


class VisPt(ctypes.Structure):
    _fields_ = [('x', c_double), ('y', c_double), ('vertex', c_int32)]


PROGRESS_FN = ctypes.CFUNCTYPE(None, c_int32, c_int32, c_void_p)

_D = c_double

# Scalar geometry helpers.
lib.cvg_ccw.argtypes = [_D] * 6
lib.cvg_ccw.restype = c_int
lib.cvg_on_segment.argtypes = [_D] * 6
lib.cvg_on_segment.restype = c_int
lib.cvg_edge_intersect.argtypes = [_D] * 8
lib.cvg_edge_intersect.restype = c_int
lib.cvg_intersect_point.argtypes = [_D] * 8 + [c_double_p, c_double_p]
lib.cvg_intersect_point.restype = c_int
lib.cvg_point_edge_distance.argtypes = [_D] * 8
lib.cvg_point_edge_distance.restype = c_double
lib.cvg_edge_distance.argtypes = [_D] * 4
lib.cvg_edge_distance.restype = c_double
lib.cvg_angle.argtypes = [_D] * 4
lib.cvg_angle.restype = c_double
lib.cvg_angle2.argtypes = [_D] * 6
lib.cvg_angle2.restype = c_double

# Obstacle graph.
lib.cvg_graph_new.argtypes = [c_int32, c_double_p, c_int32, c_int32_p,
                              c_int32, c_int32_p, c_int32_p]
lib.cvg_graph_new.restype = c_void_p
lib.cvg_graph_free.argtypes = [c_void_p]
lib.cvg_graph_free.restype = None

lib.cvg_visible_from.argtypes = [c_void_p, _D, _D, c_double_p, c_double_p,
                                 c_int, ctypes.POINTER(ctypes.POINTER(VisPt))]
lib.cvg_visible_from.restype = c_int32

lib.cvg_build.argtypes = [c_void_p, c_int, PROGRESS_FN, c_void_p,
                          ctypes.POINTER(c_int32_p)]
lib.cvg_build.restype = c_int64

lib.cvg_polygon_crossing.argtypes = [c_void_p, c_int32, _D, _D]
lib.cvg_polygon_crossing.restype = c_int
lib.cvg_point_in_polygon.argtypes = [c_void_p, _D, _D]
lib.cvg_point_in_polygon.restype = c_int32
lib.cvg_point_in_solid.argtypes = [c_void_p, _D, _D]
lib.cvg_point_in_solid.restype = c_int
lib.cvg_closest_point.argtypes = [c_void_p, _D, _D, c_int32, _D,
                                  c_double_p, c_double_p]
lib.cvg_closest_point.restype = c_int

# Path graph.
lib.cvg_pathgraph_new.argtypes = [c_int32, c_double_p, c_int32, c_int32_p]
lib.cvg_pathgraph_new.restype = c_void_p
lib.cvg_pathgraph_free.argtypes = [c_void_p]
lib.cvg_pathgraph_free.restype = None
lib.cvg_pathgraph_find.argtypes = [c_void_p, _D, _D]
lib.cvg_pathgraph_find.restype = c_int32
lib.cvg_pathgraph_shortest.argtypes = [c_void_p, c_int32, c_int32, c_int32,
                                       c_double_p, c_int32, c_int32_p, c_int,
                                       ctypes.POINTER(c_int32_p)]
lib.cvg_pathgraph_shortest.restype = c_int32

lib.cvg_free.argtypes = [c_void_p]
lib.cvg_free.restype = None

NULL_PROGRESS = PROGRESS_FN()


def as_double_array(values) -> ctypes.Array:
    return (c_double * len(values))(*values)


def as_int32_array(values) -> ctypes.Array:
    return (c_int32 * len(values))(*values)
