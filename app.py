#!/usr/bin/env python3
"""
ResearchLineage - Main Application
Generate research lineage trees from arXiv papers
"""

import sys
import os
from tree_view.tree_builder import TreeView
from tree_view.visualizer import visualize_tree_modern

def extract_paper_id(url_or_id):
    """Extract paper ID from URL or return as-is if already an ID"""
    if 'arxiv.org/abs/' in url_or_id:
        arxiv_id = url_or_id.split('/abs/')[-1].split('v')[0]
        return f"ARXIV:{arxiv_id}"
    return url_or_id

def main():
    """Main application entry point"""
    
    print("="*80)
    print("🌳 ResearchLineage - AI-Powered Research Paper Lineage Tracker")
    print("="*80)
    
    # Get paper ID from command line or prompt
    if len(sys.argv) > 1:
        paper_input = sys.argv[1]
    else:
        paper_input = input("\nEnter arXiv URL or paper ID: ").strip()
    
    if not paper_input:
        print("❌ No paper provided!")
        return
    
    paper_id = extract_paper_id(paper_input)
    print(f"\n📄 Analyzing: {paper_id}")
    
    # Initialize TreeView
    tree_view = TreeView()
    
    # Build tree
    tree = tree_view.build_tree(
        paper_id=paper_id,
        max_children=5,      # 5 descendants at Level 0
        max_depth=2,         # 2 levels deep
        window_years=3       # 3-year time window
    )
    
    if not tree:
        print("\n❌ Failed to build tree!")
        return
    
    # Generate visualization
    output_file = f"outputs/tree_{paper_id.replace(':', '_').replace('/', '_')}.html"
    os.makedirs("outputs", exist_ok=True)
    
    visualize_tree_modern(tree, output_file)
    
    print(f"\n✅ Complete! Open {output_file} to view the tree")
    print(f"   or run: open {output_file}")

if __name__ == "__main__":
    main()