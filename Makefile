# Builds the cvisgraph C backend and copies libcvisgraph.so into the
# package so pyvisgraph._clib finds it without any environment setup.
#
# CVISGRAPH_DIR points at the local cvisgraph checkout for now; eventually
# this will fetch/pin a cvisgraph release from GitHub instead.
CVISGRAPH_DIR ?= ../cvisgraph

.PHONY: cbackend test clean

cbackend:
	$(MAKE) -C $(CVISGRAPH_DIR)
	cp $(CVISGRAPH_DIR)/libcvisgraph.so pyvisgraph/

test: cbackend
	poetry run pytest tests/test_pvg.py tests/test_boundary_scenarios.py

clean:
	rm -f pyvisgraph/libcvisgraph.so
