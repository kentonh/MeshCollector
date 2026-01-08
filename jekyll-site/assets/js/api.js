/**
 * API Client for Federated Meshtastic
 * Provides wrapper functions for all API endpoints
 */

class MeshtasticAPI {
    constructor(baseURL) {
        this.baseURL = baseURL || window.API_BASE_URL || '';
        this.cache = new Map();
        this.cacheDuration = 30000; // 30 seconds default cache
    }

    /**
     * Make a GET request with caching support
     */
    async get(endpoint, params = {}, options = {}) {
        const url = new URL(`${this.baseURL}${endpoint}`);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });

        const cacheKey = url.toString();
        const useCache = options.cache !== false;

        // Check cache
        if (useCache && this.cache.has(cacheKey)) {
            const cached = this.cache.get(cacheKey);
            if (Date.now() - cached.timestamp < this.cacheDuration) {
                return cached.data;
            }
        }

        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            // Cache the result
            if (useCache) {
                this.cache.set(cacheKey, {
                    data: data,
                    timestamp: Date.now()
                });
            }

            return data;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            throw error;
        }
    }

    /**
     * Clear the cache
     */
    clearCache() {
        this.cache.clear();
    }

    /**
     * Get system statistics
     */
    async getStats() {
        return this.get('/v1/stats');
    }

    /**
     * Get network statistics
     */
    async getNetworkStats(hours = 24) {
        return this.get('/v1/network-stats', { hours });
    }

    /**
     * Get list of nodes
     */
    async getNodes(params = {}) {
        const defaults = { limit: 100, offset: 0 };
        return this.get('/v1/nodes', { ...defaults, ...params });
    }

    /**
     * Get details for a specific node
     */
    async getNode(nodeId) {
        return this.get(`/v1/nodes/${encodeURIComponent(nodeId)}`);
    }

    /**
     * Get nodes as GeoJSON for map display
     */
    async getMapGeoJSON(params = {}) {
        const defaults = { hours: 24 };
        return this.get('/v1/map/geojson', { ...defaults, ...params });
    }

    /**
     * Get traceroute list
     */
    async getTraceroutes(params = {}) {
        const defaults = { limit: 100 };
        return this.get('/v1/traceroutes', { ...defaults, ...params });
    }

    /**
     * Get traceroute details
     */
    async getTraceroute(traceId) {
        return this.get(`/v1/traceroutes/${encodeURIComponent(traceId)}`);
    }

    /**
     * Get network topology data
     */
    async getTopology(hours = 24) {
        return this.get('/v1/topology', { hours });
    }
}

// Create global API instance
window.meshtasticAPI = new MeshtasticAPI();

/**
 * Utility functions
 */
window.MeshtasticUtils = {
    /**
     * Format a timestamp as relative time
     */
    formatRelativeTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffSecs < 60) {
            return 'just now';
        } else if (diffMins < 60) {
            return `${diffMins} min${diffMins !== 1 ? 's' : ''} ago`;
        } else if (diffHours < 24) {
            return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        } else if (diffDays < 7) {
            return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        } else {
            return date.toLocaleDateString();
        }
    },

    /**
     * Format an absolute timestamp
     */
    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString();
    },

    /**
     * Get status class based on last seen time
     */
    getNodeStatus(lastSeen) {
        const date = new Date(lastSeen);
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);

        if (diffSecs < 300) { // 5 minutes
            return 'online';
        } else if (diffSecs < 3600) { // 1 hour
            return 'recent';
        } else if (diffSecs < 86400) { // 24 hours
            return 'stale';
        } else {
            return 'offline';
        }
    },

    /**
     * Get status label
     */
    getStatusLabel(status) {
        const labels = {
            'online': 'Online',
            'recent': 'Recent',
            'stale': 'Stale',
            'offline': 'Offline',
            'unknown': 'Unknown'
        };
        return labels[status] || labels['unknown'];
    },

    /**
     * Get status color
     */
    getStatusColor(status) {
        const colors = {
            'online': '#22c55e',   // green
            'recent': '#eab308',   // yellow
            'stale': '#f97316',    // orange
            'offline': '#ef4444',  // red
            'unknown': '#6b7280'   // gray
        };
        return colors[status] || colors['unknown'];
    },

    /**
     * Format battery level
     */
    formatBattery(level) {
        if (level === null || level === undefined) {
            return 'N/A';
        }
        return `${level}%`;
    },

    /**
     * Format RSSI value
     */
    formatRSSI(rssi) {
        if (rssi === null || rssi === undefined) {
            return 'N/A';
        }
        return `${rssi} dBm`;
    },

    /**
     * Format SNR value
     */
    formatSNR(snr) {
        if (snr === null || snr === undefined) {
            return 'N/A';
        }
        return `${snr.toFixed(2)} dB`;
    },

    /**
     * Truncate node ID for display
     */
    truncateNodeId(nodeId, length = 8) {
        if (!nodeId || nodeId.length <= length) {
            return nodeId;
        }
        return nodeId.substring(0, length) + '...';
    },

    /**
     * Show loading indicator
     */
    showLoading(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = '<div class="loading">Loading...</div>';
        }
    },

    /**
     * Show error message
     */
    showError(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `<div class="error">Error: ${message}</div>`;
        }
    },

    /**
     * Debounce function for search/filter inputs
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};
