import json
from typing import Dict

def visualize_tree_modern(tree: Dict, output_file: str = "research_tree.html") -> str:
    """
    Create modern interactive tree visualization
    
    Args:
        tree: Tree structure from TreeView.build_tree()
        output_file: Output HTML filename
    
    Returns:
        str: Path to generated HTML file
    """
    
    def count_all_nodes(node_list, node_type="node"):
        """Count total nodes recursively"""
        count = len(node_list)
        for node in node_list:
            if node_type == "ancestor" and node.get('ancestors'):
                count += count_all_nodes(node['ancestors'], "ancestor")
            elif node_type == "descendant" and node.get('children'):
                count += count_all_nodes(node['children'], "descendant")
        return count
    
    total_ancestors = count_all_nodes(tree.get('ancestors', []), "ancestor")
    total_descendants = count_all_nodes(tree.get('descendants', []), "descendant")
    
    json_data = json.dumps(tree, ensure_ascii=False, default=str)
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Lineage Tree - {tree['target']['title']}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            overflow: auto;
        }}

        .container {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
            margin: 0 auto;
        }}

        h1 {{
            text-align: center;
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 2.5em;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}

        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 1.1em;
        }}

        .legend {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 30px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 20px;
            background: #f8f9fa;
            border-radius: 25px;
        }}

        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}

        #tree {{
            width: 100%;
            overflow-x: auto;
            border: 2px solid #ecf0f1;
            border-radius: 15px;
            background: #fafbfc;
        }}

        .node {{
            cursor: pointer;
            transition: opacity 0.3s ease;
        }}

        .node-ancestor {{ fill: #3498db; }}
        .node-target {{ fill: #e74c3c; }}
        .node-descendant {{ fill: #2ecc71; }}

        .node rect {{
            stroke-width: 3;
            rx: 12;
            ry: 12;
            filter: drop-shadow(0 4px 6px rgba(0,0,0,0.15));
            transition: all 0.3s ease;
        }}

        .node:hover rect {{
            filter: drop-shadow(0 8px 20px rgba(0,0,0,0.25));
            stroke-width: 4;
        }}

        .node-ancestor rect {{ stroke: #2980b9; }}
        .node-target rect {{ stroke: #c0392b; stroke-width: 5; }}
        .node-descendant rect {{ stroke: #27ae60; }}

        .node text {{
            font-family: 'Segoe UI', sans-serif;
            fill: white;
            pointer-events: none;
            font-weight: 500;
        }}

        .node-target text {{ font-weight: 700; }}

        .link {{
            fill: none;
            stroke-width: 2.5;
            stroke-opacity: 0.5;
            transition: all 0.3s ease;
        }}

        .link-ancestor {{ stroke: #3498db; }}
        .link-descendant {{ stroke: #2ecc71; }}

        .link:hover {{
            stroke-opacity: 0.9;
            stroke-width: 3.5;
        }}

        .tooltip {{
            position: absolute;
            padding: 15px 20px;
            background: rgba(44, 62, 80, 0.95);
            color: white;
            border-radius: 12px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.3s;
            max-width: 450px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            z-index: 1000;
        }}

        .tooltip.show {{ opacity: 1; }}

        .tooltip h3 {{
            margin: 0 0 10px 0;
            font-size: 1.1em;
            color: #3498db;
        }}

        .tooltip p {{
            margin: 5px 0;
            font-size: 0.9em;
            line-height: 1.6;
        }}

        .tooltip .stat {{
            display: inline-block;
            margin-right: 15px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🌳 Research Lineage Tree</h1>
        <p class="subtitle">{tree['target']['title']} ({tree['target']['year']})</p>

        <div class="legend">
            <div class="legend-item">
                <div class="legend-color" style="background: #3498db;"></div>
                <span>📚 Ancestors (Top)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #e74c3c;"></div>
                <span>🎯 Target (Center)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background: #2ecc71;"></div>
                <span>🌱 Descendants (Bottom)</span>
            </div>
        </div>

        <div id="tree"></div>
        
        <p style="text-align: center; margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 10px; color: #7f8c8d; font-size: 0.9em;">
            📊 Total nodes: {total_ancestors + total_descendants + 1} | Methodology-focused filtering<br>
            💡 <strong>Click any node</strong> to highlight its lineage path | Click background to reset<br>
            🖱️ Use mouse wheel to zoom, drag to pan
        </p>
    </div>

    <div class="tooltip" id="tooltip"></div>

    <script>
        const treeData = {json_data};

        const nodeWidth = 280;
        const nodeHeight = 90;
        const levelHeight = 200;
        const nodeSpacing = 550;

        const svg = d3.select("#tree")
            .append("svg")
            .attr("width", "100%")
            .attr("height", "1800")
            .attr("viewBox", "0 0 5500 1800");

        const g = svg.append("g");

        function layoutTree() {{
            const nodes = [];
            const links = [];

            const targetY = 800;
            const centerX = 2750;

            nodes.push({{
                id: treeData.target.paperId,
                x: centerX,
                y: targetY,
                data: treeData.target,
                type: 'target'
            }});

            function layoutAncestors(ancestorList, parentX, parentY, parentId, level) {{
                const numAncestors = ancestorList.length;

                if (level === 2) {{
                    const branchIndex = Math.floor((parentX - centerX) / nodeSpacing) + 1;
                    const branchStartX = centerX + (branchIndex - 1) * nodeSpacing * 3;

                    ancestorList.forEach((node, i) => {{
                        const x = branchStartX + i * nodeSpacing;
                        const y = parentY - levelHeight;
                        const nodeId = node.paper.paperId + "_" + level + "_" + branchIndex + "_" + i;

                        nodes.push({{ id: nodeId, x: x, y: y, data: node.paper, type: 'ancestor' }});
                        links.push({{ source: nodeId, target: parentId, type: 'ancestor' }});
                    }});
                }} else {{
                    const totalWidth = (numAncestors - 1) * nodeSpacing;
                    const startX = parentX - totalWidth / 2;

                    ancestorList.forEach((node, i) => {{
                        const x = startX + i * nodeSpacing;
                        const y = parentY - levelHeight;
                        const nodeId = node.paper.paperId + "_" + level + "_" + i;

                        nodes.push({{ id: nodeId, x: x, y: y, data: node.paper, type: 'ancestor' }});
                        links.push({{ source: nodeId, target: parentId, type: 'ancestor' }});

                        if (node.ancestors && node.ancestors.length > 0) {{
                            layoutAncestors(node.ancestors, x, y, nodeId, level + 1);
                        }}
                    }});
                }}
            }}

            function layoutDescendants(descendantList, parentX, parentY, parentId, level) {{
                const numDescendants = descendantList.length;

                if (level === 2) {{
                    const branchIndex = Math.floor((parentX - centerX) / nodeSpacing) + 2;
                    const branchStartX = centerX + (branchIndex - 2) * nodeSpacing * 3;

                    descendantList.forEach((node, i) => {{
                        const x = branchStartX + i * nodeSpacing;
                        const y = parentY + levelHeight;
                        const nodeId = node.paper.paperId + "_" + level + "_" + branchIndex + "_" + i;

                        nodes.push({{ id: nodeId, x: x, y: y, data: node.paper, type: 'descendant' }});
                        links.push({{ source: parentId, target: nodeId, type: 'descendant' }});
                    }});
                }} else {{
                    const totalWidth = (numDescendants - 1) * nodeSpacing;
                    const startX = parentX - totalWidth / 2;

                    descendantList.forEach((node, i) => {{
                        const x = startX + i * nodeSpacing;
                        const y = parentY + levelHeight;
                        const nodeId = node.paper.paperId + "_" + level + "_" + i;

                        nodes.push({{ id: nodeId, x: x, y: y, data: node.paper, type: 'descendant' }});
                        links.push({{ source: parentId, target: nodeId, type: 'descendant' }});

                        if (node.children && node.children.length > 0) {{
                            layoutDescendants(node.children, x, y, nodeId, level + 1);
                        }}
                    }});
                }}
            }}

            if (treeData.ancestors && treeData.ancestors.length > 0) {{
                layoutAncestors(treeData.ancestors, centerX, targetY, treeData.target.paperId, 1);
            }}

            if (treeData.descendants && treeData.descendants.length > 0) {{
                layoutDescendants(treeData.descendants, centerX, targetY, treeData.target.paperId, 1);
            }}

            return {{ nodes, links }};
        }}

        const {{ nodes, links }} = layoutTree();

        const link = g.selectAll(".link")
            .data(links)
            .join("path")
            .attr("class", d => `link link-${{d.type}}`)
            .attr("d", d => {{
                const source = nodes.find(n => n.id === d.source);
                const target = nodes.find(n => n.id === d.target);
                if (!source || !target) return "";
                return `M${{source.x}},${{source.y}} C${{source.x}},${{(source.y + target.y) / 2}} ${{target.x}},${{(source.y + target.y) / 2}} ${{target.x}},${{target.y}}`;
            }})
            .attr("marker-end", d => `url(#arrow-${{d.type}})`);

        svg.append("defs").selectAll("marker")
            .data(["ancestor", "descendant"])
            .join("marker")
            .attr("id", d => `arrow-${{d}}`)
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 20)
            .attr("refY", 0)
            .attr("markerWidth", 8)
            .attr("markerHeight", 8)
            .attr("orient", "auto")
            .append("path")
            .attr("fill", d => d === 'ancestor' ? '#3498db' : '#2ecc71')
            .attr("d", "M0,-5L10,0L0,5");

        const node = g.selectAll(".node")
            .data(nodes)
            .join("g")
            .attr("class", d => `node node-${{d.type}}`)
            .attr("transform", d => `translate(${{d.x}},${{d.y}})`);

        node.append("rect")
            .attr("x", -nodeWidth/2)
            .attr("y", -nodeHeight/2)
            .attr("width", nodeWidth)
            .attr("height", nodeHeight);

        node.append("text")
            .attr("dy", "-1.2em")
            .attr("text-anchor", "middle")
            .text(d => d.data.title.length > 45 ? d.data.title.substring(0, 45) + "..." : d.data.title)
            .style("font-size", d => d.type === 'target' ? "14px" : "12px")
            .style("font-weight", d => d.type === 'target' ? "700" : "500");

        node.append("text")
            .attr("dy", "0.2em")
            .attr("text-anchor", "middle")
            .text(d => `📅 ${{d.data.year || 'N/A'}}`)
            .style("font-size", "11px")
            .style("opacity", "0.9");

        node.append("text")
            .attr("dy", "1.5em")
            .attr("text-anchor", "middle")
            .text(d => `📊 ${{(d.data.citationCount || d.data.citations || 0).toLocaleString()}}`)
            .style("font-size", "11px")
            .style("opacity", "0.9");

        const tooltip = d3.select("#tooltip");

        node.on("mouseover", function(event, d) {{
            tooltip
                .style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY - 15) + "px")
                .classed("show", true)
                .html(`
                    <h3>${{d.data.title}}</h3>
                    <p>
                        <span class="stat"><strong>📅 Year:</strong> ${{d.data.year || 'N/A'}}</span>
                        <span class="stat"><strong>📊 Citations:</strong> ${{(d.data.citationCount || d.data.citations || 0).toLocaleString()}}</span>
                    </p>
                    <p style="font-size: 0.85em; margin-top: 8px; color: #95a5a6;">
                        ${{d.type === 'ancestor' ? '📚 Ancestor (Target cited this)' : d.type === 'target' ? '🎯 Target Paper' : '🌱 Descendant (This cited target)'}}
                    </p>
                `);
        }})
        .on("mouseout", function() {{
            tooltip.classed("show", false);
        }});

        // Click to highlight path
        node.on("click", function(event, d) {{
            event.stopPropagation();
            
            node.style("opacity", 0.2);
            link.style("opacity", 0.1).style("stroke-width", 2);
            
            d3.select(this).style("opacity", 1);
            
            const targetId = treeData.target.paperId;
            const highlightNodes = new Set([d.id]);
            const highlightLinks = new Set();
            
            function highlightAncestors(nodeId) {{
                if (nodeId === targetId) return;
                
                links.forEach(l => {{
                    if (l.target === nodeId) {{
                        highlightLinks.add(l.source + "|" + l.target);
                        highlightNodes.add(l.source);
                        highlightAncestors(l.source);
                    }}
                }});
            }}
            
            function highlightDescendants(nodeId) {{
                if (nodeId === targetId) return;
                
                links.forEach(l => {{
                    if (l.source === nodeId) {{
                        highlightLinks.add(l.source + "|" + l.target);
                        highlightNodes.add(l.target);
                        highlightDescendants(l.target);
                    }}
                }});
            }}
            
            highlightAncestors(d.id);
            highlightDescendants(d.id);
            
            node.each(function(n) {{
                if (highlightNodes.has(n.id)) {{
                    d3.select(this).style("opacity", 1);
                }}
            }});
            
            link.each(function(l) {{
                if (highlightLinks.has(l.source + "|" + l.target)) {{
                    d3.select(this).style("opacity", 0.8).style("stroke-width", 4);
                }}
            }});
        }});

        svg.on("click", function() {{
            node.style("opacity", 1);
            link.style("opacity", 0.5).style("stroke-width", 2.5);
        }});

        const zoom = d3.zoom()
            .scaleExtent([0.2, 3])
            .on("zoom", (event) => {{
                g.attr("transform", event.transform);
            }});

        svg.call(zoom);
        svg.call(zoom.transform, d3.zoomIdentity.translate(0, 0).scale(0.4));
    </script>
</body>
</html>
    """
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ Tree visualization saved to {output_file}")
    print(f"   📊 Total nodes: {total_ancestors + total_descendants + 1}")
    print(f"   💡 Click nodes to explore lineage paths")
    
    return output_file