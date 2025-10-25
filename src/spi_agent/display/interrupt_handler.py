"""Interrupt handling for graceful operation cancellation."""

import asyncio
import logging
import signal
from typing import Optional, Set

logger = logging.getLogger(__name__)


class InterruptHandler:
    """Handler for graceful operation interruption.

    Supports ESC key and Ctrl+C interruption with:
    - Graceful asyncio task cancellation
    - MCP connection cleanup
    - Session preservation (no process exit)
    """

    def __init__(self) -> None:
        """Initialize interrupt handler."""
        self._tasks: Set[asyncio.Task] = set()
        self._interrupted = False
        self._original_sigint_handler: Optional[signal.Handlers] = None

    def register_cancellable_task(self, task: asyncio.Task) -> None:
        """Register a task that can be cancelled on interrupt.

        Args:
            task: Asyncio task to register
        """
        self._tasks.add(task)

        # Add callback to remove from set when done
        task.add_done_callback(self._tasks.discard)

    def unregister_task(self, task: asyncio.Task) -> None:
        """Unregister a cancellable task.

        Args:
            task: Task to unregister
        """
        self._tasks.discard(task)

    async def cancel_all_tasks(self) -> None:
        """Cancel all registered tasks gracefully."""
        if not self._tasks:
            return

        logger.info("Cancelling %d active task(s)...", len(self._tasks))

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("All tasks cancelled")

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for Ctrl+C.

        Note: ESC key handling is done via prompt_toolkit in the CLI.
        """
        # Save original handler
        self._original_sigint_handler = signal.signal(signal.SIGINT, self._handle_sigint)

    def restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
            self._original_sigint_handler = None

    def _handle_sigint(self, signum: int, frame) -> None:
        """Handle SIGINT (Ctrl+C) signal.

        Args:
            signum: Signal number
            frame: Current stack frame
        """
        # Set interrupted flag
        self._interrupted = True

        # Trigger cancellation of all tasks
        # Note: We can't call async function here, so we schedule it
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self.cancel_all_tasks())

    @property
    def is_interrupted(self) -> bool:
        """Check if interrupt was triggered."""
        return self._interrupted

    def reset(self) -> None:
        """Reset interrupt state."""
        self._interrupted = False
