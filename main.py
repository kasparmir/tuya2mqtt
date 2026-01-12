"""Main entry point for Tuya2MQTT Bridge"""

import logging
import argparse
import signal
import sys
from pathlib import Path

from config import ConfigManager
from device import DeviceManager
from mqtt_handler import MQTTHandler
from web_server import WebServer
from homeassistant import HomeAssistantDiscovery
from database import Database
from discovery import DeviceDiscovery

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Tuya2MQTT:
    """Main application coordinator"""
    
    def __init__(self, config_file: str = 'config.yaml'):
        self.config_manager = ConfigManager(config_file)
        self.database = Database()
        self.device_manager = DeviceManager(self.config_manager, self.database)
        self.mqtt_handler = MQTTHandler(self.config_manager, self.device_manager)
        self.ha_discovery = HomeAssistantDiscovery(self.config_manager, self.mqtt_handler)
        self.device_discovery = DeviceDiscovery(self.config_manager, self.device_manager)
        self.web_server = None
        self.running = False
        
    def start(self):
        """Start all components"""
        logger.info("Starting Tuya2MQTT Bridge v2.0")
        
        # Run auto-discovery if enabled
        if self.config_manager.config.get('discovery', {}).get('enabled', False):
            logger.info("Running automatic device discovery...")
            self.device_discovery.scan_network()
        
        # Initialize devices
        self.device_manager.initialize_devices()
        
        # Connect MQTT
        self.mqtt_handler.connect()
        
        # Publish Home Assistant discovery
        if self.config_manager.config.get('homeassistant', {}).get('enabled', True):
            self.ha_discovery.publish_all_discoveries()
        
        # Start device polling
        self.device_manager.start_polling(
            self.mqtt_handler.publish_device_state,
            self.config_manager.config.get('poll_interval', 30)
        )
        
        # Start web server if enabled
        web_config = self.config_manager.config.get('web', {})
        if web_config.get('enabled', True):
            self.web_server = WebServer(
                self.device_manager,
                self.mqtt_handler,
                self.database,
                self.device_discovery,
                web_config.get('port', 8099)
            )
            self.web_server.start()
        
        self.running = True
        logger.info("Tuya2MQTT Bridge started successfully")
        logger.info(f"Web interface: http://0.0.0.0:{web_config.get('port', 8099)}")
    
    def stop(self):
        """Stop all components"""
        logger.info("Stopping Tuya2MQTT Bridge")
        self.running = False
        
        if self.device_manager:
            self.device_manager.stop_polling()
        
        if self.mqtt_handler:
            self.mqtt_handler.disconnect()
        
        if self.web_server:
            self.web_server.stop()
        
        if self.database:
            self.database.close()
        
        logger.info("Tuya2MQTT Bridge stopped")


def main():
    parser = argparse.ArgumentParser(description='Tuya2MQTT Bridge')
    parser.add_argument('-c', '--config', default='config.yaml',
                       help='Path to configuration file')
    args = parser.parse_args()
    
    app = Tuya2MQTT(config_file=args.config)
    
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        app.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app.start()
    
    # Keep running
    try:
        while app.running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        app.stop()


if __name__ == '__main__':
    main()