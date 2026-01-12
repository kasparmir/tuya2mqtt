"""Automatic Tuya device discovery"""

import logging
import socket
import json
from typing import List, Dict, Any, Union
import tinytuya

logger = logging.getLogger(__name__)


class DeviceDiscovery:
    """Handles automatic discovery of Tuya devices"""
    
    def __init__(self, config_manager, device_manager):
        self.config_manager = config_manager
        self.device_manager = device_manager
        self.discovered_devices = []
    
    def scan_network(self):
        """Scan network for Tuya devices"""
        logger.info("Starting Tuya device discovery...")
        
        discovery_config = self.config_manager.config.get('discovery', {})
        
        try:
            # Use tinytuya scanner
            logger.info("Scanning network for Tuya devices (this may take 20-30 seconds)...")
            devices = tinytuya.deviceScan(False, 20)
            
            # Parse devices - tinytuya returns dict with device IDs as keys
            device_list = []
            
            if isinstance(devices, dict):
                for device_id, device_info in devices.items():
                    # device_info can be a dict or string
                    if isinstance(device_info, dict):
                        device_data = {
                            'id': device_id,
                            'gwId': device_id,
                            'ip': device_info.get('ip', ''),
                            'version': device_info.get('version', '3.3'),
                            'product_id': device_info.get('productKey', ''),
                            'encrypted': device_info.get('encrypted', False)
                        }
                    else:
                        # If device_info is a string (IP address)
                        device_data = {
                            'id': device_id,
                            'gwId': device_id,
                            'ip': str(device_info),
                            'version': '3.3',
                            'product_id': '',
                            'encrypted': False
                        }
                    device_list.append(device_data)
                    logger.info(f"Discovered: {device_id} at {device_data['ip']}")
            
            if device_list:
                logger.info(f"Found {len(device_list)} Tuya devices on network")
                self.discovered_devices = device_list
                
                # Save discovered devices if enabled
                if discovery_config.get('save_discovered', True):
                    self._save_discovered_devices(device_list)
                
                return device_list
            else:
                logger.warning("No Tuya devices found on network")
                return []
                
        except Exception as e:
            logger.error(f"Error during device discovery: {e}", exc_info=True)
            return []
    
    def _save_discovered_devices(self, devices: List[Dict[str, Any]]):
        """Save discovered devices info (but don't add to config automatically)"""
        # Don't automatically add to config anymore
        # Just keep them in memory for web UI display
        logger.info(f"Discovery complete. Found {len(devices)} devices.")
        logger.info("View them in web UI under 'Discovered Devices' section")
    
    def get_unconfigured_devices(self) -> List[Dict[str, Any]]:
        """Get devices that are discovered but not configured"""
        config_devices = self.config_manager.config.get('devices', {})
        unconfigured = []
        
        for device in self.discovered_devices:
            device_id = device.get('gwId') or device.get('id')
            if device_id and device_id not in config_devices:
                unconfigured.append({
                    'id': device_id,
                    'ip': device.get('ip', 'Unknown'),
                    'version': device.get('version', '3.3'),
                    'product_id': device.get('product_id', ''),
                    'encrypted': device.get('encrypted', False)
                })
        
        return unconfigured
    
    def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Get detailed info about a specific device"""
        for device in self.discovered_devices:
            if device.get('gwId') == device_id or device.get('id') == device_id:
                return device
        return {}
    
    def get_discovered_summary(self) -> List[Dict[str, str]]:
        """Get summary of discovered devices for web UI"""
        summary = []
        config_devices = self.config_manager.config.get('devices', {})
        
        for device in self.discovered_devices:
            device_id = device.get('gwId') or device.get('id')
            is_configured = device_id in config_devices
            
            summary.append({
                'id': device_id,
                'ip': device.get('ip', 'Unknown'),
                'version': device.get('version', '3.3'),
                'configured': is_configured,
                'status': 'Ready' if is_configured else 'Needs local_key'
            })
        
        return summary