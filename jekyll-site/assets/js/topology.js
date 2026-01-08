/**
 * Network Topology Visualization
 * D3.js force-directed graph for Meshtastic network
 */

class NetworkTopology {
    constructor(elementId) {
        this.elementId = elementId;
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.links = [];
        this.width = 0;
        this.height = 0;
    }

    /**
     * Initialize the visualization
     */
    init() {
        const container = document.getElementById(this.elementId);
        this.width = container.offsetWidth || 1000;
        this.height = container.offsetHeight || 700;

        // Create SVG
        this.svg = d3.select(`#${this.elementId}`)
            .append('svg')
            .attr('width', this.width)
            .attr('height', this.height)
            .attr('viewBox', [0, 0, this.width, this.height]);

        // Add zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on('zoom', (event) => {
                this.svg.selectAll('g').attr('transform', event.transform);
            });

        this.svg.call(zoom);

        // Create container groups
        this.svg.append('g').attr('class', 'links');
        this.svg.append('g').attr('class', 'nodes');

        // Initialize force simulation
        this.simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(this.width / 2, this.height / 2))
            .force('collision', d3.forceCollide().radius(30));
    }

    /**
     * Load topology data from API
     */
    async loadData(hours = 24) {
        try {
            const data = await window.meshtasticAPI.getTopology(hours);

            // Process nodes
            const nodeMap = new Map();
            data.nodes.forEach(node => {
                nodeMap.set(node.node_id, {
                    id: node.node_id,
                    name: node.short_name || node.long_name || node.node_id,
                    hardware: node.hardware,
                    role: node.role,
                    latitude: node.latitude,
                    longitude: node.longitude,
                    last_seen: node.last_seen,
                    relayCount: 0,
                    packetCount: 0
                });
            });

            // Process links (relay relationships)
            const linkMap = new Map();
            data.links.forEach(link => {
                const key = `${link.source}-${link.target}`;
                if (!linkMap.has(key)) {
                    linkMap.set(key, {
                        source: link.source,
                        target: link.target,
                        packet_count: link.packet_count || 0,
                        avg_rssi: link.avg_rssi,
                        avg_snr: link.avg_snr
                    });
                }

                // Update relay count for target node
                if (nodeMap.has(link.target)) {
                    nodeMap.get(link.target).relayCount += link.packet_count || 0;
                }

                // Update packet count for source node
                if (nodeMap.has(link.source)) {
                    nodeMap.get(link.source).packetCount += link.packet_count || 0;
                }
            });

            // Also process observation links
            data.observations.forEach(obs => {
                const key = `${obs.source}-${obs.target}`;
                if (!linkMap.has(key)) {
                    linkMap.set(key, {
                        source: obs.source,
                        target: obs.target,
                        packet_count: obs.observation_count || 0,
                        avg_rssi: obs.avg_rssi,
                        avg_snr: obs.avg_snr,
                        isObservation: true
                    });
                }
            });

            this.nodes = Array.from(nodeMap.values());
            this.links = Array.from(linkMap.values());

            // Update stats
            this.updateStats();

            // Render the graph
            this.render();

        } catch (error) {
            console.error('Error loading topology data:', error);
        }
    }

    /**
     * Update statistics display
     */
    updateStats() {
        const statsElement = document.getElementById('topology-stats');
        if (statsElement) {
            statsElement.textContent = `${this.nodes.length} nodes, ${this.links.length} connections`;
        }
    }

    /**
     * Get node size based on relay activity
     */
    getNodeSize(node) {
        const baseSize = 5;
        const relayFactor = Math.sqrt(node.relayCount) * 2;
        return Math.max(baseSize, Math.min(baseSize + relayFactor, 30));
    }

    /**
     * Get link color based on signal strength
     */
    getLinkColor(link) {
        if (!link.avg_rssi) return '#9ca3af'; // gray for unknown

        if (link.avg_rssi > -80) return '#22c55e'; // green
        if (link.avg_rssi > -100) return '#eab308'; // yellow
        return '#ef4444'; // red
    }

    /**
     * Get link width based on packet count
     */
    getLinkWidth(link) {
        const baseWidth = 1;
        const factor = Math.log10(link.packet_count + 1);
        return Math.max(baseWidth, Math.min(baseWidth + factor, 5));
    }

    /**
     * Render the force-directed graph
     */
    render() {
        // Update simulation
        this.simulation.nodes(this.nodes);
        this.simulation.force('link').links(this.links);

        // Render links
        const link = this.svg.select('g.links')
            .selectAll('line')
            .data(this.links, d => `${d.source}-${d.target}`)
            .join('line')
            .attr('stroke', d => this.getLinkColor(d))
            .attr('stroke-width', d => this.getLinkWidth(d))
            .attr('stroke-opacity', d => d.isObservation ? 0.3 : 0.6)
            .attr('stroke-dasharray', d => d.isObservation ? '4,4' : 'none');

        // Render nodes
        const node = this.svg.select('g.nodes')
            .selectAll('g')
            .data(this.nodes, d => d.id)
            .join('g')
            .call(this.drag(this.simulation));

        // Remove old circles and text
        node.selectAll('circle').remove();
        node.selectAll('text').remove();

        // Add circles
        node.append('circle')
            .attr('r', d => this.getNodeSize(d))
            .attr('fill', d => {
                const status = window.MeshtasticUtils.getNodeStatus(d.last_seen);
                return window.MeshtasticUtils.getStatusColor(status);
            })
            .attr('stroke', '#fff')
            .attr('stroke-width', 2);

        // Add labels
        node.append('text')
            .text(d => window.MeshtasticUtils.truncateNodeId(d.name, 8))
            .attr('x', 0)
            .attr('y', d => this.getNodeSize(d) + 12)
            .attr('text-anchor', 'middle')
            .attr('font-size', '10px')
            .attr('fill', '#374151');

        // Add tooltips
        node.append('title')
            .text(d => {
                const status = window.MeshtasticUtils.getNodeStatus(d.last_seen);
                return `${d.name}
Node ID: ${d.id}
Status: ${window.MeshtasticUtils.getStatusLabel(status)}
Hardware: ${d.hardware || 'Unknown'}
Role: ${d.role || 'Unknown'}
Relay Count: ${d.relayCount}
Packet Count: ${d.packetCount}
Last Seen: ${window.MeshtasticUtils.formatRelativeTime(d.last_seen)}`;
            });

        // Update positions on tick
        this.simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Restart simulation
        this.simulation.alpha(1).restart();
    }

    /**
     * Drag behavior for nodes
     */
    drag(simulation) {
        function dragstarted(event) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        return d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended);
    }

    /**
     * Refresh topology data
     */
    async refresh(hours) {
        await this.loadData(hours);
    }
}

// Initialize topology when page loads
let networkTopologyInstance = null;

window.addEventListener('DOMContentLoaded', () => {
    const config = window.topologyConfig || {};
    const element = document.getElementById(config.elementId || 'topology-graph');

    if (element) {
        networkTopologyInstance = new NetworkTopology(config.elementId || 'topology-graph');
        networkTopologyInstance.init();
        networkTopologyInstance.loadData(config.initialHours || 24);

        // Auto-refresh every 60 seconds
        setInterval(() => {
            const hours = document.getElementById('topology-hours')?.value || 24;
            networkTopologyInstance.refresh(parseInt(hours));
        }, 60000);
    }
});

// Global function for UI controls
function refreshTopology() {
    if (networkTopologyInstance) {
        const hours = document.getElementById('topology-hours').value;
        networkTopologyInstance.refresh(parseInt(hours));
    }
}
