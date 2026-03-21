#!/bin/bash
# Generate TLS certificates for PostgreSQL (Docker container SSL).
#
# Uses the existing Dryade local CA (from generate-web-certs.sh) to sign
# a server certificate for the PostgreSQL container.
#
# Certificates are written to ~/.dryade/certs/pg/ (or $DRYADE_PG_CERT_DIR).
# The key is generated with restricted permissions (0600) so PostgreSQL
# accepts it without complaint.
#
# Usage: ./scripts/generate-pg-certs.sh [--force]
#   --force: Regenerate even if certs are still valid

set -euo pipefail

CERT_DIR="${DRYADE_CERT_DIR:-$HOME/.dryade/certs}"
PG_CERT_DIR="${DRYADE_PG_CERT_DIR:-$CERT_DIR/pg}"
FORCE="${1:-}"
CA_KEY="$CERT_DIR/dryade-ca.key"
CA_CERT="$CERT_DIR/dryade-ca.pem"
PG_KEY="$PG_CERT_DIR/server.key"
PG_CERT="$PG_CERT_DIR/server.crt"
DAYS_CERT=825  # ~2 years

# Require existing CA
if [ ! -f "$CA_KEY" ] || [ ! -f "$CA_CERT" ]; then
  echo "[FATAL] CA not found. Run scripts/generate-web-certs.sh first."
  exit 1
fi

mkdir -p "$PG_CERT_DIR"

# Skip if certs exist and are still valid (>7 days remaining)
if [ "$FORCE" != "--force" ] && [ -f "$PG_CERT" ] && [ -f "$PG_KEY" ]; then
  if openssl x509 -checkend 604800 -noout -in "$PG_CERT" 2>/dev/null; then
    echo "PostgreSQL certs valid (expires in >7 days). Use --force to regenerate."
    exit 0
  fi
  echo "Existing PG cert expires within 7 days, regenerating..."
fi

echo "==> Generating PostgreSQL server certificate..."
openssl genrsa -out "$PG_KEY" 2048 2>/dev/null

TMPEXT=$(mktemp)
cat > "$TMPEXT" <<EOF
[req]
default_bits = 2048
prompt = no
distinguished_name = dn
req_extensions = v3_req

[dn]
CN = postgres
O = Dryade
OU = Database

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = postgres
DNS.2 = localhost
DNS.3 = deploy-postgres-1
IP.1 = 127.0.0.1
IP.2 = ::1

[v3_ext]
authorityKeyIdentifier = keyid,issuer
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:postgres, DNS:localhost, DNS:deploy-postgres-1, IP:127.0.0.1, IP:::1
EOF

openssl req -new -key "$PG_KEY" -out "$PG_CERT_DIR/server.csr" -config "$TMPEXT" 2>/dev/null
openssl x509 -req \
  -in "$PG_CERT_DIR/server.csr" \
  -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
  -out "$PG_CERT" \
  -days "$DAYS_CERT" \
  -extfile "$TMPEXT" -extensions v3_ext \
  2>/dev/null

# Copy CA cert for client verification
cp "$CA_CERT" "$PG_CERT_DIR/ca.crt"

# Cleanup temp files
rm -f "$TMPEXT" "$PG_CERT_DIR/server.csr" "$CERT_DIR/dryade-ca.srl"

# PostgreSQL requires key to be 0600 and owned by the postgres user.
# In Docker, the entrypoint init script handles ownership (chown to uid 70).
# On the host, just set restrictive permissions.
chmod 600 "$PG_KEY"
chmod 644 "$PG_CERT" "$PG_CERT_DIR/ca.crt"

echo ""
echo "PostgreSQL certificates generated:"
echo "  Server cert: $PG_CERT"
echo "  Server key:  $PG_KEY"
echo "  CA cert:     $PG_CERT_DIR/ca.crt"
echo ""
echo "Done. Restart the PostgreSQL container to use the new certificate."
