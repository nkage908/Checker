import asyncio
import aiohttp
import time
import logging
from datetime import datetime
from typing import List, Dict, Tuple
from urllib.parse import urljoin, urlparse
from models import IPTVChannel
from progress import ProcessProgressTracker

class StreamChecker:
    def __init__(self, config: Dict):
        self.config = config
        self.timeout = config.get("timeout", 10)
        self.max_concurrent = config.get("max_concurrent", 50)
        self.check_duration = config.get("check_duration", 3)
        self.user_agent = config.get("user_agent")
        self.session = None
        self.progress_tracker = None

    async def __aenter__(self):
        tcp_config = self.config.get("tcp_connector", {})
        timeout_config = self.config.get("client_timeout", {})
        connector = aiohttp.TCPConnector(
            limit=tcp_config.get("limit", 50),
            limit_per_host=tcp_config.get("limit_per_host", 20),
            ttl_dns_cache=tcp_config.get("ttl_dns_cache", 300),
            use_dns_cache=tcp_config.get("use_dns_cache", True),
        )
        timeout = aiohttp.ClientTimeout(
            total=timeout_config.get("total", self.timeout),
            connect=timeout_config.get("connect", 5),
            sock_read=timeout_config.get("sock_read", self.timeout)
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': self.user_agent} if self.user_agent else None
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_stream(self, channel: IPTVChannel) -> bool:
        start_time = time.time()
        try:
            if self._is_hls_stream(channel.url):
                result = await self._check_hls_stream(channel)
            elif self._is_http_stream(channel.url):
                result = await self._check_http_stream(channel)
            else:
                result = await self._check_generic_stream(channel)
            channel.response_time = time.time() - start_time
            channel.is_working = result
            channel.check_time = datetime.now()
            if self.progress_tracker:
                self.progress_tracker.update(result)
            if result:
                logging.info(f"✓ {channel.name} - OK ({channel.response_time:.2f}s)")
            else:
                logging.warning(f"✗ {channel.name} - FAILED: {channel.error_message}")
            return result
        except Exception as e:
            channel.response_time = time.time() - start_time
            channel.error_message = str(e)
            channel.is_working = False
            channel.check_time = datetime.now()
            if self.progress_tracker:
                self.progress_tracker.update(False)
            logging.warning(f"✗ {channel.name} - ERROR: {e}")
            return False

    def _is_hls_stream(self, url: str) -> bool:
        return url.endswith('.m3u8') or 'm3u8' in url.lower()

    def _is_http_stream(self, url: str) -> bool:
        return url.startswith(('http://', 'https://'))

    async def _check_hls_stream(self, channel: IPTVChannel) -> bool:
        try:
            async with self.session.get(channel.url) as response:
                if response.status != 200:
                    channel.error_message = f"HTTP {response.status}"
                    return False
                content = await response.text()
                if not content.strip().startswith('#EXTM3U'):
                    channel.error_message = "Invalid HLS playlist"
                    return False
                if '#EXT-X-STREAM-INF:' in content:
                    return await self._check_hls_variant(channel, content)
                if '#EXTINF:' in content:
                    return await self._check_hls_segments(channel, content)
                return True
        except asyncio.TimeoutError:
            channel.error_message = "Timeout"
            return False
        except Exception as e:
            channel.error_message = str(e)
            return False

    async def _check_hls_variant(self, channel: IPTVChannel, playlist_content: str) -> bool:
        lines = playlist_content.split('\n')
        for i, line in enumerate(lines):
            if line.startswith('#EXT-X-STREAM-INF:'):
                if i + 1 < len(lines):
                    variant_url = lines[i + 1].strip()
                    if variant_url:
                        if not variant_url.startswith('http'):
                            variant_url = urljoin(channel.url, variant_url)
                        temp_channel = IPTVChannel(channel.extinf_line, variant_url)
                        temp_channel.name = channel.name
                        return await self._check_hls_stream(temp_channel)
        channel.error_message = "No valid variant found"
        return False

    async def _check_hls_segments(self, channel: IPTVChannel, playlist_content: str) -> bool:
        lines = playlist_content.split('\n')
        segments = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if not line.startswith('http'):
                    line = urljoin(channel.url, line)
                segments.append(line)
                if len(segments) >= 2:
                    break
        if not segments:
            channel.error_message = "No segments found"
            return False
        try:
            async with self.session.head(segments[0]) as response:
                return response.status == 200
        except Exception:
            try:
                async with self.session.get(segments[0]) as response:
                    if response.status == 200:
                        await response.content.read(1024)
                        return True
            except Exception:
                pass
        channel.error_message = "Segment check failed"
        return False

    async def _check_http_stream(self, channel: IPTVChannel) -> bool:
        try:
            async with self.session.head(channel.url) as response:
                if response.status == 200:
                    return True
                elif response.status == 405:
                    return await self._check_with_partial_get(channel)
                else:
                    channel.error_message = f"HTTP {response.status}"
                    return False
        except asyncio.TimeoutError:
            channel.error_message = "Timeout"
            return False
        except Exception:
            return await self._check_with_partial_get(channel)

    async def _check_with_partial_get(self, channel: IPTVChannel) -> bool:
        try:
            async with self.session.get(channel.url) as response:
                if response.status != 200:
                    channel.error_message = f"HTTP {response.status}"
                    return False
                data = await response.content.read(1024)
                return len(data) > 0
        except asyncio.TimeoutError:
            channel.error_message = "Timeout"
            return False
        except Exception as e:
            channel.error_message = str(e)
            return False

    async def _check_generic_stream(self, channel: IPTVChannel) -> bool:
        return await self._check_http_stream(channel)

    async def check_all_streams(self, channels: List[IPTVChannel]) -> Tuple[List[IPTVChannel], List[IPTVChannel]]:
        start_time = time.time()
        logging.info(f"Starting check of {len(channels)} channels...")
        semaphore = asyncio.Semaphore(self.max_concurrent)
        async def check_with_semaphore(channel):
            async with semaphore:
                return await self.check_stream(channel)
        tasks = [check_with_semaphore(channel) for channel in channels]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if hasattr(self.progress_tracker, 'close'):
                self.progress_tracker.close()
        working_channels = [ch for ch in channels if ch.is_working]
        broken_channels = [ch for ch in channels if not ch.is_working]
        elapsed_time = self.progress_tracker.get_elapsed_time() if hasattr(self.progress_tracker, 'get_elapsed_time') else time.time() - start_time
        logging.info(f"Check completed in {elapsed_time:.2f}s! Working: {len(working_channels)}, Broken: {len(broken_channels)}")
        return working_channels, broken_channels