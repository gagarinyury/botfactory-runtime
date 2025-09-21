"""Background worker for processing broadcast campaigns"""
import asyncio
import signal
import sys
from typing import Optional
import structlog
from .redis_client import redis_client
from .broadcast_engine import broadcast_engine
from .main import async_session

logger = structlog.get_logger()


class BroadcastWorker:
    """Background worker to process broadcast campaigns from Redis queue"""

    def __init__(self):
        self.running = True
        self.poll_interval = 1.0  # seconds
        self.max_retries = 3

    async def start(self):
        """Start the worker"""
        logger.info("broadcast_worker_starting")

        # Connect to Redis
        await redis_client.connect()

        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)

        try:
            await self._run_worker_loop()
        except Exception as e:
            logger.error("broadcast_worker_error", error=str(e))
        finally:
            await redis_client.disconnect()
            logger.info("broadcast_worker_stopped")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("broadcast_worker_shutdown_signal", signal=signum)
        self.running = False

    async def _run_worker_loop(self):
        """Main worker loop"""
        logger.info("broadcast_worker_running")

        while self.running:
            try:
                # Poll for tasks
                broadcast_id = await self._get_next_task()

                if broadcast_id:
                    await self._process_broadcast(broadcast_id)
                else:
                    # No tasks available, wait before polling again
                    await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error("broadcast_worker_loop_error", error=str(e))
                await asyncio.sleep(self.poll_interval)

    async def _get_next_task(self) -> Optional[str]:
        """Get next broadcast task from Redis queue"""
        try:
            # Right pop from broadcast queue (FIFO)
            result = await redis_client.redis.brpop("broadcast_queue", timeout=1)

            if result:
                queue_name, broadcast_id = result
                broadcast_id = broadcast_id.decode() if isinstance(broadcast_id, bytes) else broadcast_id
                logger.info("broadcast_task_dequeued", broadcast_id=broadcast_id)
                return broadcast_id

            return None

        except Exception as e:
            logger.error("broadcast_queue_poll_error", error=str(e))
            return None

    async def _process_broadcast(self, broadcast_id: str):
        """Process a single broadcast campaign"""
        logger.info("broadcast_processing_start", broadcast_id=broadcast_id)

        try:
            async with async_session() as session:
                await broadcast_engine.execute_broadcast(session, broadcast_id)

            logger.info("broadcast_processing_complete", broadcast_id=broadcast_id)

        except Exception as e:
            logger.error("broadcast_processing_error",
                        broadcast_id=broadcast_id,
                        error=str(e))

            # Could implement retry logic here
            await self._handle_broadcast_failure(broadcast_id, str(e))

    async def _handle_broadcast_failure(self, broadcast_id: str, error_message: str):
        """Handle broadcast processing failure"""
        # In a production system, you might:
        # 1. Retry the task a limited number of times
        # 2. Send to a dead letter queue
        # 3. Alert monitoring systems

        try:
            async with async_session() as session:
                await broadcast_engine._fail_broadcast(session, broadcast_id, error_message)

            logger.error("broadcast_marked_failed",
                        broadcast_id=broadcast_id,
                        error=error_message)

        except Exception as e:
            logger.error("broadcast_failure_handling_error",
                        broadcast_id=broadcast_id,
                        error=str(e))


async def run_worker():
    """Entry point for running the broadcast worker"""
    worker = BroadcastWorker()
    await worker.start()


if __name__ == "__main__":
    """Run worker when called directly"""
    asyncio.run(run_worker())