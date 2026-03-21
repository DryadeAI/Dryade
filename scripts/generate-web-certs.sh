#!/bin/bash
# Generate TLS certificates for Dryade local development (HTTPS).
#
# Creates a local CA + server certificate with SANs for localhost,
# dryade.local, and common local dev addresses.
#
# Certificates are written to ~/.dryade/certs/ (or $DRYADE_CERT_DIR).
# The CA cert must be imported into the browser once to trust the certs.
#
# Usage: ./scripts/generate-web-certs.sh [--force]
#   --force: Regenerate even if certs are still valid

set -euo pipefail

CERT_DIR="${DRYADE_CERT_DIR:-$HOME/.dryade/certs}"
FORCE="${1:-}"
CA_KEY="$CERT_DIR/dryade-ca.key"
CA_CERT="$CERT_DIR/dryade-ca.pem"
SERVER_KEY="$CERT_DIR/server.key"
SERVER_CERT="$CERT_DIR/server.pem"
DAYS_CA=3650    # CA valid 10 years
DAYS_CERT=825   # Server cert valid ~2 years (Apple max)

mkdir -p "$CERT_DIR"

# Skip if certs exist and are still valid (>7 days remaining)
if [ "$FORCE" != "--force" ] && [ -f "$SERVER_CERT" ] && [ -f "$SERVER_KEY" ] && [ -f "$CA_CERT" ]; then
  if openssl x509 -checkend 604800 -noout -in "$SERVER_CERT" 2>/dev/null; then
    echo "Web certs valid (expires in >7 days). Use --force to regenerate."
    exit 0
  fi
  echo "Existing cert expires within 7 days, regenerating..."
fi

echo "==> Generating Dryade local CA..."
openssl genrsa -out "$CA_KEY" 2048 2>/dev/null
openssl req -new -x509 -key "$CA_KEY" -out "$CA_CERT" \
  -days "$DAYS_CA" \
  -subj "/CN=Dryade Local CA/O=Dryade/OU=Development" \
  2>/dev/null

echo "==> Generating server certificate..."
openssl genrsa -out "$SERVER_KEY" 2048 2>/dev/null

# CSR + extensions in a single temp file
TMPEXT=$(mktemp)
cat > "$TMPEXT" <<EOF
[req]
default_bits = 2048
prompt = no
distinguished_name = dn
req_extensions = v3_req

[dn]
CN = localhost
O = Dryade
OU = Development

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
DNS.3 = dryade.local
DNS.4 = *.dryade.local
IP.1 = 127.0.0.1
IP.2 = ::1

[v3_ext]
authorityKeyIdentifier = keyid,issuer
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:localhost, DNS:*.localhost, DNS:dryade.local, DNS:*.dryade.local, IP:127.0.0.1, IP:::1
EOF

openssl req -new -key "$SERVER_KEY" -out "$CERT_DIR/server.csr" -config "$TMPEXT" 2>/dev/null
openssl x509 -req \
  -in "$CERT_DIR/server.csr" \
  -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
  -out "$SERVER_CERT" \
  -days "$DAYS_CERT" \
  -extfile "$TMPEXT" -extensions v3_ext \
  2>/dev/null

# Cleanup temp files
rm -f "$TMPEXT" "$CERT_DIR/server.csr" "$CERT_DIR/dryade-ca.srl"
chmod 600 "$CA_KEY" "$SERVER_KEY"
chmod 644 "$CA_CERT" "$SERVER_CERT"

echo ""
echo "Certificates generated:"
echo "  CA cert:     $CA_CERT"
echo "  Server cert: $SERVER_CERT"
echo "  Server key:  $SERVER_KEY"
echo ""

# Try to install CA into system trust store (needs sudo)
if command -v update-ca-certificates >/dev/null 2>&1; then
  SYS_CA="/usr/local/share/ca-certificates/dryade-ca.crt"
  if [ -w /usr/local/share/ca-certificates/ ] 2>/dev/null; then
    cp "$CA_CERT" "$SYS_CA"
    update-ca-certificates 2>/dev/null
    echo "CA installed into system trust store."
  else
    echo "To trust system-wide (requires sudo):"
    echo "  sudo cp $CA_CERT /usr/local/share/ca-certificates/dryade-ca.crt && sudo update-ca-certificates"
  fi
fi

# Try to install into Chrome/Chromium NSS database
NSSDB="$HOME/.pki/nssdb"
if command -v certutil >/dev/null 2>&1; then
  # Ensure NSS db exists and is valid
  if ! certutil -d "sql:$NSSDB" -L >/dev/null 2>&1; then
    rm -rf "$NSSDB"
    mkdir -p "$NSSDB"
    certutil -d "sql:$NSSDB" -N --empty-password 2>/dev/null
  fi
  certutil -d "sql:$NSSDB" -D -n "Dryade Local CA" 2>/dev/null || true
  certutil -d "sql:$NSSDB" -A -n "Dryade Local CA" -t "CT,C,C" -i "$CA_CERT" 2>/dev/null
  echo "CA installed into Chrome/Chromium trust store."
else
  echo "To trust in Chrome: install libnss3-tools (sudo apt install libnss3-tools) and re-run,"
  echo "  or import manually: Settings > Privacy > Security > Manage certificates > Authorities > Import"
  echo "  Select: $CA_CERT"
fi

echo ""
echo "Done. Restart the Vite dev server to use the new certificate."
