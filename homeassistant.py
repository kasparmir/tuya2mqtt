"""Enhanced Home Assistant MQTT Discovery for all platforms"""

import json
import logging
import re

logger = logging.getLogger(__name__)


class HomeAssistantDiscovery:
    """Handles Home Assistant MQTT discovery for all supported platforms"""
    
    def __init__(self, config_manager, mqtt_handler):
        self.config_manager = config_manager
        self.mqtt_handler = mqtt_handler
    
    @staticmethod
    def sanitize_topic(text: str) -> str:
        """
        Sanitize text for use in MQTT topics.
        Home Assistant requires topics to only contain: a-z A-Z 0-9 _ -
        """
        # Replace spaces with underscores
        text = text.replace(' ', '_')
        # Remove any characters that aren't alphanumeric, underscore, or hyphen
        text = re.sub(r'[^a-zA-Z0-9_-]', '', text)
        # Remove consecutive underscores
        text = re.sub(r'_+', '_', text)
        # Remove leading/trailing underscores
        text = text.strip('_')
        return text
    
    def publish_all_discoveries(self):
        """Publish discovery for all entities"""
        if not self.config_manager.config.get('homeassistant', {}).get('enabled', True):
            return
        
        discovery_prefix = self.config_manager.config['mqtt'].get('discovery_prefix', 'homeassistant')
        
        for device in self.mqtt_handler.device_manager.devices.values():
            for entity in device.entities:
                self._publish_entity_discovery(device, entity, discovery_prefix)
        
        logger.info("Published Home Assistant discovery for all entities")
    
    def _publish_entity_discovery(self, device, entity, discovery_prefix):
        """Publish discovery for a single entity"""
        base_topic = self.config_manager.config['mqtt']['base_topic']
        
        # Sanitize entity_id for MQTT topic - remove spaces and special characters
        sanitized_entity_id = self.sanitize_topic(entity.entity_id)
        sanitized_name = self.sanitize_topic(entity.name)
        
        # Create discovery topic with sanitized entity_id
        discovery_topic = f"{discovery_prefix}/{entity.platform}/{sanitized_entity_id}/config"
        
        # Use only device_id in topic (no entity name)
        entity_topic = f"{base_topic}/{device.device_id}/{sanitized_entity_id}"
        
        # Base discovery payload
        discovery_payload = {
            'name': entity.friendly_name,
            'unique_id': sanitized_entity_id,
            'availability_topic': f"{base_topic}/{device.device_id}/availability",
            'icon': entity.icon,
            'device': {
                'identifiers': [f"tuya2mqtt_{device.device_id}"],
                'name': device.name,
                'model': 'Tuya Device',
                'manufacturer': 'Tuya',
                'via_device': 'tuya2mqtt'
            }
        }
        
        # Platform-specific configuration
        if entity.platform == 'light':
            color_modes = self._get_light_color_modes(entity)
            
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'schema': 'json'
            })
            
            # Only add supported_color_modes if there are valid modes
            if color_modes and len(color_modes) > 0:
                discovery_payload['supported_color_modes'] = color_modes
                
                # Add brightness_scale only if brightness is supported
                if 'brightness' in color_modes:
                    discovery_payload['brightness_scale'] = 255
        
        elif entity.platform == 'switch':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'payload_on': 'ON',
                'payload_off': 'OFF'
            })
        
        elif entity.platform == 'fan':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'percentage_state_topic': f"{entity_topic}/speed",
                'percentage_command_topic': f"{entity_topic}/set",
                'payload_on': 'ON',
                'payload_off': 'OFF'
            })
        
        elif entity.platform == 'sensor':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
            })
            if entity.unit_of_measurement:
                discovery_payload['unit_of_measurement'] = entity.unit_of_measurement
            if entity.device_class:
                discovery_payload['device_class'] = entity.device_class
        
        elif entity.platform == 'binary_sensor':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'payload_on': True,
                'payload_off': False
            })
            if entity.device_class:
                discovery_payload['device_class'] = entity.device_class
        
        elif entity.platform == 'climate':
            discovery_payload.update({
                'mode_state_topic': f"{entity_topic}/state",
                'mode_command_topic': f"{entity_topic}/set",
                'temperature_state_topic': f"{entity_topic}/state",
                'temperature_command_topic': f"{entity_topic}/set",
                'current_temperature_topic': f"{entity_topic}/state",
                'modes': entity.modes,
                'min_temp': entity.temp_range[0],
                'max_temp': entity.temp_range[1],
                'temp_step': entity.temp_step,
                'temperature_unit': entity.temperature_unit
            })
            if entity.fan_modes:
                discovery_payload['fan_modes'] = entity.fan_modes
                discovery_payload['fan_mode_state_topic'] = f"{entity_topic}/state"
                discovery_payload['fan_mode_command_topic'] = f"{entity_topic}/set"
        
        elif entity.platform == 'cover':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'position_topic': f"{entity_topic}/position",
                'set_position_topic': f"{entity_topic}/set",
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            })
        
        elif entity.platform == 'lock':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'payload_lock': 'LOCK',
                'payload_unlock': 'UNLOCK',
                'state_locked': 'ON',
                'state_unlocked': 'OFF'
            })
        
        elif entity.platform == 'alarm_control_panel':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'code_arm_required': False
            })
        
        elif entity.platform == 'vacuum':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'supported_features': ['start', 'stop', 'pause', 'return_home']
            })
        
        elif entity.platform == 'camera':
            discovery_payload.update({
                'topic': f"{entity_topic}/image"
            })
            if entity.stream_url:
                discovery_payload['stream_source'] = entity.stream_url
        
        elif entity.platform == 'humidifier':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'target_humidity_state_topic': f"{entity_topic}/target_humidity",
                'target_humidity_command_topic': f"{entity_topic}/set",
                'current_humidity_topic': f"{entity_topic}/humidity",
                'min_humidity': entity.humidity_range[0],
                'max_humidity': entity.humidity_range[1]
            })
            if entity.modes:
                discovery_payload['modes'] = entity.modes
        
        elif entity.platform == 'number':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'min': entity.min_value,
                'max': entity.max_value,
                'step': entity.step
            })
            if entity.unit_of_measurement:
                discovery_payload['unit_of_measurement'] = entity.unit_of_measurement
        
        elif entity.platform == 'select':
            discovery_payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'options': entity.options
            })
        
        elif entity.platform == 'button':
            discovery_payload.update({
                'command_topic': f"{entity_topic}/command",
                'payload_press': 'PRESS'
            })
        
        # Publish discovery
        self.mqtt_handler.client.publish(
            discovery_topic,
            json.dumps(discovery_payload),
            retain=True
        )
        
        logger.debug(f"Published HA discovery: {discovery_topic}")
    
    def _get_light_color_modes(self, entity):
        """Get supported color modes for light - only valid combinations"""
        has_brightness = entity.get_dps('brightness') is not None
        has_color_temp = entity.get_dps('color_temp') is not None
        has_color = entity.get_dps('color') is not None
        
        # Home Assistant valid color mode combinations:
        # - onoff (just on/off)
        # - brightness (brightness only)
        # - color_temp (color temp + brightness)
        # - hs (hue/sat + brightness)
        # - rgb (rgb + brightness)
        # - rgbw (rgbw + brightness)
        # - rgbww (rgbww + brightness)
        # - white (white only + brightness)
        
        # IMPORTANT: Cannot combine 'brightness' with 'hs' or 'color_temp'
        # as those modes already include brightness control
        
        if has_color:
            # Color mode includes brightness automatically
            return ['hs']
        elif has_color_temp:
            # Color temp mode includes brightness automatically
            return ['color_temp']
        elif has_brightness:
            # Just brightness control
            return ['brightness']
        else:
            # Just on/off
            return ['onoff']