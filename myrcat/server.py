"""Socket server implementation for Myrcat."""

import asyncio
import json
import logging
from typing import Callable, Awaitable, Dict, Any, Tuple, Optional

from myrcat.exceptions import ConnectionError, MyrcatException
from myrcat.utils import decode_json_data
from myrcat.utils.network import NetworkConfig, retry_async


class MyriadServer:
    """Socket server that receives Myriad track data.
    
    TODO: Potential improvements:
    - Add authentication for incoming connections
    - Support TLS/SSL for encrypted connections
    - Implement protocol versioning for compatibility
    - Add metrics for connection handling (success rate, processing time)
    - Support multiple simultaneous connections with proper concurrency handling
    """

    def __init__(
        self, 
        host: str, 
        port: int, 
        validator: Callable[[Dict[str, Any]], Tuple[bool, str]],
        processor: Callable[[Dict[str, Any]], Awaitable[None]],
        network_config: Optional[NetworkConfig] = None
    ):
        """Initialize the server.
        
        Args:
            host: Host address to bind to
            port: Port to listen on
            validator: Function to validate incoming JSON data
            processor: Async function to process validated track data
            network_config: Optional network configuration
        """
        self.host = host
        self.port = port
        self.validator = validator
        self.processor = processor
        self.network_config = network_config
        self.server = None

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming connections and process datastream.
        
        Args:
            reader: Stream reader for incoming data
            writer: Stream writer for outgoing data
        """
        peer = writer.get_extra_info("peername")
        logging.debug(f"🔌 Connection from {peer}")

        try:
            # Get socket timeout from network config or use default
            socket_timeout = (
                self.network_config.get_socket_timeout() 
                if self.network_config 
                else 5.0
            )
            
            # Set a timeout for reading data
            try:
                data = await asyncio.wait_for(reader.read(), timeout=socket_timeout)
                if not data:
                    logging.debug(f"📪 Empty data from {peer}")
                    return
            except asyncio.TimeoutError:
                logging.warning(f"⏱️ Read timeout from {peer} after {socket_timeout}s")
                return
            
            try:
                track_data = decode_json_data(data)

                # Validate JSON from Myriad containing track data
                is_valid, message = self.validator(track_data)
                if not is_valid:
                    logging.info(f"⛔️ Received data error: {message}")
                    return

                await self.processor(track_data)
            except json.JSONDecodeError as e:
                logging.error(f"💥 Metadata failure from {peer}: {e}\nRaw data: {data}")
            except ConnectionResetError as e:
                logging.error(f"🔌 Connection reset from {peer}: {e}")
            except ConnectionError as e:
                logging.error(f"🔌 Connection error from {peer}: {e}")
        except Exception as e:
            logging.error(f"💥 Error processing data from {peer}: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except ConnectionError:
                logging.debug(f"🔌 Connection already closed for {peer}")

    async def start(self):
        """Start the socket server with connection retry."""
        # Get retry settings from network config or use defaults
        retry_delay = self.network_config.retry_delay if self.network_config else 3
        max_retries = self.network_config.max_retries if self.network_config else 3
        
        retry_count = 0
        while True:
            try:
                self.server = await asyncio.start_server(
                    self.handle_connection,
                    host=self.host,
                    port=self.port,
                )

                addr = self.server.sockets[0].getsockname()
                logging.info(f"🟢 Listening for Myriad on {addr}")
                
                # Reset retry count on successful connection
                retry_count = 0

                async with self.server:
                    await self.server.serve_forever()
            except ConnectionError as e:
                retry_count += 1
                logging.error(f"🔌 Server connection error: {e} (attempt {retry_count}/{max_retries})")
                
                # Calculate wait time with exponential backoff
                wait_time = retry_delay * (2 ** min(retry_count - 1, 5))  # Cap backoff growth
                logging.debug(f"⏱️ Retrying in {wait_time}s")
                
                await asyncio.sleep(wait_time)
            except Exception as e:
                retry_count += 1
                logging.error(f"💥 Server error: {e} (attempt {retry_count}/{max_retries})")
                
                # Calculate wait time with exponential backoff
                wait_time = retry_delay * (2 ** min(retry_count - 1, 5))  # Cap backoff growth
                logging.debug(f"⏱️ Retrying in {wait_time}s")
                
                await asyncio.sleep(wait_time)
    
    async def stop(self):
        """Stop the server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logging.info("🔴 Server stopped")
            self.server = None