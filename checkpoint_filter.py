#!/usr/bin/env python3
"""
Intelligent Checkpoint Filter
Pattern recognition and consolidation for repetitive data

This is an open-source component extracted from a production Claude Memory System.
All sensitive information has been removed and made configurable.
"""

import json
import os
import re
import hashlib
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

try:
    import psycopg2
except ImportError:
    print("Missing dependencies. Install with: pip install psycopg2-binary")
    exit(1)

class CheckpointFilter:
    """
    Intelligent filter for consolidating repetitive checkpoint data
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize checkpoint filter with configuration"""
        self.config = self.load_config(config_path)
        
        # Pattern detection configuration
        self.checkpoint_patterns = self.config.get('checkpoint_patterns', [
            r'CHECKPOINT\s+\w+\s+\w+\s+\d+\s+\d+:\d+:\d+\s+\w+\s+\d+:\s+auto-sync',
            r'Sincronización automática cada \d+ min',
            r'auto-sync - Sincronización automática',
            r'SYNC:\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',
            r'Checkpoint\s+\d+\s+completed',
            r'Auto-save\s+at\s+\d{4}-\d{2}-\d{2}'
        ])
        
        self.consolidation_threshold = self.config.get('consolidation_threshold', 5)
    
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
            "consolidation_threshold": 5,
            "checkpoint_patterns": [
                r'CHECKPOINT\s+\w+\s+\w+\s+\d+\s+\d+:\d+:\d+\s+\w+\s+\d+:\s+auto-sync',
                r'Sincronización automática cada \d+ min',
                r'auto-sync - Sincronización automática'
            ],
            "processing": {
                "batch_size": 1000,
                "time_window_days": 30
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
    
    def is_checkpoint_observation(self, text: str) -> bool:
        """Determine if text is a checkpoint observation"""
        for pattern in self.checkpoint_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def generate_checkpoint_signature(self, text: str) -> str:
        """Generate unique signature for similar checkpoints"""
        # Normalize by removing variable parts
        normalized = text
        
        # Replace timestamps with placeholder
        normalized = re.sub(r'\w+\s+\w+\s+\d+\s+\d+:\d+:\d+\s+\w+\s+\d+', 'TIMESTAMP', normalized)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', 'DATETIME', normalized)
        normalized = re.sub(r'\d{2}:\d{2}:\d{2}', 'TIME', normalized)
        normalized = re.sub(r'\d+', 'NUM', normalized)
        
        # Create hash of normalized signature
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def analyze_checkpoint_redundancy(self, table_name: str = "observations", 
                                    content_column: str = "content") -> Dict:
        """Analyze redundancy in checkpoint data"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        # Get all observations
        query = f"""
            SELECT id, {content_column}, created_at 
            FROM {table_name} 
            ORDER BY created_at DESC
        """
        
        cursor.execute(query)
        observations = cursor.fetchall()
        
        checkpoint_groups = defaultdict(list)
        regular_observations = []
        
        for obs_id, content, created_at in observations:
            if self.is_checkpoint_observation(content):
                signature = self.generate_checkpoint_signature(content)
                checkpoint_groups[signature].append({
                    'id': obs_id,
                    'content': content,
                    'created_at': created_at
                })
            else:
                regular_observations.append({
                    'id': obs_id,
                    'content': content,
                    'created_at': created_at
                })
        
        # Analyze redundancy
        analysis = {
            'total_observations': len(observations),
            'checkpoint_observations': sum(len(group) for group in checkpoint_groups.values()),
            'regular_observations': len(regular_observations),
            'checkpoint_groups': len(checkpoint_groups),
            'redundant_checkpoints': sum(len(group) - 1 for group in checkpoint_groups.values() if len(group) > 1),
            'groups_analysis': {}
        }
        
        # Detailed analysis per group
        for signature, group in checkpoint_groups.items():
            if len(group) > 1:
                analysis['groups_analysis'][signature] = {
                    'count': len(group),
                    'first_occurrence': min(obs['created_at'] for obs in group),
                    'last_occurrence': max(obs['created_at'] for obs in group),
                    'sample_content': group[0]['content'][:100] + '...',
                    'frequency': self._calculate_frequency(group)
                }
        
        conn.close()
        return analysis
    
    def _calculate_frequency(self, group: List[Dict]) -> str:
        """Calculate frequency of checkpoint group"""
        if len(group) < 2:
            return "N/A"
        
        timestamps = [obs['created_at'] for obs in group]
        timestamps.sort()
        
        # Calculate average intervals
        intervals = []
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i-1]
            intervals.append(diff.total_seconds() / 60)  # minutes
        
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        return f"~{avg_interval:.1f} min"
    
    def create_checkpoint_summary(self, group: List[Dict]) -> Dict:
        """Create consolidated summary for checkpoint group"""
        if not group:
            return None
        
        first_obs = min(group, key=lambda x: x['created_at'])
        last_obs = max(group, key=lambda x: x['created_at'])
        
        summary = {
            'type': 'checkpoint_summary',
            'pattern': self.generate_checkpoint_signature(first_obs['content']),
            'count': len(group),
            'first_occurrence': first_obs['created_at'],
            'last_occurrence': last_obs['created_at'],
            'frequency': self._calculate_frequency(group),
            'sample_content': first_obs['content'],
            'consolidated_content': f"SUMMARY: {len(group)} automatic checkpoints from {first_obs['created_at'].strftime('%Y-%m-%d %H:%M')} to {last_obs['created_at'].strftime('%Y-%m-%d %H:%M')} - {self._calculate_frequency(group)}"
        }
        
        return summary
    
    def apply_checkpoint_filtering(self, table_name: str = "observations",
                                 content_column: str = "content",
                                 dry_run: bool = True) -> Dict:
        """Apply checkpoint filtering and consolidation"""
        analysis = self.analyze_checkpoint_redundancy(table_name, content_column)
        
        if analysis['redundant_checkpoints'] < self.consolidation_threshold:
            return {
                'action': 'no_action_needed',
                'message': f'Only {analysis["redundant_checkpoints"]} redundant checkpoints (threshold: {self.consolidation_threshold})',
                'analysis': analysis
            }
        
        conn = self.connect_db()
        cursor = conn.cursor()
        
        actions_taken = []
        space_saved = 0
        
        try:
            for signature, group_info in analysis['groups_analysis'].items():
                if group_info['count'] > 1:
                    # Get full group data
                    cursor.execute(f"""
                        SELECT id, {content_column}, created_at 
                        FROM {table_name} 
                        WHERE {content_column} LIKE %s
                        ORDER BY created_at
                    """, (f"%{group_info['sample_content'][:50]}%",))
                    
                    group_records = cursor.fetchall()
                    
                    if len(group_records) > 1:
                        # Create consolidated summary
                        group_data = [
                            {
                                'id': record[0],
                                'content': record[1],
                                'created_at': record[2]
                            } for record in group_records
                        ]
                        
                        summary = self.create_checkpoint_summary(group_data)
                        
                        if not dry_run:
                            # Insert consolidated record
                            cursor.execute(f"""
                                INSERT INTO {table_name} ({content_column}, created_at)
                                VALUES (%s, %s)
                            """, (
                                summary['consolidated_content'],
                                summary['last_occurrence']
                            ))
                            
                            # Mark original records as consolidated
                            record_ids = [record[0] for record in group_records]
                            cursor.execute(f"""
                                UPDATE {table_name} 
                                SET {content_column} = {content_column} || ' [CONSOLIDATED]'
                                WHERE id = ANY(%s)
                            """, (record_ids,))
                        
                        actions_taken.append({
                            'action': 'consolidate_group',
                            'group_signature': signature,
                            'records_affected': len(group_records),
                            'space_saved_chars': sum(len(record[1]) for record in group_records) - len(summary['consolidated_content'])
                        })
                        
                        space_saved += sum(len(record[1]) for record in group_records) - len(summary['consolidated_content'])
            
            if not dry_run:
                conn.commit()
                
        except Exception as e:
            conn.rollback()
            return {
                'action': 'error',
                'message': f'Error applying filters: {str(e)}',
                'analysis': analysis
            }
        finally:
            conn.close()
        
        return {
            'action': 'filtering_applied' if not dry_run else 'dry_run_completed',
            'actions_taken': actions_taken,
            'space_saved_chars': space_saved,
            'redundant_checkpoints_processed': len(actions_taken),
            'analysis': analysis
        }
    
    def generate_filtering_report(self, table_name: str = "observations",
                                content_column: str = "content") -> Dict:
        """Generate comprehensive filtering report"""
        analysis = self.analyze_checkpoint_redundancy(table_name, content_column)
        filtering_preview = self.apply_checkpoint_filtering(table_name, content_column, dry_run=True)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'system_stats': {
                'total_observations': analysis['total_observations'],
                'checkpoint_percentage': round((analysis['checkpoint_observations'] / analysis['total_observations']) * 100, 1) if analysis['total_observations'] > 0 else 0,
                'redundancy_rate': round((analysis['redundant_checkpoints'] / analysis['checkpoint_observations']) * 100, 1) if analysis['checkpoint_observations'] > 0 else 0
            },
            'redundancy_analysis': analysis,
            'filtering_preview': filtering_preview,
            'recommendations': self._generate_recommendations(analysis, filtering_preview)
        }
        
        return report
    
    def _generate_recommendations(self, analysis: Dict, filtering_result: Dict) -> List[str]:
        """Generate recommendations based on analysis"""
        recommendations = []
        
        checkpoint_percentage = (analysis['checkpoint_observations'] / analysis['total_observations']) * 100 if analysis['total_observations'] > 0 else 0
        
        if checkpoint_percentage > 60:
            recommendations.append(f"HIGH checkpoint ratio ({checkpoint_percentage:.1f}%) - consider consolidation")
        
        if analysis['redundant_checkpoints'] > 10:
            recommendations.append(f"MANY redundant checkpoints ({analysis['redundant_checkpoints']}) - apply filtering")
        
        if len(analysis['groups_analysis']) > 5:
            recommendations.append(f"MULTIPLE patterns ({len(analysis['groups_analysis'])}) - review checkpoint configuration")
        
        estimated_savings = filtering_result.get('space_saved_chars', 0)
        if estimated_savings > 1000:
            recommendations.append(f"SIGNIFICANT space savings: {estimated_savings:,} characters (~{estimated_savings/1000:.1f}KB)")
        
        recommendations.append("AUTOMATION: Configure automatic filtering for future checkpoints")
        recommendations.append("MONITORING: Implement quality metrics post-filtering")
        
        return recommendations
    
    def save_report(self, report: Dict, filename: str = None) -> str:
        """Save filtering report to file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"checkpoint_filtering_report_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        return filename

def main():
    """CLI interface for checkpoint filter"""
    parser = argparse.ArgumentParser(description='Intelligent Checkpoint Filter')
    parser.add_argument('--config', default='config.json', help='Configuration file path')
    parser.add_argument('--analyze', action='store_true', help='Run checkpoint analysis')
    parser.add_argument('--apply', action='store_true', help='Apply filtering')
    parser.add_argument('--table', default='observations', help='Table name to process')
    parser.add_argument('--column', default='content', help='Content column name')
    parser.add_argument('--dry-run', action='store_true', help='Simulation mode (no changes)')
    parser.add_argument('--output', help='Output report file')
    
    args = parser.parse_args()
    
    # Initialize filter
    filter_engine = CheckpointFilter(args.config)
    
    if args.analyze:
        print("📊 Analyzing checkpoint redundancy...")
        
        # Generate report
        report = filter_engine.generate_filtering_report(args.table, args.column)
        
        # Display results
        print(f"\n📈 SYSTEM STATISTICS:")
        stats = report['system_stats']
        print(f"   Total observations: {stats['total_observations']}")
        print(f"   Checkpoint percentage: {stats['checkpoint_percentage']}%")
        print(f"   Redundancy rate: {stats['redundancy_rate']}%")
        
        print(f"\n🔍 REDUNDANCY ANALYSIS:")
        analysis = report['redundancy_analysis']
        print(f"   Redundant checkpoints: {analysis['redundant_checkpoints']}")
        print(f"   Pattern groups: {analysis['checkpoint_groups']}")
        
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"   {rec}")
        
        # Save report
        filename = filter_engine.save_report(report, args.output)
        print(f"\n📄 Report saved: {filename}")
        
        # Apply filtering if requested
        if args.apply:
            print(f"\n⚙️ Applying checkpoint filtering...")
            
            result = filter_engine.apply_checkpoint_filtering(
                table_name=args.table,
                content_column=args.column,
                dry_run=args.dry_run
            )
            
            if result['action'] == 'filtering_applied':
                print("✅ Filtering applied successfully")
                print(f"   Groups processed: {result['redundant_checkpoints_processed']}")
                print(f"   Space saved: {result['space_saved_chars']:,} characters")
                
                if args.dry_run:
                    print("   Mode: DRY RUN (no actual changes)")
            elif result['action'] == 'no_action_needed':
                print(f"ℹ️  {result['message']}")
            else:
                print(f"❌ Error: {result.get('message', 'Unknown error')}")
    
    else:
        print("Use --analyze to run checkpoint analysis")
        print("Use --help for full options")

if __name__ == "__main__":
    main()