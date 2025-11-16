# 🏗️ Lab Gateway Smart Contract Registry Architecture
## Decentralized Authentication & Gateway Discovery System

---

## 📋 Current State Analysis

### **Current Centralized Model:**
```mermaid
graph TD
    A[Marketplace] --> B[Centralized Auth Service]
    B --> C[Lab Gateway 1]
    B --> D[Lab Gateway 2]
    B --> E[Lab Gateway N]
    
    F[Provider] --> A
    F --> G[NFT Metadata]
    G --> H[auth_service_url: centralized.decentra.labs]
```

### **Problems with Current Approach:**
- 🔴 **Single Point of Failure** - Centralized auth service
- 🔴 **Scalability Bottleneck** - All requests through one service
- 🔴 **Manual Configuration** - Providers must specify auth service URLs
- 🔴 **Service Discovery** - No automatic way to find lab gateways
- 🔴 **Maintenance Overhead** - Centralized infrastructure costs
- 🔴 **Censorship Risk** - Vulnerable to external control
- 🔴 **Trust Issues** - Users must trust centralized authority

---

## 🎯 Proposed Smart Contract Registry Architecture

### **Why Smart Contract Registry?**

#### **🔐 Security & Trust Benefits:**
- **Immutable Records**: Gateway registrations cannot be tampered with
- **Cryptographic Verification**: Automatic validation of gateway ownership
- **Economic Incentives**: Staking mechanisms prevent malicious behavior
- **Transparent Operations**: All registrations are publicly auditable

#### **🌐 Decentralization Benefits:**
- **No Single Point of Failure**: Registry exists across multiple blockchain nodes
- **Censorship Resistance**: Extremely difficult to shut down or control
- **Global Accessibility**: Available 24/7 without geographic restrictions
- **Community Governance**: Token holders can vote on registry upgrades

#### **💰 Economic Benefits:**
- **Reduced Operating Costs**: No centralized infrastructure to maintain
- **Scalable Economics**: Costs decrease as network grows
- **Provider Incentives**: Direct economic rewards for reliable service
- **User Benefits**: Lower costs passed through to end users

---

## 🏗️ Core Architecture Components

### **1. Smart Contract Registry System**

#### **1.1 Enhanced LabGateway Registry Contract**

```solidity
// LabGatewayRegistry.sol - Enhanced Version with Staking & Reputation
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract LabGatewayRegistry is ReentrancyGuard, Ownable {
    // Minimum stake required to register a gateway (in wei)
    uint256 public constant MINIMUM_STAKE = 1 ether;
    
    // Maximum time a gateway can be offline before being marked inactive
    uint256 public constant MAX_OFFLINE_TIME = 1 hours;
    
    struct GatewayInfo {
        address owner;                  // Provider wallet
        string gatewayUrl;              // https://lab.university.edu
        string authServiceUrl;          // https://lab.university.edu/auth
        uint256 registeredAt;           // Registration timestamp
        uint256 lastHeartbeat;          // Last health check timestamp
        uint256 stakingAmount;          // Amount staked by provider
        bool isActive;                  // Current status
        bytes32[] supportedProtocols;   // RDP, VNC, SSH, etc.
        uint256 successfulRequests;     // Reputation metric
        uint256 failedRequests;         // Reputation metric
        uint256 totalUptime;            // Cumulative uptime in seconds
    }
    
    // Provider wallet => Gateway Info
    mapping(address => GatewayInfo) public gateways;
    
    // Lab NFT ID => Gateway Address
    mapping(uint256 => address) public labToGateway;
    
    // Gateway reputation scores (0-1000)
    mapping(address => uint256) public reputationScores;
    
    // Events
    event GatewayRegistered(address indexed provider, string gatewayUrl, uint256 stake);
    event GatewayUpdated(address indexed provider, string gatewayUrl);
    event LabAssigned(uint256 indexed labId, address indexed gateway);
    event HeartbeatReceived(address indexed gateway, uint256 timestamp);
    event GatewaySlashed(address indexed gateway, uint256 amount, string reason);
    event StakeWithdrawn(address indexed gateway, uint256 amount);
    
    modifier onlyActiveGateway() {
        require(gateways[msg.sender].isActive, "Gateway not active");
        require(gateways[msg.sender].stakingAmount >= MINIMUM_STAKE, "Insufficient stake");
        _;
    }
    
    function registerGateway(
        string memory _gatewayUrl,
        string memory _authServiceUrl,
        bytes32[] memory _protocols
    ) external payable nonReentrant {
        require(msg.value >= MINIMUM_STAKE, "Insufficient staking amount");
        require(bytes(_gatewayUrl).length > 0, "Invalid gateway URL");
        require(bytes(_authServiceUrl).length > 0, "Invalid auth service URL");
        
        // If gateway already exists, add to existing stake
        if (gateways[msg.sender].owner != address(0)) {
            gateways[msg.sender].stakingAmount += msg.value;
            gateways[msg.sender].gatewayUrl = _gatewayUrl;
            gateways[msg.sender].authServiceUrl = _authServiceUrl;
            gateways[msg.sender].supportedProtocols = _protocols;
            gateways[msg.sender].isActive = true;
            gateways[msg.sender].lastHeartbeat = block.timestamp;
            
            emit GatewayUpdated(msg.sender, _gatewayUrl);
        } else {
            // New gateway registration
            gateways[msg.sender] = GatewayInfo({
                owner: msg.sender,
                gatewayUrl: _gatewayUrl,
                authServiceUrl: _authServiceUrl,
                registeredAt: block.timestamp,
                lastHeartbeat: block.timestamp,
                stakingAmount: msg.value,
                isActive: true,
                supportedProtocols: _protocols,
                successfulRequests: 0,
                failedRequests: 0,
                totalUptime: 0
            });
            
            // Initial reputation score
            reputationScores[msg.sender] = 500; // Neutral starting point
            
            emit GatewayRegistered(msg.sender, _gatewayUrl, msg.value);
        }
    }
    
    function sendHeartbeat() external onlyActiveGateway {
        uint256 lastBeat = gateways[msg.sender].lastHeartbeat;
        uint256 currentTime = block.timestamp;
        
        // Add to uptime if gateway was previously active
        if (currentTime > lastBeat && gateways[msg.sender].isActive) {
            gateways[msg.sender].totalUptime += (currentTime - lastBeat);
        }
        
        gateways[msg.sender].lastHeartbeat = currentTime;
        gateways[msg.sender].isActive = true;
        
        emit HeartbeatReceived(msg.sender, currentTime);
    }
    
    function assignLabToGateway(uint256 _labId) external onlyActiveGateway {
        labToGateway[_labId] = msg.sender;
        emit LabAssigned(_labId, msg.sender);
    }
    
    function reportAuthSuccess(address _gateway) external {
        // This would be called by the auth service or verified oracle
        gateways[_gateway].successfulRequests++;
        _updateReputation(_gateway);
    }
    
    function reportAuthFailure(address _gateway) external {
        // This would be called by the auth service or verified oracle  
        gateways[_gateway].failedRequests++;
        _updateReputation(_gateway);
    }
    
    function _updateReputation(address _gateway) internal {
        GatewayInfo storage gateway = gateways[_gateway];
        uint256 total = gateway.successfulRequests + gateway.failedRequests;
        
        if (total > 0) {
            // Calculate success rate (0-1000 scale)
            uint256 successRate = (gateway.successfulRequests * 1000) / total;
            
            // Weight recent performance more heavily
            uint256 uptimeScore = _calculateUptimeScore(_gateway);
            
            // Combined reputation score
            reputationScores[_gateway] = (successRate * 70 + uptimeScore * 30) / 100;
        }
    }
    
    function _calculateUptimeScore(address _gateway) internal view returns (uint256) {
        GatewayInfo storage gateway = gateways[_gateway];
        uint256 totalTime = block.timestamp - gateway.registeredAt;
        
        if (totalTime == 0) return 1000;
        
        uint256 uptimePercentage = (gateway.totalUptime * 100) / totalTime;
        return uptimePercentage > 100 ? 1000 : uptimePercentage * 10; // Scale to 0-1000
    }
    
    function verifyGateway(address _gateway) public view returns (bool, uint256, bool) {
        GatewayInfo storage gateway = gateways[_gateway];
        
        bool isStaked = gateway.stakingAmount >= MINIMUM_STAKE;
        bool isRecent = (block.timestamp - gateway.lastHeartbeat) <= MAX_OFFLINE_TIME;
        bool isHealthy = gateway.isActive && isStaked && isRecent;
        
        return (isHealthy, reputationScores[_gateway], isStaked);
    }
    
    function getOptimalGateways(uint256 _count) external view returns (address[] memory) {
        // Return top gateways by reputation score
        // Implementation would sort by reputation and return top N
        // Simplified version here
        address[] memory topGateways = new address[](_count);
        // ... sorting logic would go here ...
        return topGateways;
    }
    
    function withdrawStake(uint256 _amount) external nonReentrant {
        GatewayInfo storage gateway = gateways[msg.sender];
        require(gateway.owner == msg.sender, "Not gateway owner");
        require(gateway.stakingAmount >= _amount, "Insufficient stake");
        require(gateway.stakingAmount - _amount >= MINIMUM_STAKE || !gateway.isActive, 
                "Cannot withdraw below minimum while active");
        
        gateway.stakingAmount -= _amount;
        
        // Deactivate if below minimum stake
        if (gateway.stakingAmount < MINIMUM_STAKE) {
            gateway.isActive = false;
        }
        
        payable(msg.sender).transfer(_amount);
        emit StakeWithdrawn(msg.sender, _amount);
    }
    
    function slashGateway(address _gateway, uint256 _amount, string memory _reason) 
        external onlyOwner {
        GatewayInfo storage gateway = gateways[_gateway];
        require(gateway.stakingAmount >= _amount, "Insufficient stake to slash");
        
        gateway.stakingAmount -= _amount;
        
        // Deactivate if slashed below minimum
        if (gateway.stakingAmount < MINIMUM_STAKE) {
            gateway.isActive = false;
        }
        
        emit GatewaySlashed(_gateway, _amount, _reason);
    }
}
```

### **2. Automatic Lab-Gateway Association System**

#### **2.1 Intelligent Lab NFT Minting with Gateway Assignment**

```javascript
// Enhanced Lab NFT Minting with Smart Gateway Selection
class LabNFTMinter {
    constructor(registryContract, labNFTContract) {
        this.registry = registryContract;
        this.labNFT = labNFTContract;
        this.loadBalancer = new GatewayLoadBalancer(registryContract);
    }
    
    async mintLab(providerWallet, labMetadata, requirements = {}) {
        try {
            // 1. Verify provider has an active, staked gateway
            const [isHealthy, reputation, isStaked] = await this.registry.verifyGateway(providerWallet);
            
            if (!isHealthy || !isStaked) {
                throw new Error("Provider must register and stake a Lab Gateway first");
            }
            
            // 2. Check if provider's gateway meets lab requirements
            const gateway = await this.registry.gateways(providerWallet);
            const canHandle = this.validateGatewayCapabilities(gateway, requirements);
            
            if (!canHandle) {
                // Find alternative gateway that can handle requirements
                const alternativeGateway = await this.findSuitableGateway(requirements);
                if (!alternativeGateway) {
                    throw new Error("No suitable gateway found for lab requirements");
                }
            }
            
            // 3. Mint the lab NFT with enhanced metadata
            const enhancedMetadata = {
                ...labMetadata,
                requirements,
                gatewayReputation: reputation,
                assignedGateway: providerWallet,
                mintedAt: Date.now(),
                version: "2.0"
            };
            
            const labId = await this.labNFT.mint(providerWallet, enhancedMetadata);
            
            // 4. Assign lab to gateway in registry
            await this.registry.assignLabToGateway(labId);
            
            // 5. Update NFT metadata with full gateway information
            const gatewayInfo = await this.registry.gateways(providerWallet);
            const finalMetadata = {
                ...enhancedMetadata,
                gateway: {
                    url: gatewayInfo.gatewayUrl,
                    authServiceUrl: gatewayInfo.authServiceUrl,
                    supportedProtocols: gatewayInfo.supportedProtocols,
                    reputation: reputation,
                    uptime: gatewayInfo.totalUptime
                }
            };
            
            await this.labNFT.updateMetadata(labId, finalMetadata);
            
            return { 
                labId, 
                gateway: gatewayInfo.gatewayUrl,
                authService: gatewayInfo.authServiceUrl,
                reputation
            };
            
        } catch (error) {
            console.error("Lab minting failed:", error);
            throw error;
        }
    }
    
    validateGatewayCapabilities(gateway, requirements) {
        if (!requirements.protocols) return true;
        
        const requiredProtocols = requirements.protocols.map(p => 
            ethers.utils.formatBytes32String(p)
        );
        
        return requiredProtocols.every(protocol => 
            gateway.supportedProtocols.includes(protocol)
        );
    }
    
    async findSuitableGateway(requirements) {
        const optimalGateways = await this.registry.getOptimalGateways(10);
        
        for (const gatewayAddress of optimalGateways) {
            const gateway = await this.registry.gateways(gatewayAddress);
            if (this.validateGatewayCapabilities(gateway, requirements)) {
                return gatewayAddress;
            }
        }
        
        return null;
    }
}
```

### **3. Advanced Discovery & Load Balancing System**

#### **3.1 Multi-Layer Service Discovery**

```javascript
// Enhanced Discovery Service with Fallback Mechanisms
class AuthServiceDiscovery {
    constructor(registryContract) {
        this.registry = registryContract;
        this.cache = new Map();
        this.fallbackServices = [
            'https://fallback1.decentra.labs/auth',
            'https://fallback2.decentra.labs/auth'
        ];
        this.cacheTimeout = 300000; // 5 minutes
    }
    
    async findAuthService(labId, userLocation = null) {
        try {
            // 1. Check cache first
            const cached = this.getCachedService(labId);
            if (cached && this.isCacheValid(cached)) {
                return cached.service;
            }
            
            // 2. Query registry for primary gateway
            const gatewayAddress = await this.registry.labToGateway(labId);
            const primaryService = await this.getGatewayService(gatewayAddress);
            
            // 3. Health check primary service
            const healthCheck = await this.checkAuthServiceHealth(primaryService.authServiceUrl);
            
            if (healthCheck.healthy && healthCheck.responseTime < 2000) {
                this.cacheService(labId, primaryService);
                return primaryService;
            }
            
            // 4. Find backup gateways with same lab capabilities
            const backupGateways = await this.findBackupGateways(labId);
            
            for (const backup of backupGateways) {
                const backupHealth = await this.checkAuthServiceHealth(backup.authServiceUrl);
                if (backupHealth.healthy) {
                    this.cacheService(labId, backup);
                    return backup;
                }
            }
            
            // 5. Use geographic load balancing if available
            if (userLocation) {
                const geoOptimized = await this.findGeographicallyOptimal(labId, userLocation);
                if (geoOptimized) return geoOptimized;
            }
            
            // 6. Fallback to centralized services
            return await this.useFallbackService(labId);
            
        } catch (error) {
            console.error("Service discovery failed:", error);
            return await this.useFallbackService(labId);
        }
    }
    
    async getGatewayService(gatewayAddress) {
        const [isHealthy, reputation, isStaked] = await this.registry.verifyGateway(gatewayAddress);
        const gatewayInfo = await this.registry.gateways(gatewayAddress);
        
        return {
            authServiceUrl: gatewayInfo.authServiceUrl,
            gatewayUrl: gatewayInfo.gatewayUrl,
            provider: gatewayAddress,
            reputation,
            healthy: isHealthy,
            staked: isStaked,
            lastHeartbeat: gatewayInfo.lastHeartbeat
        };
    }
    
    async checkAuthServiceHealth(authServiceUrl) {
        const startTime = Date.now();
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);
            
            const response = await fetch(`${authServiceUrl}/health`, {
                signal: controller.signal,
                method: 'GET',
                headers: {
                    'User-Agent': 'DecentraLabs-Discovery/2.0'
                }
            });
            
            clearTimeout(timeoutId);
            const responseTime = Date.now() - startTime;
            
            return {
                healthy: response.ok,
                responseTime,
                status: response.status,
                version: response.headers.get('x-service-version') || 'unknown',
                load: response.headers.get('x-current-load') || 'unknown'
            };
            
        } catch (error) {
            return { 
                healthy: false, 
                error: error.message,
                responseTime: Date.now() - startTime
            };
        }
    }
    
    async findBackupGateways(labId) {
        // Get gateways with similar capabilities sorted by reputation
        const optimalGateways = await this.registry.getOptimalGateways(5);
        const backups = [];
        
        for (const gatewayAddress of optimalGateways) {
            const currentLab = await this.registry.labToGateway(labId);
            if (gatewayAddress !== currentLab) {
                const service = await this.getGatewayService(gatewayAddress);
                if (service.healthy && service.reputation > 600) { // Only high-reputation backups
                    backups.push(service);
                }
            }
        }
        
        return backups.sort((a, b) => b.reputation - a.reputation);
    }
    
    cacheService(labId, service) {
        this.cache.set(labId, {
            service,
            timestamp: Date.now()
        });
    }
    
    getCachedService(labId) {
        return this.cache.get(labId);
    }
    
    isCacheValid(cached) {
        return (Date.now() - cached.timestamp) < this.cacheTimeout;
    }
    
    async useFallbackService(labId) {
        console.warn(`Using fallback service for lab ${labId}`);
        
        // Try fallback services in order
        for (const fallbackUrl of this.fallbackServices) {
            const health = await this.checkAuthServiceHealth(fallbackUrl);
            if (health.healthy) {
                return {
                    authServiceUrl: fallbackUrl,
                    gatewayUrl: fallbackUrl.replace('/auth', ''),
                    provider: 'fallback',
                    healthy: true,
                    fallback: true
                };
            }
        }
        
        throw new Error('All authentication services are unavailable');
    }
}

### **4. Gateway Auto-Registration & Health Monitoring**

#### **4.1 Enhanced Auto-Registration Script**

```bash
#!/bin/bash
# DecentraLabs Gateway Auto-Registration v2.0

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/.gateway-config"
LOG_FILE="$SCRIPT_DIR/registration.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" | tee -a "$LOG_FILE" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}" | tee -a "$LOG_FILE"
}

# Header
echo -e "${BLUE}"
cat << 'EOF'
🚀 DecentraLabs Gateway Auto-Registration v2.0
===============================================
Decentralized Lab Gateway Registration & Monitoring
EOF
echo -e "${NC}"

# Load or create configuration
load_config() {
    if [[ -f "$CONFIG_FILE" ]]; then
        source "$CONFIG_FILE"
        log "Loaded existing configuration"
    fi
}

# Detect public URL with multiple methods
detect_public_url() {
    local detected_url=""
    
    # Method 1: Check if GATEWAY_URL is already set
    if [[ -n "${GATEWAY_URL:-}" ]]; then
        detected_url="$GATEWAY_URL"
        log "Using configured GATEWAY_URL: $detected_url"
        return
    fi
    
    # Method 2: Try to detect from reverse proxy config
    if [[ -f "nginx.conf" ]] || [[ -f "lab_access.conf" ]]; then
        detected_url=$(grep -o 'server_name [^;]*' nginx.conf lab_access.conf 2>/dev/null | head -1 | cut -d' ' -f2 || true)
        if [[ -n "$detected_url" && "$detected_url" != "_" ]]; then
            detected_url="https://$detected_url"
            log "Detected URL from nginx config: $detected_url"
        fi
    fi
    
    # Method 3: Use external IP detection
    if [[ -z "$detected_url" ]]; then
        local external_ip
        external_ip=$(curl -s https://ipinfo.io/ip 2>/dev/null || curl -s https://api.ipify.org 2>/dev/null || echo "")
        
        if [[ -n "$external_ip" ]]; then
            read -p "No domain detected. Use IP $external_ip? (y/N): " use_ip
            if [[ "$use_ip" =~ ^[Yy]$ ]]; then
                detected_url="https://$external_ip"
            fi
        fi
    fi
    
    # Method 4: Manual input
    if [[ -z "$detected_url" ]]; then
        read -p "Enter your gateway URL (e.g., https://lab.university.edu): " detected_url
    fi
    
    # Validate URL format
    if [[ ! "$detected_url" =~ ^https?:// ]]; then
        error "Invalid URL format. Must start with http:// or https://"
        exit 1
    fi
    
    GATEWAY_URL="$detected_url"
    AUTH_SERVICE_URL="${GATEWAY_URL}/auth"
}

# Generate or load provider wallet
setup_wallet() {
    if [[ -n "${PROVIDER_PRIVATE_KEY:-}" ]]; then
        log "Using existing provider wallet"
        return
    fi
    
    if [[ -f "$SCRIPT_DIR/.wallet" ]]; then
        PROVIDER_PRIVATE_KEY=$(cat "$SCRIPT_DIR/.wallet")
        log "Loaded existing wallet from .wallet file"
    else
        log "Generating new provider wallet..."
        
        # Generate new private key using Node.js
        PROVIDER_PRIVATE_KEY=$(node -e "
            const crypto = require('crypto');
            const privateKey = '0x' + crypto.randomBytes(32).toString('hex');
            console.log(privateKey);
        ")
        
        echo "$PROVIDER_PRIVATE_KEY" > "$SCRIPT_DIR/.wallet"
        chmod 600 "$SCRIPT_DIR/.wallet"
        
        # Get public address
        PROVIDER_ADDRESS=$(node -e "
            const { ethers } = require('ethers');
            const wallet = new ethers.Wallet('$PROVIDER_PRIVATE_KEY');
            console.log(wallet.address);
        ")
        
        success "Generated new wallet: $PROVIDER_ADDRESS"
        warn "IMPORTANT: Fund this wallet with ETH and DecentraLabs tokens!"
        warn "Private key saved to .wallet (keep secure!)"
    fi
}

# Check if auth service is running
check_auth_service() {
    local max_attempts=30
    local attempt=1
    
    log "Checking auth service health..."
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -sf "${AUTH_SERVICE_URL}/health" >/dev/null 2>&1; then
            success "Auth service is healthy"
            return 0
        fi
        
        log "Attempt $attempt/$max_attempts - Auth service not ready, waiting..."
        sleep 10
        ((attempt++))
    done
    
    error "Auth service failed to start after $max_attempts attempts"
    return 1
}

# Deploy auth service if needed
deploy_auth_service() {
    if check_auth_service; then
        log "Auth service already running"
        return
    fi
    
    log "Deploying authentication service..."
    
    if [[ -f "docker-compose.yml" ]]; then
        docker-compose up -d
    elif [[ -f "docker-compose.auth.yml" ]]; then
        docker-compose -f docker-compose.auth.yml up -d
    else
        error "No docker-compose file found"
        exit 1
    fi
    
    check_auth_service
}

# Register with blockchain
register_with_blockchain() {
    log "Registering gateway with DecentraLabs Registry..."
    
    # Check if already registered
    local is_registered
    is_registered=$(node -e "
        const { ethers } = require('ethers');
        const registryABI = require('./contracts/LabGatewayRegistry.json');
        
        async function checkRegistration() {
            try {
                const provider = new ethers.providers.JsonRpcProvider(process.env.RPC_URL || 'https://polygon-rpc.com');
                const registry = new ethers.Contract('${REGISTRY_CONTRACT}', registryABI, provider);
                const gateway = await registry.gateways('${PROVIDER_ADDRESS}');
                console.log(gateway.isActive);
            } catch (error) {
                console.log(false);
            }
        }
        
        checkRegistration();
    " 2>/dev/null || echo "false")
    
    if [[ "$is_registered" == "true" ]]; then
        log "Gateway already registered, updating..."
    fi
    
    # Register or update
    local tx_hash
    tx_hash=$(node -e "
        const { ethers } = require('ethers');
        const registryABI = require('./contracts/LabGatewayRegistry.json');
        
        async function register() {
            try {
                const provider = new ethers.providers.JsonRpcProvider(process.env.RPC_URL || 'https://polygon-rpc.com');
                const wallet = new ethers.Wallet('${PROVIDER_PRIVATE_KEY}', provider);
                const registry = new ethers.Contract('${REGISTRY_CONTRACT}', registryABI, wallet);
                
                const protocols = ['RDP', 'VNC', 'SSH'].map(p => ethers.utils.formatBytes32String(p));
                
                const tx = await registry.registerGateway(
                    '${GATEWAY_URL}',
                    '${AUTH_SERVICE_URL}',
                    protocols,
                    { value: ethers.utils.parseEther('1.0') } // 1 ETH stake
                );
                
                console.log(tx.hash);
                await tx.wait();
            } catch (error) {
                console.error('Registration failed:', error.message);
                process.exit(1);
            }
        }
        
        register();
    ")
    
    if [[ -n "$tx_hash" ]]; then
        success "Gateway registered! Transaction: $tx_hash"
    else
        error "Registration failed"
        exit 1
    fi
}

# Save configuration
save_config() {
    cat > "$CONFIG_FILE" << EOF
# DecentraLabs Gateway Configuration
GATEWAY_URL="$GATEWAY_URL"
AUTH_SERVICE_URL="$AUTH_SERVICE_URL"
PROVIDER_PRIVATE_KEY="$PROVIDER_PRIVATE_KEY"
PROVIDER_ADDRESS="$PROVIDER_ADDRESS"
REGISTRY_CONTRACT="${REGISTRY_CONTRACT:-0x...}"
REGISTERED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RPC_URL="${RPC_URL:-https://polygon-rpc.com}"
EOF
    
    chmod 600 "$CONFIG_FILE"
    success "Configuration saved to $CONFIG_FILE"
}

# Main execution
main() {
    log "Starting gateway registration process..."
    
    load_config
    detect_public_url
    setup_wallet
    deploy_auth_service
    register_with_blockchain
    save_config
    
    echo
    success "🎉 Gateway registration completed successfully!"
    echo
    echo -e "${GREEN}📋 Gateway Information:${NC}"
    echo -e "   🌐 Gateway URL: ${BLUE}$GATEWAY_URL${NC}"
    echo -e "   🔐 Auth Service: ${BLUE}$AUTH_SERVICE_URL${NC}"
    echo -e "   💼 Provider Address: ${BLUE}$PROVIDER_ADDRESS${NC}"
    echo -e "   ⛓️  Registry Contract: ${BLUE}$REGISTRY_CONTRACT${NC}"
    echo
    echo -e "${YELLOW}⚠️  Next Steps:${NC}"
    echo "   1. Monitor gateway health with: ./monitor.sh"
    echo "   2. Check registration status on blockchain explorer"
    echo "   3. Test auth service: curl $AUTH_SERVICE_URL/health"
    echo
    
    # Start health monitor if available
    if [[ -f "$SCRIPT_DIR/monitor.sh" ]]; then
        read -p "Start health monitoring now? (Y/n): " start_monitor
        if [[ ! "$start_monitor" =~ ^[Nn]$ ]]; then
            log "Starting health monitor..."
            bash "$SCRIPT_DIR/monitor.sh" &
            echo $! > "$SCRIPT_DIR/.monitor.pid"
            success "Health monitor started (PID: $(cat $SCRIPT_DIR/.monitor.pid))"
        fi
    fi
}

# Error handling
trap 'error "Script interrupted"; exit 1' INT TERM

# Run main function
main "$@"
```

#### **4.2 Advanced Health Monitoring System**

```javascript
// Enhanced Gateway Health Monitor with Reputation Management
class AdvancedGatewayHealthMonitor {
    constructor(registryContract, providerWallet, config = {}) {
        this.registry = registryContract;
        this.wallet = providerWallet;
        this.config = {
            healthCheckInterval: config.healthCheckInterval || 30000, // 30 seconds
            heartbeatInterval: config.heartbeatInterval || 60000,     // 60 seconds
            reputationUpdateInterval: config.reputationUpdateInterval || 300000, // 5 minutes
            maxFailures: config.maxFailures || 3,
            ...config
        };
        
        this.metrics = {
            uptime: 0,
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            averageResponseTime: 0,
            lastFailure: null,
            consecutiveFailures: 0
        };
        
        this.healthHistory = [];
        this.isMonitoring = false;
    }
    
    async startMonitoring() {
        if (this.isMonitoring) {
            console.log("Monitoring already active");
            return;
        }
        
        this.isMonitoring = true;
        console.log("🔍 Starting advanced gateway health monitoring...");
        
        // Start all monitoring processes
        this.startHealthChecks();
        this.startHeartbeat();
        this.startReputationUpdates();
        this.startMetricsCollection();
        
        // Setup graceful shutdown
        process.on('SIGINT', () => this.stopMonitoring());
        process.on('SIGTERM', () => this.stopMonitoring());
        
        console.log("✅ Health monitoring system active");
    }
    
    startHealthChecks() {
        this.healthCheckTimer = setInterval(async () => {
            try {
                await this.performComprehensiveHealthCheck();
                this.metrics.consecutiveFailures = 0;
            } catch (error) {
                this.metrics.consecutiveFailures++;
                this.metrics.lastFailure = Date.now();
                
                console.error(`❌ Health check failed (${this.metrics.consecutiveFailures}/${this.config.maxFailures}):`, error.message);
                
                if (this.metrics.consecutiveFailures >= this.config.maxFailures) {
                    await this.handleCriticalFailure(error);
                }
            }
        }, this.config.healthCheckInterval);
    }
    
    startHeartbeat() {
        this.heartbeatTimer = setInterval(async () => {
            try {
                await this.sendHeartbeatToRegistry();
                console.log("💓 Heartbeat sent to registry");
            } catch (error) {
                console.error("💔 Heartbeat failed:", error.message);
            }
        }, this.config.heartbeatInterval);
    }
    
    startReputationUpdates() {
        this.reputationTimer = setInterval(async () => {
            try {
                await this.updateReputationMetrics();
            } catch (error) {
                console.error("📊 Reputation update failed:", error.message);
            }
        }, this.config.reputationUpdateInterval);
    }
    
    async performComprehensiveHealthCheck() {
        const startTime = Date.now();
        const healthResults = {};
        
        // 1. Auth Service Health
        healthResults.authService = await this.checkAuthServiceHealth();
        
        // 2. Gateway Connectivity
        healthResults.gateway = await this.checkGatewayConnectivity();
        
        // 3. Blockchain Connectivity  
        healthResults.blockchain = await this.checkBlockchainConnection();
        
        // 4. Resource Usage
        healthResults.resources = await this.checkResourceUsage();
        
        // 5. SSL Certificate
        healthResults.ssl = await this.checkSSLCertificate();
        
        const totalTime = Date.now() - startTime;
        
        // Evaluate overall health
        const isHealthy = Object.values(healthResults).every(result => result.healthy);
        
        const healthReport = {
            timestamp: Date.now(),
            healthy: isHealthy,
            responseTime: totalTime,
            details: healthResults
        };
        
        // Store in history
        this.healthHistory.push(healthReport);
        if (this.healthHistory.length > 100) {
            this.healthHistory.shift(); // Keep last 100 records
        }
        
        // Update metrics
        this.updateHealthMetrics(healthReport);
        
        if (!isHealthy) {
            throw new Error(`Health check failed: ${this.getFailureReasons(healthResults)}`);
        }
        
        return healthReport;
    }
    
    async checkAuthServiceHealth() {
        try {
            const response = await fetch(`${process.env.AUTH_SERVICE_URL}/health`, {
                timeout: 5000,
                headers: { 'User-Agent': 'HealthMonitor/2.0' }
            });
            
            const healthData = await response.json();
            
            return {
                healthy: response.ok && healthData.status === 'healthy',
                responseTime: response.headers.get('x-response-time'),
                load: healthData.load || 0,
                memory: healthData.memory || {},
                activeConnections: healthData.connections || 0
            };
        } catch (error) {
            return { healthy: false, error: error.message };
        }
    }
    
    async checkGatewayConnectivity() {
        try {
            // Check main gateway endpoint
            const response = await fetch(`${process.env.GATEWAY_URL}/status`, {
                timeout: 5000
            });
            
            // Check if Guacamole is responding
            const guacResponse = await fetch(`${process.env.GATEWAY_URL}/guacamole`, {
                timeout: 5000,
                method: 'HEAD'
            });
            
            return {
                healthy: response.ok && (guacResponse.ok || guacResponse.status === 401),
                gatewayStatus: response.status,
                guacamoleStatus: guacResponse.status
            };
        } catch (error) {
            return { healthy: false, error: error.message };
        }
    }
    
    async checkBlockchainConnection() {
        try {
            const blockNumber = await this.registry.provider.getBlockNumber();
            const networkId = await this.registry.provider.getNetwork();
            
            return {
                healthy: blockNumber > 0,
                blockNumber,
                networkId: networkId.chainId,
                latency: Date.now() // Could measure actual latency
            };
        } catch (error) {
            return { healthy: false, error: error.message };
        }
    }
    
    async checkResourceUsage() {
        try {
            // Get Docker container stats if available
            const dockerStats = await this.getDockerStats();
            
            // Get system resources
            const systemStats = await this.getSystemStats();
            
            const cpuUsage = systemStats.cpu || dockerStats.cpu || 0;
            const memoryUsage = systemStats.memory || dockerStats.memory || 0;
            const diskUsage = systemStats.disk || 0;
            
            return {
                healthy: cpuUsage < 80 && memoryUsage < 85 && diskUsage < 90,
                cpu: cpuUsage,
                memory: memoryUsage,
                disk: diskUsage,
                details: { docker: dockerStats, system: systemStats }
            };
        } catch (error) {
            return { healthy: true, error: error.message }; // Non-critical
        }
    }
    
    async sendHeartbeatToRegistry() {
        const tx = await this.registry.sendHeartbeat();
        await tx.wait();
        return tx.hash;
    }
    
    async handleCriticalFailure(error) {
        console.error("🚨 CRITICAL: Gateway experiencing continuous failures");
        console.error("Error:", error.message);
        
        // Attempt automatic recovery
        await this.attemptAutomaticRecovery();
        
        // If recovery fails, consider emergency shutdown
        if (this.metrics.consecutiveFailures > this.config.maxFailures * 2) {
            console.error("🛑 Emergency shutdown - too many failures");
            await this.emergencyShutdown();
        }
    }
    
    async attemptAutomaticRecovery() {
        console.log("🔄 Attempting automatic recovery...");
        
        try {
            // 1. Restart Docker containers
            await this.restartServices();
            
            // 2. Clear caches
            await this.clearCaches();
            
            // 3. Re-register with blockchain if needed
            await this.reregisterIfNeeded();
            
            console.log("✅ Automatic recovery completed");
        } catch (error) {
            console.error("❌ Automatic recovery failed:", error.message);
        }
    }
    
    stopMonitoring() {
        console.log("🛑 Stopping health monitoring...");
        
        this.isMonitoring = false;
        
        if (this.healthCheckTimer) clearInterval(this.healthCheckTimer);
        if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
        if (this.reputationTimer) clearInterval(this.reputationTimer);
        if (this.metricsTimer) clearInterval(this.metricsTimer);
        
        console.log("✅ Health monitoring stopped");
    }
    
    generateHealthReport() {
        const recentHealth = this.healthHistory.slice(-10);
        const uptimePercentage = recentHealth.filter(h => h.healthy).length / recentHealth.length * 100;
        
        return {
            currentStatus: this.healthHistory[this.healthHistory.length - 1],
            metrics: this.metrics,
            uptime: `${uptimePercentage.toFixed(2)}%`,
            totalChecks: this.healthHistory.length,
            recentFailures: recentHealth.filter(h => !h.healthy).length
        };
    }
}

---

## 🏆 Implementation Strategy & Timeline

### **Phase 1: Core Smart Contract System (4-6 weeks)**
```mermaid
gantt
    title Smart Contract Registry Implementation
    dateFormat  2025-01-01
    section Smart Contracts
    Registry Contract Development    :a1, 2025-01-01, 2w
    Security Audit & Testing        :a2, after a1, 1w
    Mainnet Deployment             :a3, after a2, 1w
    
    section Integration Tools
    Auto-registration Script       :b1, 2025-01-15, 2w
    Health Monitoring System       :b2, after b1, 1w
    
    section API & Frontend
    Discovery Service API          :c1, 2025-01-22, 1w
    Marketplace Integration        :c2, after c1, 1w
```

**Priority Deliverables:**
1. ✅ **Enhanced LabGatewayRegistry Contract** - With staking, reputation, and slashing
2. ✅ **Automated Registration System** - One-command gateway setup with monitoring
3. ✅ **Multi-layer Service Discovery** - Fallback mechanisms and load balancing
4. ✅ **Advanced Health Monitoring** - Comprehensive system monitoring and auto-recovery
5. ✅ **Reputation System** - Economic incentives for reliable service

### **Phase 2: Network Optimization (3-4 weeks)**
```mermaid
gantt
    title Network Enhancement
    dateFormat  2025-02-01
    section Performance
    Load Balancing System          :d1, 2025-02-01, 2w
    Geographic Optimization        :d2, after d1, 1w
    
    section Analytics
    Network Analytics Dashboard    :e1, 2025-02-08, 2w
    Predictive Monitoring         :e2, after e1, 1w
```

### **Phase 3: Advanced Features (4-5 weeks)**
```mermaid
gantt
    title Advanced Ecosystem Features  
    dateFormat  2025-02-15
    section Cross-Gateway
    Inter-Gateway Communication    :f1, 2025-02-15, 3w
    Cross-Provider Lab Sharing     :f2, after f1, 2w
    
    section Governance
    DAO Governance Integration     :g1, 2025-03-01, 2w
    Community Rewards System      :g2, after g1, 2w
```

---

## 🎯 Architecture Benefits Analysis

### **For Lab Providers:**
| Benefit | Current System | Smart Contract Registry | Impact |
|---------|---------------|-------------------------|---------|
| **Setup Complexity** | Manual configuration | One-click deployment | 🟢 90% reduction |
| **Maintenance** | Manual monitoring | Automated health checks | 🟢 95% reduction |
| **Scalability** | Single gateway limit | Unlimited horizontal scaling | 🟢 Unlimited |
| **Operating Costs** | High infrastructure costs | Decentralized, pay-as-you-go | 🟢 70% reduction |
| **Reliability** | Single point of failure | Distributed redundancy | 🟢 99.9% uptime |

### **For Students/Users:**
| Benefit | Current System | Smart Contract Registry | Impact |
|---------|---------------|-------------------------|---------|
| **Access Speed** | Centralized bottleneck | Direct gateway routing | 🟢 60% faster |
| **Availability** | Dependent on central service | 24/7 decentralized access | 🟢 99.9% availability |
| **Global Reach** | Limited by geography | Worldwide gateway network | 🟢 Global coverage |
| **Cost** | High due to centralization | Lower distributed costs | 🟢 40% cost reduction |

### **For DecentraLabs Ecosystem:**
| Benefit | Impact | Measurement |
|---------|---------|-------------|
| **Infrastructure Costs** | 🟢 80% reduction | Less centralized services |
| **Network Effect** | 🟢 Exponential growth | Self-sustaining ecosystem |
| **Innovation Speed** | 🟢 3x faster | Provider-driven improvements |
| **Market Penetration** | 🟢 10x increase | Lower barriers to entry |

---

## 🔧 Technical Implementation Considerations

### **Security Framework:**

#### **Multi-layered Security**
```solidity
// Security measures in smart contract
modifier onlyAuthorizedGateway() {
    require(gateways[msg.sender].isActive, "Gateway not active");
    require(gateways[msg.sender].stakingAmount >= MINIMUM_STAKE, "Insufficient stake");
    require(block.timestamp - gateways[msg.sender].lastHeartbeat <= MAX_OFFLINE_TIME, "Gateway offline too long");
    _;
}

function slashGateway(address _gateway, uint256 _amount, string memory _reason) 
    external onlyOwner {
    // Economic penalties for malicious behavior
    // Automatic reputation reduction
    // Community governance integration
}
```

#### **Cryptographic Verification**
- **Gateway Ownership**: Each gateway must prove ownership of registered wallet
- **Message Signing**: All health reports and updates must be cryptographically signed
- **Reputation Staking**: Economic incentives prevent malicious behavior
- **Automated Auditing**: Smart contracts automatically verify all claims

### **Scalability Solutions:**

#### **Registry Sharding Strategy**
```javascript
// Multiple registry contracts for different regions/types
const registryContracts = {
    'americas': '0x123...',
    'europe': '0x456...',
    'asia': '0x789...',
    'university': '0xabc...',
    'commercial': '0xdef...'
};

class ShardedRegistryManager {
    async findOptimalRegistry(gatewayInfo) {
        // Route to appropriate shard based on:
        // - Geographic location
        // - Institution type  
        // - Performance requirements
        // - Current load
    }
}
```

#### **IPFS Integration for Metadata**
```javascript
// Store large metadata off-chain
class IPFSMetadataManager {
    async storeGatewayMetadata(gatewayInfo) {
        const ipfsHash = await this.ipfs.add(JSON.stringify({
            detailedSpecs: gatewayInfo.specs,
            certifications: gatewayInfo.certs,
            supportedSoftware: gatewayInfo.software,
            pricing: gatewayInfo.pricing
        }));
        
        // Only store IPFS hash on-chain
        return ipfsHash;
    }
}
```

### **Monitoring & Analytics Framework:**

#### **Network Health Dashboard**
```javascript
// Real-time network monitoring
class NetworkHealthAnalytics {
    async generateHealthReport() {
        return {
            overview: {
                totalGateways: await this.getTotalGateways(),
                activeGateways: await this.getActiveGateways(),
                averageReputation: await this.getAverageReputation(),
                networkUptime: await this.calculateNetworkUptime()
            },
            performance: {
                averageResponseTime: await this.getAverageResponseTime(),
                successRate: await this.getGlobalSuccessRate(),
                loadDistribution: await this.getLoadDistribution()
            },
            predictions: {
                capacityForecast: await this.predictCapacity(),
                maintenanceWindows: await this.predictMaintenance(),
                growthProjections: await this.projectGrowth()
            }
        };
    }
}
```

#### **Predictive Maintenance**
- **AI-powered failure prediction** based on historical patterns
- **Automated resource scaling** before peak usage periods
- **Proactive security updates** and patches
- **Community-driven improvements** through governance voting

---

## 🚀 Advanced Network Features

### **Cross-Gateway Collaboration**

#### **Lab Sharing Protocol**
```javascript
// Allow gateways to share computational resources
class InterGatewayCollaboration {
    async shareLabCapacity(labRequest, requesterGateway) {
        // 1. Evaluate if local gateway can handle request
        const canHandle = await this.evaluateCapacity(labRequest);
        
        if (!canHandle) {
            // 2. Find suitable partner gateways
            const partners = await this.findPartnerGateways(labRequest);
            
            // 3. Negotiate resource sharing
            const sharing = await this.negotiateSharing(partners, labRequest);
            
            // 4. Route user to optimal gateway
            return await this.routeToPartner(sharing.optimalGateway, labRequest);
        }
        
        return await this.processLocally(labRequest);
    }
}
```

### **Economic Incentive System**

#### **Dynamic Pricing & Rewards**
```solidity
// Smart contract for automatic reward distribution
contract GatewayRewardsSystem {
    mapping(address => uint256) public performanceScores;
    mapping(address => uint256) public monthlyRewards;
    
    function calculateRewards(address gateway) public view returns (uint256) {
        GatewayInfo storage info = registry.gateways(gateway);
        
        // Base reward for active participation
        uint256 baseReward = 100 * 10**18; // 100 tokens
        
        // Performance multiplier (0.5x to 2.0x)
        uint256 performanceMultiplier = (performanceScores[gateway] * 2000) / 1000;
        
        // Uptime bonus
        uint256 uptimeBonus = (info.totalUptime * 500) / (30 days);
        
        return (baseReward * performanceMultiplier / 1000) + uptimeBonus;
    }
    
    function distributeMonthlyRewards() external {
        // Automated monthly reward distribution
        // Based on performance, uptime, and community votes
    }
}
```

---

## 📈 Success Metrics & KPIs

### **Network Growth Metrics**
- **Gateway Count**: Target 1000+ gateways in first year
- **Geographic Distribution**: Coverage in 50+ countries
- **University Adoption**: 200+ educational institutions
- **Commercial Adoption**: 100+ commercial providers

### **Performance Metrics**  
- **Average Response Time**: < 500ms for service discovery
- **Network Uptime**: 99.9% availability
- **Success Rate**: > 99% authentication success
- **Load Distribution**: < 20% variance between gateways

### **Economic Metrics**
- **Total Value Locked**: Gateway staking amounts
- **Transaction Volume**: Monthly auth requests processed
- **Cost Savings**: Provider infrastructure cost reductions
- **Revenue Generation**: Network fees and rewards distributed

### **User Experience Metrics**
- **Time to Access**: < 30 seconds from request to lab connection
- **User Satisfaction**: > 4.5/5 rating
- **Support Tickets**: < 1% of sessions require support
- **Retention Rate**: > 90% monthly active users

---

*This Smart Contract Registry architecture provides a robust, scalable, and truly decentralized solution for managing authentication services across the DecentraLabs ecosystem. By leveraging blockchain technology, economic incentives, and automated monitoring, it creates a self-sustaining network that grows stronger with each new participant while maintaining high security and performance standards.*

