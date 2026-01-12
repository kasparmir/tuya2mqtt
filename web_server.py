"""Enhanced Flask web server with improved UI"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading

logger = logging.getLogger(__name__)


class WebServer:
    """Enhanced Flask web server"""
    
    def __init__(self, device_manager, mqtt_handler, database, discovery, port=8099):
        self.device_manager = device_manager
        self.mqtt_handler = mqtt_handler
        self.database = database
        self.discovery = discovery
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)
        self.server_thread = None
        self.start_time = datetime.now()
        
        self._setup_routes()
        self._create_templates()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template('index.html')
        
        @self.app.route('/api/devices')
        def get_devices():
            devices = [d.to_dict() for d in self.device_manager.devices.values()]
            return jsonify(devices)
        
        @self.app.route('/api/devices/unconfigured')
        def get_unconfigured_devices():
            """Get discovered but unconfigured devices"""
            unconfigured = self.discovery.get_unconfigured_devices()
            return jsonify(unconfigured)
        
        @self.app.route('/api/device/<device_id>')
        def get_device(device_id):
            device = self.device_manager.get_device(device_id)
            if not device:
                return jsonify({'error': 'Device not found'}), 404
            return jsonify(device.to_dict())
        
        @self.app.route('/api/device/<device_id>/entity/<entity_name>/set', methods=['POST'])
        def set_entity(device_id, entity_name):
            device = self.device_manager.get_device(device_id)
            if not device:
                return jsonify({'error': 'Device not found'}), 404
            
            entity = device.get_entity_by_id(f"{device_id}_{entity_name}")
            if not entity:
                return jsonify({'error': 'Entity not found'}), 404
            
            data = request.json
            success = self._handle_entity_control(device, entity, data)
            
            if success:
                time.sleep(0.5)
                device.get_status()
                return jsonify({'success': True, 'entity': entity.to_dict()})
            
            return jsonify({'success': False}), 400
        
        @self.app.route('/api/entity/<entity_id>/history')
        def get_entity_history(entity_id):
            if not self.database:
                return jsonify({'error': 'Database not enabled'}), 400
            
            limit = request.args.get('limit', 100, type=int)
            history = self.database.get_entity_history(entity_id, limit)
            return jsonify(history)
        
        @self.app.route('/api/stats')
        def get_stats():
            uptime = datetime.now() - self.start_time
            stats = {
                'uptime': str(uptime).split('.')[0],
                'devices_total': len(self.device_manager.devices),
                'devices_online': sum(1 for d in self.device_manager.devices.values() if d.available),
                'entities_total': len(self.device_manager.get_all_entities()),
                'mqtt_sent': self.mqtt_handler.stats['messages_sent'],
                'mqtt_received': self.mqtt_handler.stats['messages_received']
            }
            
            if self.database:
                db_stats = self.database.get_statistics()
                stats.update(db_stats)
            
            return jsonify(stats)
        
        @self.app.route('/api/discovery/scan', methods=['POST'])
        def scan_devices():
            try:
                logger.info("Starting device scan from web interface...")
                devices = self.discovery.scan_network()
                summary = self.discovery.get_discovered_summary()
                
                return jsonify({
                    'success': True,
                    'discovered': len(devices),
                    'devices': summary,
                    'message': f'Found {len(devices)} devices. Check logs for details.'
                })
            except Exception as e:
                logger.error(f"Scan failed: {e}", exc_info=True)
                return jsonify({
                    'success': False,
                    'error': str(e),
                    'message': 'Scan failed. Check logs for details.'
                }), 500
        
        @self.app.route('/api/discovery/devices')
        def get_discovered_devices():
            """Get list of discovered devices"""
            summary = self.discovery.get_discovered_summary()
            return jsonify(summary)
        
        @self.app.route('/api/config', methods=['GET'])
        def get_config():
            config = self.device_manager.config_manager.config.copy()
            # Sanitize sensitive data
            if 'devices' in config:
                for device in config['devices'].values():
                    if 'local_key' in device:
                        device['local_key'] = '***'
            if 'mqtt' in config and 'password' in config['mqtt']:
                config['mqtt']['password'] = '***'
            return jsonify(config)
    
    def _handle_entity_control(self, device, entity, data):
        """Handle entity control from web interface"""
        try:
            dps_changes = {}
            
            # Universal switch/power control
            if 'state' in data:
                switch_dps = entity.get_dps('switch') or entity.get_dps('power') or entity.get_dps('lock')
                if switch_dps:
                    dps_changes[switch_dps] = data['state']
            
            # Brightness/Speed/Level control
            if 'brightness' in data or 'level' in data:
                value = data.get('brightness', data.get('level', 0))
                brightness_dps = entity.get_dps('brightness') or entity.get_dps('speed')
                if brightness_dps:
                    if entity.platform == 'light':
                        min_val, max_val = entity.brightness_range
                        scaled = int(min_val + (value / 100) * (max_val - min_val))
                    else:
                        min_val, max_val = entity.speed_range
                        scaled = int(min_val + (value / 100) * (max_val - min_val))
                    dps_changes[brightness_dps] = scaled
            
            # Temperature control
            if 'temperature' in data or 'target_temp' in data:
                temp = data.get('temperature', data.get('target_temp'))
                temp_dps = entity.get_dps('target_temp')
                if temp_dps:
                    dps_changes[temp_dps] = int(temp / entity.temp_step)
            
            # Mode control
            if 'mode' in data:
                mode_dps = entity.get_dps('mode')
                if mode_dps:
                    dps_changes[mode_dps] = data['mode']
            
            # Position control (cover)
            if 'position' in data:
                pos_dps = entity.get_dps('position')
                if pos_dps:
                    dps_changes[pos_dps] = int(data['position'])
            
            # Humidity control
            if 'target_humidity' in data:
                humidity_dps = entity.get_dps('target_humidity')
                if humidity_dps:
                    dps_changes[humidity_dps] = int(data['target_humidity'])
            
            # Apply changes
            if dps_changes:
                if len(dps_changes) == 1:
                    dps, value = list(dps_changes.items())[0]
                    return device.set_dps(dps, value)
                else:
                    return device.set_multiple_dps(dps_changes)
            
            return False
        except Exception as e:
            logger.error(f"Error handling entity control: {e}")
            return False
    
    def _create_templates(self):
        """Create enhanced HTML template"""
        templates_dir = Path('templates')
        templates_dir.mkdir(exist_ok=True)
        
        html = '''<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tuya2MQTT Bridge v2.0</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --primary: #667eea;
            --secondary: #764ba2;
            --success: #4caf50;
            --danger: #f44336;
            --warning: #ff9800;
            --info: #2196f3;
            --dark: #333;
            --light: #f8f9fa;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container { max-width: 1600px; margin: 0 auto; }
        
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header-left h1 { color: var(--primary); font-size: 2.5em; margin-bottom: 5px; }
        .header-left .subtitle { color: #666; font-size: 1.1em; }
        .header-left .version { color: #999; font-size: 0.9em; margin-top: 5px; }
        
        .header-right { display: flex; gap: 10px; }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.3s;
        }
        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: #5568d3; transform: translateY(-2px); }
        .btn-success { background: var(--success); color: white; }
        .btn-success:hover { background: #45a049; }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-value { font-size: 2em; font-weight: bold; color: var(--primary); }
        .stat-label { color: #666; margin-top: 5px; font-size: 0.9em; }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 12px 24px;
            background: white;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }
        .tab.active {
            background: var(--primary);
            color: white;
        }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .devices-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 20px;
        }
        
        .device-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 25px rgba(0,0,0,0.15);
            transition: all 0.3s;
        }
        .device-card:hover { transform: translateY(-5px); box-shadow: 0 10px 35px rgba(0,0,0,0.2); }
        
        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid #f0f0f0;
        }
        
        .device-name { font-size: 1.5em; font-weight: bold; color: var(--dark); }
        .device-status {
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .status-online { background: var(--success); color: white; }
        .status-offline { background: var(--danger); color: white; }
        
        .entities { display: flex; flex-direction: column; gap: 15px; }
        
        .entity {
            background: var(--light);
            padding: 18px;
            border-radius: 12px;
            border-left: 4px solid var(--primary);
        }
        
        .entity-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .entity-name { font-weight: 600; color: var(--dark); font-size: 1.1em; }
        .entity-platform {
            background: var(--primary);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.75em;
            text-transform: uppercase;
        }
        
        .entity-controls { display: flex; flex-direction: column; gap: 12px; }
        
        .control-row {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .control-label {
            min-width: 100px;
            font-size: 0.95em;
            color: #666;
            font-weight: 500;
        }
        
        .control-value {
            min-width: 60px;
            text-align: right;
            font-weight: 700;
            color: var(--primary);
            font-size: 1.05em;
        }
        
        .toggle {
            position: relative;
            width: 60px;
            height: 30px;
            background: #ccc;
            border-radius: 15px;
            cursor: pointer;
            transition: background 0.3s;
        }
        .toggle.active { background: var(--success); }
        .toggle::after {
            content: '';
            position: absolute;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: white;
            top: 2px;
            left: 2px;
            transition: transform 0.3s;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .toggle.active::after { transform: translateX(30px); }
        
        .slider-container {
            flex: 1;
            position: relative;
            height: 8px;
            background: #ddd;
            border-radius: 4px;
            cursor: pointer;
        }
        .slider-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--secondary));
            border-radius: 4px;
            transition: width 0.2s;
        }
        .slider-thumb {
            position: absolute;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: white;
            border: 3px solid var(--primary);
            top: -6px;
            cursor: grab;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            transition: box-shadow 0.2s;
        }
        .slider-thumb:active { cursor: grabbing; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        
        .mode-selector {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        .mode-btn {
            padding: 6px 14px;
            border: 2px solid var(--primary);
            background: white;
            color: var(--primary);
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.85em;
            transition: all 0.2s;
        }
        .mode-btn:hover { background: var(--light); }
        .mode-btn.active { background: var(--primary); color: white; }
        
        .dps-info {
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #ddd;
            font-size: 0.85em;
            color: #666;
            font-family: 'Courier New', monospace;
        }
        
        .loading {
            text-align: center;
            color: white;
            font-size: 1.8em;
            padding: 60px;
            animation: pulse 1.5s ease-in-out infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .platform-light { border-left-color: #ffd700; }
        .platform-switch { border-left-color: #2196f3; }
        .platform-fan { border-left-color: #00bcd4; }
        .platform-climate { border-left-color: #ff5722; }
        .platform-sensor { border-left-color: #4caf50; }
        .platform-alarm_control_panel { border-left-color: #f44336; }
        .platform-vacuum { border-left-color: #9c27b0; }
        .platform-lock { border-left-color: #795548; }
        
        @media (max-width: 768px) {
            .devices-grid { grid-template-columns: 1fr; }
            .header { flex-direction: column; gap: 20px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                <h1>🔌 Tuya2MQTT Bridge</h1>
                <div class="subtitle">Enhanced s databází a auto-detekcí</div>
                <div class="version">v2.0 | Home Assistant Compatible</div>
            </div>
            <div class="header-right">
                <button class="btn btn-success" onclick="scanDevices()">🔍 Skenovat zařízení</button>
                <button class="btn btn-primary" onclick="refreshAll()">🔄 Obnovit</button>
            </div>
        </div>
        
        <div class="stats-grid" id="stats"></div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('devices')">📱 Zařízení</button>
            <button class="tab" onclick="showTab('unconfigured')">🔍 Nenakonfigurovaná</button>
            <button class="tab" onclick="showTab('entities')">⚙️ Entity</button>
        </div>
        
        <div id="devices-tab" class="tab-content active">
            <div class="devices-grid" id="devices">
                <div class="loading">⏳ Načítám zařízení...</div>
            </div>
        </div>
        
        <div id="unconfigured-tab" class="tab-content">
            <div id="unconfigured-devices">
                <div class="loading">⏳ Načítám nenakonfigurovaná zařízení...</div>
            </div>
        </div>
        
        <div id="entities-tab" class="tab-content">
            <div class="devices-grid" id="entities-list"></div>
        </div>
    </div>
    
    <script>
        let devicesData = {};
        
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tab + '-tab').classList.add('active');
            
            if (tab === 'unconfigured') loadUnconfiguredDevices();
            if (tab === 'entities') loadEntitiesList();
        }
        
        async function loadUnconfiguredDevices() {
            try {
                const res = await fetch('/api/devices/unconfigured');
                const devices = await res.json();
                
                const container = document.getElementById('unconfigured-devices');
                
                if (devices.length === 0) {
                    container.innerHTML = `
                        <div class="device-card" style="text-align: center; padding: 40px;">
                            <h2 style="color: #4caf50; margin-bottom: 10px;">✅ Vše nakonfigurováno!</h2>
                            <p style="color: #666;">Žádná nenakonfigurovaná zařízení nebyla nalezena.</p>
                            <p style="color: #666; margin-top: 10px;">Klikněte na "🔍 Skenovat zařízení" pro vyhledání nových.</p>
                        </div>
                    `;
                    return;
                }
                
                container.innerHTML = devices.map(device => `
                    <div class="device-card" style="border: 2px solid #ff9800;">
                        <div class="device-header">
                            <div class="device-name">Nenakonfigurované zařízení</div>
                            <div class="device-status" style="background: #ff9800;">Nové</div>
                        </div>
                        <div style="margin-bottom: 15px; padding: 15px; background: #fff3e0; border-radius: 8px;">
                            <div style="margin-bottom: 8px;"><strong>ID:</strong> ${device.id}</div>
                            <div style="margin-bottom: 8px;"><strong>IP:</strong> ${device.ip}</div>
                            <div style="margin-bottom: 8px;"><strong>Verze:</strong> ${device.version}</div>
                            ${device.product_id ? `<div><strong>Product ID:</strong> ${device.product_id}</div>` : ''}
                        </div>
                        <div style="padding: 15px; background: #f8f9fa; border-radius: 8px; font-size: 0.9em;">
                            <strong>📝 Jak přidat:</strong>
                            <ol style="margin: 10px 0 0 20px; line-height: 1.8;">
                                <li>Získejte local_key: <code style="background: white; padding: 2px 6px; border-radius: 3px;">python -m tinytuya wizard</code></li>
                                <li>Přidejte do <code style="background: white; padding: 2px 6px; border-radius: 3px;">config.yaml</code></li>
                                <li>Restartujte bridge</li>
                            </ol>
                        </div>
                        <button class="btn btn-primary" style="width: 100%; margin-top: 10px;" 
                                onclick="copyDeviceTemplate('${device.id}', '${device.ip}', '${device.version}')">
                            📋 Kopírovat šablonu konfigurace
                        </button>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Chyba:', e);
                document.getElementById('unconfigured-devices').innerHTML = 
                    '<div class="loading">❌ Chyba při načítání</div>';
            }
        }
        
        function copyDeviceTemplate(deviceId, ip, version) {
            const template = `  ${deviceId}:
    name: "Nové zařízení"
    ip: "${ip}"
    local_key: "ZÍSKEJTE_POMOCÍ_TINYTUYA_WIZARD"
    version: "${version}"
    entities:
      - platform: switch
        name: "main_switch"
        friendly_name: "Hlavní vypínač"
        dps:
          switch: 1
        icon: "mdi:power"`;
            
            navigator.clipboard.writeText(template).then(() => {
                alert('✅ Šablona zkopírována do schránky!\n\nVložte ji do config.yaml pod sekci "devices:"');
            }).catch(() => {
                alert('❌ Nepodařilo se zkopírovat. Zkopírujte ručně:\n\n' + template);
            });
        }
        
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const stats = await res.json();
                
                let html = `
                    <div class="stat-card">
                        <div class="stat-value">${stats.uptime}</div>
                        <div class="stat-label">⏱️ Uptime</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.devices_online}/${stats.devices_total}</div>
                        <div class="stat-label">📱 Online zařízení</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.entities_total}</div>
                        <div class="stat-label">⚙️ Entity</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${stats.mqtt_sent + stats.mqtt_received}</div>
                        <div class="stat-label">📨 MQTT zprávy</div>
                    </div>
                `;
                
                if (stats.history_records !== undefined) {
                    html += `
                        <div class="stat-card">
                            <div class="stat-value">${stats.history_records}</div>
                            <div class="stat-label">💾 DB záznamy</div>
                        </div>
                    `;
                }
                
                document.getElementById('stats').innerHTML = html;
            } catch (e) {
                console.error('Chyba:', e);
            }
        }
        
        async function loadDevices() {
            try {
                const res = await fetch('/api/devices');
                const devices = await res.json();
                devicesData = {};
                devices.forEach(d => devicesData[d.device_id] = d);
                
                const container = document.getElementById('devices');
                container.innerHTML = devices.map(createDeviceCard).join('');
                attachEventListeners();
            } catch (e) {
                console.error('Chyba:', e);
                document.getElementById('devices').innerHTML = '<div class="loading">❌ Chyba při načítání</div>';
            }
        }
        
        function createDeviceCard(device) {
            const statusClass = device.available ? 'status-online' : 'status-offline';
            const statusText = device.available ? 'Online' : 'Offline';
            const entitiesHtml = device.entities.map(e => createEntityControl(device, e)).join('');
            
            return `
                <div class="device-card">
                    <div class="device-header">
                        <div class="device-name">${device.name}</div>
                        <div class="device-status ${statusClass}">${statusText}</div>
                    </div>
                    <div class="entities">${entitiesHtml}</div>
                </div>
            `;
        }
        
        function createEntityControl(device, entity) {
            const platform = entity.platform;
            let controls = '';
            
            if (['light', 'switch', 'fan', 'lock'].includes(platform)) {
                const isOn = entity.state.switch || entity.state.lock || false;
                controls += `
                    <div class="control-row">
                        <span class="control-label">Stav:</span>
                        <div class="toggle ${isOn ? 'active' : ''}" 
                             data-entity="${entity.entity_id}" 
                             data-control="switch"></div>
                    </div>
                `;
                
                if (platform === 'light' && entity.state.brightness !== undefined) {
                    const brightness = Math.round((entity.state.brightness / 1000) * 100);
                    controls += createSlider(entity.entity_id, 'brightness', brightness, 'Jas');
                } else if (platform === 'fan' && entity.state.speed !== undefined) {
                    controls += createSlider(entity.entity_id, 'brightness', entity.state.speed * 33, 'Rychlost');
                }
            } else if (platform === 'climate') {
                const temp = entity.state.target_temp || 20;
                controls += `
                    <div class="control-row">
                        <span class="control-label">Teplota:</span>
                        <div class="control-value">${temp}°C</div>
                    </div>
                `;
            } else if (platform === 'sensor') {
                const value = entity.state.value || 0;
                const unit = entity.unit_of_measurement || '';
                controls += `
                    <div class="control-row">
                        <span class="control-label">Hodnota:</span>
                        <div class="control-value">${value} ${unit}</div>
                    </div>
                `;
            }
            
            const dps = Object.entries(entity.state).map(([k,v]) => `${k}: ${JSON.stringify(v)}`).join(', ');
            
            // Show unmapped DPS if available
            let unmappedHtml = '';
            if (device.unmapped_dps && Object.keys(device.unmapped_dps).length > 0) {
                const unmappedEntries = Object.entries(device.unmapped_dps)
                    .map(([dps, val]) => `DPS ${dps}: ${JSON.stringify(val)}`)
                    .join(', ');
                unmappedHtml = `
                    <div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px; font-size: 0.85em;">
                        <strong>⚠️ Nepřiřazené DPS:</strong> ${unmappedEntries}
                    </div>
                `;
            }
            
            return `
                <div class="entity platform-${platform}">
                    <div class="entity-header">
                        <div class="entity-name">${entity.friendly_name}</div>
                        <div class="entity-platform">${platform}</div>
                    </div>
                    <div class="entity-controls">${controls}</div>
                    <div class="dps-info">DPS: ${dps}</div>
                    ${unmappedHtml}
                </div>
            `;
        }
        
        function createSlider(entityId, control, value, label) {
            return `
                <div class="control-row">
                    <span class="control-label">${label}:</span>
                    <div class="slider-container" data-entity="${entityId}" data-control="${control}">
                        <div class="slider-fill" style="width: ${value}%"></div>
                        <div class="slider-thumb" style="left: calc(${value}% - 10px)"></div>
                    </div>
                    <div class="control-value">${Math.round(value)}%</div>
                </div>
            `;
        }
        
        function attachEventListeners() {
            document.querySelectorAll('.toggle').forEach(toggle => {
                toggle.onclick = async function() {
                    const entityId = this.dataset.entity;
                    const isActive = this.classList.contains('active');
                    await controlEntity(entityId, { state: !isActive });
                };
            });
            
            document.querySelectorAll('.slider-container').forEach(slider => {
                const thumb = slider.querySelector('.slider-thumb');
                let isDragging = false;
                
                function updateSlider(e) {
                    const rect = slider.getBoundingClientRect();
                    const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
                    const percent = Math.round((x / rect.width) * 100);
                    
                    slider.querySelector('.slider-fill').style.width = percent + '%';
                    thumb.style.left = `calc(${percent}% - 10px)`;
                    slider.nextElementSibling.textContent = percent + '%';
                    return percent;
                }
                
                thumb.onmousedown = () => isDragging = true;
                document.onmousemove = (e) => { if (isDragging) updateSlider(e); };
                document.onmouseup = async (e) => {
                    if (isDragging) {
                        const percent = updateSlider(e);
                        const entityId = slider.dataset.entity;
                        const control = slider.dataset.control;
                        await controlEntity(entityId, { [control]: percent });
                        isDragging = false;
                    }
                };
                
                slider.onclick = async (e) => {
                    if (e.target !== thumb) {
                        const percent = updateSlider(e);
                        await controlEntity(entityId, { [slider.dataset.control]: percent });
                    }
                };
            });
        }
        
        async function controlEntity(entityId, data) {
            const parts = entityId.split('_');
            const deviceId = parts[0];
            const entityName = parts.slice(1).join('_');
            
            try {
                const res = await fetch(`/api/device/${deviceId}/entity/${entityName}/set`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                
                if (res.ok) setTimeout(loadDevices, 500);
            } catch (e) {
                console.error('Chyba:', e);
            }
        }
        
        async function loadEntitiesList() {
            const entities = document.getElementById('entities-list');
            entities.innerHTML = '<div class="loading">Načítám všechny entity...</div>';
            
            try {
                const res = await fetch('/api/devices');
                const devices = await res.json();
                
                let allEntities = [];
                devices.forEach(device => {
                    device.entities.forEach(entity => {
                        allEntities.push({
                            device: device,
                            entity: entity
                        });
                    });
                });
                
                if (allEntities.length === 0) {
                    entities.innerHTML = '<div class="loading">Žádné entity nenalezeny</div>';
                    return;
                }
                
                entities.innerHTML = allEntities.map(item => `
                    <div class="device-card">
                        <div class="entity-header" style="margin-bottom: 15px;">
                            <div>
                                <div class="entity-name">${item.entity.friendly_name}</div>
                                <div style="color: #666; font-size: 0.9em; margin-top: 5px;">
                                    ${item.device.name} (${item.entity.entity_id})
                                </div>
                            </div>
                            <div class="entity-platform">${item.entity.platform}</div>
                        </div>
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                            <div style="margin-bottom: 10px;"><strong>Stav:</strong> ${JSON.stringify(item.entity.state)}</div>
                            <div style="margin-bottom: 10px;"><strong>DPS mapování:</strong> ${JSON.stringify(item.entity.dps_map)}</div>
                            ${item.entity.icon ? `<div><strong>Ikona:</strong> ${item.entity.icon}</div>` : ''}
                        </div>
                    </div>
                `).join('');
            } catch (e) {
                console.error('Chyba:', e);
                entities.innerHTML = '<div class="loading">❌ Chyba při načítání</div>';
            }
        }
        
        async function loadDatabaseStats() {
            // Removed - no longer needed
        }
        
        async function scanDevices() {
            if (!confirm('Spustit sken sítě pro Tuya zařízení? Trvá 20-30 sekund.')) return;
            
            const btn = event.target;
            const originalText = btn.innerHTML;
            btn.innerHTML = '⏳ Skenování...';
            btn.disabled = true;
            
            try {
                const res = await fetch('/api/discovery/scan', { method: 'POST' });
                const data = await res.json();
                
                if (data.success) {
                    const unconfigured = data.devices.filter(d => !d.configured);
                    let message = `✅ Nalezeno ${data.discovered} zařízení!\n\n`;
                    
                    if (unconfigured.length > 0) {
                        message += `⚠️ Nenakonfigurovaná zařízení: ${unconfigured.length}\n`;
                        message += 'Zobrazují se v sekci "Nenakonfigurovaná zařízení"\n\n';
                        unconfigured.forEach(d => {
                            message += `• ${d.id.substring(0, 16)}...\n`;
                            message += `  IP: ${d.ip}\n`;
                        });
                    } else {
                        message += 'Všechna nalezená zařízení jsou již nakonfigurovaná.';
                    }
                    
                    alert(message);
                    loadDevices();
                    loadUnconfiguredDevices();
                } else {
                    alert('❌ Chyba při skenování: ' + (data.error || data.message));
                }
            } catch (e) {
                alert('❌ Chyba při skenování: ' + e.message);
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }
        
        function refreshAll() {
            loadStats();
            loadDevices();
        }
        
        // Inicializace
        loadStats();
        loadDevices();
        loadUnconfiguredDevices();
        setInterval(() => { loadStats(); loadDevices(); }, 5000);
    </script>
</body>
</html>'''
        
        with open(templates_dir / 'index.html', 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info("Created enhanced web interface")
    
    def start(self):
        """Start web server"""
        def run():
            self.app.run(host='0.0.0.0', port=self.port, debug=False, use_reloader=False)
        
        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        logger.info(f"Web server started on http://0.0.0.0:{self.port}")
    
    def stop(self):
        """Stop web server"""
        logger.info("Web server stopped")