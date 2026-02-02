import requests
import time
from typing import Dict, List, Optional

class TreeView:
    """Build research lineage trees using Semantic Scholar API"""
    
    def __init__(self, api_key=None):
        self.base_url = "https://api.semanticscholar.org/graph/v1"
        self.api_key = api_key
    
    def api_call(self, endpoint, params=None, max_retries=10):
        """Make API call with rate limiting and retry logic"""
        endpoint = endpoint.lstrip('/')
        url = f"{self.base_url}/{endpoint}"
        
        headers = {}
        if self.api_key:
            headers['x-api-key'] = self.api_key
        
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    time.sleep(1.2)
                    return response.json()
                
                elif response.status_code == 429:
                    wait_time = 5 * (attempt + 1)
                    print(f"⚠️  Rate limited! Waiting {wait_time} seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                
                else:
                    print(f"❌ Error {response.status_code}: {response.text[:200]}")
                    return None
                    
            except Exception as e:
                print(f"❌ Request failed: {str(e)}")
                return None
        
        print(f"❌ Failed after {max_retries} retries")
        return None
    
    def build_recursive_ancestors(self, paper_id, paper_year, current_depth=0, max_depth=2, max_children=3):
        """Recursively build ancestor tree (papers this paper cited)"""
        
        if current_depth >= max_depth:
            return []
        
        indent = "  " * current_depth
        print(f"{indent}🔍 Level {current_depth}: Fetching references...")
        
        refs_params = {
            'fields': 'citedPaper.paperId,citedPaper.title,citedPaper.year,citedPaper.citationCount,isInfluential,intents',
            'limit': 100
        }
        refs_response = self.api_call(f"paper/{paper_id}/references", refs_params)
        
        # Defensive checks
        if refs_response is None:
            print(f"{indent}   ⚠️  API returned None, skipping...")
            return []
        
        if 'data' not in refs_response or refs_response['data'] is None:
            print(f"{indent}   ⚠️  No valid data, skipping...")
            return []
        
        # Filter by methodology intent
        methodology_refs = [
            ref for ref in refs_response['data']
            if 'citedPaper' in ref
            and 'intents' in ref and ref['intents']
            and 'methodology' in ref['intents']
        ]
        
        print(f"{indent}   🔬 Papers cited for methodology: {len(methodology_refs)}")
        
        # Fallback to influential if needed
        if len(methodology_refs) < max_children:
            print(f"{indent}   ⚠️  Adding influential papers...")
            influential_refs = [
                ref for ref in refs_response['data']
                if ref.get('isInfluential', False) and 'citedPaper' in ref
            ]
            all_valid = methodology_refs + [r for r in influential_refs if r not in methodology_refs]
        else:
            all_valid = methodology_refs
        
        if not all_valid:
            return []
        
        # Sort and take top N
        all_valid.sort(
            key=lambda x: x.get('citedPaper', {}).get('citationCount') or 0,
            reverse=True
        )
        
        top_refs = all_valid[:max_children]
        
        print(f"{indent}   ✅ Found {len(top_refs)} ancestors")
        for i, ref in enumerate(top_refs, 1):
            paper = ref['citedPaper']
            print(f"{indent}      {i}. {paper['title'][:50]}... ({paper.get('year', 'N/A')})")
        
        # Recursively build ancestors
        ancestors = []
        for ref in top_refs:
            cited_paper = ref['citedPaper']
            node = {
                'paper': cited_paper,
                'ancestors': []
            }
            
            if cited_paper.get('paperId'):
                node['ancestors'] = self.build_recursive_ancestors(
                    cited_paper['paperId'],
                    cited_paper.get('year'),
                    current_depth + 1,
                    max_depth,
                    max_children
                )
            
            ancestors.append(node)
        
        return ancestors
    
    def build_recursive_descendants(self, paper_id, paper_year, current_depth=0, max_depth=2, window_years=3, max_children=3):
        """Recursively build descendant tree using time windows"""
        
        if current_depth >= max_depth:
            return []
        
        indent = "  " * current_depth
        max_papers = 10000 if current_depth == 0 else 5000
        
        print(f"{indent}🔍 Level {current_depth}: Searching {paper_year + 1} to {paper_year + window_years} (up to {max_papers:,} papers)")
        
        start_year = paper_year + 1
        end_year = paper_year + window_years
        
        all_cites = []
        offset = 0
        limit = 1000
        
        while offset < max_papers and offset < 9000:
            cites_params = {
                'fields': 'citingPaper.paperId,citingPaper.title,citingPaper.year,citingPaper.citationCount,intents,isInfluential',
                'limit': limit,
                'offset': offset,
                'publicationDateOrYear': f'{start_year}:{end_year}'
            }
            
            cites_response = self.api_call(f"paper/{paper_id}/citations", cites_params)
            
            if cites_response is None:
                print(f"{indent}   ⚠️  API call failed, stopping...")
                break
            
            if 'data' not in cites_response:
                break
            
            batch = cites_response['data']
            all_cites.extend(batch)
            
            if current_depth == 0 and offset % 5000 == 0 and offset > 0:
                print(f"{indent}   📊 Fetched {offset:,} papers so far...")
            
            if len(batch) < limit:
                break
            
            offset += limit
            
            if offset < max_papers and offset < 9000:
                time.sleep(2)
        
        print(f"{indent}   📊 Total fetched: {len(all_cites):,} papers")
        
        if not all_cites:
            print(f"{indent}   ⚠️  No citations fetched, skipping...")
            return []
        
        # Filter by methodology intent
        methodology_cites = [
            cite for cite in all_cites
            if 'citingPaper' in cite and cite['citingPaper'] is not None
            and 'intents' in cite and cite['intents']
            and 'methodology' in cite['intents']
        ]
        
        print(f"{indent}   🔬 Papers using methodology: {len(methodology_cites):,}")
        
        # Fallback to influential
        if len(methodology_cites) < max_children:
            print(f"{indent}   ⚠️  Adding influential papers...")
            influential_cites = [
                cite for cite in all_cites
                if 'citingPaper' in cite and cite['citingPaper'] is not None
                and cite.get('isInfluential', False)
            ]
            all_valid = methodology_cites + [c for c in influential_cites if c not in methodology_cites]
        else:
            all_valid = methodology_cites
        
        if not all_valid:
            return []
        
        valid_papers = [cite['citingPaper'] for cite in all_valid]
        
        valid_papers.sort(
            key=lambda x: x.get('citationCount') or 0,
            reverse=True
        )
        
        children_limit = max_children if current_depth == 0 else 3
        top_cites = valid_papers[:children_limit]
        
        print(f"{indent}   ✅ Top {len(top_cites)} papers")
        for i, cite in enumerate(top_cites, 1):
            print(f"{indent}      {i}. {cite['title'][:50]}... ({cite.get('year', 'N/A')})")
        
        # Recursively build children
        descendants = []
        for cite in top_cites:
            node = {
                'paper': cite,
                'children': []
            }
            
            if cite.get('year'):
                node['children'] = self.build_recursive_descendants(
                    cite['paperId'],
                    cite['year'],
                    current_depth + 1,
                    max_depth,
                    window_years,
                    max_children
                )
            
            descendants.append(node)
        
        return descendants
    
    def build_tree(self, paper_id, max_children=5, max_depth=2, window_years=3):
        """
        Build complete tree view for a paper
        
        Args:
            paper_id: Paper ID (e.g., "ARXIV:1706.03762")
            max_children: Maximum children per level (default: 5)
            max_depth: Recursion depth (default: 2)
            window_years: Years after publication to search (default: 3)
        
        Returns:
            dict: Tree structure with ancestors, target, and descendants
        """
        
        tree = {
            'ancestors': [],
            'target': None,
            'descendants': []
        }
        
        print(f"🎯 Building tree for: {paper_id}")
        
        # Get target paper
        print("\n1️⃣ Fetching target paper...")
        target_params = {'fields': 'paperId,title,year,citationCount,influentialCitationCount'}
        target = self.api_call(f"paper/{paper_id}", target_params)
        
        if not target:
            print("❌ Failed to fetch target paper")
            return None
        
        tree['target'] = target
        print(f"   ✅ {target['title']} ({target['year']})")
        
        # Build ancestors
        print(f"\n2️⃣ Fetching ancestors recursively (max depth: {max_depth})...")
        tree['ancestors'] = self.build_recursive_ancestors(
            paper_id,
            target.get('year'),
            current_depth=0,
            max_depth=max_depth,
            max_children=3
        )
        
        # Build descendants
        print(f"\n3️⃣ Fetching descendants recursively (max depth: {max_depth}, window: {window_years} years)...")
        
        if target.get('year'):
            tree['descendants'] = self.build_recursive_descendants(
                paper_id,
                target['year'],
                current_depth=0,
                max_depth=max_depth,
                window_years=window_years,
                max_children=max_children
            )
        
        return tree