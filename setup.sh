#!/bin/bash

# =================================================================
# DecentraLabs Gateway - Full Version Setup Script (Linux/macOS)
# Complete blockchain-based authentication system with blockchain-services
# =================================================================

echo "DecentraLabs Gateway - Full Version Setup"
echo "=========================================="
echo

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Docker Compose is not installed."
    echo "   Visit: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "Docker and Docker Compose are available"
echo

# Check if .env already exists
if [ -f ".env" ]; then
    echo ".env file already exists!"
    read -p "Do you want to overwrite it? (y/N): " overwrite
    overwrite=$(echo "$overwrite" | tr -d ' ')
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 0
    fi
    # User said yes, so overwrite
    cp .env.example .env
    echo "Overwritten .env file from template"
else
    # No .env exists, create it
    cp .env.example .env
    echo "Created .env file from template"
fi
echo

# Database Passwords Configuration
echo
echo "Database Passwords"
echo "=================="
echo "Enter database passwords (leave empty for auto-generated):"
read -p "MySQL root password: " mysql_root_password
read -p "Guacamole database password: " mysql_password

if [ -z "$mysql_root_password" ]; then
    mysql_root_password="R00t_P@ss_${RANDOM}_$(date +%s)"
    echo "Generated root password: $mysql_root_password"
fi

if [ -z "$mysql_password" ]; then
    mysql_password="Gu@c_${RANDOM}_$(date +%s)"
    echo "Generated database password: $mysql_password"
fi

# Update passwords in .env file
sed -i "s/MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$mysql_root_password/" .env
sed -i "s/MYSQL_PASSWORD=.*/MYSQL_PASSWORD=$mysql_password/" .env

# Update Guacamole properties file to match the configuration in .env
echo "Updating Guacamole configuration..."
sed -i "s/mysql-password:.*/mysql-password: $mysql_password/" guacamole/guacamole.properties

echo
echo "IMPORTANT: Save these passwords securely!"
echo "   Root password: $mysql_root_password"
echo "   Database password: $mysql_password"
echo

# Domain Configuration
echo "Domain Configuration"
echo "===================="
echo "Enter your domain name (or press Enter for localhost):"
read -p "Domain: " domain
# Clean the domain variable and set default
domain=$(echo "$domain" | tr -d ' ')
if [ -z "$domain" ]; then
    domain="localhost"
fi

# Update .env file with intelligent defaults
if [ "$domain" == "localhost" ]; then
    echo "Configuring for local development..."
    sed -i 's/SERVER_NAME=.*/SERVER_NAME=localhost/' .env
    sed -i 's/BASE_DOMAIN=.*/BASE_DOMAIN=https:\/\/localhost/' .env
    sed -i 's/ISSUER=.*/ISSUER=https:\/\/localhost\/auth/' .env
    sed -i 's/HTTPS_PORT=.*/HTTPS_PORT=8443/' .env
    sed -i 's/HTTP_PORT=.*/HTTP_PORT=8080/' .env
    echo "   * Server: https://localhost:8443"
    echo "   * Using development ports (8443/8080)"
else
    echo "Configuring for production..."
    sed -i "s/SERVER_NAME=.*/SERVER_NAME=$domain/" .env
    sed -i "s/BASE_DOMAIN=.*/BASE_DOMAIN=https:\/\/$domain/" .env
    sed -i "s/ISSUER=.*/ISSUER=https:\/\/$domain\/auth/" .env
    sed -i 's/HTTPS_PORT=.*/HTTPS_PORT=443/' .env
    sed -i 's/HTTP_PORT=.*/HTTP_PORT=80/' .env
    echo "   * Server: https://$domain"
    echo "   * Using standard ports (443/80)"
fi

echo "To use different ports, edit HTTPS_PORT/HTTP_PORT in .env after setup"

echo
echo "SSL Certificates"
echo "================"

# Check certificates
if [ ! -d "certs" ]; then
    mkdir -p certs
fi

if [ ! -f "certs/fullchain.pem" ]; then
    echo "SSL certificates not found!"
    echo
    echo "You need to add SSL certificates to the 'certs' folder:"
    echo "  * certs/fullchain.pem (certificate)"
    echo "  * certs/privkey.pem (private key)"
    echo "  * certs/public_key.pem (blockchain-services public key)"
    echo
    if [ "$domain" == "localhost" ]; then
        echo "We will generate self-signed certificates for you..."
    else
        echo "You can get valid certificates from:"
        echo "  * Let's Encrypt (certbot)"
        echo "  * Your certificate authority"
        echo "  * Cloud provider (AWS ACM, etc.)"
    fi
else
    echo "SSL certificates found"
fi

echo
echo "Next Steps"
echo "=========="
echo "1. Review and customize .env file if needed"
echo "2. Ensure SSL certificates are in place"
echo "3. Configure blockchain settings in .env (CONTRACT_ADDRESS, WALLET_ADDRESS, INSTITUTIONAL_WALLET_*)"
echo "4. Run: docker-compose up -d"
if [ "$domain" == "localhost" ]; then
    echo "5. Access: https://localhost:8443"
else
    echo "5. Access: https://$domain"
fi
echo "   * Guacamole: /guacamole/"
echo "   * Blockchain Services API: /auth"
echo

# Ask if user wants to start services
read -p "Do you want to start the services now? (Y/n): " start_services
if [[ "$start_services" =~ ^[Nn]$ ]] || [[ "$start_services" =~ ^[Nn][Oo]$ ]]; then
    echo "Configuration complete!"
    echo
    echo "Next steps:"
echo "1. Configure blockchain settings in .env (CONTRACT_ADDRESS, WALLET_ADDRESS, INSTITUTIONAL_WALLET_*)"
    echo "2. Run: docker-compose up -d"
    echo "3. Access your services"
    echo
    echo "For more information, see README.md"
    echo "Setup complete!"
    exit 0
fi

echo
echo "Building and starting services..."
echo "This may take several minutes on first run..."

# Use appropriate docker-compose command
if command -v docker-compose &> /dev/null; then
    docker-compose down --remove-orphans
    docker-compose build --no-cache
    docker-compose up -d
    compose_result=$?
else
    docker compose down --remove-orphans
    docker compose build --no-cache
    docker compose up -d
    compose_result=$?
fi

if [ $compose_result -eq 0 ]; then
    echo
    echo "Services started successfully!"
    if [ "$domain" == "localhost" ]; then
        echo "Access your lab at: https://localhost:8443"
    else
        echo "Access your lab at: https://$domain"
    fi
    echo "   * Guacamole: /guacamole/ (guacadmin / guacadmin)"
    echo "   * Blockchain Services API: /auth"
    echo
    echo "To check status: docker-compose ps"
    echo "To view logs: docker-compose logs -f"
    echo
    echo "Configuration:"
    echo "   Environment: .env"
    echo "   Certificates: certs/"
    echo "   Blockchain Services Config: blockchain-services/src/main/resources/"
    echo
    echo "Full version deployment complete!"
    echo "Your blockchain-based authentication system is now running."
else
    echo "Failed to start services. Check the error messages above."
fi

echo
echo "For more information, see README.md"
echo "Setup complete!"
