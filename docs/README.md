# PaperSorter Documentation

This directory contains the Sphinx-based documentation for PaperSorter.

## Quick Start

### Prerequisites

Install the documentation dependencies:

```bash
pip install -r requirements.txt
```

### Building Documentation

#### Build HTML Documentation

```bash
make html
```

The built documentation will be in `_build/html/`. Open `_build/html/index.html` in your browser to view it.

#### Live Development Server

For development with automatic rebuilds:

```bash
make livehtml
```

This will start a server at http://localhost:8000 that automatically rebuilds when you make changes.

### Alternative Build Methods

Using the build script:

```bash
./build.sh html     # Build HTML
./build.sh serve    # Build and serve locally
./build.sh live     # Live reload for development
./build.sh all      # Build everything (HTML, PDF, check links)
```

Using Sphinx directly:

```bash
sphinx-build -b html . _build/html
```

## Documentation Structure

```
docs/
├── getting-started/    # Quick start guides for new users
├── user-guide/         # Detailed user documentation
├── admin-guide/        # System administration guides
├── cli-reference/      # Command-line interface documentation
├── api/                # API documentation (auto-generated)
├── development/        # Developer guides
├── tutorials/          # Step-by-step tutorials
├── reference/          # Reference materials
├── conf.py            # Sphinx configuration
├── index.rst          # Main documentation entry point
├── requirements.txt   # Documentation dependencies
└── build.sh           # Build automation script
```

## Contributing to Documentation

1. **Edit Markdown/RST Files**: Most documentation is in Markdown format for easy editing
2. **API Documentation**: Update docstrings in Python code; they're auto-included
3. **Build Locally**: Always build and preview your changes before submitting
4. **Check Links**: Run `make linkcheck` to verify all links work

## Deployment

### GitHub Pages

The documentation is automatically deployed to GitHub Pages when changes are pushed to the main branch:

1. GitHub Actions builds the documentation
2. Deploys to the `gh-pages` branch
3. Available at: https://yourusername.github.io/papersorter/

### Manual Deployment

```bash
./build.sh deploy
```

## Troubleshooting

### Common Issues

**Import Errors in API Documentation**
- Ensure PaperSorter is installed: `pip install -e ..`
- Check that all dependencies are installed

**Broken Links**
- Run `make linkcheck` to identify broken links
- Fix references in the source files

**Build Warnings**
- Missing toctree references: Create the missing files or remove references
- Duplicate descriptions: Add `:no-index:` directive to one instance

## Documentation Standards

- Use **Markdown** for general documentation
- Use **reStructuredText** for complex formatting and directives
- Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) for docstrings
- Include code examples wherever possible
- Keep line length under 100 characters for better readability

## License

The documentation is licensed under the same terms as PaperSorter (MIT License).