(function () {
    function initializeDatasetVisualization() {
        var section = document.getElementById('Visualization');
        if (!section || typeof Ajax === 'undefined' || typeof d3 === 'undefined' || typeof d3.jsonldVis === 'undefined') {
            return;
        }

        var container = section.querySelector('[data-role="graph-container"]');
        var loading = section.querySelector('[data-role="graph-loading"]');
        var isLoaded = false;

        function loadVisualization() {
            if (isLoaded || !container) {
                return;
            }
            isLoaded = true;

            Ajax.load({
                url: section.dataset.rocrateUrl,
                method: 'get',
                success: function (data) {
                    if (loading) {
                        loading.remove();
                    }
                    d3.jsonldVis(data, '[data-role="graph-container"]', {
                        h: 600,
                        w: container.offsetWidth
                    });
                }
            });
        }

        section.addEventListener('toggle', function () {
            if (section.open) {
                loadVisualization();
            }
        });

        if (section.open) {
            loadVisualization();
        }
    }

    function initializeWorkflowGraph() {
        var section = document.getElementById('WorkflowGraph');
        if (!section || typeof cytoscape === 'undefined') {
            return;
        }

        var graphContainer = section.querySelector('[data-role="workflow-graph"]');
        var resetButton = section.querySelector('[data-role="graph-reset"]');
        var isLoaded = false;

        function resetGraphView(cy) {
            cy.fit(cy.elements(), 0);
            cy.center(cy.elements());
        }

        function loadWorkflowGraph() {
            if (isLoaded || !graphContainer) {
                return;
            }
            isLoaded = true;

            var graphUrl = section.dataset.graphUrl;
            var workflowUrl = section.dataset.workflowUrl;
            if (!graphUrl || !workflowUrl) {
                console.error('Workflow graph is missing endpoint or workflow URL.');
                return;
            }

            fetch(graphUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url: workflowUrl })
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('Workflow graph request failed with status ' + response.status);
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (!data || !data.elements || !Array.isArray(data.elements.nodes) || !Array.isArray(data.elements.edges)) {
                        throw new Error('Workflow graph API did not return a valid graph payload.');
                    }

                    var elements = [];
                    var visibleNodeIds = {};

                    (data.elements.nodes || []).forEach(function (node) {
                        var nodeData = (node && node.data) ? node.data : {};
                        var isArtifact = nodeData.type === 'artifact';
                        var isGcTrue = nodeData.gc === true || nodeData.gc === 'true' || nodeData.gc === 'True';

                        if (!(isArtifact && isGcTrue)) {
                            elements.push(node);
                            if (nodeData.id) {
                                visibleNodeIds[nodeData.id] = true;
                            }
                        }
                    });

                    (data.elements.edges || []).forEach(function (edge) {
                        var edgeData = (edge && edge.data) ? edge.data : {};
                        if (visibleNodeIds[edgeData.source] && visibleNodeIds[edgeData.target]) {
                            elements.push(edge);
                        }
                    });

                    var cy = cytoscape({
                        container: graphContainer,
                        elements: elements,
                        userZoomingEnabled: true,
                        userPanningEnabled: true,
                        autoungrabify: true,
                        minZoom: 0.3,
                        maxZoom: 3,
                        style: [
                            {
                                selector: 'node',
                                style: {
                                    label: 'data(name)',
                                    'text-valign': 'center',
                                    'text-halign': 'center',
                                    'font-size': '11px',
                                    'text-wrap': 'wrap',
                                    'text-max-width': '100px',
                                    width: 'label',
                                    height: 'label',
                                    padding: '8px',
                                    shape: 'roundrectangle',
                                    color: '#fff'
                                }
                            },
                            {
                                selector: 'node[type = "task"]',
                                style: {
                                    'background-color': '#137752'
                                }
                            },
                            {
                                selector: 'node[type = "artifact"]',
                                style: {
                                    'background-color': '#f9b233',
                                    color: '#333',
                                    shape: 'ellipse'
                                }
                            },
                            {
                                selector: 'edge[type = "control"]',
                                style: {
                                    width: 2,
                                    'line-color': '#aaa',
                                    'target-arrow-color': '#aaa',
                                    'target-arrow-shape': 'triangle',
                                    'curve-style': 'bezier'
                                }
                            },
                            {
                                selector: 'edge[type = "data"]',
                                style: {
                                    width: 1,
                                    'line-color': '#aaa',
                                    'target-arrow-color': '#aaa',
                                    'target-arrow-shape': 'triangle',
                                    'curve-style': 'bezier',
                                    'line-style': 'dashed'
                                }
                            }
                        ],
                        layout: {
                            name: 'breadthfirst',
                            directed: true,
                            spacingFactor: 0.6
                        }
                    });

                    resetGraphView(cy);

                    if (resetButton) {
                        resetButton.addEventListener('click', function () {
                            resetGraphView(cy);
                        });
                    }
                })
                .catch(function (error) {
                    console.error('Failed to load workflow graph:', error);
                    graphContainer.innerHTML = '<p class="dark-red f6">Failed to load workflow graph.</p>';
                });
        }

        section.addEventListener('toggle', function () {
            if (section.open) {
                loadWorkflowGraph();
            }
        });

        if (section.open) {
            loadWorkflowGraph();
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        initializeDatasetVisualization();
        initializeWorkflowGraph();
    });
})();