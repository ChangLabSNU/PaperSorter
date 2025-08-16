#!/bin/bash
# Build script for PaperSorter documentation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DOCS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${DOCS_DIR}/_build"
PROJECT_ROOT="$(dirname "$DOCS_DIR")"

# Functions
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check dependencies
check_dependencies() {
    echo "Checking dependencies..."
    
    if ! command -v sphinx-build &> /dev/null; then
        print_error "Sphinx not found. Installing..."
        pip install -r "${DOCS_DIR}/requirements.txt"
    fi
    
    print_status "Dependencies OK"
}

# Clean build directory
clean_build() {
    echo "Cleaning build directory..."
    rm -rf "${BUILD_DIR}"
    print_status "Build directory cleaned"
}

# Build HTML documentation
build_html() {
    echo "Building HTML documentation..."
    cd "${DOCS_DIR}"
    sphinx-build -b html . "${BUILD_DIR}/html" -W --keep-going
    print_status "HTML documentation built"
}

# Check for broken links
check_links() {
    echo "Checking for broken links..."
    cd "${DOCS_DIR}"
    if sphinx-build -b linkcheck . "${BUILD_DIR}/linkcheck" 2>/dev/null; then
        print_status "No broken links found"
    else
        print_warning "Some broken links detected (see ${BUILD_DIR}/linkcheck/output.txt)"
    fi
}

# Build PDF documentation
build_pdf() {
    echo "Building PDF documentation..."
    cd "${DOCS_DIR}"
    
    if ! command -v latexmk &> /dev/null; then
        print_warning "latexmk not found, skipping PDF build"
        return
    fi
    
    sphinx-build -b latex . "${BUILD_DIR}/latex"
    cd "${BUILD_DIR}/latex"
    make
    print_status "PDF documentation built"
}

# Serve documentation locally
serve_docs() {
    echo "Serving documentation at http://localhost:8000"
    cd "${BUILD_DIR}/html"
    python -m http.server 8000
}

# Live reload for development
live_reload() {
    echo "Starting live reload server..."
    cd "${DOCS_DIR}"
    sphinx-autobuild . "${BUILD_DIR}/html" \
        --watch "${PROJECT_ROOT}/PaperSorter" \
        --ignore "*.pyc" \
        --ignore "*~" \
        --port 8000
}

# Deploy to GitHub Pages
deploy_github() {
    echo "Preparing for GitHub Pages deployment..."
    
    # Ensure we're on main branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$current_branch" != "main" ]; then
        print_error "Must be on main branch to deploy (currently on $current_branch)"
        exit 1
    fi
    
    # Build fresh documentation
    clean_build
    build_html
    
    # Add .nojekyll file for GitHub Pages
    touch "${BUILD_DIR}/html/.nojekyll"
    
    # Create or switch to gh-pages branch
    if git show-ref --verify --quiet refs/heads/gh-pages; then
        git checkout gh-pages
    else
        git checkout --orphan gh-pages
    fi
    
    # Copy documentation
    cp -r "${BUILD_DIR}/html/"* .
    
    # Commit and push
    git add -A
    git commit -m "Update documentation $(date +%Y-%m-%d)"
    git push origin gh-pages
    
    # Switch back to main
    git checkout main
    
    print_status "Documentation deployed to GitHub Pages"
}

# Main script
main() {
    case "${1:-}" in
        clean)
            clean_build
            ;;
        html)
            check_dependencies
            build_html
            ;;
        pdf)
            check_dependencies
            build_pdf
            ;;
        linkcheck)
            check_dependencies
            check_links
            ;;
        serve)
            check_dependencies
            build_html
            serve_docs
            ;;
        live)
            check_dependencies
            live_reload
            ;;
        deploy)
            check_dependencies
            deploy_github
            ;;
        all)
            check_dependencies
            clean_build
            build_html
            check_links
            build_pdf
            ;;
        *)
            echo "PaperSorter Documentation Builder"
            echo ""
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  clean      - Clean build directory"
            echo "  html       - Build HTML documentation"
            echo "  pdf        - Build PDF documentation"
            echo "  linkcheck  - Check for broken links"
            echo "  serve      - Serve documentation locally"
            echo "  live       - Live reload for development"
            echo "  deploy     - Deploy to GitHub Pages"
            echo "  all        - Build everything"
            echo ""
            echo "Default: html"
            
            # Default action
            check_dependencies
            build_html
            ;;
    esac
}

# Run main function
main "$@"