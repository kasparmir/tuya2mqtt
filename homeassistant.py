"""Enhanced Home Assistant MQTT Discovery for all platforms"""

import json
import logging

logger = logging.getLogger(__name__)


class HomeAssistantDiscovery:
    """Handles Home Assistant MQTT discovery for all supported platforms"""
    
    def __init__(self, config_manager, mqtt_handler):
        self.config_manager = config_manager
        self.mqtt_handler = mqtt_handler
    
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
        discovery_topic = f"{discovery_prefix}/{entity.platform}/{entity.entity_id}/config"
        entity_topic = f"{base_topic}/{device.device_id}/{entity.name}"
        
        # Base payload
        payload = {
            'name': entity.friendly_name,
            'unique_id': entity.entity_id,
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
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'schema': 'json',
                'brightness': entity.get_dps('brightness') is not None,
                'color_temp': entity.get_dps('color_temp') is not None,
                'supported_color_modes': self._get_light_color_modes(entity)
            })
            if entity.get_dps('brightness'):
                payload['brightness_scale'] = 255
        
        elif entity.platform == 'switch':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'payload_on': 'ON',
                'payload_off': 'OFF'
            })
        
        elif entity.platform == 'fan':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'percentage_state_topic': f"{entity_topic}/speed",
                'percentage_command_topic': f"{entity_topic}/set",
                'payload_on': 'ON',
                'payload_off': 'OFF'
            })
        
        elif entity.platform == 'sensor':
            payload.update({
                'state_topic': f"{entity_topic}/state",
            })
            if entity.unit_of_measurement:
                payload['unit_of_measurement'] = entity.unit_of_measurement
            if entity.device_class:
                payload['device_class'] = entity.device_class
        
        elif entity.platform == 'binary_sensor':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'payload_on': True,
                'payload_off': False
            })
            if entity.device_class:
                payload['device_class'] = entity.device_class
        
        elif entity.platform == 'climate':
            payload.update({
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
                payload['fan_modes'] = entity.fan_modes
                payload['fan_mode_state_topic'] = f"{entity_topic}/state"
                payload['fan_mode_command_topic'] = f"{entity_topic}/set"
        
        elif entity.platform == 'cover':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'position_topic': f"{entity_topic}/position",
                'set_position_topic': f"{entity_topic}/set",
                'payload_open': 'OPEN',
                'payload_close': 'CLOSE',
                'payload_stop': 'STOP'
            })
        
        elif entity.platform == 'lock':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'payload_lock': 'LOCK',
                'payload_unlock': 'UNLOCK',
                'state_locked': 'ON',
                'state_unlocked': 'OFF'
            })
        
        elif entity.platform == 'alarm_control_panel':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'code_arm_required': False
            })
        
        elif entity.platform == 'vacuum':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/command",
                'supported_features': ['start', 'stop', 'pause', 'return_home']
            })
        
        elif entity.platform == 'camera':
            payload.update({
                'topic': f"{entity_topic}/image"
            })
            if entity.stream_url:
                payload['stream_source'] = entity.stream_url
        
        elif entity.platform == 'humidifier':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'target_humidity_state_topic': f"{entity_topic}/target_humidity",
                'target_humidity_command_topic': f"{entity_topic}/set",
                'current_humidity_topic': f"{entity_topic}/humidity",
                'min_humidity': entity.humidity_range[0],
                'max_humidity': entity.humidity_range[1]
            })
            if entity.modes:
                payload['modes'] = entity.modes
        
        elif entity.platform == 'number':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'min': entity.min_value,
                'max': entity.max_value,
                'step': entity.step
            })
            if entity.unit_of_measurement:
                payload['unit_of_measurement'] = entity.unit_of_measurement
        
        elif entity.platform == 'select':
            payload.update({
                'state_topic': f"{entity_topic}/state",
                'command_topic': f"{entity_topic}/set",
                'options': entity.options
            })
        
        elif entity.platform == 'button':
            payload.update({
                'command_topic': f"{entity_topic}/command",
                'payload_press': 'PRESS'
            })
        
        # Publish discovery
        self.mqtt_handler.client.publish(
            discovery_topic,
            json.dumps(payload),
            retain=True
        )
    
    def _get_light_color_modes(self, entity):
        """Get supported color modes for light"""
        modes = []
        if entity.get_dps('brightness'):
            modes.append('brightness')
        if entity.get_dps('color_temp'):
            modes.append('color_temp')
        if entity.get_dps('color'):
            modes.append('hs')
        return modes if modes else ['onoff']