import json
from pathlib import Path
from typing import Dict

ENHANCED_DEFAULT_CONFIG = {
    "timeout": 10,
    "max_concurrent": 5,
    "check_duration": 3,
    "user_agent": "Mozilla/5.0 (Wink/1.28.3 (AndroidTV/9)HlsWinkPlayer;Linux; Android 4.4.3",
    "output_prefix": "checked",
    "log_level": "INFO",
    "log_to_file": "True",
    "log_file": "LOG/checker.log",
    "show_progress_bar": "True",
    "show_errors_in_summary": "True",
    "max_errors_to_show": 10,
    "encodings_to_try": ["utf-8", "cp1251", "latin-1", "iso-8859-1"],
    "resume": {
        "enabled": "True",
        "check_channel_count": "True",
        "auto_cleanup_incomplete": "False"
    },
    "tcp_connector": {
        "limit": 50,
        "limit_per_host": 20,
        "ttl_dns_cache": 300,
        "use_dns_cache": "True"
    },
    "client_timeout": {
        "total": 10,
        "connect": 5,
        "sock_read": 10
    },
    "batch_processing": {
        "default_processes": 2,
        "max_processes": 8,
        "separate_logs": "True",
        "log_per_file": "False"
    },
    "directories": {
        "default_input": "./IN",
        "default_working_output": "./ON",
        "default_broken_output": "./OFF"
    }
}

def load_config(config_path: str = "config.json") -> Dict:
    config_file = Path(config_path)
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            config = ENHANCED_DEFAULT_CONFIG.copy()
            config.update(user_config)
            return config
        except Exception as e:
            print(f"WARNING: Error loading config file {config_path}: {e}")
            print("Using default configuration")
    else:
        print(f"Config file {config_path} not found, using defaults")
    return ENHANCED_DEFAULT_CONFIG.copy()
