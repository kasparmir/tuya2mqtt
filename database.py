"""SQLite database for persistent state storage"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class Database:
    """Manages SQLite database for device states and history"""
    
    def __init__(self, db_path: str = 'tuya2mqtt.db'):
        self.db_path = db_path
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """Initialize database schema"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            cursor = self.conn.cursor()
            
            # Devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    version TEXT,
                    last_seen TIMESTAMP,
                    available INTEGER DEFAULT 1,
                    config TEXT
                )
            ''')
            
            # Entity states table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS entity_states (
                    entity_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    state TEXT,
                    attributes TEXT,
                    last_updated TIMESTAMP,
                    FOREIGN KEY (device_id) REFERENCES devices(device_id)
                )
            ''')
            
            # State history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    state TEXT,
                    attributes TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (entity_id) REFERENCES entity_states(entity_id)
                )
            ''')
            
            # Events table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT,
                    event_type TEXT NOT NULL,
                    data TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state_history_entity ON state_history(entity_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state_history_timestamp ON state_history(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_device ON events(device_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
            
            self.conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def save_device(self, device_id: str, name: str, ip: str, version: str, config: Dict[str, Any]):
        """Save or update device"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO devices (device_id, name, ip, version, last_seen, available, config)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            ''', (device_id, name, ip, version, datetime.now(), json.dumps(config)))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save device: {e}")
    
    def save_entity_state(self, entity_id: str, device_id: str, platform: str, 
                         state: Any, attributes: Dict[str, Any]):
        """Save entity state"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO entity_states 
                (entity_id, device_id, platform, state, attributes, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (entity_id, device_id, platform, json.dumps(state), 
                  json.dumps(attributes), datetime.now()))
            
            # Save to history
            cursor.execute('''
                INSERT INTO state_history (entity_id, state, attributes)
                VALUES (?, ?, ?)
            ''', (entity_id, json.dumps(state), json.dumps(attributes)))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save entity state: {e}")
    
    def get_entity_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity state"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM entity_states WHERE entity_id = ?', (entity_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'entity_id': row['entity_id'],
                    'device_id': row['device_id'],
                    'platform': row['platform'],
                    'state': json.loads(row['state']),
                    'attributes': json.loads(row['attributes']),
                    'last_updated': row['last_updated']
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get entity state: {e}")
            return None
    
    def get_entity_history(self, entity_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get entity history"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM state_history 
                WHERE entity_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (entity_id, limit))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'id': row['id'],
                    'entity_id': row['entity_id'],
                    'state': json.loads(row['state']),
                    'attributes': json.loads(row['attributes']),
                    'timestamp': row['timestamp']
                })
            return history
        except Exception as e:
            logger.error(f"Failed to get entity history: {e}")
            return []
    
    def log_event(self, device_id: str, event_type: str, data: Dict[str, Any]):
        """Log an event"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO events (device_id, event_type, data)
                VALUES (?, ?, ?)
            ''', (device_id, event_type, json.dumps(data)))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as count FROM devices')
            devices_count = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM entity_states')
            entities_count = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM state_history')
            history_count = cursor.fetchone()['count']
            
            cursor.execute('SELECT COUNT(*) as count FROM events')
            events_count = cursor.fetchone()['count']
            
            return {
                'devices': devices_count,
                'entities': entities_count,
                'history_records': history_count,
                'events': events_count
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def cleanup_old_history(self, days: int = 30):
        """Clean up old history records"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                DELETE FROM state_history 
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            ''', (days,))
            cursor.execute('''
                DELETE FROM events 
                WHERE timestamp < datetime('now', '-' || ? || ' days')
            ''', (days,))
            self.conn.commit()
            logger.info(f"Cleaned up history older than {days} days")
        except Exception as e:
            logger.error(f"Failed to cleanup history: {e}")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
