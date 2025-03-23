"""Socket server implementation for Myrcat."""

import asyncio
import json
import logging
from typing import Callable, Awaitable, Dict, Any, Tuple

from myrcat.exceptions import ConnectionError, MyrcatException
from myrcat.utils import decode_json_data


class MyriadServer:
    """Socket server that receives Myriad track data."""

    def __init__(
        self, 
        host: str, 
        port: int, 
        validator: Callable[[Dict[str, Any]], Tuple[bool, str]],
        processor: Callable[[Dict[str, Any]], Awaitable[None]]
    ):
        """Initialize the server.
        
        Args:
            host: Host address to bind to
            port: Port to listen on
            validator: Function to validate incoming JSON data
            processor: Async function to process validated track data
        """
        self.host = host
        self.port = port
        self.validator = validator
        self.processor = processor
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
            data = await reader.read()
            if not data:
                logging.debug(f"📪 Empty data from {peer}")
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
        while True:
            try:
                self.server = await asyncio.start_server(
                    self.handle_connection,
                    host=self.host,
                    port=self.port,
                )

                addr = self.server.sockets[0].getsockname()
                logging.info(f"🟢 Listening for Myriad on {addr}")

                async with self.server:
                    await self.server.serve_forever()
            except ConnectionError as e:
                logging.error(f"🔌 Server connection error: {e}")
                await asyncio.sleep(3)  # Wait before retry
            except Exception as e:
                logging.error(f"💥 Server error: {e}")
                await asyncio.sleep(3)  # Wait before retry
    
    async def stop(self):
        """Stop the server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logging.info("🔴 Server stopped")
            self.server = None