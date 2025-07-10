#!/usr/bin/env python3
"""
Effectiveness Monitor
Real-time monitoring and analytics for optimization systems

This is an open-source component extracted from a production Claude Memory System.
All sensitive information has been removed and made configurable.
"""

import json
import os
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

try:
    import psycopg2
except ImportError:
    print("Missing dependencies. Install with: pip install psycopg2-binary")
    exit(1)

class EffectivenessMonitor:
    """
    Monitor effectiveness of optimization systems with trend analysis
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize effectiveness monitor with configuration"""
        self.config = self.load_config(config_path)
        
        self.reports_path = self.config.get('reports_path', 'reports')
        self.metrics_history_file = os.path.join(self.reports_path, 'effectiveness_metrics_history.json')
        
        # Create reports directory if it doesn't exist
        os.makedirs(self.reports_path, exist_ok=True)
    
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
            "reports_path": "reports",
            "monitoring": {
                "history_limit": 30,
                "trend_analysis_days": 7
            },
            "thresholds": {
                "duplicate_rate_warning": 5.0,
                "checkpoint_rate_warning": 70.0,
                "processing_rate_target": 10.0
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
    
    def get_current_metrics(self, table_name: str = "observations",
                          content_column: str = "content") -> Dict:
        """Collect current system metrics"""
        conn = self.connect_db()
        cursor = conn.cursor()
        
        # General statistics
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_records,
                AVG(LENGTH({content_column})) as avg_text_length,
                MIN(created_at) as oldest_record,
                MAX(created_at) as newest_record
            FROM {table_name}
        """)
        
        general_stats = cursor.fetchone()
        
        # Checkpoint analysis
        cursor.execute(f"""
            SELECT COUNT(*) as checkpoint_count
            FROM {table_name} 
            WHERE {content_column} LIKE '%CHECKPOINT%' 
               OR {content_column} LIKE '%auto-sync%'
               OR {content_column} LIKE '%checkpoint%'
        """)
        
        checkpoint_stats = cursor.fetchone()
        
        # Duplicate analysis (simple exact matches)
        cursor.execute(f"""
            SELECT {content_column}, COUNT(*) as occurrences
            FROM {table_name} 
            GROUP BY {content_column}
            HAVING COUNT(*) > 1
        """)
        
        duplicates = cursor.fetchall()
        
        # Processed observations (marked as consolidated, archived, etc.)
        cursor.execute(f"""
            SELECT COUNT(*) as processed_count
            FROM {table_name} 
            WHERE {content_column} LIKE '%[CONSOLIDATED]%'
               OR {content_column} LIKE '%[ARCHIVED%'
               OR {content_column} LIKE '%[MERGED%'
               OR {content_column} LIKE '%[DUPLICATE%'
        """)
        
        processed_stats = cursor.fetchone()
        
        # Daily activity (last 7 days)
        cursor.execute(f"""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as daily_count
            FROM {table_name} 
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """)
        
        daily_activity = cursor.fetchall()
        
        conn.close()
        
        # Calculate metrics
        total_records = general_stats[0] or 0
        checkpoint_count = checkpoint_stats[0] or 0
        total_duplicates = sum(count - 1 for _, count in duplicates)
        processed_count = processed_stats[0] or 0
        
        return {
            'timestamp': datetime.now().isoformat(),
            'general': {
                'total_records': total_records,
                'avg_text_length': round(float(general_stats[1]) if general_stats[1] else 0, 2),
                'oldest_record': general_stats[2].isoformat() if general_stats[2] else None,
                'newest_record': general_stats[3].isoformat() if general_stats[3] else None
            },
            'checkpoints': {
                'total_checkpoints': checkpoint_count,
                'checkpoint_percentage': round((checkpoint_count / total_records * 100), 2) if total_records > 0 else 0
            },
            'duplicates': {
                'duplicate_groups': len(duplicates),
                'total_duplicates': total_duplicates,
                'duplicate_rate': round((total_duplicates / total_records * 100), 2) if total_records > 0 else 0
            },
            'processed': {
                'processed_records': processed_count,
                'processing_rate': round((processed_count / total_records * 100), 2) if total_records > 0 else 0
            },
            'activity': {
                'daily_counts': [
                    {'date': date.isoformat() if date else None, 'count': count}
                    for date, count in daily_activity
                ],
                'avg_daily_activity': round(sum(count for _, count in daily_activity) / len(daily_activity), 2) if daily_activity else 0
            }
        }
    
    def load_metrics_history(self) -> List[Dict]:
        """Load historical metrics"""
        if os.path.exists(self.metrics_history_file):
            try:
                with open(self.metrics_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
    
    def save_metrics_history(self, history: List[Dict]):
        """Save metrics history"""
        with open(self.metrics_history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False, default=str)
    
    def calculate_effectiveness(self, current_metrics: Dict, history: List[Dict]) -> Dict:
        """Calculate optimization effectiveness"""
        if len(history) < 2:
            return {
                'effectiveness_score': 'N/A',
                'message': 'Insufficient history for effectiveness analysis',
                'trends': {}
            }
        
        # Compare with previous metrics
        previous_metrics = history[-2] if len(history) >= 2 else history[-1]
        baseline_metrics = history[0] if len(history) > 0 else current_metrics
        
        # Calculate trends
        trends = {}
        
        # Duplicate rate trend
        if previous_metrics['duplicates']['duplicate_rate'] > 0:
            duplicate_improvement = (
                (previous_metrics['duplicates']['duplicate_rate'] - current_metrics['duplicates']['duplicate_rate']) /
                previous_metrics['duplicates']['duplicate_rate'] * 100
            )
            trends['duplicate_reduction'] = round(duplicate_improvement, 2)
        else:
            trends['duplicate_reduction'] = 0
        
        # Checkpoint optimization trend
        if previous_metrics['checkpoints']['checkpoint_percentage'] > 0:
            checkpoint_improvement = (
                (previous_metrics['checkpoints']['checkpoint_percentage'] - current_metrics['checkpoints']['checkpoint_percentage']) /
                previous_metrics['checkpoints']['checkpoint_percentage'] * 100
            )
            trends['checkpoint_optimization'] = round(checkpoint_improvement, 2)
        else:
            trends['checkpoint_optimization'] = 0
        
        # Processing activity trend
        processing_increase = (
            current_metrics['processed']['processing_rate'] - previous_metrics['processed']['processing_rate']
        )
        trends['processing_increase'] = round(processing_increase, 2)
        
        # Calculate effectiveness score (0-100)
        effectiveness_components = {
            'duplicate_reduction': max(0, min(trends['duplicate_reduction'], 50)),  # Max 50 points
            'checkpoint_optimization': max(0, min(trends['checkpoint_optimization'], 30)),  # Max 30 points
            'processing_activity': max(0, min(trends['processing_increase'] * 2, 20))  # Max 20 points
        }
        
        effectiveness_score = sum(effectiveness_components.values())
        
        return {
            'effectiveness_score': round(effectiveness_score, 1),
            'effectiveness_grade': self._get_effectiveness_grade(effectiveness_score),
            'trends': trends,
            'components': effectiveness_components,
            'comparison_period': {
                'baseline_date': baseline_metrics['timestamp'],
                'previous_date': previous_metrics['timestamp'],
                'current_date': current_metrics['timestamp']
            }
        }
    
    def _get_effectiveness_grade(self, score: float) -> str:
        """Get effectiveness grade based on score"""
        if score >= 80:
            return "Excellent"
        elif score >= 60:
            return "Good"
        elif score >= 40:
            return "Fair"
        elif score >= 20:
            return "Poor"
        else:
            return "Very Poor"
    
    def generate_optimization_recommendations(self, metrics: Dict, effectiveness: Dict) -> List[str]:
        """Generate recommendations based on metrics and effectiveness"""
        recommendations = []
        thresholds = self.config['thresholds']
        
        # Duplicate rate recommendations
        if metrics['duplicates']['duplicate_rate'] > thresholds['duplicate_rate_warning']:
            recommendations.append(f"HIGH duplicate rate ({metrics['duplicates']['duplicate_rate']}%) - run deduplication more frequently")
        
        # Checkpoint recommendations
        if metrics['checkpoints']['checkpoint_percentage'] > thresholds['checkpoint_rate_warning']:
            recommendations.append(f"MANY checkpoints ({metrics['checkpoints']['checkpoint_percentage']}%) - consider automatic consolidation")
        
        # Processing rate recommendations
        if metrics['processed']['processing_rate'] < thresholds['processing_rate_target']:
            recommendations.append(f"LOW processing rate ({metrics['processed']['processing_rate']}%) - increase optimization frequency")
        
        # Effectiveness-based recommendations
        if isinstance(effectiveness['effectiveness_score'], (int, float)):
            if effectiveness['effectiveness_score'] < 40:
                recommendations.append("LOW effectiveness - review optimization configuration")
                recommendations.append("CONSIDER adjusting similarity thresholds and consolidation rules")
            elif effectiveness['effectiveness_score'] > 80:
                recommendations.append("EXCELLENT effectiveness - maintain current configuration")
        
        # Activity-based recommendations
        if metrics['activity']['avg_daily_activity'] < 1:
            recommendations.append("VERY LOW daily activity - verify data input systems")
        
        if not recommendations:
            recommendations.append("SYSTEM optimal - continue regular monitoring")
        
        return recommendations
    
    def run_effectiveness_monitoring(self, table_name: str = "observations",
                                   content_column: str = "content") -> Dict:
        """Run complete effectiveness monitoring cycle"""
        
        # Collect current metrics
        current_metrics = self.get_current_metrics(table_name, content_column)
        
        # Load historical metrics
        history = self.load_metrics_history()
        
        # Add current metrics to history
        history.append(current_metrics)
        
        # Maintain history limit
        history_limit = self.config['monitoring']['history_limit']
        if len(history) > history_limit:
            history = history[-history_limit:]
        
        # Save updated history
        self.save_metrics_history(history)
        
        # Calculate effectiveness
        effectiveness = self.calculate_effectiveness(current_metrics, history)
        
        # Generate recommendations
        recommendations = self.generate_optimization_recommendations(current_metrics, effectiveness)
        
        # Create comprehensive report
        report = {
            'monitoring_timestamp': datetime.now().isoformat(),
            'current_metrics': current_metrics,
            'effectiveness_analysis': effectiveness,
            'recommendations': recommendations,
            'metrics_history_length': len(history),
            'configuration_used': {
                'table_name': table_name,
                'content_column': content_column,
                'thresholds': self.config['thresholds']
            }
        }
        
        return report
    
    def save_report(self, report: Dict, filename: str = None) -> str:
        """Save effectiveness report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.reports_path, f"effectiveness_report_{timestamp}.json")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        return filename
    
    def display_monitoring_results(self, report: Dict):
        """Display monitoring results in console"""
        print("📊 EFFECTIVENESS MONITORING RESULTS")
        print("=" * 50)
        
        # Current metrics
        metrics = report['current_metrics']
        print(f"\n📈 CURRENT METRICS:")
        print(f"   Total records: {metrics['general']['total_records']}")
        print(f"   Duplicate rate: {metrics['duplicates']['duplicate_rate']}%")
        print(f"   Checkpoint rate: {metrics['checkpoints']['checkpoint_percentage']}%")
        print(f"   Processing rate: {metrics['processed']['processing_rate']}%")
        print(f"   Avg daily activity: {metrics['activity']['avg_daily_activity']}")
        
        # Effectiveness analysis
        effectiveness = report['effectiveness_analysis']
        if isinstance(effectiveness['effectiveness_score'], (int, float)):
            print(f"\n🎯 EFFECTIVENESS ANALYSIS:")
            print(f"   Overall score: {effectiveness['effectiveness_score']}/100")
            print(f"   Grade: {effectiveness['effectiveness_grade']}")
            
            print(f"\n📈 TRENDS:")
            for trend_name, trend_value in effectiveness['trends'].items():
                trend_emoji = "📈" if trend_value > 0 else "📉" if trend_value < 0 else "➡️"
                print(f"   {trend_emoji} {trend_name}: {trend_value:+.1f}%")
        else:
            print(f"\n🎯 EFFECTIVENESS: {effectiveness['message']}")
        
        # Recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        for rec in report['recommendations']:
            print(f"   • {rec}")
        
        print(f"\n📊 History: {report['metrics_history_length']} data points")

def main():
    """CLI interface for effectiveness monitor"""
    parser = argparse.ArgumentParser(description='Effectiveness Monitor')
    parser.add_argument('--config', default='config.json', help='Configuration file path')
    parser.add_argument('--report', action='store_true', help='Generate effectiveness report')
    parser.add_argument('--table', default='observations', help='Table name to monitor')
    parser.add_argument('--column', default='content', help='Content column name')
    parser.add_argument('--output', help='Output report file')
    parser.add_argument('--quiet', action='store_true', help='Suppress console output')
    
    args = parser.parse_args()
    
    # Initialize monitor
    monitor = EffectivenessMonitor(args.config)
    
    if args.report:
        print("📊 Running effectiveness monitoring...")
        
        # Run monitoring
        report = monitor.run_effectiveness_monitoring(args.table, args.column)
        
        # Display results (unless quiet mode)
        if not args.quiet:
            monitor.display_monitoring_results(report)
        
        # Save report
        filename = monitor.save_report(report, args.output)
        print(f"\n📄 Report saved: {filename}")
        
    else:
        print("Use --report to run effectiveness monitoring")
        print("Use --help for full options")

if __name__ == "__main__":
    main()