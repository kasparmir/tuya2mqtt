"""Device management with extended platform support"""

import logging
import threading
import time
from typing import Dict, Any, Optional, Callable
from datetime import datetime

import tinytuya

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = [
    'light', 'switch', 'fan', 'sensor', 'binary_sensor',
    'climate', 'cover', 'lock', 'alarm_control_panel',
    'vacuum', 'camera', 'humidifier', 'water_heater',
    'button', 'number', 'select'
]


class Entity:
    """Represents a Home Assistant entity with DPS mapping"""
    
    def __init__(self, device_id: str, entity_config: Dict[str, Any]):
        self.device_id = device_id
        self.platform = entity_config.get('platform', 'switch')
        self.name = entity_config.get('name', 'entity')
        self.friendly_name = entity_config.get('friendly_name', self.name)
        self.dps_map = entity_config.get('dps', {})
        self.icon = entity_config.get('icon', 'mdi:help-circle')
        
        # Common attributes
        self.unit_of_measurement = entity_config.get('unit_of_measurement')
        self.device_class = entity_config.get('device_class')
        self.scale = entity_config.get('scale', 1.0)
        
        # Light/Fan attributes
        self.brightness_range = entity_config.get('brightness_range', [10, 1000])
        self.color_temp_range = entity_config.get('color_temp_range', [0, 1000])
        self.speed_range = entity_config.get('speed_range', [1, 3])
        
        # Climate attributes
        self.temperature_unit = entity_config.get('temperature_unit', 'C')
        self.temp_range = entity_config.get('temp_range', [16, 30])
        self.temp_step = entity_config.get('temp_step', 0.5)
        self.modes = entity_config.get('modes', [])
        self.fan_modes = entity_config.get('fan_modes', [])
        
        # Alarm attributes
        self.states = entity_config.get('states', {})
        
        # Vacuum attributes
        self.vacuum_modes = entity_config.get('modes', [])
        
        # Cover attributes
        self.position_range = entity_config.get('position_range', [0, 100])
        
        # Number attributes
        self.min_value = entity_config.get('min', 0)
        self.max_value = entity_config.get('max', 100)
        self.step = entity_config.get('step', 1)
        
        # Select attributes
        self.options = entity_config.get('options', [])
        
        # Camera attributes
        self.stream_url = entity_config.get('stream_url')
        
        # Humidifier attributes
        self.humidity_range = entity_config.get('humidity_range', [30, 80])
        
        self.state = {}
        
    @property
    def entity_id(self) -> str:
        """Generate entity ID"""
        return f"{self.device_id}_{self.name}"
    
    def get_dps(self, key: str) -> Optional[int]:
        """Get DPS number for a key"""
        return self.dps_map.get(key)
    
    def update_state(self, dps_values: Dict[int, Any]):
        """Update entity state from DPS values"""
        self.state = {}
        
        for key, dps_num in self.dps_map.items():
            if dps_num in dps_values:
                value = dps_values[dps_num]
                
                # Apply scaling if needed
                if self.scale != 1.0 and isinstance(value, (int, float)):
                    value = value * self.scale
                
                self.state[key] = value
    
    def get_state_value(self) -> Any:
        """Get main state value based on platform"""
        if self.platform in ['light', 'switch', 'fan', 'lock']:
            return self.state.get('switch', False) or self.state.get('lock', False)
        elif self.platform in ['sensor', 'number']:
            return self.state.get('value', 0)
        elif self.platform == 'binary_sensor':
            return self.state.get('state', False)
        elif self.platform == 'cover':
            return self.state.get('position', 0)
        elif self.platform == 'climate':
            return self.state.get('current_temp', 20)
        elif self.platform == 'alarm_control_panel':
            return self.state.get('state', 'disarmed')
        elif self.platform == 'vacuum':
            return self.state.get('status', 'docked')
        elif self.platform == 'select':
            return self.state.get('option', self.options[0] if self.options else '')
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary"""
        return {
            'entity_id': self.entity_id,
            'platform': self.platform,
            'name': self.name,
            'friendly_name': self.friendly_name,
            'icon': self.icon,
            'state': self.state,
            'dps_map': self.dps_map,
            'unit_of_measurement': self.unit_of_measurement,
            'device_class': self.device_class
        }


class TuyaDevice:
    """Represents a Tuya device with entities"""
    
    def __init__(self, device_id: str, config: Dict[str, Any], database=None):
        self.device_id = device_id
        self.name = config.get('name', device_id)
        self.ip = config['ip']
        self.local_key = config['local_key']
        self.version = config.get('version', '3.3')
        self.database = database
        
        # Initialize Tuya device connection
        self.device = tinytuya.Device(
            dev_id=device_id,
            address=self.ip,
            local_key=self.local_key,
            version=self.version
        )
        self.device.set_socketPersistent(True)
        
        # Create entities from config
        self.entities = []
        for entity_config in config.get('entities', []):
            entity = Entity(device_id, entity_config)
            self.entities.append(entity)
        
        self.last_state = {}
        self.last_update = None
        self.available = True
        
        # Save to database if available
        if self.database:
            self.database.save_device(device_id, self.name, self.ip, self.version, config)
    
    def get_status(self) -> Optional[Dict[int, Any]]:
        """Get current device status"""
        try:
            status = self.device.status()
            if status and 'dps' in status:
                self.last_state = status['dps']
                self.last_update = datetime.now()
                self.available = True
                
                # Update all entities
                for entity in self.entities:
                    entity.update_state(self.last_state)
                    
                    # Save entity state to database
                    if self.database:
                        self.database.save_entity_state(
                            entity.entity_id,
                            self.device_id,
                            entity.platform,
                            entity.get_state_value(),
                            entity.state
                        )
                
                # Log event
                if self.database:
                    self.database.log_event(
                        self.device_id,
                        'state_update',
                        {'dps': self.last_state}
                    )
                
                return self.last_state
            self.available = False
            return None
        except Exception as e:
            logger.error(f"Error getting status for {self.name}: {e}")
            self.available = False
            return None
    
    def set_dps(self, dps: int, value: Any) -> bool:
        """Set a DPS value"""
        try:
            result = self.device.set_value(dps, value)
            logger.info(f"Set {self.name} DPS {dps} to {value}")
            
            if self.database:
                self.database.log_event(
                    self.device_id,
                    'dps_set',
                    {'dps': dps, 'value': value}
                )
            
            return True
        except Exception as e:
            logger.error(f"Error setting DPS for {self.name}: {e}")
            return False
    
    def set_multiple_dps(self, values: Dict[int, Any]) -> bool:
        """Set multiple DPS values"""
        try:
            result = self.device.set_multiple_values(values)
            logger.info(f"Set multiple DPS for {self.name}")
            
            if self.database:
                self.database.log_event(
                    self.device_id,
                    'multiple_dps_set',
                    {'values': values}
                )
            
            return True
        except Exception as e:
            logger.error(f"Error setting multiple DPS for {self.name}: {e}")
            return False
    
    def get_entity_by_id(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary"""
        return {
            'device_id': self.device_id,
            'name': self.name,
            'ip': self.ip,
            'available': self.available,
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'entities': [e.to_dict() for e in self.entities],
            'raw_state': self.last_state
        }


class DeviceManager:
    """Manages all Tuya devices"""
    
    def __init__(self, config_manager, database=None):
        self.config_manager = config_manager
        self.database = database
        self.devices: Dict[str, TuyaDevice] = {}
        self.poll_thread = None
        self.polling = False
    
    def initialize_devices(self):
        """Initialize all devices from config"""
        device_configs = self.config_manager.config.get('devices', {})
        
        for device_id, device_config in device_configs.items():
            try:
                device = TuyaDevice(device_id, device_config, self.database)
                self.devices[device_id] = device
                logger.info(f"Initialized device: {device.name} with {len(device.entities)} entities")
            except Exception as e:
                logger.error(f"Failed to initialize device {device_id}: {e}")
    
    def get_device(self, device_id: str) -> Optional[TuyaDevice]:
        """Get device by ID"""
        return self.devices.get(device_id)
    
    def get_all_entities(self) -> list:
        """Get all entities from all devices"""
        entities = []
        for device in self.devices.values():
            entities.extend(device.entities)
        return entities
    
    def start_polling(self, publish_callback: Callable, interval: int):
        """Start polling devices"""
        self.polling = True
        self.poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(publish_callback, interval),
            daemon=True
        )
        self.poll_thread.start()
        logger.info(f"Started device polling (interval: {interval}s)")
    
    def stop_polling(self):
        """Stop polling devices"""
        self.polling = False
        if self.poll_thread:
            self.poll_thread.join(timeout=5)
    
    def _poll_loop(self, publish_callback: Callable, interval: int):
        """Polling loop"""
        while self.polling:
            for device in self.devices.values():
                try:
                    device.get_status()
                    publish_callback(device)
                except Exception as e:
                    logger.error(f"Error polling device {device.device_id}: {e}")
            time.sleep(interval)


