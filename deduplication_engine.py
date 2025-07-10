#!/usr/bin/env python3
"""
Intelligent Deduplication Engine
Multi-algorithm similarity detection for AI memory systems

This is an open-source component extracted from a production Claude Memory System.
All sensitive information has been removed and made configurable.
"""

import json
import os
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
from collections import defaultdict

try:
    import psycopg2
    import Levenshtein
except ImportError:
    print("Missing dependencies. Install with: pip install psycopg2-binary python-Levenshtein")
    exit(1)

class IntelligentDeduplicationEngine:
    """
    Advanced deduplication engine using multiple similarity algorithms
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize deduplication engine with configuration"""
        self.config = self.load_config(config_path)
        
        # Algorithm configuration
        self.similarity_threshold = self.config.get('similarity_threshold', 0.85)
        self.fuzzy_threshold = self.config.get('fuzzy_threshold', 0.90)
        
        # Algorithm weights for composite scoring
        self.weights = self.config.get('algorithm_weights', {
            'exact_match': 0.3,
            'sequence_similarity': 0.25,
            'levenshtein_similarity': 0.25,
            'jaccard_similarity': 0.2
        })
    
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        else:
            return self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "memory_db",
                "user": "username",
                "password": "password"
            },
            "similarity_threshold": 0.85,
            "fuzzy_threshold": 0.90,
            "algorithm_weights": {
                "exact_match": 0.3,
                "sequence_similarity": 0.25,
                "levenshtein_similarity": 0.25,
                "jaccard_similarity": 0.2
            },
            "performance": {
                "batch_size": 1000,
                "max_memory_usage": "512MB"
            }
        }
    
    def connect_db(self):
        """Connect to database using configuration"""
        db_config = self.config['database']
        return psycopg2.connect(
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Convert to lowercase
        normalized = text.lower().strip()
        
        # Remove common variable patterns (dates, times, IDs)
        import re
        patterns = [
            r'\d{4}-\d{2}-\d{2}',  # Dates
            r'\d{2}:\d{2}:\d{2}',  # Times
            r'ID:\s*\d+',          # IDs
            r'#\d+',               # Hash numbers
        ]
        
        for pattern in patterns:
            normalized = re.sub(pattern, '', normalized)
        
        # Clean up whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        return normalized.strip()
    
    def calculate_similarity(self, text1: str, text2: str) -> Dict[str, float]:
        """Calculate similarity using multiple algorithms"""
        # Normalize texts
        norm1 = self.normalize_text(text1)
        norm2 = self.normalize_text(text2)
        
        # Exact match
        exact_match = 1.0 if norm1 == norm2 else 0.0
        
        # Sequence similarity (difflib)
        sequence_similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Levenshtein similarity
        max_len = max(len(norm1), len(norm2))
        if max_len == 0:
            levenshtein_similarity = 1.0
        else:
            levenshtein_distance = Levenshtein.distance(norm1, norm2)
            levenshtein_similarity = 1.0 - (levenshtein_distance / max_len)
        
        # Jaccard similarity (word-based)
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if not words1 and not words2:
            jaccard_similarity = 1.0
        elif not words1 or not words2:
            jaccard_similarity = 0.0
        else:
            intersection = words1.intersection(words2)
            union = words1.union(words2)
            jaccard_similarity = len(intersection) / len(union)
        
        # Composite similarity (weighted average)
        composite_similarity = (
            exact_match * self.weights['exact_match'] +
            sequence_similarity * self.weights['sequence_similarity'] +
            levenshtein_similarity * self.weights['levenshtein_similarity'] +
            jaccard_similarity * self.weights['jaccard_similarity']
        )
        
        return {
            'exact_match': exact_match,
            'sequence_similarity': sequence_similarity,
            'levenshtein_similarity': levenshtein_similarity,
            'jaccard_similarity': jaccard_similarity,
            'composite_similarity': composite_similarity
        }
    
    def find_duplicates(self, table_name: str = "observations", 
                       content_column: str = "content", 
                       entity_filter: str = None) -> Dict:
        """Find duplicates in specified table"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        # Build query dynamically
        query = f"""
            SELECT id, {content_column}, created_at 
            FROM {table_name}
        """
        params = []
        
        if entity_filter:
            query += " WHERE entity_name = %s"
            params.append(entity_filter)
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        records = cursor.fetchall()
        
        # Find duplicate groups
        duplicate_groups = []
        processed_ids = set()
        
        for i, record1 in enumerate(records):
            if record1[0] in processed_ids:
                continue
                
            id1, content1, created_at1 = record1
            current_group = [record1]
            
            for j, record2 in enumerate(records[i+1:], i+1):
                if record2[0] in processed_ids:
                    continue
                    
                id2, content2, created_at2 = record2
                
                # Calculate similarity
                similarity = self.calculate_similarity(content1, content2)
                
                # Check if duplicate
                if similarity['composite_similarity'] >= self.similarity_threshold:
                    current_group.append(record2)
                    processed_ids.add(id2)
            
            # Add group if duplicates found
            if len(current_group) > 1:
                duplicate_groups.append({
                    'group_id': len(duplicate_groups),
                    'records': current_group,
                    'count': len(current_group),
                    'similarity_scores': [
                        self.calculate_similarity(current_group[0][1], record[1])
                        for record in current_group[1:]
                    ]
                })
                
            processed_ids.add(id1)
        
        conn.close()
        
        # Generate statistics
        total_records = len(records)
        duplicate_records = sum(group['count'] for group in duplicate_groups)
        
        return {
            'total_records': total_records,
            'duplicate_groups': duplicate_groups,
            'duplicate_records': duplicate_records,
            'duplicate_rate': (duplicate_records / total_records * 100) if total_records > 0 else 0,
            'analysis_timestamp': datetime.now().isoformat(),
            'config_used': {
                'similarity_threshold': self.similarity_threshold,
                'algorithm_weights': self.weights
            }
        }
    
    def resolve_duplicates(self, analysis_result: Dict, 
                          strategy: str = 'keep_latest',
                          dry_run: bool = True) -> Dict:
        """Resolve duplicates using specified strategy"""
        
        if not analysis_result['duplicate_groups']:
            return {
                'action': 'no_duplicates_found',
                'message': 'No duplicates to resolve'
            }
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        resolution_actions = []
        
        try:
            for group in analysis_result['duplicate_groups']:
                records = group['records']
                
                if strategy == 'keep_latest':
                    # Keep most recent, mark others
                    latest_record = max(records, key=lambda x: x[2])  # by created_at
                    older_records = [r for r in records if r[0] != latest_record[0]]
                    
                    if not dry_run:
                        for record in older_records:
                            cursor.execute("""
                                UPDATE observations 
                                SET content = content || ' [DUPLICATE - KEPT ID: ' || %s || ']'
                                WHERE id = %s
                            """, (latest_record[0], record[0]))
                    
                    resolution_actions.append({
                        'action': 'keep_latest',
                        'kept_id': latest_record[0],
                        'marked_ids': [r[0] for r in older_records],
                        'group_size': len(records)
                    })
                
                elif strategy == 'merge':
                    # Merge content into primary record
                    primary_record = max(records, key=lambda x: x[2])
                    secondary_records = [r for r in records if r[0] != primary_record[0]]
                    
                    merged_content = self._merge_content(primary_record, secondary_records)
                    
                    if not dry_run:
                        cursor.execute("""
                            UPDATE observations 
                            SET content = %s, updated_at = %s
                            WHERE id = %s
                        """, (merged_content, datetime.now(), primary_record[0]))
                        
                        for record in secondary_records:
                            cursor.execute("""
                                UPDATE observations 
                                SET content = content || ' [MERGED INTO ID: ' || %s || ']'
                                WHERE id = %s
                            """, (primary_record[0], record[0]))
                    
                    resolution_actions.append({
                        'action': 'merge',
                        'primary_id': primary_record[0],
                        'secondary_ids': [r[0] for r in secondary_records],
                        'group_size': len(records)
                    })
                
                elif strategy == 'flag_only':
                    # Just flag as duplicates
                    if not dry_run:
                        for record in records:
                            cursor.execute("""
                                UPDATE observations 
                                SET content = content || ' [DUPLICATE GROUP: ' || %s || ']'
                                WHERE id = %s
                            """, (group['group_id'], record[0]))
                    
                    resolution_actions.append({
                        'action': 'flag_only',
                        'flagged_ids': [r[0] for r in records],
                        'group_id': group['group_id'],
                        'group_size': len(records)
                    })
            
            if not dry_run:
                conn.commit()
                
        except Exception as e:
            conn.rollback()
            return {
                'action': 'error',
                'message': f'Error resolving duplicates: {str(e)}'
            }
        finally:
            conn.close()
        
        return {
            'action': 'resolution_applied' if not dry_run else 'dry_run_completed',
            'strategy': strategy,
            'groups_processed': len(analysis_result['duplicate_groups']),
            'records_affected': sum(action['group_size'] for action in resolution_actions),
            'resolution_actions': resolution_actions
        }
    
    def _merge_content(self, primary_record: Tuple, secondary_records: List[Tuple]) -> str:
        """Merge content from multiple records"""
        primary_content = primary_record[1]
        
        merge_info = f"\n[MERGED from {len(secondary_records)} duplicates on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"
        
        dates_info = "\n[Original dates: " + ", ".join(
            record[2].strftime('%Y-%m-%d %H:%M:%S') for record in secondary_records
        ) + "]"
        
        return primary_content + merge_info + dates_info
    
    def generate_report(self, analysis_result: Dict, output_file: str = None) -> str:
        """Generate comprehensive deduplication report"""
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_records': analysis_result['total_records'],
                'duplicate_groups': len(analysis_result['duplicate_groups']),
                'duplicate_records': analysis_result['duplicate_records'],
                'duplicate_rate': round(analysis_result['duplicate_rate'], 2)
            },
            'analysis_details': analysis_result,
            'recommendations': self._generate_recommendations(analysis_result)
        }
        
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"deduplication_report_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        return output_file
    
    def _generate_recommendations(self, analysis_result: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        duplicate_rate = analysis_result['duplicate_rate']
        
        if duplicate_rate > 10:
            recommendations.append(f"HIGH duplicate rate ({duplicate_rate:.1f}%) - immediate action required")
        elif duplicate_rate > 5:
            recommendations.append(f"MEDIUM duplicate rate ({duplicate_rate:.1f}%) - schedule cleanup")
        elif duplicate_rate > 1:
            recommendations.append(f"LOW duplicate rate ({duplicate_rate:.1f}%) - monitor trends")
        else:
            recommendations.append("EXCELLENT data quality - maintain current practices")
        
        if analysis_result['duplicate_groups']:
            recommendations.append("Consider implementing real-time duplicate prevention")
            recommendations.append("Schedule regular deduplication maintenance")
        
        recommendations.append("Monitor system performance after resolution")
        recommendations.append("Consider adjusting similarity thresholds based on results")
        
        return recommendations

def main():
    """CLI interface for deduplication engine"""
    parser = argparse.ArgumentParser(description='Intelligent Deduplication Engine')
    parser.add_argument('--config', default='config.json', help='Configuration file path')
    parser.add_argument('--analyze', action='store_true', help='Run duplicate analysis')
    parser.add_argument('--resolve', choices=['keep_latest', 'merge', 'flag_only'], help='Resolution strategy')
    parser.add_argument('--table', default='observations', help='Table name to process')
    parser.add_argument('--column', default='content', help='Content column name')
    parser.add_argument('--entity-filter', help='Filter by entity name')
    parser.add_argument('--dry-run', action='store_true', help='Simulation mode (no changes)')
    parser.add_argument('--output', help='Output report file')
    
    args = parser.parse_args()
    
    # Initialize engine
    engine = IntelligentDeduplicationEngine(args.config)
    
    if args.analyze:
        print("🔍 Running duplicate analysis...")
        
        # Run analysis
        results = engine.find_duplicates(
            table_name=args.table,
            content_column=args.column,
            entity_filter=args.entity_filter
        )
        
        # Display results
        print(f"\n📊 ANALYSIS RESULTS:")
        print(f"   Total records: {results['total_records']}")
        print(f"   Duplicate groups: {len(results['duplicate_groups'])}")
        print(f"   Duplicate rate: {results['duplicate_rate']:.2f}%")
        
        # Generate report
        report_file = engine.generate_report(results, args.output)
        print(f"\n📄 Report saved: {report_file}")
        
        # Resolution if requested
        if args.resolve:
            print(f"\n⚙️ Applying resolution strategy: {args.resolve}")
            
            resolution_result = engine.resolve_duplicates(
                results, 
                strategy=args.resolve,
                dry_run=args.dry_run
            )
            
            if resolution_result['action'] in ['resolution_applied', 'dry_run_completed']:
                print(f"✅ Resolution completed:")
                print(f"   Groups processed: {resolution_result['groups_processed']}")
                print(f"   Records affected: {resolution_result['records_affected']}")
                
                if args.dry_run:
                    print("   Mode: DRY RUN (no actual changes)")
            else:
                print(f"❌ Resolution failed: {resolution_result.get('message', 'Unknown error')}")
    
    else:
        print("Use --analyze to run duplicate detection")
        print("Use --help for full options")

if __name__ == "__main__":
    main()