#!/bin/bash
# Initialize Let's Encrypt SSL for sorteio.overflowmvmt.com
# Run this ONCE on the VPS before starting docker compose

set -e

DOMAIN="sorteio.overflowmvmt.com"
EMAIL="admin@overflowmvmt.com"
CERT_DIR="/opt/apps/sorteios/certs"
APP_DIR="/opt/apps/sorteios/sorteios-prod"

echo "🔐 Initializing SSL certificate for $DOMAIN..."

# Create certificate directory
mkdir -p $CERT_DIR

# Check if certificate already exists
if [ -f "$CERT_DIR/fullchain.pem" ]; then
  echo "⚠️  Certificate already exists at $CERT_DIR"
  echo "To renew: certbot renew --force-renewal"
  exit 0
fi

# Install certbot if not present
if ! command -v certbot &> /dev/null; then
  echo "📥 Installing Certbot..."
  apt-get update
  apt-get install -y certbot
fi

# Obtain certificate (using standalone mode - make sure port 80 is free!)
echo "🔗 Requesting Let's Encrypt certificate for $DOMAIN..."
certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  --email $EMAIL \
  --preferred-challenges http \
  -d $DOMAIN

# Copy certificate to app directory
echo "📋 Copying certificates..."
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $CERT_DIR/
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $CERT_DIR/

# Set permissions
chmod 644 $CERT_DIR/fullchain.pem
chmod 644 $CERT_DIR/privkey.pem

# Setup auto-renewal hook
echo "🔄 Setting up auto-renewal hook..."
mkdir -p /etc/letsencrypt/renewal-hooks/post

cat > /etc/letsencrypt/renewal-hooks/post/docker-restart.sh << 'HOOK'
#!/bin/bash
APP_DIR="/opt/apps/sorteios/sorteios-prod"
CERT_DIR="/opt/apps/sorteios/certs"

if [ -d "$APP_DIR" ]; then
  # Copy new cert to app directory
  cp /etc/letsencrypt/live/sorteio.overflowmvmt.com/fullchain.pem $CERT_DIR/
  cp /etc/letsencrypt/live/sorteio.overflowmvmt.com/privkey.pem $CERT_DIR/
  
  # Restart nginx container
  cd $APP_DIR
  docker compose -f docker-compose.prod.yml restart nginx > /dev/null 2>&1 || true
  
  echo "[$(date)] Certificate renewed and nginx restarted" >> /var/log/certbot-renewal.log
fi
HOOK

chmod +x /etc/letsencrypt/renewal-hooks/post/docker-restart.sh

# Verify certificate
echo "✅ Certificate installed successfully!"
certbot certificates

# Show renewal schedule
echo ""
echo "📅 Auto-renewal will run: Twice daily (certbot timer)"
echo "Manual renewal: certbot renew --dry-run"
echo ""
echo "🎉 SSL setup complete! You can now start docker compose."
