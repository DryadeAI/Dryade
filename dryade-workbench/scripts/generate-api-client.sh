#!/bin/bash
# Generate TypeScript API client from backend OpenAPI spec
#
# This script exports the OpenAPI specification from the Dryade backend
# and generates a type-safe TypeScript client using openapi-generator.
#
# Usage:
#   npm run generate-api          # Generate from running backend
#   ./scripts/generate-api-client.sh  # Same, run directly
#
# Prerequisites:
#   - Backend server running at BACKEND_URL or http://localhost:8000
#   - npm packages installed (including devDependencies)
#
# Output:
#   - src/api/generated/  - Generated TypeScript client

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_ROOT="${BACKEND_ROOT:-$(dirname "$PROJECT_ROOT")}"
OUTPUT_DIR="${PROJECT_ROOT}/src/api/generated"
TEMP_SPEC="${PROJECT_ROOT}/openapi.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Clean previous generation
info "Cleaning previous generated client..."
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Export OpenAPI spec from backend
info "Exporting OpenAPI spec from backend..."

# Try to use the Python export script first (more reliable)
if [ -f "${BACKEND_ROOT}/scripts/export_openapi.py" ]; then
    info "Using backend export script..."
    cd "$BACKEND_ROOT"
    if [ -f ".venv/bin/python" ]; then
        .venv/bin/python scripts/export_openapi.py -o "$TEMP_SPEC" 2>/dev/null
    elif command -v python3 &> /dev/null; then
        python3 scripts/export_openapi.py -o "$TEMP_SPEC" 2>/dev/null
    else
        error "Python not found. Please install Python 3."
    fi
    cd "$PROJECT_ROOT"
else
    # Fallback: fetch from running backend
    BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
    info "Fetching OpenAPI spec from ${BACKEND_URL}/openapi.json..."

    if ! curl -sf "${BACKEND_URL}/openapi.json" -o "$TEMP_SPEC"; then
        error "Failed to fetch OpenAPI spec. Is the backend running at ${BACKEND_URL}?"
    fi
fi

# Verify spec was generated
if [ ! -f "$TEMP_SPEC" ] || [ ! -s "$TEMP_SPEC" ]; then
    error "OpenAPI spec not generated or empty"
fi

info "OpenAPI spec exported successfully"

# Generate TypeScript client
info "Generating TypeScript client..."

cd "$PROJECT_ROOT"

npx @openapitools/openapi-generator-cli generate \
    -i "$TEMP_SPEC" \
    -g typescript-fetch \
    -o "$OUTPUT_DIR" \
    --additional-properties=supportsES6=true,typescriptThreePlus=true,modelPropertyNaming=camelCase

# Clean up temp file
rm -f "$TEMP_SPEC"

# Generate index file for easier imports
info "Creating index exports..."
cat > "${OUTPUT_DIR}/index.ts" << 'EOF'
// Auto-generated API client
// DO NOT EDIT - regenerate with: npm run generate-api

export * from './apis';
export * from './models';
export * from './runtime';
EOF

info "API client generated successfully at ${OUTPUT_DIR}"
info ""
info "Usage in your code:"
info "  import { DefaultApi, Configuration } from '@/api/generated';"
info ""
info "  const config = new Configuration({ basePath: 'http://localhost:8000' });"
info "  const api = new DefaultApi(config);"
