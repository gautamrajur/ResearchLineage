"""Utility functions for tree view"""

def display_tree_text(tree):
    """Print tree in text format"""
    
    def display_recursive_ancestors(node, indent=0):
        prefix = "  " * indent
        paper = node['paper']
        citations = paper.get('citationCount', 0)
        
        print(f"{prefix}├─ [{paper.get('year', 'N/A')}] {paper['title']}")
        print(f"{prefix}│  └─ {citations:,} citations")
        
        for ancestor in node.get('ancestors', []):
            display_recursive_ancestors(ancestor, indent + 1)
    
    def display_recursive_descendants(node, indent=0):
        prefix = "  " * indent
        paper = node['paper']
        citations = paper.get('citationCount', 0)
        
        print(f"{prefix}├─ [{paper.get('year', 'N/A')}] {paper['title']}")
        print(f"{prefix}│  └─ {citations:,} citations")
        
        for child in node.get('children', []):
            display_recursive_descendants(child, indent + 1)
    
    if not tree:
        return
    
    print("\n" + "="*80)
    print("🌳 RESEARCH TREE VIEW")
    print("="*80)
    
    if tree['ancestors']:
        print("\n📚 ANCESTORS:")
        for node in tree['ancestors']:
            display_recursive_ancestors(node, indent=1)
        print()
    
    print("\n🎯 TARGET PAPER:")
    target = tree['target']
    print(f"   [{target.get('year', 'N/A')}] {target['title']}")
    print(f"   └─ {target.get('citationCount', 0):,} citations\n")
    
    if tree['descendants']:
        print("\n🌱 DESCENDANTS:")
        for node in tree['descendants']:
            display_recursive_descendants(node, indent=1)
        print()
    
    print("="*80)