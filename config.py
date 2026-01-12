"""Configuration management for Tuya2MQTT"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading and validation"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Configuration loaded from {self.config_file}")
                return config
        except FileNotFoundError:
            logger.error(f"Config file {self.config_file} not found!")
            self.create_example_config()
            raise SystemExit(1)
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def create_example_config(self):
        """Create example configuration with all platform types"""
        example_config = {
            'mqtt': {
                'host': 'localhost',
                'port': 1883,
                'username': None,
                'password': None,
                'base_topic': 'tuya2mqtt',
                'discovery_prefix': 'homeassistant'
            },
            'web': {
                'enabled': True,
                'port': 8099
            },
            'database': {
                'enabled': True,
                'path': 'tuya2mqtt.db'
            },
            'discovery': {
                'enabled': False,
                'network': '192.168.1.0/24',
                'save_discovered': True
            },
            'poll_interval': 30,
            'homeassistant': {
                'enabled': True
            },
            'devices': {
                'bf1234567890abcdef': {
                    'name': 'Chytré světlo',
                    'ip': '192.168.1.100',
                    'local_key': 'your_local_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'light',
                            'name': 'main_light',
                            'friendly_name': 'Hlavní světlo',
                            'dps': {'switch': 1, 'brightness': 2, 'color_temp': 3},
                            'brightness_range': [10, 1000],
                            'color_temp_range': [0, 1000],
                            'icon': 'mdi:lightbulb'
                        }
                    ]
                },
                'climate_device_id': {
                    'name': 'Termostat',
                    'ip': '192.168.1.101',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'climate',
                            'name': 'thermostat',
                            'friendly_name': 'Termostat',
                            'dps': {
                                'switch': 1,
                                'current_temp': 2,
                                'target_temp': 3,
                                'mode': 4,
                                'fan_mode': 5
                            },
                            'temperature_unit': 'C',
                            'temp_range': [16, 30],
                            'temp_step': 0.5,
                            'modes': ['off', 'heat', 'cool', 'auto'],
                            'fan_modes': ['auto', 'low', 'medium', 'high'],
                            'icon': 'mdi:thermostat'
                        }
                    ]
                },
                'alarm_device_id': {
                    'name': 'Alarm',
                    'ip': '192.168.1.102',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'alarm_control_panel',
                            'name': 'alarm',
                            'friendly_name': 'Domácí alarm',
                            'dps': {
                                'state': 1,
                                'mode': 2
                            },
                            'states': {
                                'disarmed': 'disarmed',
                                'armed_home': 'home',
                                'armed_away': 'away',
                                'triggered': 'sos'
                            },
                            'icon': 'mdi:shield-home'
                        }
                    ]
                },
                'vacuum_device_id': {
                    'name': 'Robotický vysavač',
                    'ip': '192.168.1.103',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'vacuum',
                            'name': 'vacuum',
                            'friendly_name': 'Vysavač',
                            'dps': {
                                'power': 1,
                                'mode': 2,
                                'direction': 3,
                                'battery': 4,
                                'status': 5
                            },
                            'modes': ['auto', 'spot', 'edge', 'single_room'],
                            'icon': 'mdi:robot-vacuum'
                        }
                    ]
                },
                'lock_device_id': {
                    'name': 'Chytrý zámek',
                    'ip': '192.168.1.104',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'lock',
                            'name': 'door_lock',
                            'friendly_name': 'Zámek dveří',
                            'dps': {
                                'lock': 1,
                                'battery': 2
                            },
                            'icon': 'mdi:door-closed-lock'
                        }
                    ]
                },
                'camera_device_id': {
                    'name': 'Kamera',
                    'ip': '192.168.1.105',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'camera',
                            'name': 'camera',
                            'friendly_name': 'Vstupní kamera',
                            'dps': {
                                'power': 1,
                                'motion_detect': 2,
                                'night_vision': 3
                            },
                            'stream_url': 'rtsp://192.168.1.105:554/stream',
                            'icon': 'mdi:cctv'
                        }
                    ]
                },
                'humidifier_device_id': {
                    'name': 'Zvlhčovač',
                    'ip': '192.168.1.106',
                    'local_key': 'your_key',
                    'version': '3.3',
                    'entities': [
                        {
                            'platform': 'humidifier',
                            'name': 'humidifier',
                            'friendly_name': 'Zvlhčovač vzduchu',
                            'dps': {
                                'switch': 1,
                                'mode': 2,
                                'humidity': 3,
                                'target_humidity': 4
                            },
                            'modes': ['auto', 'low', 'medium', 'high'],
                            'humidity_range': [30, 80],
                            'icon': 'mdi:air-humidifier'
                        }
                    ]
                }
            }
        }
        
        with open('config.example.yaml', 'w', encoding='utf-8') as f:
            yaml.dump(example_config, f, default_flow_style=False, allow_unicode=True)
        logger.info("Created config.example.yaml with all platform examples")
