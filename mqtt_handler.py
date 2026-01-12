"""Enhanced MQTT communication handler with all platform support"""

import json
import logging
from typing import Dict, Any
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTHandler:
    """Handles MQTT communication for all platforms"""
    
    def __init__(self, config_manager, device_manager):
        self.config_manager = config_manager
        self.device_manager = device_manager
        self.client = None
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0
        }
    
    def connect(self):
        """Connect to MQTT broker"""
        mqtt_config = self.config_manager.config['mqtt']
        
        self.client = mqtt.Client(client_id='tuya2mqtt')
        
        if mqtt_config.get('username') and mqtt_config.get('password'):
            self.client.username_pw_set(
                mqtt_config['username'],
                mqtt_config['password']
            )
        
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        
        base_topic = mqtt_config['base_topic']
        self.client.will_set(f"{base_topic}/bridge/state", "offline", retain=True)
        
        self.client.connect(
            mqtt_config['host'],
            mqtt_config.get('port', 1883),
            60
        )
        self.client.loop_start()
        logger.info(f"Connected to MQTT broker at {mqtt_config['host']}")
    
    def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            base_topic = self.config_manager.config['mqtt']['base_topic']
            self.client.publish(f"{base_topic}/bridge/state", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
    
    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connect callback"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            base_topic = self.config_manager.config['mqtt']['base_topic']
            
            # Subscribe to command topics
            client.subscribe(f"{base_topic}/+/+/set")
            client.subscribe(f"{base_topic}/+/+/command")
            client.subscribe(f"{base_topic}/+/set")
            
            # Publish online status
            client.publish(f"{base_topic}/bridge/state", "online", retain=True)
    
    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback"""
        if rc != 0:
            logger.warning(f"Unexpected MQTT disconnect: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            self.stats['messages_received'] += 1
            base_topic = self.config_manager.config['mqtt']['base_topic']
            topic = msg.topic.replace(f"{base_topic}/", "")
            parts = topic.split('/')
            
            if len(parts) < 2:
                return
            
            device_id = parts[0]
            device = self.device_manager.get_device(device_id)
            
            if not device:
                logger.warning(f"Unknown device: {device_id}")
                return
            
            payload = msg.payload.decode()
            
            # Handle entity commands
            if len(parts) >= 3 and parts[2] in ['set', 'command']:
                entity_name = parts[1]
                entity = device.get_entity_by_id(f"{device_id}_{entity_name}")
                
                if entity:
                    self._handle_entity_command(device, entity, payload)
        
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")
    
    def _handle_entity_command(self, device, entity, payload):
        """Handle entity-specific command for all platforms"""
        try:
            data = json.loads(payload) if payload.startswith('{') else {'command': payload}
            dps_changes = {}
            
            # Light, Switch, Fan
            if entity.platform in ['light', 'switch', 'fan']:
                if 'state' in data:
                    switch_dps = entity.get_dps('switch')
                    if switch_dps:
                        dps_changes[switch_dps] = data['state'] in ['ON', True, 1, 'true']
                
                if 'brightness' in data and entity.platform in ['light', 'fan']:
                    brightness_dps = entity.get_dps('brightness' if entity.platform == 'light' else 'speed')
                    if brightness_dps:
                        min_val, max_val = entity.brightness_range if entity.platform == 'light' else entity.speed_range
                        scaled = int(min_val + (data['brightness'] / 255) * (max_val - min_val))
                        dps_changes[brightness_dps] = scaled
                
                if 'color_temp' in data and entity.platform == 'light':
                    color_temp_dps = entity.get_dps('color_temp')
                    if color_temp_dps:
                        min_val, max_val = entity.color_temp_range
                        scaled = int(min_val + (data['color_temp'] / 500) * (max_val - min_val))
                        dps_changes[color_temp_dps] = scaled
            
            # Climate
            elif entity.platform == 'climate':
                if 'mode' in data:
                    mode_dps = entity.get_dps('mode')
                    if mode_dps:
                        dps_changes[mode_dps] = data['mode']
                
                if 'target_temp' in data or 'temperature' in data:
                    temp_dps = entity.get_dps('target_temp')
                    temp = data.get('target_temp', data.get('temperature'))
                    if temp_dps and temp:
                        dps_changes[temp_dps] = int(temp / entity.temp_step)
                
                if 'fan_mode' in data:
                    fan_dps = entity.get_dps('fan_mode')
                    if fan_dps:
                        dps_changes[fan_dps] = data['fan_mode']
            
            # Cover
            elif entity.platform == 'cover':
                if 'command' in data:
                    cmd = data['command'].lower()
                    switch_dps = entity.get_dps('switch')
                    if cmd == 'open':
                        dps_changes[switch_dps] = True
                    elif cmd == 'close':
                        dps_changes[switch_dps] = False
                    elif cmd == 'stop':
                        dps_changes[entity.get_dps('direction')] = 'stop'
                
                if 'position' in data:
                    pos_dps = entity.get_dps('position')
                    if pos_dps:
                        dps_changes[pos_dps] = int(data['position'])
            
            # Lock
            elif entity.platform == 'lock':
                if 'command' in data or 'state' in data:
                    lock_dps = entity.get_dps('lock')
                    cmd = data.get('command', data.get('state', '')).lower()
                    if lock_dps:
                        dps_changes[lock_dps] = cmd == 'lock'
            
            # Alarm
            elif entity.platform == 'alarm_control_panel':
                if 'command' in data:
                    state_dps = entity.get_dps('state')
                    cmd = data['command'].lower()
                    state_map = {v: k for k, v in entity.states.items()}
                    if state_dps and cmd in state_map:
                        dps_changes[state_dps] = state_map[cmd]
            
            # Vacuum
            elif entity.platform == 'vacuum':
                if 'command' in data:
                    cmd = data['command'].lower()
                    power_dps = entity.get_dps('power')
                    mode_dps = entity.get_dps('mode')
                    
                    if cmd == 'start':
                        dps_changes[power_dps] = True
                    elif cmd == 'stop' or cmd == 'pause':
                        dps_changes[power_dps] = False
                    elif cmd == 'return_to_base':
                        dps_changes[mode_dps] = 'return'
                
                if 'mode' in data:
                    mode_dps = entity.get_dps('mode')
                    if mode_dps:
                        dps_changes[mode_dps] = data['mode']
            
            # Humidifier
            elif entity.platform == 'humidifier':
                if 'state' in data:
                    switch_dps = entity.get_dps('switch')
                    if switch_dps:
                        dps_changes[switch_dps] = data['state'] in ['ON', True]
                
                if 'mode' in data:
                    mode_dps = entity.get_dps('mode')
                    if mode_dps:
                        dps_changes[mode_dps] = data['mode']
                
                if 'target_humidity' in data:
                    humidity_dps = entity.get_dps('target_humidity')
                    if humidity_dps:
                        dps_changes[humidity_dps] = int(data['target_humidity'])
            
            # Number
            elif entity.platform == 'number':
                if 'value' in data:
                    value_dps = entity.get_dps('value')
                    if value_dps:
                        dps_changes[value_dps] = data['value']
            
            # Select
            elif entity.platform == 'select':
                if 'option' in data:
                    option_dps = entity.get_dps('option')
                    if option_dps:
                        dps_changes[option_dps] = data['option']
            
            # Apply changes
            if dps_changes:
                if len(dps_changes) == 1:
                    dps, value = list(dps_changes.items())[0]
                    device.set_dps(dps, value)
                else:
                    device.set_multiple_dps(dps_changes)
                
                # Update state
                import time
                time.sleep(0.5)
                device.get_status()
                self.publish_device_state(device)
        
        except Exception as e:
            logger.error(f"Error handling entity command: {e}")
    
    def publish_device_state(self, device):
        """Publish device state to MQTT"""
        base_topic = self.config_manager.config['mqtt']['base_topic']
        
        # Publish availability
        availability = "online" if device.available else "offline"
        self.client.publish(
            f"{base_topic}/{device.device_id}/availability",
            availability,
            retain=True
        )
        
        if not device.available:
            return
        
        # Publish entity states
        for entity in device.entities:
            entity_topic = f"{base_topic}/{device.device_id}/{entity.name}"
            
            # Platform-specific state publishing
            if entity.platform in ['light', 'switch', 'fan', 'lock']:
                state = "ON" if entity.state.get('switch', False) or entity.state.get('lock', False) else "OFF"
                self.client.publish(f"{entity_topic}/state", state)
                
                # Additional attributes
                for key, value in entity.state.items():
                    if key != 'switch' and key != 'lock':
                        self.client.publish(f"{entity_topic}/{key}", json.dumps(value))
            
            elif entity.platform in ['sensor', 'binary_sensor']:
                value = entity.get_state_value()
                self.client.publish(f"{entity_topic}/state", json.dumps(value))
            
            elif entity.platform == 'climate':
                state_data = {
                    'current_temperature': entity.state.get('current_temp', 20),
                    'temperature': entity.state.get('target_temp', 20),
                    'mode': entity.state.get('mode', 'off'),
                    'fan_mode': entity.state.get('fan_mode', 'auto')
                }
                self.client.publish(f"{entity_topic}/state", json.dumps(state_data))
            
            elif entity.platform == 'alarm_control_panel':
                alarm_state = entity.state.get('state', 'disarmed')
                self.client.publish(f"{entity_topic}/state", alarm_state)
            
            elif entity.platform == 'vacuum':
                vacuum_state = {
                    'state': 'cleaning' if entity.state.get('power') else 'docked',
                    'battery_level': entity.state.get('battery', 100)
                }
                self.client.publish(f"{entity_topic}/state", json.dumps(vacuum_state))
            
            else:
                # Generic state publishing
                self.client.publish(f"{entity_topic}/state", json.dumps(entity.state))
        
        # Publish raw DPS state
        self.client.publish(
            f"{base_topic}/{device.device_id}/state",
            json.dumps(device.last_state)
        )
        
        self.stats['messages_sent'] += len(device.entities) + 2
