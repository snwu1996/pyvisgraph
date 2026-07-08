# The cvisgraph C backend is a pinned git submodule (extern/cvisgraph).
# `poetry build`/`poetry install`/`pip install` run build.py, which compiles
# the submodule's C sources into pyvisgraph/libcvisgraph.so and bundles it into
# the wheel. These targets are convenience wrappers around that flow.

.PHONY: submodule cbackend test clean

# Check out (or update to) the pinned cvisgraph commit.
submodule:
	git submodule update --init --recursive

# Compile the C backend into the package via the Poetry build hook.
cbackend: submodule
	poetry install

test: cbackend
	poetry run pytest tests/test_pvg.py tests/test_boundary_scenarios.py

clean:
	rm -f pyvisgraph/libcvisgraph.so
	rm -rf build dist
