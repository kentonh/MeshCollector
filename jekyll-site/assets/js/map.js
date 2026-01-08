/**
 * Map Controller for Federated Meshtastic
 * Handles Leaflet map display with node markers
 */

class MeshtasticMap {
    constructor(elementId, options = {}) {
        this.elementId = elementId;
        this.map = null;
        this.markersLayer = null;
        this.allFeatures = [];
        this.filteredFeatures = [];
        this.options = {
            center: options.center || [37.0902, -95.7129],
            zoom: options.zoom || 5,
            tileServer: options.tileServer || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            attribution: options.attribution || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        };
    }

    /**
     * Initialize the map
     */
    init() {
        // Create map
        this.map = L.map(this.elementId).setView(this.options.center, this.options.zoom);

        // Add tile layer
        L.tileLayer(this.options.tileServer, {
            attribution: this.options.attribution,
            maxZoom: 19
        }).addTo(this.map);

        // Create marker cluster group
        this.markersLayer = L.markerClusterGroup({
            maxClusterRadius: 50,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true
        });

        this.map.addLayer(this.markersLayer);
    }

    /**
     * Load nodes from API and display on map
     */
    async loadNodes(hours = 24) {
        try {
            const geojson = await window.meshtasticAPI.getMapGeoJSON({ hours });
            this.allFeatures = geojson.features || [];
            this.filteredFeatures = this.allFeatures;
            this.displayMarkers();
            this.updateNodeCount();
        } catch (error) {
            console.error('Error loading map data:', error);
        }
    }

    /**
     * Get marker icon based on node status
     */
    getMarkerIcon(status) {
        const colors = {
            'online': '#22c55e',
            'recent': '#eab308',
            'stale': '#f97316',
            'offline': '#ef4444',
            'unknown': '#6b7280'
        };

        const color = colors[status] || colors['unknown'];

        return L.divIcon({
            className: 'custom-marker',
            html: `<div style="background-color: ${color}; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });
    }

    /**
     * Create popup content for a node
     */
    createPopupContent(feature) {
        const props = feature.properties;
        const status = props.status || 'unknown';
        const statusLabel = window.MeshtasticUtils.getStatusLabel(status);

        return `
            <div class="node-popup">
                <h3>${props.short_name || props.long_name || props.node_id}</h3>
                <p><strong>Node ID:</strong> <span class="node-id">${props.node_id}</span></p>
                <p><strong>Status:</strong> <span class="status-badge status-${status}">${statusLabel}</span></p>
                <p><strong>Hardware:</strong> ${props.hardware || 'Unknown'}</p>
                <p><strong>Role:</strong> ${props.role || 'Unknown'}</p>
                <p><strong>Last Seen:</strong> ${window.MeshtasticUtils.formatRelativeTime(props.last_seen)}</p>
                ${props.battery_level ? `<p><strong>Battery:</strong> ${props.battery_level}%</p>` : ''}
                ${props.altitude ? `<p><strong>Altitude:</strong> ${props.altitude}m</p>` : ''}
            </div>
        `;
    }

    /**
     * Display markers on the map
     */
    displayMarkers() {
        // Clear existing markers
        this.markersLayer.clearLayers();

        // Add markers for filtered features
        this.filteredFeatures.forEach(feature => {
            const coords = feature.geometry.coordinates;
            const lat = coords[1];
            const lng = coords[0];
            const status = feature.properties.status;

            const marker = L.marker([lat, lng], {
                icon: this.getMarkerIcon(status)
            });

            marker.bindPopup(this.createPopupContent(feature));
            this.markersLayer.addLayer(marker);
        });

        // Fit bounds if markers exist
        if (this.filteredFeatures.length > 0) {
            const bounds = L.latLngBounds(
                this.filteredFeatures.map(f => [f.geometry.coordinates[1], f.geometry.coordinates[0]])
            );
            this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
        }
    }

    /**
     * Filter markers by status
     */
    filterByStatus(status) {
        if (!status) {
            this.filteredFeatures = this.allFeatures;
        } else {
            this.filteredFeatures = this.allFeatures.filter(
                feature => feature.properties.status === status
            );
        }
        this.displayMarkers();
        this.updateNodeCount();
    }

    /**
     * Update node count display
     */
    updateNodeCount() {
        const countElement = document.getElementById('node-count');
        if (countElement) {
            countElement.textContent = `${this.filteredFeatures.length} of ${this.allFeatures.length} nodes shown`;
        }
    }

    /**
     * Refresh map data
     */
    async refresh(hours) {
        await this.loadNodes(hours);
    }
}

// Initialize map when page loads
let meshtasticMapInstance = null;

window.addEventListener('DOMContentLoaded', () => {
    const config = window.mapConfig || {};
    const mapElement = document.getElementById(config.mapElementId || 'map');

    if (mapElement) {
        meshtasticMapInstance = new MeshtasticMap(config.mapElementId || 'map');
        meshtasticMapInstance.init();
        meshtasticMapInstance.loadNodes(config.initialHours || 24);

        // Auto-refresh every 60 seconds
        setInterval(() => {
            const hours = document.getElementById('map-hours')?.value || 24;
            meshtasticMapInstance.refresh(parseInt(hours));
        }, 60000);
    }
});

// Global functions for UI controls
function refreshMap() {
    if (meshtasticMapInstance) {
        const hours = document.getElementById('map-hours').value;
        meshtasticMapInstance.refresh(parseInt(hours));
    }
}

function filterMarkers() {
    if (meshtasticMapInstance) {
        const status = document.getElementById('map-status-filter').value;
        meshtasticMapInstance.filterByStatus(status);
    }
}
