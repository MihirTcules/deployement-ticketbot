"""
Configuration management module for Recreation.gov Booking Bot
Handles secure storage and retrieval of user configuration settings
"""

import json
import os
import base64
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

# Get data directory from environment variable or use current directory
DATA_DIR = os.getenv("DATA_DIR", ".")

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"📁 Created data directory: {DATA_DIR}")
    except Exception as e:
        logger.warning(f"⚠️ Could not create data directory {DATA_DIR}: {e}")
        logger.warning("⚠️ Using current directory for data storage")
        DATA_DIR = "."

CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")
KEY_FILE = os.path.join(DATA_DIR, ".config_key")

# Warn if using /tmp (data will be lost on restart)
if DATA_DIR == "/tmp":
    logger.warning("⚠️ Using /tmp for data storage - data will be lost on restart!")
    logger.warning("⚠️ For persistent storage, upgrade to a paid Render plan with disk storage")

class ConfigManager:
    """Manages bot configuration with secure password storage"""
    
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.key_file = KEY_FILE
        self.cipher = None
        self._initialize_encryption()
        
    def _initialize_encryption(self):
        """Initialize encryption key for password storage"""
        # First, try to get key from environment variable (production)
        env_key = os.getenv("ENCRYPTION_KEY")
        if env_key:
            try:
                key = env_key.encode()
                self.cipher = Fernet(key)
                logger.info("🔐 Using encryption key from environment variable")
                return
            except Exception as e:
                logger.warning(f"⚠️  Invalid ENCRYPTION_KEY in environment: {e}")

        # Fall back to file-based key (development)
        if os.path.exists(self.key_file):
            # Load existing key
            with open(self.key_file, 'rb') as f:
                key = f.read()
            logger.info("🔐 Using encryption key from file")
        else:
            # Generate new key
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            logger.info("🔐 Generated new encryption key and saved to file")

        self.cipher = Fernet(key)
    
    def _encrypt_password(self, password: str) -> str:
        """Encrypt password for secure storage"""
        if not password:
            return ""
        encrypted = self.cipher.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()
    
    def _decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt password from storage"""
        if not encrypted_password:
            return ""
        try:
            encrypted_bytes = base64.b64decode(encrypted_password.encode())
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"❌ Failed to decrypt password: {e}")
            return ""
    
    def load_config(self) -> dict:
        """Load configuration from file"""
        if not os.path.exists(self.config_file):
            logger.info("ℹ️ No configuration file found, using defaults")
            return self._get_default_config()
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Decrypt password if present
            if config.get('password_encrypted'):
                config['password'] = self._decrypt_password(config['password_encrypted'])
                del config['password_encrypted']
            
            logger.info("✅ Configuration loaded successfully")
            return config
        except Exception as e:
            logger.error(f"❌ Failed to load configuration: {e}")
            return self._get_default_config()
    
    def save_config(self, config: dict) -> bool:
        """Save configuration to file"""
        try:
            # Create a copy to avoid modifying original
            config_to_save = config.copy()
            
            # Encrypt password before saving
            if config_to_save.get('password'):
                config_to_save['password_encrypted'] = self._encrypt_password(config_to_save['password'])
                del config_to_save['password']
            
            with open(self.config_file, 'w') as f:
                json.dump(config_to_save, f, indent=2)
            
            logger.info("✅ Configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save configuration: {e}")
            return False
    
    def get_config_for_api(self) -> dict:
        """Get configuration for API response (password masked)"""
        config = self.load_config()
        
        # Mask password for security
        if config.get('password'):
            config['password'] = '********'
        
        return config
    
    def _get_default_config(self) -> dict:
        """Get default configuration"""
        return {
            'email': '',
            'password': '',
            'default_url': '',
            'slot_monitoring_time': 30,  # minutes
            'monitoring_interval': 50,   # milliseconds
        }
    
    def update_config(self, updates: dict) -> bool:
        """Update configuration with new values"""
        config = self.load_config()
        
        # Update only provided fields
        for key in ['email', 'password', 'default_url', 'slot_monitoring_time', 'monitoring_interval']:
            if key in updates:
                config[key] = updates[key]
        
        return self.save_config(config)
    
    def clear_config(self) -> bool:
        """Clear all configuration"""
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            logger.info("🗑️ Configuration cleared")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear configuration: {e}")
            return False

# Global instance
config_manager = ConfigManager()

