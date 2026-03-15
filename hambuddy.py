#!/usr/bin/env python3
"""
CW Companion - Helper application for qlog CW operations
Enhanced with flrig process monitoring and verification
"""

import sys
import subprocess
import xmlrpc.client
import sqlite3
import os
import socket
import threading
import re
import psutil  # For process monitoring
import configparser  # For config file
import json  # For settings persistence
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QTextEdit, QLabel, 
                             QGroupBox, QMessageBox, QLineEdit, QComboBox,
                             QTabWidget, QCheckBox, QTableWidget, QTableWidgetItem,
                             QHeaderView, QDialog, QDialogButtonBox, QSplitter,
                             QSpinBox, QDoubleSpinBox, QFormLayout, QButtonGroup,
                             QRadioButton)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

# Default settings
DEFAULT_SETTINGS = {
    'frequency_tolerance': {
        'lock_tolerance_khz': 1.0,      # Manual selection lock tolerance (±kHz)
        'search_tolerance_khz': 5.0,    # Auto-detection search tolerance (±kHz)
    },
    'dx_cluster': {
        'host': 'dxc.nc7j.com',         # Default cluster
        'port': 7373,
        'callsign': 'DA1BB'
    }
}

# Settings file path
SETTINGS_FILE = os.path.expanduser('~/.config/cw_companion/settings.json')

class DXClusterWorker(QObject):
    """Worker thread for DX cluster connection"""
    spot_received = pyqtSignal(dict)
    connection_status = pyqtSignal(str, str)  # message, status (ok/error)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.socket = None
        
    def connect(self, host, port, callsign):
        """Connect to DX cluster"""
        try:
            print(f"[CLUSTER] Connecting to {host}:{port}")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)
            self.socket.connect((host, port))
            
            # Read login prompt
            data = self.socket.recv(4096).decode('latin-1', errors='ignore')
            print(f"[CLUSTER] Login prompt: {data[:100]}")
            
            # Send callsign
            self.socket.send(f"{callsign}\n".encode())
            
            # Read welcome message
            data = self.socket.recv(4096).decode('latin-1', errors='ignore')
            print(f"[CLUSTER] Welcome: {data[:100]}")
            
            self.connection_status.emit(f"Connected to {host}", "ok")
            self.running = True
            
            # Start reading spots
            self.read_spots()
            
        except Exception as e:
            error_msg = f"Failed to connect: {str(e)}"
            print(f"[CLUSTER ERROR] {error_msg}")
            self.connection_status.emit(error_msg, "error")
            self.running = False
    
    def read_spots(self):
        """Read and parse spots from cluster"""
        buffer = ""
        
        while self.running:
            try:
                data = self.socket.recv(4096).decode('latin-1', errors='ignore')
                if not data:
                    break
                
                buffer += data
                
                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    self.parse_spot_line(line)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[CLUSTER ERROR] Read error: {e}")
                break
        
        self.disconnect()
    
    def parse_spot_line(self, line):
        """Parse a DX spot line"""
        if not line.startswith('DX de '):
            return
        
        try:
            line = line[6:]
            pattern = r'(\S+):\s+(\d+\.\d+)\s+(\S+)\s+(.+?)\s+(\d{4}Z)'
            match = re.match(pattern, line)
            
            if match:
                spotter, freq_str, callsign, comment, time_str = match.groups()
                
                spot = {
                    'spotter': spotter,
                    'freq': float(freq_str) / 1000.0,
                    'callsign': callsign.upper(),
                    'comment': comment.strip(),
                    'time': time_str,
                    'band': self.freq_to_band(float(freq_str) / 1000.0)
                }
                
                print(f"[SPOT] {spot['callsign']} @ {spot['freq']:.3f} MHz - {spot['comment']}")
                self.spot_received.emit(spot)
                
        except Exception as e:
            print(f"[CLUSTER] Parse error: {e} - Line: {line}")
    
    def freq_to_band(self, freq_mhz):
        """Convert frequency to band name"""
        if 1.8 <= freq_mhz < 2.0:
            return '160m'
        elif 3.5 <= freq_mhz < 4.0:
            return '80m'
        elif 7.0 <= freq_mhz < 7.3:
            return '40m'
        elif 10.1 <= freq_mhz < 10.15:
            return '30m'
        elif 14.0 <= freq_mhz < 14.35:
            return '20m'
        elif 18.068 <= freq_mhz < 18.168:
            return '17m'
        elif 21.0 <= freq_mhz < 21.45:
            return '15m'
        elif 24.89 <= freq_mhz < 24.99:
            return '12m'
        elif 28.0 <= freq_mhz < 29.7:
            return '10m'
        else:
            return 'Unknown'
    
    def disconnect(self):
        """Disconnect from cluster"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.connection_status.emit("Disconnected", "error")
        print("[CLUSTER] Disconnected")

class DXClusterDialog(QDialog):
    """Dialog for DX cluster connection settings"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle('Connect to DX Cluster')
        self.setModal(True)
        
        # Load settings or use defaults
        self.settings = settings or DEFAULT_SETTINGS
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel('Select a DX Cluster:'))
        self.cluster_combo = QComboBox()
        self.cluster_combo.addItems([
            'telnet.reversebeacon.net:7000 (RBN)',
            'dxc.nc7j.com:7373 (NC7J DXSpider)',
            'dxc.kc6ete.com:7373 (KC6ETE DXSpider)',
            'dxc.ai9t.com:7373 (AI9T DXSpider)',
            'w6cua.no-ip.org:7300 (W6CUA)',
            'dxfun.com:8000 (DXFun)',
            'Custom...'
        ])
        layout.addWidget(self.cluster_combo)
        
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel('Host:'))
        self.host_input = QLineEdit()
        self.host_input.setText(self.settings['dx_cluster']['host'])
        host_layout.addWidget(self.host_input)
        host_layout.addWidget(QLabel('Port:'))
        self.port_input = QLineEdit()
        self.port_input.setText(str(self.settings['dx_cluster']['port']))
        self.port_input.setMaximumWidth(80)
        host_layout.addWidget(self.port_input)
        layout.addLayout(host_layout)
        
        call_layout = QHBoxLayout()
        call_layout.addWidget(QLabel('Your Callsign:'))
        self.callsign_input = QLineEdit()
        self.callsign_input.setText(self.settings['dx_cluster']['callsign'])
        call_layout.addWidget(self.callsign_input)
        layout.addLayout(call_layout)
        
        info = QLabel('Note: These settings will be saved to your preferences.\n'
                     'DX clusters are free to use. You\'ll receive real-time DX spots.')
        info.setStyleSheet('color: gray; font-style: italic;')
        layout.addWidget(info)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        self.cluster_combo.currentIndexChanged.connect(self.on_cluster_changed)
        
        # Set initial preset based on settings
        self.update_preset_selection()
    
    def update_preset_selection(self):
        """Update preset combo based on current host/port"""
        host = self.host_input.text()
        port = self.port_input.text()
        
        try:
            port_num = int(port)
            if host == 'telnet.reversebeacon.net' and port_num == 7000:
                self.cluster_combo.setCurrentIndex(0)
            elif host == 'dxc.nc7j.com' and port_num == 7373:
                self.cluster_combo.setCurrentIndex(1)
            elif host == 'dxc.kc6ete.com' and port_num == 7373:
                self.cluster_combo.setCurrentIndex(2)
            elif host == 'dxc.ai9t.com' and port_num == 7373:
                self.cluster_combo.setCurrentIndex(3)
            elif host == 'w6cua.no-ip.org' and port_num == 7300:
                self.cluster_combo.setCurrentIndex(4)
            elif host == 'dxfun.com' and port_num == 8000:
                self.cluster_combo.setCurrentIndex(5)
            else:
                self.cluster_combo.setCurrentIndex(6)  # Custom
        except:
            self.cluster_combo.setCurrentIndex(6)  # Custom
    
    def on_cluster_changed(self, index):
        """Handle cluster selection change"""
        if index == 0:
            self.host_input.setText('telnet.reversebeacon.net')
            self.port_input.setText('7000')
        elif index == 1:
            self.host_input.setText('dxc.nc7j.com')
            self.port_input.setText('7373')
        elif index == 2:
            self.host_input.setText('dxc.kc6ete.com')
            self.port_input.setText('7373')
        elif index == 3:
            self.host_input.setText('dxc.ai9t.com')
            self.port_input.setText('7373')
        elif index == 4:
            self.host_input.setText('w6cua.no-ip.org')
            self.port_input.setText('7300')
        elif index == 5:
            self.host_input.setText('dxfun.com')
            self.port_input.setText('8000')

class SettingsDialog(QDialog):
    """Dialog for application settings"""
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle('CW Companion Settings')
        self.setModal(True)
        self.settings = settings or DEFAULT_SETTINGS.copy()
        
        layout = QVBoxLayout()
        
        # Frequency Tolerance Group
        freq_group = QGroupBox("Frequency Tolerance")
        freq_layout = QFormLayout()
        
        # Lock tolerance
        lock_layout = QHBoxLayout()
        self.lock_tolerance = QDoubleSpinBox()
        self.lock_tolerance.setRange(0.1, 50.0)
        self.lock_tolerance.setSingleStep(0.1)
        self.lock_tolerance.setDecimals(1)
        self.lock_tolerance.setSuffix(' kHz')
        self.lock_tolerance.setValue(
            self.settings.get('frequency_tolerance', {}).get('lock_tolerance_khz', 1.0)
        )
        lock_layout.addWidget(self.lock_tolerance)
        lock_info = QLabel('(Manual selection stays locked within this range)')
        lock_info.setStyleSheet('color: gray; font-size: 9pt;')
        lock_layout.addWidget(lock_info)
        freq_layout.addRow('Lock Tolerance (±):', lock_layout)
        
        # Search tolerance
        search_layout = QHBoxLayout()
        self.search_tolerance = QDoubleSpinBox()
        self.search_tolerance.setRange(0.5, 100.0)
        self.search_tolerance.setSingleStep(0.5)
        self.search_tolerance.setDecimals(1)
        self.search_tolerance.setSuffix(' kHz')
        self.search_tolerance.setValue(
            self.settings.get('frequency_tolerance', {}).get('search_tolerance_khz', 5.0)
        )
        search_layout.addWidget(self.search_tolerance)
        search_info = QLabel('(Auto-detection search radius)')
        search_info.setStyleSheet('color: gray; font-size: 9pt;')
        search_layout.addWidget(search_info)
        freq_layout.addRow('Search Tolerance (±):', search_layout)
        
        freq_group.setLayout(freq_layout)
        layout.addWidget(freq_group)
        
        # DX Cluster Group
        cluster_group = QGroupBox("Default DX Cluster")
        cluster_layout = QFormLayout()
        
        # Preset clusters
        self.cluster_combo = QComboBox()
        self.cluster_combo.addItems([
            'telnet.reversebeacon.net:7000 (RBN)',
            'dxc.nc7j.com:7373 (NC7J DXSpider)',
            'dxc.kc6ete.com:7373 (KC6ETE DXSpider)',
            'dxc.ai9t.com:7373 (AI9T DXSpider)',
            'w6cua.no-ip.org:7300 (W6CUA)',
            'dxfun.com:8000 (DXFun)',
            'Custom...'
        ])
        self.cluster_combo.currentIndexChanged.connect(self.on_preset_changed)
        cluster_layout.addRow('Preset:', self.cluster_combo)
        
        # Host
        self.cluster_host = QLineEdit()
        self.cluster_host.setText(
            self.settings.get('dx_cluster', {}).get('host', 'dxc.nc7j.com')
        )
        cluster_layout.addRow('Host:', self.cluster_host)
        
        # Port
        self.cluster_port = QSpinBox()
        self.cluster_port.setRange(1, 65535)
        self.cluster_port.setValue(
            self.settings.get('dx_cluster', {}).get('port', 7373)
        )
        cluster_layout.addRow('Port:', self.cluster_port)
        
        # Callsign
        self.cluster_callsign = QLineEdit()
        self.cluster_callsign.setText(
            self.settings.get('dx_cluster', {}).get('callsign', 'DA1BB')
        )
        self.cluster_callsign.setPlaceholderText('Your callsign')
        cluster_layout.addRow('Callsign:', self.cluster_callsign)
        
        cluster_group.setLayout(cluster_layout)
        layout.addWidget(cluster_group)
        
        # Info label
        info = QLabel(
            'Settings are saved to: ~/.config/cw_companion/settings.json\n'
            'Changes take effect immediately.'
        )
        info.setStyleSheet('color: gray; font-style: italic; font-size: 9pt;')
        layout.addWidget(info)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.restore_defaults)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
        # Set initial preset based on current settings
        self.update_preset_selection()
    
    def on_preset_changed(self, index):
        """Handle preset cluster selection"""
        if index == 0:  # RBN
            self.cluster_host.setText('telnet.reversebeacon.net')
            self.cluster_port.setValue(7000)
        elif index == 1:  # NC7J
            self.cluster_host.setText('dxc.nc7j.com')
            self.cluster_port.setValue(7373)
        elif index == 2:  # KC6ETE
            self.cluster_host.setText('dxc.kc6ete.com')
            self.cluster_port.setValue(7373)
        elif index == 3:  # AI9T
            self.cluster_host.setText('dxc.ai9t.com')
            self.cluster_port.setValue(7373)
        elif index == 4:  # W6CUA
            self.cluster_host.setText('w6cua.no-ip.org')
            self.cluster_port.setValue(7300)
        elif index == 5:  # DXFun
            self.cluster_host.setText('dxfun.com')
            self.cluster_port.setValue(8000)
        # Custom - don't change anything
    
    def update_preset_selection(self):
        """Update preset combo based on current host/port"""
        host = self.cluster_host.text()
        port = self.cluster_port.value()
        
        if host == 'telnet.reversebeacon.net' and port == 7000:
            self.cluster_combo.setCurrentIndex(0)
        elif host == 'dxc.nc7j.com' and port == 7373:
            self.cluster_combo.setCurrentIndex(1)
        elif host == 'dxc.kc6ete.com' and port == 7373:
            self.cluster_combo.setCurrentIndex(2)
        elif host == 'dxc.ai9t.com' and port == 7373:
            self.cluster_combo.setCurrentIndex(3)
        elif host == 'w6cua.no-ip.org' and port == 7300:
            self.cluster_combo.setCurrentIndex(4)
        elif host == 'dxfun.com' and port == 8000:
            self.cluster_combo.setCurrentIndex(5)
        else:
            self.cluster_combo.setCurrentIndex(6)  # Custom
    
    def restore_defaults(self):
        """Restore default settings"""
        reply = QMessageBox.question(
            self, 'Restore Defaults',
            'Reset all settings to defaults?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.lock_tolerance.setValue(DEFAULT_SETTINGS['frequency_tolerance']['lock_tolerance_khz'])
            self.search_tolerance.setValue(DEFAULT_SETTINGS['frequency_tolerance']['search_tolerance_khz'])
            self.cluster_host.setText(DEFAULT_SETTINGS['dx_cluster']['host'])
            self.cluster_port.setValue(DEFAULT_SETTINGS['dx_cluster']['port'])
            self.cluster_callsign.setText(DEFAULT_SETTINGS['dx_cluster']['callsign'])
            self.update_preset_selection()
    
    def get_settings(self):
        """Get current settings from dialog"""
        return {
            'frequency_tolerance': {
                'lock_tolerance_khz': self.lock_tolerance.value(),
                'search_tolerance_khz': self.search_tolerance.value(),
            },
            'dx_cluster': {
                'host': self.cluster_host.text(),
                'port': self.cluster_port.value(),
                'callsign': self.cluster_callsign.text()
            }
        }

class CWCompanion(QMainWindow):
    def __init__(self):
        super().__init__()
        self.flrig_process = None
        self.flrig_client = None
        self.qlog_process = None  # NEW: qlog process
        self.hamclock_process = None  # NEW: hamclock process
        self.qlog_db_path = os.path.expanduser('~/.config/qlog/qlog.db')
        self.last_callsign = None
        self.current_freq = None
        self.dx_spots = []
        self.cluster_worker = None
        self.cluster_thread = None
        
        # NEW: Spot cache and tracking
        self.spot_cache = {}  # frequency (MHz) -> spot data
        self.manually_selected_spot = None  # Track user-selected spots
        self.last_selected_freq = None  # Track last selected frequency
        
        # Load settings
        self.settings = self.load_settings()
        
        # Configuration (legacy)
        self.config_file = os.path.expanduser('~/.config/cw_companion/config.ini')
        self.own_callsign = self.load_config()
        
        # Timers
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_flrig_connection)
        
        self.freq_monitor_timer = QTimer()
        self.freq_monitor_timer.timeout.connect(self.monitor_frequency)
        
        # NEW: Process monitoring timer
        self.process_monitor_timer = QTimer()
        self.process_monitor_timer.timeout.connect(self.monitor_flrig_process)
        
        # NEW: Rig connection monitoring timer
        self.rig_connection_timer = QTimer()
        self.rig_connection_timer.timeout.connect(self.monitor_rig_connection)
        
        # NEW: qlog process monitoring timer
        self.qlog_monitor_timer = QTimer()
        self.qlog_monitor_timer.timeout.connect(self.monitor_qlog_process)
        
        # NEW: hamclock process monitoring timer
        self.hamclock_monitor_timer = QTimer()
        self.hamclock_monitor_timer.timeout.connect(self.monitor_hamclock_process)
        
        self.init_ui()
    
    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()
        own_callsign = "YOUR_CALL"  # Default
        
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            if os.path.exists(self.config_file):
                config.read(self.config_file)
                if 'Station' in config:
                    own_callsign = config['Station'].get('callsign', 'YOUR_CALL')
                print(f"[CONFIG] Loaded callsign: {own_callsign}")
        except Exception as e:
            print(f"[CONFIG] Load error: {e}")
        
        return own_callsign
    
    def save_config(self):
        """Save configuration to file"""
        config = configparser.ConfigParser()
        config['Station'] = {
            'callsign': self.own_callsign
        }
        
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                config.write(f)
            print(f"[CONFIG] Saved callsign: {self.own_callsign}")
        except Exception as e:
            print(f"[CONFIG] Save error: {e}")
            QMessageBox.warning(self, 'Config Error', f'Could not save config: {e}')
    
    def load_settings(self):
        """Load settings from JSON file"""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to handle new settings
                    settings = DEFAULT_SETTINGS.copy()
                    if 'frequency_tolerance' in loaded:
                        settings['frequency_tolerance'].update(loaded['frequency_tolerance'])
                    if 'dx_cluster' in loaded:
                        settings['dx_cluster'].update(loaded['dx_cluster'])
                    print(f"[SETTINGS] Loaded from {SETTINGS_FILE}")
                    return settings
        except Exception as e:
            print(f"[SETTINGS] Error loading settings: {e}")
        
        print("[SETTINGS] Using default settings")
        return DEFAULT_SETTINGS.copy()
    
    def save_settings(self):
        """Save settings to JSON file"""
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(self.settings, f, indent=4)
            print(f"[SETTINGS] Saved to {SETTINGS_FILE}")
            return True
        except Exception as e:
            print(f"[SETTINGS] Error saving settings: {e}")
            QMessageBox.warning(self, 'Save Error', 
                              f'Could not save settings:\n{e}')
            return False
    
    def show_settings_dialog(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self, self.settings)
        if dialog.exec_() == QDialog.Accepted:
            self.settings = dialog.get_settings()
            if self.save_settings():
                QMessageBox.information(self, 'Settings Saved',
                                      'Settings have been saved successfully.\n\n'
                                      f'Lock tolerance: ±{self.settings["frequency_tolerance"]["lock_tolerance_khz"]} kHz\n'
                                      f'Search tolerance: ±{self.settings["frequency_tolerance"]["search_tolerance_khz"]} kHz\n'
                                      f'DX Cluster: {self.settings["dx_cluster"]["host"]}:{self.settings["dx_cluster"]["port"]}')
                print(f"[SETTINGS] Updated: {self.settings}")

        
    def init_ui(self):
        """Initialize UI with modern sidebar design and dark theme"""
        self.setWindowTitle('HamBuddy - Amateur Radio Companion')
        self.setGeometry(100, 100, 1600, 1000)
        
        # Apply dark theme stylesheet
        dark_stylesheet = """
            QMainWindow, QWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
            }
            QGroupBox {
                border: 1px solid #3a3a3a;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
                color: #b0b0b0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 6px 12px;
                color: #e0e0e0;
                min-height: 25px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border: 1px solid #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #252525;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                color: #666666;
            }
            QLineEdit, QTextEdit {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 5px;
                color: #e0e0e0;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 1px solid #4a90e2;
            }
            QTableWidget {
                background-color: #252525;
                alternate-background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                gridline-color: #3a3a3a;
                color: #e0e0e0;
            }
            QTableWidget::item:selected {
                background-color: #4a90e2;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #b0b0b0;
                padding: 5px;
                border: 1px solid #3a3a3a;
                font-weight: bold;
            }
            QLabel {
                color: #e0e0e0;
            }
            QRadioButton {
                color: #e0e0e0;
                spacing: 5px;
            }
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #5a5a5a;
                border-radius: 8px;
                background-color: #2d2d2d;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #4a90e2;
                border-radius: 8px;
                background-color: #4a90e2;
            }
            QCheckBox {
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                background-color: #2d2d2d;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #b0b0b0;
                padding: 8px 16px;
                border: 1px solid #3a3a3a;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #3a3a3a;
                color: #e0e0e0;
            }
            QTabBar::tab:hover {
                background-color: #353535;
            }
            QSplitter::handle {
                background-color: #3a3a3a;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background-color: #4a4a4a;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5a5a5a;
            }
        """
        self.setStyleSheet(dark_stylesheet)
        
        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create splitter for resizable sidebar
        splitter = QSplitter(Qt.Horizontal)
        
        # ===== LEFT SIDEBAR =====
        sidebar = QWidget()
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(300)
        sidebar.setStyleSheet("QWidget { background-color: #252525; border-right: 1px solid #3a3a3a; }")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(5, 10, 5, 10)
        sidebar_layout.setSpacing(5)
        
        # Sidebar header
        header = QLabel("HamBuddy")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #4a90e2; padding: 10px;")
        sidebar_layout.addWidget(header)
        
        subheader = QLabel("Amateur Radio Companion")
        subheader.setStyleSheet("font-size: 11px; color: #888888; padding: 0 10px 10px 10px;")
        sidebar_layout.addWidget(subheader)
        
        # Sidebar sections (collapsible)
        from PyQt5.QtWidgets import QToolButton
        
        # FLRig Control Section
        flrig_section = self.create_collapsible_section("🔧 FLRig Control", sidebar_layout)
        
        # FLRig status indicator
        self.flrig_sidebar_status = QLabel('❌ Not running')
        self.flrig_sidebar_status.setStyleSheet('color: #ff4444; font-size: 9pt; padding: 2px 0;')
        flrig_section.addWidget(self.flrig_sidebar_status)
        
        # Horizontal layout for buttons
        flrig_buttons_layout = QHBoxLayout()
        
        self.btn_start = QPushButton('Start')
        self.btn_start.clicked.connect(self.start_flrig)
        flrig_buttons_layout.addWidget(self.btn_start)
        
        self.btn_stop = QPushButton('Stop')
        self.btn_stop.clicked.connect(self.stop_flrig)
        self.btn_stop.setEnabled(False)
        flrig_buttons_layout.addWidget(self.btn_stop)
        
        self.btn_restart = QPushButton('Restart')
        self.btn_restart.clicked.connect(self.restart_flrig)
        self.btn_restart.setEnabled(False)
        flrig_buttons_layout.addWidget(self.btn_restart)
        
        # Create widget to hold the button layout
        flrig_buttons_widget = QWidget()
        flrig_buttons_widget.setLayout(flrig_buttons_layout)
        flrig_section.addWidget(flrig_buttons_widget)
        
        # My Rig Control Section (placeholder for future features)
        rig_section = self.create_collapsible_section("📡 My Rig Control", sidebar_layout)
        
        self.btn_reconnect_rig = QPushButton('Reconnect Rig')
        self.btn_reconnect_rig.clicked.connect(self.reconnect_rig)
        self.btn_reconnect_rig.setEnabled(False)
        rig_section.addWidget(self.btn_reconnect_rig)
        
        # Qlog Control Section
        qlog_section = self.create_collapsible_section("📝 Qlog Control", sidebar_layout)
        
        self.qlog_status_label = QLabel('❌ Not running')
        self.qlog_status_label.setStyleSheet('color: red; font-size: 9pt;')
        qlog_section.addWidget(self.qlog_status_label)
        
        # Horizontal layout for buttons
        qlog_buttons_layout = QHBoxLayout()
        
        self.btn_start_qlog = QPushButton('Start')
        self.btn_start_qlog.clicked.connect(self.start_qlog)
        qlog_buttons_layout.addWidget(self.btn_start_qlog)
        
        self.btn_stop_qlog = QPushButton('Stop')
        self.btn_stop_qlog.clicked.connect(self.stop_qlog)
        self.btn_stop_qlog.setEnabled(False)
        qlog_buttons_layout.addWidget(self.btn_stop_qlog)
        
        self.btn_restart_qlog = QPushButton('Restart')
        self.btn_restart_qlog.clicked.connect(self.restart_qlog)
        self.btn_restart_qlog.setEnabled(False)
        qlog_buttons_layout.addWidget(self.btn_restart_qlog)
        
        # Create widget to hold the button layout
        qlog_buttons_widget = QWidget()
        qlog_buttons_widget.setLayout(qlog_buttons_layout)
        qlog_section.addWidget(qlog_buttons_widget)
        
        # HamClock Control Section
        hamclock_section = self.create_collapsible_section("🌍 HamClock Control", sidebar_layout)
        
        self.hamclock_status_label = QLabel('❌ Not running')
        self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
        hamclock_section.addWidget(self.hamclock_status_label)
        
        # Horizontal layout for buttons
        hamclock_buttons_layout = QHBoxLayout()
        
        self.btn_start_hamclock = QPushButton('Start')
        self.btn_start_hamclock.clicked.connect(self.start_hamclock)
        hamclock_buttons_layout.addWidget(self.btn_start_hamclock)
        
        self.btn_stop_hamclock = QPushButton('Stop')
        self.btn_stop_hamclock.clicked.connect(self.stop_hamclock)
        self.btn_stop_hamclock.setEnabled(False)
        hamclock_buttons_layout.addWidget(self.btn_stop_hamclock)
        
        self.btn_restart_hamclock = QPushButton('Restart')
        self.btn_restart_hamclock.clicked.connect(self.restart_hamclock)
        self.btn_restart_hamclock.setEnabled(False)
        hamclock_buttons_layout.addWidget(self.btn_restart_hamclock)
        
        # Create widget to hold the button layout
        hamclock_buttons_widget = QWidget()
        hamclock_buttons_widget.setLayout(hamclock_buttons_layout)
        hamclock_section.addWidget(hamclock_buttons_widget)
        
        
        # CW Style Settings Section
        style_section = self.create_collapsible_section("📻 CW Style Settings", sidebar_layout)
        
        self.style_group = QButtonGroup()
        
        self.radio_normal = QRadioButton("Normal")
        self.radio_normal.setChecked(True)
        self.radio_normal.toggled.connect(lambda: self.on_style_changed('normal'))
        self.style_group.addButton(self.radio_normal)
        style_section.addWidget(self.radio_normal)
        
        self.radio_sota = QRadioButton("SOTA")
        self.radio_sota.toggled.connect(lambda: self.on_style_changed('sota'))
        self.style_group.addButton(self.radio_sota)
        style_section.addWidget(self.radio_sota)
        
        self.radio_pota = QRadioButton("POTA")
        self.radio_pota.toggled.connect(lambda: self.on_style_changed('pota'))
        self.style_group.addButton(self.radio_pota)
        style_section.addWidget(self.radio_pota)
        
        self.radio_contest = QRadioButton("Contest")
        self.radio_contest.toggled.connect(lambda: self.on_style_changed('contest'))
        self.style_group.addButton(self.radio_contest)
        style_section.addWidget(self.radio_contest)
        
        self.current_cw_style = 'normal'
        
        # Add separator
        separator_label = QLabel("─" * 20)
        separator_label.setStyleSheet('color: #555; font-size: 8pt;')
        style_section.addWidget(separator_label)
        
        # Direction setting
        direction_label = QLabel("Who is calling CQ?")
        direction_label.setStyleSheet('color: #e0e0e0; font-size: 10pt; font-weight: bold; margin-top: 5px;')
        style_section.addWidget(direction_label)
        
        self.direction_group = QButtonGroup()
        
        self.radio_i_call = QRadioButton("I am calling CQ")
        self.radio_i_call.setChecked(True)
        self.radio_i_call.toggled.connect(lambda: self.on_direction_changed('calling'))
        self.direction_group.addButton(self.radio_i_call)
        style_section.addWidget(self.radio_i_call)
        
        self.radio_other_calls = QRadioButton("Other station calls")
        self.radio_other_calls.toggled.connect(lambda: self.on_direction_changed('answering'))
        self.direction_group.addButton(self.radio_other_calls)
        style_section.addWidget(self.radio_other_calls)
        
        self.cw_direction = 'calling'  # Default: I am calling CQ
        
        # Settings Section
        settings_section = self.create_collapsible_section("⚙️ Settings", sidebar_layout)
        
        self.btn_settings = QPushButton('Preferences')
        self.btn_settings.clicked.connect(self.show_settings_dialog)
        settings_section.addWidget(self.btn_settings)
        
        theme_btn = QPushButton('Theme')
        theme_btn.setEnabled(False)
        settings_section.addWidget(theme_btn)
        
        audio_btn = QPushButton('Audio')
        audio_btn.setEnabled(False)
        settings_section.addWidget(audio_btn)
        
        advanced_btn = QPushButton('Advanced')
        advanced_btn.setEnabled(False)
        settings_section.addWidget(advanced_btn)
        
        sidebar_layout.addStretch()
        
        # ===== MAIN AREA =====
        main_area = QWidget()
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(15, 15, 15, 15)
        main_area_layout.setSpacing(15)
        
        # Rig Status Section (Top)
        rig_status_group = QGroupBox("Rig Status")
        rig_status_group.setMinimumHeight(25)
        rig_status_group.setMaximumHeight(75)
        rig_status_layout = QHBoxLayout()
        rig_status_layout.setSpacing(20)
        
        # Status labels with green/red styling
        self.status_label = QLabel('Process: Not running')
        self.status_label.setStyleSheet('color: #ff4444; font-size: 11pt; font-weight: bold;')
        rig_status_layout.addWidget(self.status_label)
        
        self.xmlrpc_status_label = QLabel('XML-RPC: Disconnected')
        self.xmlrpc_status_label.setStyleSheet('color: #ff4444; font-size: 11pt; font-weight: bold;')
        rig_status_layout.addWidget(self.xmlrpc_status_label)
        
        self.rig_connection_label = QLabel('Rig: Not connected')
        self.rig_connection_label.setStyleSheet('color: #ff4444; font-size: 11pt; font-weight: bold;')
        rig_status_layout.addWidget(self.rig_connection_label)
        
        rig_status_layout.addStretch()
        
        # Rig info
        self.freq_label = QLabel('Frequency: 14.100 MHz')
        self.freq_label.setStyleSheet('font-size: 13pt; font-weight: bold; color: #4ade80;')
        rig_status_layout.addWidget(self.freq_label)
        
        self.mode_label = QLabel('Mode: CW-U')
        self.mode_label.setStyleSheet('font-size: 12pt; font-weight: bold; color: #e0e0e0;')
        rig_status_layout.addWidget(self.mode_label)
        
        self.band_label = QLabel('Band: 20m')
        self.band_label.setStyleSheet('font-size: 12pt; font-weight: bold; color: #e0e0e0;')
        rig_status_layout.addWidget(self.band_label)
        
        self.btn_refresh = QPushButton('↻')
        self.btn_refresh.clicked.connect(self.update_rig_info)
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setMaximumWidth(40)
        self.btn_refresh.setToolTip('Refresh rig info')
        rig_status_layout.addWidget(self.btn_refresh)
        
        # Connected badge (top right)
        self.connected_badge = QLabel('Rig: Connected [12:34]')
        self.connected_badge.setStyleSheet('''
            background-color: #4ade80; 
            color: #1e1e1e; 
            font-weight: bold; 
            padding: 5px 10px; 
            border-radius: 4px;
            font-size: 10pt;
        ''')
        self.connected_badge.setVisible(False)
        rig_status_layout.addWidget(self.connected_badge)
        
        rig_status_group.setLayout(rig_status_layout)
        main_area_layout.addWidget(rig_status_group)
        
        # Current QSO Section
        qso_group = QGroupBox("Call")
        qso_group.setMinimumHeight(25)
        qso_group.setMaximumHeight(70)
        qso_layout = QHBoxLayout()
        
        self.current_call_label = QLabel('DL0MHN')
        self.current_call_label.setFont(QFont('Arial', 18, QFont.Bold))
        self.current_call_label.setStyleSheet('color: #fbbf24; padding: 5px;')
        qso_layout.addWidget(self.current_call_label)
        
        qso_layout.addStretch()
        
        self.manual_call_input = QLineEdit()
        self.manual_call_input.setPlaceholderText('Enter callsign...')
        self.manual_call_input.setStyleSheet('font-size: 13pt; min-width: 200px; padding: 8px;')
        qso_layout.addWidget(self.manual_call_input)
        
        self.btn_load_call = QPushButton('Load')
        self.btn_load_call.clicked.connect(self.load_manual_callsign)
        self.btn_load_call.setStyleSheet('background-color: #fbbf24; color: #1e1e1e; font-weight: bold; padding: 8px 20px;')
        qso_layout.addWidget(self.btn_load_call)
        
        self.btn_clear_selection = QPushButton('Save')
        self.btn_clear_selection.clicked.connect(self.clear_manual_selection)
        self.btn_clear_selection.setStyleSheet('background-color: #fbbf24; color: #1e1e1e; font-weight: bold; padding: 8px 20px;')
        qso_layout.addWidget(self.btn_clear_selection)
        
        # Current QSO counter
        qso_counter = QLabel("current QSO: 0")
        qso_counter.setStyleSheet('font-size: 10pt; color: #888888;')
        qso_layout.addWidget(qso_counter)
        
        qso_group.setLayout(qso_layout)
        main_area_layout.addWidget(qso_group)
        
        # CW Example + Abbreviations (side by side)
        cw_splitter = QSplitter(Qt.Horizontal)
        
        # CW Example
        cw_example_group = QGroupBox("CW example")
        cw_example_layout = QVBoxLayout()
        
        self.cw_format_tab = QTextEdit()
        self.cw_format_tab.setReadOnly(True)
        self.cw_format_tab.setFont(QFont('Courier', 13))  # Increased from 11
        self.cw_format_tab.setMinimumHeight(400)  # Increased from 400
        cw_example_layout.addWidget(self.cw_format_tab)
        
        cw_example_group.setLayout(cw_example_layout)
        cw_splitter.addWidget(cw_example_group)
        
        # CW Abbreviations (narrower)
        abbrev_group = QGroupBox("CW Abbreviations")
        abbrev_layout = QVBoxLayout()
        
        self.abbreviations_tab = QTextEdit()
        self.abbreviations_tab.setReadOnly(True)
        self.abbreviations_tab.setFont(QFont('Courier', 9))  # Smaller font
        self.abbreviations_tab.setMinimumHeight(400)  # Increased from 400
        abbrev_layout.addWidget(self.abbreviations_tab)
        
        abbrev_group.setLayout(abbrev_layout)
        cw_splitter.addWidget(abbrev_group)
        
        # Set initial sizes (CW example much wider, abbreviations narrower)
        cw_splitter.setSizes([700, 350])  # Changed from [600, 400]
        
        main_area_layout.addWidget(cw_splitter)
        
        # ===== BOTTOM: DX CLUSTER =====
        cluster_group = QGroupBox("CW Cluster")
        cluster_group.setMinimumHeight(350)  # Increased from 200
        cluster_group.setMaximumHeight(500)  # Increased from 300

        cluster_layout = QVBoxLayout()
        
        # TOP ROW: Filters in horizontal layout
        filters_layout = QHBoxLayout()

        # SECOND ROW: Cluster controls
        cluster_ctrl = QHBoxLayout()
        
        self.btn_connect_cluster = QPushButton('Connect')
        self.btn_connect_cluster.setMaximumWidth(100)
        self.btn_connect_cluster.clicked.connect(self.connect_cluster)
        cluster_ctrl.addWidget(self.btn_connect_cluster)
        
        self.btn_disconnect_cluster = QPushButton('Disconnect')
        self.btn_disconnect_cluster.setMaximumWidth(100)
        self.btn_disconnect_cluster.clicked.connect(self.disconnect_cluster)
        cluster_ctrl.addWidget(self.btn_disconnect_cluster)
        
        cluster_ctrl.addStretch()
        
        self.spot_match_label = QLabel('🔴 No spot at this frequency')
        self.spot_match_label.setStyleSheet('color: #888888; font-size: 9pt; font-family: monospace;')
        cluster_ctrl.addWidget(self.spot_match_label)
        
        filters_layout.addLayout(cluster_ctrl)

        # Vertical separator
        separator1 = QLabel("│")
        separator1.setStyleSheet('color: #555; font-size: 20pt;')
        filters_layout.addWidget(separator1)
        
        # WPM Filter Section
        wpm_widget = QWidget()
        wpm_layout = QVBoxLayout(wpm_widget)
        wpm_layout.setContentsMargins(5, 5, 5, 5)
        
        wpm_label = QLabel("⚡ WPM Speed:")
        wpm_label.setStyleSheet('color: #4a9eff; font-size: 10pt; font-weight: bold;')
        wpm_layout.addWidget(wpm_label)
        
        # WPM buttons in horizontal layout
        wpm_buttons_layout = QHBoxLayout()
        
        self.wpm_filter_group = QButtonGroup()
        self.wpm_filter_group.setExclusive(True)
        self.current_wpm_filter = 'all'
        
        self.radio_wpm_all = QRadioButton("All")
        self.radio_wpm_all.setChecked(True)
        self.radio_wpm_all.toggled.connect(lambda: self.on_wpm_filter_changed('all'))
        self.wpm_filter_group.addButton(self.radio_wpm_all)
        wpm_buttons_layout.addWidget(self.radio_wpm_all)
        
        self.radio_wpm_10 = QRadioButton("<10")
        self.radio_wpm_10.toggled.connect(lambda: self.on_wpm_filter_changed(10))
        self.wpm_filter_group.addButton(self.radio_wpm_10)
        wpm_buttons_layout.addWidget(self.radio_wpm_10)
        
        self.radio_wpm_15 = QRadioButton("<15")
        self.radio_wpm_15.toggled.connect(lambda: self.on_wpm_filter_changed(15))
        self.wpm_filter_group.addButton(self.radio_wpm_15)
        wpm_buttons_layout.addWidget(self.radio_wpm_15)
        
        self.radio_wpm_20 = QRadioButton("<20")
        self.radio_wpm_20.toggled.connect(lambda: self.on_wpm_filter_changed(20))
        self.wpm_filter_group.addButton(self.radio_wpm_20)
        wpm_buttons_layout.addWidget(self.radio_wpm_20)
        
        self.radio_wpm_25 = QRadioButton("<25")
        self.radio_wpm_25.toggled.connect(lambda: self.on_wpm_filter_changed(25))
        self.wpm_filter_group.addButton(self.radio_wpm_25)
        wpm_buttons_layout.addWidget(self.radio_wpm_25)
        
        self.radio_wpm_30 = QRadioButton("<30")
        self.radio_wpm_30.toggled.connect(lambda: self.on_wpm_filter_changed(30))
        self.wpm_filter_group.addButton(self.radio_wpm_30)
        wpm_buttons_layout.addWidget(self.radio_wpm_30)
        
        self.radio_wpm_over30 = QRadioButton(">30")
        self.radio_wpm_over30.toggled.connect(lambda: self.on_wpm_filter_changed('>30'))
        self.wpm_filter_group.addButton(self.radio_wpm_over30)
        wpm_buttons_layout.addWidget(self.radio_wpm_over30)
        
        wpm_layout.addLayout(wpm_buttons_layout)
        filters_layout.addWidget(wpm_widget)
        
        # Vertical separator
        separator1 = QLabel("│")
        separator1.setStyleSheet('color: #555; font-size: 20pt;')
        filters_layout.addWidget(separator1)
        
        # Band Filter Section
        band_widget = QWidget()
        band_layout = QVBoxLayout(band_widget)
        band_layout.setContentsMargins(5, 5, 5, 5)
        
        band_label = QLabel("📡 Bands: (uncheck all to select specific bands)")
        band_label.setStyleSheet('color: #4ade80; font-size: 10pt; font-weight: bold;')
        band_layout.addWidget(band_label)
        
        # All bands checkbox
        self.check_all_bands = QCheckBox("All bands")
        self.check_all_bands.setChecked(True)
        self.check_all_bands.toggled.connect(self.on_all_bands_toggled)
        band_layout.addWidget(self.check_all_bands)
        
        # Help text
        #self.band_help = QLabel("(Uncheck 'All' to select specific bands)")
        #self.band_help.setStyleSheet('color: #ff8800; font-size: 8pt; font-style: italic;')
        #band_layout.addWidget(self.band_help)
        
        # Band checkboxes in TWO horizontal rows
        bands = ['160m', '80m', '60m', '40m', '30m', '20m', '17m', '15m', '12m', '10m', '6m']
        
        # First row: 160m - 20m
        band_row1 = QHBoxLayout()
        self.band_filters = {}
        from functools import partial
        
        for band in bands[:11]:  # First 6 bands
            checkbox = QCheckBox(band)
            checkbox.setChecked(False)
            checkbox.setEnabled(False)
            checkbox.toggled.connect(partial(self.on_band_filter_changed, band))
            band_row1.addWidget(checkbox)
            self.band_filters[band] = checkbox
        
        band_layout.addLayout(band_row1)
        
        ## Second row: 17m - 6m
        #band_row2 = QHBoxLayout()
        #for band in bands[6:]:  # Last 5 bands
        #    checkbox = QCheckBox(band)
        #    checkbox.setChecked(False)
        #    checkbox.setEnabled(False)
        #    checkbox.toggled.connect(partial(self.on_band_filter_changed, band))
        #    band_row2.addWidget(checkbox)
        #    self.band_filters[band] = checkbox
        
        #band_row2.addStretch()  # Fill remaining space
        #band_layout.addLayout(band_row2)
        
        self.selected_bands = set()
        filters_layout.addWidget(band_widget)
        
        filters_layout.addStretch()
        cluster_layout.addLayout(filters_layout)
        
        
        # Create horizontal splitter for two cluster tables
        cluster_splitter = QSplitter(Qt.Horizontal)
        cluster_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #444;
                width: 2px;
            }
        """)
        
        # Left side: ALL SPOTS
        all_spots_widget = QWidget()
        all_spots_layout = QVBoxLayout(all_spots_widget)
        all_spots_layout.setContentsMargins(0, 0, 0, 0)
        
        all_spots_header = QLabel("📡 All DX Spots")
        all_spots_header.setStyleSheet('color: #4a9eff; font-size: 11pt; font-weight: bold; padding: 5px;')
        all_spots_layout.addWidget(all_spots_header)
        
        self.spots_table = QTableWidget()
        self.spots_table.setColumnCount(5)
        self.spots_table.setHorizontalHeaderLabels(['Time', 'Freq', 'Call', 'Band', 'Comment'])
        self.spots_table.setAlternatingRowColors(True)
        
        header = self.spots_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        
        self.spots_table.setMinimumHeight(300)
        self.spots_table.setMaximumHeight(350)
        self.spots_table.cellClicked.connect(self.on_spot_clicked)
        
        all_spots_layout.addWidget(self.spots_table)
        cluster_splitter.addWidget(all_spots_widget)
        
        # Right side: FILTERED SPOTS
        filtered_spots_widget = QWidget()
        filtered_spots_layout = QVBoxLayout(filtered_spots_widget)
        filtered_spots_layout.setContentsMargins(0, 0, 0, 0)
        
        self.filtered_spots_header = QLabel("🎯 Filtered Spots (All speeds)")
        self.filtered_spots_header.setStyleSheet('color: #4ade80; font-size: 11pt; font-weight: bold; padding: 5px;')
        filtered_spots_layout.addWidget(self.filtered_spots_header)
        
        self.filtered_spots_table = QTableWidget()
        self.filtered_spots_table.setColumnCount(5)
        self.filtered_spots_table.setHorizontalHeaderLabels(['Time', 'Freq', 'Call', 'Band', 'Comment'])
        self.filtered_spots_table.setAlternatingRowColors(True)
        
        filtered_header = self.filtered_spots_table.horizontalHeader()
        filtered_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        filtered_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        filtered_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        filtered_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        filtered_header.setSectionResizeMode(4, QHeaderView.Stretch)
        
        self.filtered_spots_table.setMinimumHeight(100)
        self.filtered_spots_table.setMaximumHeight(350)
        self.filtered_spots_table.cellClicked.connect(self.on_filtered_spot_clicked)
        
        filtered_spots_layout.addWidget(self.filtered_spots_table)
        cluster_splitter.addWidget(filtered_spots_widget)
        
        # Set initial sizes (equal split)
        cluster_splitter.setSizes([800, 800])
        
        cluster_layout.addWidget(cluster_splitter)
        cluster_group.setLayout(cluster_layout)
        
        main_area_layout.addWidget(cluster_group)
        
        # Add widgets to splitter
        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        
        # Set initial sizes (sidebar smaller)
        splitter.setSizes([250, 1350])
        
        main_layout.addWidget(splitter)
        
        # Load welcome screen
        self.load_welcome_screen()
    
    def create_collapsible_section(self, title, parent_layout):
        """Create a collapsible section for sidebar"""
        from PyQt5.QtWidgets import QToolButton
        
        # Create toggle button
        toggle = QToolButton()
        toggle.setText(title)
        toggle.setCheckable(True)
        toggle.setChecked(True)
        toggle.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: transparent;
                color: #e0e0e0;
                font-weight: bold;
                font-size: 12px;
                padding: 8px 5px;
                text-align: left;
            }
            QToolButton:hover {
                background-color: #2d2d2d;
            }
            QToolButton::indicator {
                width: 0px;
            }
        """)
        toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        
        # Create content widget with layout
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 5, 10, 5)
        content_layout.setSpacing(5)
        content.setMaximumHeight(400)
        
        # Connect toggle
        def toggle_section():
            if toggle.isChecked():
                content.setMaximumHeight(400)
                toggle.setArrowType(Qt.DownArrow)
            else:
                content.setMaximumHeight(0)
                toggle.setArrowType(Qt.RightArrow)
        
        toggle.setArrowType(Qt.DownArrow)
        toggle.clicked.connect(toggle_section)
        
        parent_layout.addWidget(toggle)
        parent_layout.addWidget(content)
        
        return content_layout  # Return the layout, not the widget
    def start_flrig(self):
        """Start flrig with verification"""
        # Check if already running
        is_running, existing_proc = self.is_flrig_already_running()
        
        if is_running:
            reply = QMessageBox.question(
                self, 
                'flrig Already Running',
                'flrig is already running. Do you want to:\n\n'
                '• Connect to existing instance (Yes)\n'
                '• Start a new instance anyway (No)\n'
                '• Cancel (Cancel)',
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                # Connect to existing instance
                print("[FLRIG] Connecting to existing instance...")
                self.btn_start.setEnabled(False)
                self.btn_stop.setEnabled(True)
                self.btn_restart.setEnabled(True)
                self.status_label.setText('Process: Running (existing)')
                self.status_label.setStyleSheet('color: #4ade80; font-size: 11pt; font-weight: bold;')
                self.flrig_sidebar_status.setText('✅ Running')
                self.flrig_sidebar_status.setStyleSheet('color: #4ade80; font-size: 9pt; padding: 2px 0;')
                self.connection_timer.start(1000)
                # Start process monitoring
                self.process_monitor_timer.start(2000)
                return
            # If No, continue to start new instance
        
        try:
            print("[FLRIG] Starting new instance...")
            self.flrig_process = subprocess.Popen(['flrig'])
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_restart.setEnabled(True)
            self.status_label.setText('Process: Starting...')
            self.status_label.setStyleSheet('color: #fbbf24; font-size: 11pt; font-weight: bold;')
            self.flrig_sidebar_status.setText('⏳ Starting...')
            self.flrig_sidebar_status.setStyleSheet('color: #fbbf24; font-size: 9pt; padding: 2px 0;')
            self.connection_timer.start(1000)
            # Start process monitoring
            self.process_monitor_timer.start(2000)
            
        except FileNotFoundError:
            QMessageBox.critical(self, 'Error', 
                               'flrig not found. Please install flrig first.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to start flrig: {e}')
    
    # ===== NEW: Process monitoring =====
    
    def monitor_flrig_process(self):
        """Monitor if flrig process is still running"""
        is_running, proc = self.is_flrig_already_running()
        
        if not is_running:
            # flrig process died
            print("[FLRIG] Process no longer running!")
            self.status_label.setText('Process: Stopped (crashed?)')
            self.status_label.setStyleSheet('color: #ff4444; font-size: 11pt; font-weight: bold;')
            self.flrig_sidebar_status.setText('❌ Crashed')
            self.flrig_sidebar_status.setStyleSheet('color: #ff4444; font-size: 9pt; padding: 2px 0;')
            
            # Stop all monitoring
            self.process_monitor_timer.stop()
            self.connection_timer.stop()
            self.freq_monitor_timer.stop()
            self.rig_connection_timer.stop()
            
            # Reset state
            self.flrig_process = None
            self.flrig_client = None
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.btn_restart.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            self.btn_reconnect_rig.setEnabled(False)
            
            self.xmlrpc_status_label.setText('XML-RPC: Disconnected')
            self.xmlrpc_status_label.setStyleSheet('color: red; font-weight: bold;')
            self.rig_connection_label.setText('Rig: Not connected')
            self.rig_connection_label.setStyleSheet('color: red; font-weight: bold;')
            
            self.clear_rig_info()
            
            QMessageBox.warning(self, 'flrig Stopped', 
                              'flrig process has stopped running.')
        else:
            # Process is running
            self.status_label.setText('Process: Running')
            self.status_label.setStyleSheet('color: #4ade80; font-size: 11pt; font-weight: bold;')
            self.flrig_sidebar_status.setText('✅ Running')
            self.flrig_sidebar_status.setStyleSheet('color: #4ade80; font-size: 9pt; padding: 2px 0;')
    
    # ===== NEW: Rig connection monitoring =====
    
    def monitor_rig_connection(self):
        """Monitor if flrig is still connected to the rig"""
        if not self.flrig_client:
            return
        
        try:
            # Check multiple indicators to verify real rig connection
            xcvr = self.flrig_client.rig.get_xcvr()
            freq = self.flrig_client.rig.get_vfo()
            
            # Verify we have a real rig connected:
            # 1. Transceiver name should not be empty or "NONE"
            # 2. Frequency should be reasonable (> 0)
            
            is_connected = False
            
            if xcvr and xcvr.strip() and xcvr.upper() != "NONE":
                freq_hz = int(freq)
                # Reasonable frequency range: 100 kHz to 60 MHz
                if freq_hz > 100000 and freq_hz < 60000000:
                    is_connected = True
            
            if is_connected:
                # Rig is actually connected
                self.rig_connection_label.setText(f'Rig: Connected ({xcvr})')
                self.rig_connection_label.setStyleSheet('color: green; font-weight: bold;')
                self.btn_reconnect_rig.setEnabled(True)
            else:
                # No real rig connection
                self.rig_connection_label.setText('Rig: Not connected')
                self.rig_connection_label.setStyleSheet('color: red; font-weight: bold;')
                self.btn_reconnect_rig.setEnabled(True)
            
        except Exception as e:
            # XML-RPC error - flrig not responding properly
            print(f"[RIG] Connection check error: {e}")
            self.rig_connection_label.setText('Rig: Error checking status')
            self.rig_connection_label.setStyleSheet('color: orange; font-weight: bold;')
            self.btn_reconnect_rig.setEnabled(False)
    
    def reconnect_rig(self):
        """Reconnect/reinitialize the rig"""
        if not self.flrig_client:
            QMessageBox.warning(self, 'Error', 'flrig is not connected')
            return
        
        try:
            reply = QMessageBox.question(
                self,
                'Reconnect Rig',
                'This will reinitialize the rig connection in flrig.\n\n'
                'Make sure:\n'
                '• Your rig is powered on\n'
                '• USB/Serial cable is connected\n'
                '• Correct COM port is selected in flrig\n\n'
                'Continue with reconnection?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                self.rig_connection_label.setText('Rig: Reconnecting...')
                self.rig_connection_label.setStyleSheet('color: orange; font-weight: bold;')
                
                # Try to reinitialize the rig
                # Note: flrig's XML-RPC API doesn't have a direct "reconnect" method
                # But we can try to set/get values which might trigger reconnection
                
                QMessageBox.information(
                    self,
                    'Manual Reconnection Required',
                    'Please use flrig\'s GUI to reconnect:\n\n'
                    '1. Go to flrig Config menu\n'
                    '2. Click "Initialize" button\n'
                    '3. Or restart flrig\n\n'
                    'The connection status will update automatically.'
                )
                
                # Force an immediate check
                QTimer.singleShot(1000, self.monitor_rig_connection)
                
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to reconnect: {e}')
    
    def stop_flrig(self):
        """Stop flrig"""
        if self.flrig_process:
            print("[FLRIG] Stopping...")
            self.flrig_process.terminate()
            self.flrig_process.wait(timeout=5)
            self.flrig_process = None
            self.flrig_client = None
        
        # Stop all timers
        self.connection_timer.stop()
        self.freq_monitor_timer.stop()
        self.process_monitor_timer.stop()
        self.rig_connection_timer.stop()
        
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_restart.setEnabled(False)
        self.btn_refresh.setEnabled(False)
        self.btn_reconnect_rig.setEnabled(False)
        
        self.status_label.setText('Process: Stopped')
        self.status_label.setStyleSheet('color: #ff4444; font-size: 11pt; font-weight: bold;')
        self.flrig_sidebar_status.setText('❌ Not running')
        self.flrig_sidebar_status.setStyleSheet('color: #ff4444; font-size: 9pt; padding: 2px 0;')
        self.xmlrpc_status_label.setText('XML-RPC: Disconnected')
        self.xmlrpc_status_label.setStyleSheet('color: red; font-weight: bold;')
        self.rig_connection_label.setText('Rig: Not connected')
        self.rig_connection_label.setStyleSheet('color: red; font-weight: bold;')
        
        self.clear_rig_info()
    
    def restart_flrig(self):
        """Restart flrig"""
        self.stop_flrig()
        QTimer.singleShot(1000, self.start_flrig)
    
    def check_flrig_connection(self):
        """Check flrig XML-RPC connection"""
        try:
            if not self.flrig_client:
                self.flrig_client = xmlrpc.client.ServerProxy("http://localhost:12345")
            
            version = self.flrig_client.main.get_version()
            print(f"[FLRIG] XML-RPC connected v{version}")
            
            self.connection_timer.stop()
            self.xmlrpc_status_label.setText(f'XML-RPC: Connected (v{version})')
            self.xmlrpc_status_label.setStyleSheet('color: green; font-weight: bold;')
            self.btn_refresh.setEnabled(True)
            self.btn_reconnect_rig.setEnabled(True)  # Enable reconnect button
            
            # Start frequency monitoring
            self.freq_monitor_timer.start(500)
            
            # Start rig connection monitoring
            self.rig_connection_timer.start(3000)  # Check every 3 seconds
            
            # Do immediate check
            self.update_rig_info()
            self.monitor_rig_connection()
            
        except Exception as e:
            # Still waiting for XML-RPC to be ready
            pass
    
    def monitor_frequency(self):
        """Monitor frequency changes and match with spots"""
        if not self.flrig_client:
            return
        
        try:
            freq = self.flrig_client.rig.get_vfo()
            freq_mhz = float(freq) / 1000000
            
            # Update display
            self.update_rig_info()
            
            # Check for matching spots
            self.check_spot_match(freq_mhz)
            
        except Exception as e:
            print(f"[FREQ] Monitor error: {e}")
    
    def check_spot_match(self, freq_mhz):
        """Check if current frequency matches a DX spot"""
        # Get tolerances from settings (convert kHz to MHz)
        lock_tolerance_mhz = self.settings['frequency_tolerance']['lock_tolerance_khz'] / 1000.0
        search_tolerance_mhz = self.settings['frequency_tolerance']['search_tolerance_khz'] / 1000.0
        
        # Round frequency to 3 decimal places for cache key
        freq_key = round(freq_mhz, 3)
        
        # If user manually selected a spot, check if we're still on that frequency
        if self.manually_selected_spot:
            selected_freq = self.manually_selected_spot['freq']
            # If still within lock tolerance of manually selected frequency, keep showing it
            if abs(freq_mhz - selected_freq) <= lock_tolerance_mhz:
                spot = self.manually_selected_spot
                self.spot_match_label.setText(
                    f'🟢 SPOT: {spot["callsign"]} @ {spot["freq"]:.3f} MHz '
                    f'[{spot["time"]}] - {spot["comment"]} (selected)'
                )
                self.spot_match_label.setStyleSheet('color: green; font-weight: bold;')
                return
            else:
                # User has moved away from manually selected spot
                self.manually_selected_spot = None
        
        # Check cache first (exact frequency matches)
        if freq_key in self.spot_cache:
            spot = self.spot_cache[freq_key]
            self.spot_match_label.setText(
                f'🟢 SPOT: {spot["callsign"]} @ {spot["freq"]:.3f} MHz '
                f'[{spot["time"]}] - {spot["comment"]}'
            )
            self.spot_match_label.setStyleSheet('color: green; font-weight: bold;')
            
            # Auto-load callsign format only if different from current
            if spot['callsign'] != self.last_callsign:
                self.current_call_label.setText(spot['callsign'])
                self.load_cw_format_for_callsign(spot['callsign'])
            return
        
        # Check recent spots with configurable search tolerance
        best_match = None
        closest_distance = float('inf')
        
        for spot in self.dx_spots:
            spot_freq = spot['freq']
            distance = abs(freq_mhz - spot_freq)
            
            # Match within search tolerance
            if distance <= search_tolerance_mhz and distance < closest_distance:
                closest_distance = distance
                best_match = spot
        
        if best_match:
            self.spot_match_label.setText(
                f'🟢 SPOT: {best_match["callsign"]} @ {best_match["freq"]:.3f} MHz '
                f'[{best_match["time"]}] - {best_match["comment"]}'
            )
            self.spot_match_label.setStyleSheet('color: green; font-weight: bold;')
            
            # Auto-load callsign format only if different from current
            if best_match['callsign'] != self.last_callsign:
                self.current_call_label.setText(best_match['callsign'])
                self.load_cw_format_for_callsign(best_match['callsign'])
        else:
            # No match
            self.spot_match_label.setText('🔴 No spot at this frequency')
            self.spot_match_label.setStyleSheet('color: red; font-weight: bold;')
    
    def update_rig_info(self):
        """Update rig info"""
        if not self.flrig_client:
            return
        try:
            xcvr = self.flrig_client.rig.get_xcvr()
            freq = self.flrig_client.rig.get_vfo()
            mode = self.flrig_client.rig.get_mode()
            freq_mhz = float(freq) / 1000000
            band = self.freq_to_band(freq_mhz)
            
            # Check if we have a real rig
            if xcvr and xcvr.strip() and xcvr.upper() != "NONE" and freq_mhz > 0.1:
                self.freq_label.setText(f'Frequency: {freq_mhz:.6f} MHz')
                self.mode_label.setText(f'Mode: {mode}')
                self.band_label.setText(f'Band: {band} | Rig: {xcvr}')
            else:
                self.freq_label.setText('Frequency: --- (No rig)')
                self.mode_label.setText('Mode: ---')
                self.band_label.setText('Band: --- | Rig: Not connected')
        except Exception as e:
            print(f"[RIG] Error: {e}")
            self.freq_label.setText('Frequency: --- (Error)')
            self.mode_label.setText('Mode: ---')
            self.band_label.setText('Band: ---')
    
    def freq_to_band(self, freq_mhz):
        """Convert freq to band"""
        if 1.8 <= freq_mhz < 2.0: return '160m'
        elif 3.5 <= freq_mhz < 4.0: return '80m'
        elif 7.0 <= freq_mhz < 7.3: return '40m'
        elif 10.1 <= freq_mhz < 10.15: return '30m'
        elif 14.0 <= freq_mhz < 14.35: return '20m'
        elif 18.068 <= freq_mhz < 18.168: return '17m'
        elif 21.0 <= freq_mhz < 21.45: return '15m'
        elif 24.89 <= freq_mhz < 24.99: return '12m'
        elif 28.0 <= freq_mhz < 29.7: return '10m'
        return 'Unknown'
    
    def clear_rig_info(self):
        """Clear rig info"""
        self.freq_label.setText('Frequency: ---')
        self.mode_label.setText('Mode: ---')
        self.band_label.setText('Band: --- | Rig: Not connected')
        self.spot_match_label.setText('🔴 No spot at this frequency')
        self.spot_match_label.setStyleSheet('color: red; font-weight: bold;')
    
    # ===== qlog process management =====
    
    def is_qlog_already_running(self):
        """Check if qlog is already running"""
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] == 'qlog':
                    return True, proc
                # Also check cmdline
                if proc.info['cmdline'] and 'qlog' in ' '.join(proc.info['cmdline']):
                    return True, proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False, None
    
    def start_qlog(self):
        """Start qlog with verification"""
        # Check if already running
        is_running, existing_proc = self.is_qlog_already_running()
        
        if is_running:
            reply = QMessageBox.question(
                self,
                'qlog Already Running',
                'qlog is already running. Do you want to:\n\n'
                '• Use existing instance (Yes)\n'
                '• Start a new instance anyway (No)\n'
                '• Cancel (Cancel)',
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                # Use existing instance
                print("[QLOG] Using existing instance...")
                self.btn_start_qlog.setEnabled(False)
                self.btn_stop_qlog.setEnabled(True)
                self.btn_restart_qlog.setEnabled(True)
                self.qlog_status_label.setText('Process: Running (existing)')
                self.qlog_status_label.setStyleSheet('color: green; font-weight: bold;')
                # Start process monitoring
                self.qlog_monitor_timer.start(2000)
                return
            # If No, continue to start new instance
        
        try:
            print("[QLOG] Starting new instance...")
            self.qlog_process = subprocess.Popen(['qlog'])
            self.btn_start_qlog.setEnabled(False)
            self.btn_stop_qlog.setEnabled(True)
            self.btn_restart_qlog.setEnabled(True)
            self.qlog_status_label.setText('Process: Starting...')
            self.qlog_status_label.setStyleSheet('color: orange; font-weight: bold;')
            
            # Start process monitoring
            self.qlog_monitor_timer.start(2000)
            
            # Update status after a moment
            QTimer.singleShot(2000, self.update_qlog_status)
            
        except FileNotFoundError:
            QMessageBox.critical(self, 'Error',
                               'qlog not found. Please install qlog first.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to start qlog: {e}')
    
    def stop_qlog(self):
        """Stop qlog"""
        if self.qlog_process:
            print("[QLOG] Stopping...")
            self.qlog_process.terminate()
            try:
                self.qlog_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[QLOG] Force killing...")
                self.qlog_process.kill()
            self.qlog_process = None
        
        self.qlog_monitor_timer.stop()
        self.btn_start_qlog.setEnabled(True)
        self.btn_stop_qlog.setEnabled(False)
        self.btn_restart_qlog.setEnabled(False)
        self.qlog_status_label.setText('Process: Stopped')
        self.qlog_status_label.setStyleSheet('color: red; font-weight: bold;')
    
    def restart_qlog(self):
        """Restart qlog"""
        self.stop_qlog()
        QTimer.singleShot(1000, self.start_qlog)
    
    def monitor_qlog_process(self):
        """Monitor if qlog process is still running"""
        is_running, proc = self.is_qlog_already_running()
        
        if not is_running:
            # qlog process died
            print("[QLOG] Process no longer running!")
            self.qlog_status_label.setText('Process: Stopped (crashed?)')
            self.qlog_status_label.setStyleSheet('color: red; font-weight: bold;')
            
            # Stop monitoring
            self.qlog_monitor_timer.stop()
            
            # Reset state
            self.qlog_process = None
            self.btn_start_qlog.setEnabled(True)
            self.btn_stop_qlog.setEnabled(False)
            self.btn_restart_qlog.setEnabled(False)
            
            QMessageBox.warning(self, 'qlog Stopped',
                              'qlog process has stopped running.')
        else:
            # Process is running
            self.qlog_status_label.setText('Process: Running')
            self.qlog_status_label.setStyleSheet('color: green; font-weight: bold;')
    
    def update_qlog_status(self):
        """Update qlog status display"""
        is_running, proc = self.is_qlog_already_running()
        if is_running:
            self.qlog_status_label.setText('Process: Running')
            self.qlog_status_label.setStyleSheet('color: green; font-weight: bold;')
    
    # ===== HamClock Control =====
    
    def is_hamclock_already_running(self):
        """Check if hamclock is already running"""
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] and 'hamclock' in proc.info['name'].lower():
                    return True, proc
                if proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline']).lower()
                    if 'hamclock' in cmdline:
                        return True, proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False, None
    
    def start_hamclock(self):
        """Start hamclock with verification"""
        is_running, existing_proc = self.is_hamclock_already_running()
        
        if is_running:
            reply = QMessageBox.question(self, 'HamClock Running',
                'HamClock is already running. Do you want to:\n\n'
                'Yes - Use existing process\n'
                'No - Start a new instance',
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            
            if reply == QMessageBox.Yes:
                self.hamclock_process = existing_proc
                self.hamclock_status_label.setText('✅ Running (existing)')
                self.hamclock_status_label.setStyleSheet('color: green; font-size: 9pt;')
                self.btn_start_hamclock.setEnabled(False)
                self.btn_stop_hamclock.setEnabled(True)
                self.btn_restart_hamclock.setEnabled(True)
                self.hamclock_monitor_timer.start(2000)
                return
            elif reply == QMessageBox.Cancel:
                return
        
        # Try to start hamclock
        try:
            self.hamclock_status_label.setText('⏳ Starting...')
            self.hamclock_status_label.setStyleSheet('color: orange; font-size: 9pt;')
            
            self.hamclock_process = subprocess.Popen(['hamclock'])
            
            # Wait a moment and verify it started
            QTimer.singleShot(2000, self.verify_hamclock_started)
            
        except FileNotFoundError:
            QMessageBox.critical(self, 'Error',
                'Could not find hamclock executable.\n\n'
                'Please install HamClock or update the path in Settings.')
            self.hamclock_status_label.setText('❌ Not installed')
            self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
        except Exception as e:
            QMessageBox.critical(self, 'Error',
                f'Failed to start hamclock:\n{e}')
            self.hamclock_status_label.setText('❌ Failed to start')
            self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
    
    def verify_hamclock_started(self):
        """Verify hamclock actually started"""
        is_running, proc = self.is_hamclock_already_running()
        
        if is_running:
            self.hamclock_status_label.setText('✅ Running')
            self.hamclock_status_label.setStyleSheet('color: green; font-size: 9pt;')
            self.btn_start_hamclock.setEnabled(False)
            self.btn_stop_hamclock.setEnabled(True)
            self.btn_restart_hamclock.setEnabled(True)
            self.hamclock_monitor_timer.start(2000)
            print("[HAMCLOCK] Started successfully")
        else:
            self.hamclock_status_label.setText('❌ Failed to start')
            self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
            self.btn_start_hamclock.setEnabled(True)
            print("[HAMCLOCK] Failed to start")
    
    def stop_hamclock(self):
        """Stop hamclock"""
        if self.hamclock_process:
            try:
                self.hamclock_process.terminate()
                self.hamclock_process.wait(timeout=5)
                self.hamclock_process = None
            except:
                try:
                    self.hamclock_process.kill()
                except:
                    pass
        
        # Also try to kill any running hamclock processes
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and 'hamclock' in proc.info['name'].lower():
                    proc.terminate()
            except:
                pass
        
        self.hamclock_monitor_timer.stop()
        self.hamclock_status_label.setText('❌ Stopped')
        self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
        self.btn_start_hamclock.setEnabled(True)
        self.btn_stop_hamclock.setEnabled(False)
        self.btn_restart_hamclock.setEnabled(False)
        print("[HAMCLOCK] Stopped")
    
    def restart_hamclock(self):
        """Restart hamclock"""
        self.stop_hamclock()
        QTimer.singleShot(1000, self.start_hamclock)
    
    def monitor_hamclock_process(self):
        """Monitor if hamclock process is still running"""
        is_running, proc = self.is_hamclock_already_running()
        
        if not is_running:
            print("[HAMCLOCK] Process no longer running!")
            self.hamclock_status_label.setText('❌ Stopped')
            self.hamclock_status_label.setStyleSheet('color: red; font-size: 9pt;')
            
            self.hamclock_monitor_timer.stop()
            self.hamclock_process = None
            self.btn_start_hamclock.setEnabled(True)
            self.btn_stop_hamclock.setEnabled(False)
            self.btn_restart_hamclock.setEnabled(False)
            
            QMessageBox.warning(self, 'HamClock Stopped',
                              'HamClock process has stopped running.')
        else:
            self.hamclock_status_label.setText('✅ Running')
            self.hamclock_status_label.setStyleSheet('color: green; font-size: 9pt;')
    
    def update_hamclock_status(self):
        """Update hamclock status display"""
        is_running, proc = self.is_hamclock_already_running()
        if is_running:
            self.hamclock_status_label.setText('✅ Running')
            self.hamclock_status_label.setStyleSheet('color: green; font-size: 9pt;')
    
    # ===== DX Cluster =====
    
    def connect_cluster(self):
        """Connect to DX cluster"""
        dialog = DXClusterDialog(self, self.settings)
        if dialog.exec_() == QDialog.Accepted:
            host = dialog.host_input.text()
            port = int(dialog.port_input.text())
            callsign = dialog.callsign_input.text()
            
            # Save cluster settings for next time
            self.settings['dx_cluster']['host'] = host
            self.settings['dx_cluster']['port'] = port
            self.settings['dx_cluster']['callsign'] = callsign
            self.save_settings()
            
            self.cluster_worker = DXClusterWorker()
            self.cluster_worker.spot_received.connect(self.on_cluster_spot)
            self.cluster_worker.connection_status.connect(self.on_cluster_status)
            
            self.cluster_thread = threading.Thread(
                target=self.cluster_worker.connect,
                args=(host, port, callsign)
            )
            self.cluster_thread.daemon = True
            self.cluster_thread.start()
            
            self.btn_connect_cluster.setEnabled(False)
            self.btn_disconnect_cluster.setEnabled(True)
    
    def disconnect_cluster(self):
        """Disconnect from cluster"""
        if self.cluster_worker:
            self.cluster_worker.disconnect()
            self.cluster_worker = None
        self.btn_connect_cluster.setEnabled(True)
        self.btn_disconnect_cluster.setEnabled(False)
    
    def extract_wpm_from_comment(self, comment):
        """Extract WPM speed from comment string"""
        import re
        # Look for patterns like "20 WPM", "25WPM", "20-25 WPM", etc.
        match = re.search(r'(\d+)\s*-?\s*(\d+)?\s*wpm', comment, re.IGNORECASE)
        if match:
            # If range like "20-25 WPM", use the lower number
            wpm = int(match.group(1))
            return wpm
        return None
    
    def passes_wpm_filter(self, wpm):
        """Check if WPM passes current filter"""
        if self.current_wpm_filter == 'all':
            return True
        elif self.current_wpm_filter == '>30':
            return wpm is not None and wpm > 30
        else:
            # Filter is a number like 10, 15, 20, 25, 30
            return wpm is not None and wpm < self.current_wpm_filter
    
    def passes_band_filter(self, band):
        """Check if band passes current filter"""
        # If selected_bands is empty, all bands pass (when "All bands" is checked)
        if not self.selected_bands:
            return True
        # Otherwise, check if band is in selected set
        return band in self.selected_bands
    
    def passes_filters(self, spot):
        """Check if spot passes both WPM and band filters"""
        wpm = spot.get('wpm')
        band = spot.get('band')
        
        # Must pass both filters
        wpm_pass = self.passes_wpm_filter(wpm)
        band_pass = self.passes_band_filter(band)
        
        return wpm_pass and band_pass
    
    def on_cluster_spot(self, spot):
        """Handle received spot"""
        self.dx_spots.insert(0, spot)
        if len(self.dx_spots) > 50:
            self.dx_spots.pop()
        
        # Add to spot cache using frequency as key
        freq_key = round(spot['freq'], 3)
        self.spot_cache[freq_key] = spot
        
        # Extract WPM from comment
        wpm = self.extract_wpm_from_comment(spot['comment'])
        spot['wpm'] = wpm  # Store WPM in spot dict
        
        # Add to ALL SPOTS table
        self.spots_table.insertRow(0)
        self.spots_table.setItem(0, 0, QTableWidgetItem(spot['time']))
        self.spots_table.setItem(0, 1, QTableWidgetItem(f"{spot['freq']:.3f}"))
        
        call_item = QTableWidgetItem(spot['callsign'])
        call_item.setFont(QFont('Arial', 10, QFont.Bold))
        call_item.setForeground(QColor(0, 0, 255))
        self.spots_table.setItem(0, 2, call_item)
        
        self.spots_table.setItem(0, 3, QTableWidgetItem(spot['band']))
        self.spots_table.setItem(0, 4, QTableWidgetItem(spot['comment']))
        
        # Keep only 15 rows in all spots table
        if self.spots_table.rowCount() > 15:
            self.spots_table.removeRow(15)
        
        # Add to FILTERED table if it passes both filters
        if self.passes_filters(spot):
            self.add_to_filtered_table(spot)
    
    def add_to_filtered_table(self, spot):
        """Add spot to filtered table"""
        self.filtered_spots_table.insertRow(0)
        self.filtered_spots_table.setItem(0, 0, QTableWidgetItem(spot['time']))
        self.filtered_spots_table.setItem(0, 1, QTableWidgetItem(f"{spot['freq']:.3f}"))
        
        call_item = QTableWidgetItem(spot['callsign'])
        call_item.setFont(QFont('Arial', 10, QFont.Bold))
        call_item.setForeground(QColor(0, 200, 0))  # Green for filtered
        self.filtered_spots_table.setItem(0, 2, call_item)
        
        self.filtered_spots_table.setItem(0, 3, QTableWidgetItem(spot['band']))
        
        # Highlight WPM in comment if present
        comment = spot['comment']
        if spot.get('wpm'):
            comment_item = QTableWidgetItem(comment)
            comment_item.setForeground(QColor(255, 215, 0))  # Gold for WPM
            self.filtered_spots_table.setItem(0, 4, comment_item)
        else:
            self.filtered_spots_table.setItem(0, 4, QTableWidgetItem(comment))
        
        # Keep only 15 rows in filtered table
        if self.filtered_spots_table.rowCount() > 15:
            self.filtered_spots_table.removeRow(15)
    
    def on_cluster_status(self, message, status):
        """Handle cluster status"""
        if status == 'ok':
            # Show connection status briefly, then revert to spot status
            self.spot_match_label.setText(f'✅ {message}')
            self.spot_match_label.setStyleSheet('color: #4ade80; font-size: 9pt; font-family: monospace;')
        else:
            self.spot_match_label.setText(f'❌ {message}')
            self.spot_match_label.setStyleSheet('color: #ff4444; font-size: 9pt; font-family: monospace;')
    
    def on_spot_clicked(self, row, col):
        """Handle spot click"""
        if row < len(self.dx_spots):
            spot = self.dx_spots[row]
            
            # Mark this spot as manually selected
            self.manually_selected_spot = spot
            self.last_selected_freq = spot['freq']
            
            # Add to cache
            freq_key = round(spot['freq'], 3)
            self.spot_cache[freq_key] = spot
            
            # Update display
            self.current_call_label.setText(spot['callsign'])
            self.load_cw_format_for_callsign(spot['callsign'])
            
            # Update spot match indicator immediately
            self.spot_match_label.setText(
                f'🟢 SPOT: {spot["callsign"]} @ {spot["freq"]:.3f} MHz '
                f'[{spot["time"]}] - {spot["comment"]} (selected)'
            )
            self.spot_match_label.setStyleSheet('color: green; font-weight: bold;')
            
            # Tune rig if connected
            if self.flrig_client:
                try:
                    freq_hz = int(spot['freq'] * 1000000)
                    self.flrig_client.rig.set_vfo(freq_hz)
                    self.flrig_client.rig.set_mode('CW')
                    self.update_rig_info()
                    print(f"[RIG] Tuned to {spot['freq']:.3f} MHz for {spot['callsign']}")
                except Exception as e:
                    print(f"[RIG] Tune error: {e}")
                    QMessageBox.warning(self, 'Tune Error', 
                                      f'Could not tune rig: {e}\n\n'
                                      'Make sure rig is connected and flrig is working.')
    
    def on_filtered_spot_clicked(self, row, col):
        """Handle filtered spot click"""
        # Get the spot from filtered table
        if row < self.filtered_spots_table.rowCount():
            # Extract spot details from table
            time_str = self.filtered_spots_table.item(row, 0).text()
            freq_str = self.filtered_spots_table.item(row, 1).text()
            callsign = self.filtered_spots_table.item(row, 2).text()
            
            # Find the spot in dx_spots list
            for spot in self.dx_spots:
                if (spot['callsign'] == callsign and 
                    spot['time'] == time_str and 
                    f"{spot['freq']:.3f}" == freq_str):
                    
                    # Mark this spot as manually selected
                    self.manually_selected_spot = spot
                    self.last_selected_freq = spot['freq']
                    
                    # Add to cache
                    freq_key = round(spot['freq'], 3)
                    self.spot_cache[freq_key] = spot
                    
                    # Update display
                    self.current_call_label.setText(spot['callsign'])
                    self.load_cw_format_for_callsign(spot['callsign'])
                    
                    # Update spot match indicator
                    wpm_info = f" ({spot.get('wpm')} WPM)" if spot.get('wpm') else ""
                    self.spot_match_label.setText(
                        f'🟢 FILTERED: {spot["callsign"]} @ {spot["freq"]:.3f} MHz '
                        f'[{spot["time"]}]{wpm_info} - {spot["comment"]} (selected)'
                    )
                    self.spot_match_label.setStyleSheet('color: green; font-weight: bold;')
                    
                    # Tune rig if connected
                    if self.flrig_client:
                        try:
                            freq_hz = int(spot['freq'] * 1000000)
                            self.flrig_client.rig.set_vfo(freq_hz)
                            self.flrig_client.rig.set_mode('CW')
                            self.update_rig_info()
                            print(f"[RIG] Tuned to {spot['freq']:.3f} MHz for {spot['callsign']} (filtered)")
                        except Exception as e:
                            print(f"[RIG] Tune error: {e}")
                            QMessageBox.warning(self, 'Tune Error', 
                                              f'Could not tune rig: {e}\n\n'
                                              'Make sure rig is connected and flrig is working.')
                    break
    
    def on_wpm_filter_changed(self, filter_value):
        """Handle WPM filter change"""
        if not hasattr(self, 'current_wpm_filter'):
            return
        
        self.current_wpm_filter = filter_value
        print(f"[WPM FILTER] Changed to: {filter_value}")
        
        # Update header label
        self.update_filter_header()
        
        # Rebuild filtered table
        self.rebuild_filtered_table()
    
    def on_all_bands_toggled(self, checked):
        """Handle 'All bands' checkbox toggle"""
        print(f"[BAND FILTER] All bands toggled: checked={checked}")
        
        if checked:
            # Disable and uncheck all individual band checkboxes
            for band, checkbox in self.band_filters.items():
                checkbox.setEnabled(False)
                checkbox.setChecked(False)
                print(f"[BAND FILTER] Disabled checkbox: {band}")
            self.selected_bands.clear()
            print("[BAND FILTER] All bands selected (individual bands disabled)")
            
        else:
            # Enable all individual band checkboxes
            for band, checkbox in self.band_filters.items():
                checkbox.setEnabled(True)
                print(f"[BAND FILTER] Enabled checkbox: {band}")
            print("[BAND FILTER] Individual band selection enabled - you can now click band checkboxes!")
            
        
        # Update header and rebuild
        self.update_filter_header()
        self.rebuild_filtered_table()
    
    def on_band_filter_changed(self, band, checked):
        """Handle individual band checkbox change"""
        print(f"[BAND FILTER] Band checkbox changed: {band} = {checked}")
        
        if checked:
            self.selected_bands.add(band)
            print(f"[BAND FILTER] Added: {band} (total selected: {len(self.selected_bands)})")
        else:
            self.selected_bands.discard(band)
            print(f"[BAND FILTER] Removed: {band} (total selected: {len(self.selected_bands)})")
        
        # If no bands selected, revert to "All bands"
        if not self.selected_bands and not self.check_all_bands.isChecked():
            print("[BAND FILTER] No bands selected, reverting to 'All bands'")
            self.check_all_bands.setChecked(True)
        
        # Update header and rebuild
        self.update_filter_header()
        self.rebuild_filtered_table()
    
    def update_filter_header(self):
        """Update filtered spots header with current filter info"""
        # WPM part
        if self.current_wpm_filter == 'all':
            wpm_text = "All speeds"
        elif self.current_wpm_filter == '>30':
            wpm_text = "> 30 WPM"
        else:
            wpm_text = f"< {self.current_wpm_filter} WPM"
        
        # Band part
        if not self.selected_bands:
            band_text = "All bands"
        else:
            # Show selected bands
            bands_list = sorted(self.selected_bands, key=lambda x: int(x.replace('m', '')))
            if len(bands_list) <= 3:
                band_text = ", ".join(bands_list)
            else:
                band_text = f"{len(bands_list)} bands"
        
        # Combine
        self.filtered_spots_header.setText(f"🎯 Filtered Spots ({wpm_text}, {band_text})")
    
    def rebuild_filtered_table(self):
        """Rebuild filtered table based on current filters"""
        # Clear filtered table
        self.filtered_spots_table.setRowCount(0)
        
        # Re-add spots that pass both filters
        for spot in self.dx_spots:
            if self.passes_filters(spot):
                self.add_to_filtered_table(spot)
    
    def load_manual_callsign(self):
        """Load manual callsign"""
        callsign = self.manual_call_input.text().strip().upper()
        if callsign:
            # Clear manual spot selection when user enters callsign manually
            self.manually_selected_spot = None
            self.current_call_label.setText(callsign)
            self.load_cw_format_for_callsign(callsign)
            self.spot_match_label.setText('🔵 Manual entry')
            self.spot_match_label.setStyleSheet('color: blue; font-weight: bold;')
    
    def clear_manual_selection(self):
        """Clear manual selection and resume auto-tracking"""
        self.manually_selected_spot = None
        self.last_selected_freq = None
        self.current_call_label.setText('---')
        self.manual_call_input.clear()
        self.spot_match_label.setText('🟠 Auto-tracking resumed')
        self.spot_match_label.setStyleSheet('color: orange; font-weight: bold;')
        
        # Reset to generic example
        self.load_welcome_screen()
        
        # Force an immediate frequency check
        if self.flrig_client:
            try:
                freq = self.flrig_client.rig.get_vfo()
                freq_mhz = float(freq) / 1000000
                self.check_spot_match(freq_mhz)
            except:
                pass
        
        print("[UI] Manual selection cleared, auto-tracking resumed")
    
    def load_welcome_screen(self, callsign=None):
        """Load welcome screen with short style-specific examples"""
        
        # If no callsign provided, use generic placeholder
        if not callsign or callsign == '---':
            other_call = "W1AW"
        else:
            other_call = callsign
        
        # Short, concise examples without long explanations
        if self.current_cw_style == 'normal':
            # Use HTML for colored text
            if self.cw_direction == 'calling':
                # YOU are calling CQ
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║          📻 NORMAL CW - Working {other_call}              ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #ff6b6b;'>                &lt; QRL? QRL? QRL?</span>
<span style='color: #ff6b6b;'>                &lt; CQ CQ CQ DE {self.own_callsign} {self.own_callsign} PSE K</span>
<span style='color: #4a9eff;'>&gt; {other_call}</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} GM ES TNX FER CALL =</span>
<span style='color: #ff6b6b;'>                &lt; RST 599 5nn =</span>
<span style='color: #ff6b6b;'>                &lt; NAME Benni Benni =</span>
<span style='color: #ff6b6b;'>                &lt; QTH Braunschweig Braunschweig =</span>
<span style='color: #ff6b6b;'>                &lt; HW? {other_call} DE {self.own_callsign} KN</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} DE {other_call} GM OM Max =</span>
<span style='color: #4a9eff;'>&gt; RST 599 5nn =</span>
<span style='color: #4a9eff;'>&gt; NAME Max Max =</span>
<span style='color: #4a9eff;'>&gt; QTH Poznan Poznan =</span>
<span style='color: #4a9eff;'>&gt; HW? {self.own_callsign} DE {other_call} KN</span>
<span style='color: #ff6b6b;'>                &lt; R R {other_call} DE {self.own_callsign} =</span>
<span style='color: #ff6b6b;'>                &lt; FB TU FER QSO = PSE QSL = 73 ES GUD DX</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} SK TU E E</span>
</div>
</div>
"""
            else:
                # THEY are calling CQ, YOU answer
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║          📻 NORMAL CW - Working {other_call}              ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #4a9eff;'>&gt; QRL? QRL? QRL?</span>
<span style='color: #4a9eff;'>&gt; CQ CQ CQ DE {other_call} {other_call} PSE K</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} PSE KN</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} DE {other_call} GM ES TNX FER CALL =</span>
<span style='color: #4a9eff;'>&gt; RST 599 5nn =</span>
<span style='color: #4a9eff;'>&gt; NAME Max Max =</span>
<span style='color: #4a9eff;'>&gt; QTH Poznan Poznan =</span>
<span style='color: #4a9eff;'>&gt; HW? {self.own_callsign} DE {other_call} KN</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} GM OM Max =</span>
<span style='color: #ff6b6b;'>                &lt; RST 599 5nn =</span>
<span style='color: #ff6b6b;'>                &lt; NAME Benni Benni =</span>
<span style='color: #ff6b6b;'>                &lt; QTH Braunschweig Braunschweig =</span>
<span style='color: #ff6b6b;'>                &lt; HW? {other_call} DE {self.own_callsign} KN</span>
<span style='color: #4a9eff;'>&gt; R R {self.own_callsign} DE {other_call} =</span>
<span style='color: #4a9eff;'>&gt; FB TU FER QSO = PSE QSL = 73 ES GUD DX</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} DE {other_call} TU</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} OK =</span>
<span style='color: #ff6b6b;'>                &lt; FB TU FER QSO = PSE QSL = 73 ES GUD DX</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} SK TU E E</span>
</div>
</div>
"""
            self.cw_format_tab.setHtml(welcome)
        elif self.current_cw_style == 'sota':
            # Use HTML for colored text
            if self.cw_direction == 'calling':
                # YOU are ACTIVATING (on summit, calling CQ)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      ⛰️  SOTA ACTIVATING - Working {other_call}           ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #ff6b6b;'>                &lt; CQ SOTA DE {self.own_callsign}/P DM/NS-123 K</span>
<span style='color: #4a9eff;'>&gt; {other_call}</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} 599 DM/NS-123</span>
<span style='color: #4a9eff;'>&gt; R 599 TNX</span>
<span style='color: #ff6b6b;'>                &lt; 73</span>
</div>
</div>
"""
            else:
                # YOU are CHASING (they're on summit)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      ⛰️  SOTA CHASING - Working {other_call}              ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #4a9eff;'>&gt; CQ SOTA DE {other_call}/P K</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} K</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} 599 W1/HA-001</span>
<span style='color: #ff6b6b;'>                &lt; R 599 73</span>
</div>
</div>
"""
            self.cw_format_tab.setHtml(welcome)
        elif self.current_cw_style == 'pota':
            # Use HTML for colored text
            if self.cw_direction == 'calling':
                # YOU are ACTIVATING (at park, calling CQ)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      🏞️  POTA ACTIVATING - Working {other_call}           ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #ff6b6b;'>                &lt; CQ POTA DE {self.own_callsign}/P DL-0123 K</span>
<span style='color: #4a9eff;'>&gt; {other_call}</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} 599 DL-0123</span>
<span style='color: #4a9eff;'>&gt; R 599 TNX</span>
<span style='color: #ff6b6b;'>                &lt; 73</span>
</div>
</div>
"""
            else:
                # YOU are HUNTING (they're at park)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      🏞️  POTA HUNTING - Working {other_call}              ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #4a9eff;'>&gt; CQ POTA DE {other_call}/P K</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} DE {self.own_callsign} K</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} 599 K-0001</span>
<span style='color: #ff6b6b;'>                &lt; R 599 73</span>
</div>
</div>
"""
            self.cw_format_tab.setHtml(welcome)
        else:  # contest
            # Use HTML for colored text
            if self.cw_direction == 'calling':
                # YOU are RUNNING (calling CQ TEST)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      🏆 CONTEST RUNNING - Working {other_call}            ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #ff6b6b;'>                &lt; CQ TEST {self.own_callsign} TEST</span>
<span style='color: #4a9eff;'>&gt; {other_call}</span>
<span style='color: #ff6b6b;'>                &lt; {other_call} TU 599 001</span>
<span style='color: #4a9eff;'>&gt; R 599 184</span>
<span style='color: #ff6b6b;'>                &lt; TU</span>
</div>
</div>
"""
            else:
                # YOU are S&P (Search and Pounce - answering CQ)
                welcome = f"""
<div style='font-family: Courier; font-size: 22pt; white-space: pre;'>
<div style='text-align: center;'>
<b>╔═══════════════════════════════════════════════════════════╗</b>
<b>║      🏆 CONTEST S&P - Working {other_call}                ║</b>
<b>╚═══════════════════════════════════════════════════════════╝</b>
</div>
<div style='text-align: left;'>
<span style='color: #4a9eff;'>&gt; CQ TEST {other_call} TEST</span>
<span style='color: #ff6b6b;'>                &lt; {self.own_callsign}</span>
<span style='color: #4a9eff;'>&gt; {self.own_callsign} 599 752</span>
<span style='color: #ff6b6b;'>                &lt; 599 042</span>
<span style='color: #4a9eff;'>&gt; TU</span>
</div>
</div>
"""
            self.cw_format_tab.setHtml(welcome)
        
        # Populate abbreviations tab
        abbreviations = """
╔════════════════════════════════════════════════════════════════════╗
║                    CW ABBREVIATIONS REFERENCE                      ║
╚════════════════════════════════════════════════════════════════════╝

GREETINGS:
GM  = Good Morning              GA  = Good Afternoon
GE  = Good Evening              GN  = Good Night

COMMON RESPONSES:
R   = Roger (I understand)      TU  = Thank you
TNX = Thanks                    FB  = Fine business (great!)
CONGRATS = Congratulations      GL  = Good luck
VY  = Very                      CUAGN = See you again

SIGNAL REPORTS:
UR  = Your                      RST = Readability-Signal-Tone
599 = Perfect signal            579 = Very good
559 = Good                      539 = Fair

LOCATIONS:
QTH = Location (where)          WX  = Weather  
TEMP = Temperature              HR  = Here

EQUIPMENT:
RIG = Transceiver/Radio         ANT = Antenna
PWR = Power                     HW  = How (copy)?

REQUESTS:
PSE = Please                    AGN = Again (repeat)
QRS = Send slower               QRQ = Send faster
QSY = Change frequency          QRX = Wait

OPERATING:
CQ  = Calling any station       DE  = From (French "de")
K   = Go ahead / Over           KN  = Over to you only
BK  = Break / Back to you       SK  = End of contact
CL  = Closing station           AR  = End of message

QUESTIONS (Q-CODES):
QRL? = Is frequency busy?       QRM = Interference
QRN = Static noise              QSB = Fading signal
QRP = Low power operation       QRO = High power
QRT = Stop transmitting         QRV = Ready to receive
QRZ = Who is calling me?        QSO = Contact
QSL = Confirm/confirmation card QSX = Listen on freq
QTH = Location                  QTR = Time

NAMES/TITLES:
OM  = Old Man (term of respect) YL  = Young Lady
XYL = Wife                      OP  = Operator
STN = Station                   SRI = Sorry

NUMBERS:
FONE = Phone (voice mode)       CW  = Morse code
73  = Best regards              88  = Love and kisses
99  = Go away!

SOTA SPECIFIC:
SOTA = Summits On The Air       CHASER = Non-activator
ACTIVATOR = On summit           S2S = Summit to Summit

POTA SPECIFIC:
POTA = Parks On The Air         P2P = Park to Park
HUNTER = Non-activator          ACTIVATOR = At park

CONTEST SPECIFIC:
TEST = Contest                  SN  = Serial Number
NR  = Number                    MULT = Multiplier
DX  = Distance/foreign station  NA  = North America

MISCELLANEOUS:
ES  = And                       FER = For
WID = With                      ABT = About
BURO = QSL bureau              DX  = Distance
HPE = Hope                      INFO = Information
MSG = Message                   NAME = Name
NW  = Now                       PKT = Packet
RPT = Report/repeat            SIG = Signal
TMW = Tomorrow                  TKS = Thanks
UR  = Your/You're              BCNU = Be seeing you
CUAGN = See you again          CUL = See you later
"""
        self.abbreviations_tab.setText(abbreviations)
        
    
    # ===== NEW: flrig process verification =====
    
    def is_flrig_already_running(self):
        """Check if flrig is already running"""
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] == 'flrig':
                    return True, proc
                # Also check cmdline for cases where name might be different
                if proc.info['cmdline'] and 'flrig' in ' '.join(proc.info['cmdline']):
                    return True, proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False, None
    
    def on_style_changed(self, style):
        """Handle CW style change"""
        if not hasattr(self, 'current_cw_style'):
            return
            
        self.current_cw_style = style
        print(f"[CW STYLE] Changed to: {style.upper()}")
        
        # Update display based on style
        style_messages = {
            'normal': '📻 Normal CW mode - Standard exchanges',
            'sota': '⛰️ SOTA mode - Summit exchanges (RST + Summit ref)',
            'pota': '🏞️ POTA mode - Park exchanges (RST + Park ref)',
            'contest': '🏆 Contest mode - RST + Serial number'
        }
        
        # Reload welcome screen with new style and current callsign
        current_call = self.current_call_label.text()
        self.load_welcome_screen(current_call)
    
    def on_direction_changed(self, direction):
        """Handle CW direction change (who's calling)"""
        if not hasattr(self, 'cw_direction'):
            return
            
        self.cw_direction = direction
        print(f"[CW DIRECTION] Changed to: {direction.upper()}")
        
        # Reload welcome screen with new direction and current callsign
        current_call = self.current_call_label.text()
        self.load_welcome_screen(current_call)
    
    def load_cw_format_for_callsign(self, callsign):
        """Load CW format for callsign based on selected style"""
        self.last_callsign = callsign
        
        # Use the new unified load_welcome_screen with callsign
        self.load_welcome_screen(callsign)
    
    def load_cw_format_normal(self, callsign):
        """Load normal CW format"""
        prefix = self.extract_prefix(callsign)
        country, qth = self.lookup_country(prefix)
        
        format_guide = f"""
╔════════════════════════════════════════════════════════════════════╗
║          📻 NORMAL CW - {callsign:^10} ({country})                      ║
╚════════════════════════════════════════════════════════════════════╝

1. CALL:
{callsign} {callsign} DE {self.own_callsign} K

2. EXCHANGE:
{callsign} DE {self.own_callsign}
GM OM = UR 599 = NAME BENNI = QTH BRAUNSCHWEIG = HW?

3. CLOSE:
TNX OM = 73 GL = {callsign} DE {self.own_callsign} SK
"""
        self.cw_format_tab.setText(format_guide)
    
    def load_cw_format_sota(self, callsign):
        """Load SOTA CW format"""
        prefix = self.extract_prefix(callsign)
        country, qth = self.lookup_country(prefix)
        
        format_guide = f"""
╔════════════════════════════════════════════════════════════════════╗
║          ⛰️  SOTA - {callsign:^10} ({country})                         ║
╚════════════════════════════════════════════════════════════════════╝

ACTIVATING:
───────────────────────────────────────────
{callsign} {callsign} DE {self.own_callsign}/P K
{callsign} 599 DM/NS-123
73

CHASING:
───────────────────────────────────────────
{callsign} DE {self.own_callsign} K
{self.own_callsign} 599 W1/HA-001
R 599 73
"""
        self.cw_format_tab.setText(format_guide)
    
    def load_cw_format_pota(self, callsign):
        """Load POTA CW format"""
        prefix = self.extract_prefix(callsign)
        country, qth = self.lookup_country(prefix)
        
        format_guide = f"""
╔════════════════════════════════════════════════════════════════════╗
║          🏞️  POTA - {callsign:^10} ({country})                         ║
╚════════════════════════════════════════════════════════════════════╝

ACTIVATING:
───────────────────────────────────────────
{callsign} {callsign} DE {self.own_callsign}/P K
{callsign} 599 DL-0123
73

HUNTING:
───────────────────────────────────────────
{callsign} DE {self.own_callsign} K
{self.own_callsign} 599 K-0001
R 599 73
"""
        self.cw_format_tab.setText(format_guide)
    
    def load_cw_format_contest(self, callsign):
        """Load contest CW format"""
        prefix = self.extract_prefix(callsign)
        country, qth = self.lookup_country(prefix)
        
        format_guide = f"""
╔════════════════════════════════════════════════════════════════════╗
║          🏆 CONTEST - {callsign:^10} ({country})                       ║
╚════════════════════════════════════════════════════════════════════╝

CQ TEST {self.own_callsign} TEST

{callsign}

{callsign} TU 599 001

R 599 184

TU
"""
        self.cw_format_tab.setText(format_guide)
    
    
    def extract_prefix(self, callsign):
        """Extract prefix"""
        prefix = ''
        for char in callsign:
            if char.isdigit():
                break
            prefix += char
        if len(prefix) <= 2 and len(callsign) > len(prefix):
            prefix += callsign[len(prefix)]
        return prefix
    
    def lookup_country(self, prefix):
        """Lookup country"""
        lookup = {
            'VK': ('AUSTRALIA', 'Sydney/Melbourne'),
            'JA': ('JAPAN', 'Tokyo'),
            'W': ('USA', 'Various'),
            'K': ('USA', 'Various'),
            'DL': ('GERMANY', 'Various'),
            'F': ('FRANCE', 'Paris'),
            'G': ('ENGLAND', 'Various'),
            'EA': ('SPAIN', 'Madrid'),
            'I': ('ITALY', 'Rome'),
            'PA': ('NETHERLANDS', 'Amsterdam'),
            'OH': ('FINLAND', 'Helsinki'),
            'SM': ('SWEDEN', 'Stockholm'),
            'UA': ('RUSSIA', 'Moscow'),
            'ZL': ('NEW ZEALAND', 'Auckland'),
            'ZS': ('SOUTH AFRICA', 'Cape Town'),
            'PY': ('BRAZIL', 'Sao Paulo'),
        }
        
        for key in sorted(lookup.keys(), key=len, reverse=True):
            if prefix.startswith(key):
                return lookup[key]
        return ('DX STATION', 'Unknown')
    
    def get_best_time(self, prefix):
        """Get time hint"""
        if prefix.startswith(('VK', 'JA', 'ZL')):
            return 'afternoon/evening'
        elif prefix.startswith(('W', 'K')):
            return 'morning/afternoon'
        return 'daytime'
    
    def closeEvent(self, event):
        """Handle close"""
        self.disconnect_cluster()
        
        # Build list of running processes to ask about
        processes_to_stop = []
        if self.flrig_process or self.is_flrig_already_running()[0]:
            processes_to_stop.append('flrig')
        if self.qlog_process or self.is_qlog_already_running()[0]:
            processes_to_stop.append('qlog')
        if self.hamclock_process or self.is_hamclock_already_running()[0]:
            processes_to_stop.append('hamclock')
        
        if processes_to_stop:
            msg = f'Stop {" and ".join(processes_to_stop)} before quitting?'
            reply = QMessageBox.question(
                self, 'Quit', 
                msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if 'flrig' in processes_to_stop:
                    self.stop_flrig()
                if 'qlog' in processes_to_stop:
                    self.stop_qlog()
                if 'hamclock' in processes_to_stop:
                    self.stop_hamclock()
        
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = CWCompanion()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
