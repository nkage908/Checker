from typing import List, Dict
import logging
from pathlib import Path
from models import IPTVChannel
class M3UParser:
    @staticmethod
    def parse(file_path: str, config: Dict) -> List[IPTVChannel]:
        channels = []
        encodings = config.get("encodings_to_try", ["utf-8", "cp1251", "latin-1"])
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File {file_path} not found")
        content = None
        used_encoding = None
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.readlines()
                used_encoding = encoding
                logging.info(f"Successfully decoded file using {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logging.error(f"Error reading file with {encoding}: {e}")
                continue
        if content is None or not content:
            raise Exception(f"File {file_path} is empty or could not be decoded")
        extinf_line = None
        line_number = 0
        for line in content:
            line_number += 1
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF:'):
                extinf_line = line
            elif line and not line.startswith('#') and extinf_line:
                if M3UParser._is_valid_url(line):
                    channels.append(IPTVChannel(extinf_line, line))
                else:
                    logging.warning(f"Invalid URL on line {line_number}: {line}")
                extinf_line = None
            elif line and not line.startswith('#') and not extinf_line:
                logging.warning(f"URL without EXTINF on line {line_number}: {line}")
        logging.info(f"Found {len(channels)} valid channels")
        return channels
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        if not url or len(url.strip()) == 0:
            return False
        valid_protocols = ['http://', 'https://', 'rtmp://', 'rtmps://', 'udp://', 'rtp://']
        return any(url.lower().startswith(protocol) for protocol in valid_protocols)
    @staticmethod
    def save_playlist(channels: List[IPTVChannel], file_path: str, header: str = "#EXTM3U"):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(header + '\n')
                for channel in channels:
                    f.write(channel.extinf_line + '\n')
                    f.write(channel.url + '\n')
            logging.info(f"Playlist saved to {file_path} with {len(channels)} channels")
        except Exception as e:
            logging.error(f"Error saving playlist to {file_path}: {e}")
            raise