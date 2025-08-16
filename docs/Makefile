# Makefile for Sphinx documentation

# You can set these variables from the command line.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Custom targets
.PHONY: clean
clean:
	rm -rf $(BUILDDIR)/*
	@echo "Build directory cleaned."

.PHONY: livehtml
livehtml:
	sphinx-autobuild -b html $(SOURCEDIR) $(BUILDDIR)/html \
		--watch ../PaperSorter \
		--ignore "*.pyc" \
		--ignore "*~" \
		--ignore ".*"

.PHONY: serve
serve: html
	@cd $(BUILDDIR)/html && python -m http.server 8000

.PHONY: github-pages
github-pages: clean html
	@touch $(BUILDDIR)/html/.nojekyll
	@echo "Documentation ready for GitHub Pages in $(BUILDDIR)/html"

.PHONY: check
check:
	@$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS) $(O)
	@$(SPHINXBUILD) -b doctest "$(SOURCEDIR)" "$(BUILDDIR)/doctest" $(SPHINXOPTS) $(O)
	@echo "All checks passed!"

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
