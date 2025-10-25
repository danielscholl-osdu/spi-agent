"""Hierarchical execution tree display using Rich Live."""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.text import Text
from rich.tree import Tree

from spi_agent.display.events import (
    EventEmitter,
    ExecutionEvent,
    LLMRequestEvent,
    LLMResponseEvent,
    SubprocessOutputEvent,
    ToolCompleteEvent,
    ToolErrorEvent,
    ToolStartEvent,
    WorkflowStepEvent,
    get_event_emitter,
)


class TreeNode:
    """Node in the execution tree.

    Attributes:
        event_id: Unique identifier matching the event
        event_type: Type of event
        label: Display label
        status: Current status (in_progress, completed, error)
        children: Child nodes
        metadata: Additional metadata
        start_time: When the node was created
        end_time: When the node completed
    """

    def __init__(
        self,
        event_id: str,
        event_type: str,
        label: str,
        status: str = "in_progress",
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.label = label
        self.status = status
        self.children: List[TreeNode] = []
        self.metadata: Dict = {}
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.error_details: Optional[str] = None

    def add_child(self, child: "TreeNode") -> None:
        """Add a child node."""
        self.children.append(child)

    def complete(self, summary: Optional[str] = None, duration: Optional[float] = None) -> None:
        """Mark node as completed."""
        self.status = "completed"
        self.end_time = datetime.now()
        if summary:
            self.metadata["summary"] = summary
        if duration is not None:
            self.metadata["duration"] = duration

    def mark_error(self, error_message: str, duration: Optional[float] = None) -> None:
        """Mark node as error."""
        self.status = "error"
        self.end_time = datetime.now()
        self.error_details = error_message
        if duration is not None:
            self.metadata["duration"] = duration


class ExecutionTreeDisplay:
    """Hierarchical execution tree display using Rich Live.

    This class manages a tree of execution events and renders them
    in real-time using Rich's Live display with visual hierarchy.
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialize execution tree display.

        Args:
            console: Rich console to use (creates new one if not provided)
        """
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._root_nodes: List[TreeNode] = []
        self._node_map: Dict[str, TreeNode] = {}
        self._event_emitter: EventEmitter = get_event_emitter()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._is_rich_supported = self.console.is_terminal

    def _create_node(self, event: ExecutionEvent, label: str) -> TreeNode:
        """Create a new tree node from an event.

        Args:
            event: Event to create node for
            label: Display label

        Returns:
            New tree node
        """
        node = TreeNode(event.event_id, type(event).__name__, label)
        self._node_map[event.event_id] = node

        # Add to parent if specified, otherwise add to root
        if event.parent_id and event.parent_id in self._node_map:
            parent = self._node_map[event.parent_id]
            parent.add_child(node)
        else:
            self._root_nodes.append(node)

        return node

    def _render_tree(self) -> RenderableType:
        """Render the execution tree.

        Returns:
            Rich renderable tree
        """
        if not self._is_rich_supported:
            # Fallback to simple text rendering
            lines = []
            for node in self._root_nodes:
                lines.extend(self._render_node_simple(node, indent=0))
            return Text("\n".join(lines))

        # Create Rich tree for hierarchical display
        if not self._root_nodes:
            return Text("🤖 Thinking...", style="dim")

        # Render all root nodes
        renderables = []
        for root_node in self._root_nodes:
            renderables.append(self._render_node_rich(root_node))

        return Group(*renderables) if renderables else Text("🤖 Thinking...", style="dim")

    def _render_node_simple(self, node: TreeNode, indent: int) -> List[str]:
        """Render node in simple text format (non-Rich terminals).

        Args:
            node: Node to render
            indent: Indentation level

        Returns:
            List of lines to render
        """
        lines = []
        prefix = "  " * indent

        # Status symbol
        if node.status == "in_progress":
            symbol = "⏺"
        elif node.status == "completed":
            symbol = "✓"
        else:  # error
            symbol = "✗"

        # Build line
        line = f"{prefix}{symbol} {node.label}"
        if node.status == "completed" and "summary" in node.metadata:
            line += f" - {node.metadata['summary']}"
        if "duration" in node.metadata:
            line += f" ({node.metadata['duration']:.2f}s)"

        lines.append(line)

        # Render children
        for child in node.children:
            lines.extend(self._render_node_simple(child, indent + 1))

        return lines

    def _render_node_rich(self, node: TreeNode) -> RenderableType:
        """Render node in Rich format with styling.

        Args:
            node: Node to render

        Returns:
            Rich renderable
        """
        # Status symbol and style
        if node.status == "in_progress":
            symbol = "⏺"
            style = "bold blue"
        elif node.status == "completed":
            symbol = "⎿"
            style = "dim"
        else:  # error
            symbol = "✗"
            style = "bold red"

        # Build label text
        label_parts = [symbol, " ", node.label]

        if node.status == "completed" and "summary" in node.metadata:
            label_parts.append(f" - {node.metadata['summary']}")

        if "duration" in node.metadata:
            label_parts.append(f" ({node.metadata['duration']:.2f}s)")

        label_text = Text.from_markup("".join(label_parts), style=style)

        # If node has children, render as tree
        if node.children:
            tree = Tree(label_text)
            for child in node.children:
                child_renderable = self._render_node_rich(child)
                tree.add(child_renderable)
            return tree
        else:
            return label_text

    async def _process_events(self) -> None:
        """Background task to process events from the queue."""
        while self._running:
            try:
                # Get events with timeout to allow checking _running flag
                try:
                    event = await asyncio.wait_for(
                        self._event_emitter.get_event(), timeout=0.1
                    )
                except asyncio.TimeoutError:
                    continue

                await self._handle_event(event)

                # Force immediate update after processing event
                if self._live:
                    self._live.update(self._render_tree())

            except asyncio.CancelledError:
                break
            except Exception:
                # Ignore errors in event processing to avoid crashing display
                pass

    async def _handle_event(self, event: ExecutionEvent) -> None:
        """Handle a single event.

        Args:
            event: Event to handle
        """
        # Debug: log event processing
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Processing event: {type(event).__name__} - {event.event_id}")

        if isinstance(event, ToolStartEvent):
            # Create node for tool start
            label = f"🔧 {event.tool_name}"
            if event.arguments:
                # Add key arguments to label
                if "repo" in event.arguments:
                    label += f" ({event.arguments['repo']})"
                elif "repository" in event.arguments:
                    label += f" ({event.arguments['repository']})"
                elif "service" in event.arguments:
                    label += f" ({event.arguments['service']})"
            node = self._create_node(event, label)
            logger.debug(f"Created node for tool: {event.tool_name}, total nodes: {len(self._root_nodes)}")

        elif isinstance(event, ToolCompleteEvent):
            # Update existing node
            if event.event_id in self._node_map:
                node = self._node_map[event.event_id]
                node.complete(event.result_summary, event.duration)

        elif isinstance(event, ToolErrorEvent):
            # Mark node as error
            if event.event_id in self._node_map:
                node = self._node_map[event.event_id]
                node.mark_error(event.error_message, event.duration)

        elif isinstance(event, WorkflowStepEvent):
            # Create or update workflow step node
            if event.status == "started":
                label = f"📋 {event.step_name}"
                self._create_node(event, label)
            elif event.event_id in self._node_map:
                node = self._node_map[event.event_id]
                if event.status == "completed":
                    summary = event.metadata.get("summary") if event.metadata else None
                    node.complete(summary)
                elif event.status == "failed":
                    error = event.metadata.get("error") if event.metadata else "Failed"
                    node.mark_error(error)

        elif isinstance(event, SubprocessOutputEvent):
            # Create node for subprocess output (condensed)
            label = f"💻 {event.command}"
            if event.event_id not in self._node_map:
                node = self._create_node(event, label)
                node.metadata["output_lines"] = [event.output_line]
            else:
                node = self._node_map[event.event_id]
                node.metadata.setdefault("output_lines", []).append(event.output_line)

        elif isinstance(event, LLMRequestEvent):
            label = f"🤖 Thinking with AI ({event.message_count} messages)"
            self._create_node(event, label)

        elif isinstance(event, LLMResponseEvent):
            if event.event_id in self._node_map:
                node = self._node_map[event.event_id]
                node.complete(f"Response received", event.duration)

    async def start(self) -> None:
        """Start the execution tree display.

        This starts the Rich Live display and background event processing.
        """
        if self._running:
            return

        self._running = True

        # Start Rich Live display with higher refresh rate
        self._live = Live(
            self._render_tree(),
            console=self.console,
            refresh_per_second=20,  # 50ms refresh rate for smoother updates
            transient=False,
        )
        self._live.start()

        # Start background event processing task
        self._task = asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        """Stop the execution tree display."""
        if not self._running:
            return

        # Process any remaining events before stopping
        while True:
            event = await self._event_emitter.get_event_nowait()
            if event is None:
                break
            await self._handle_event(event)

        self._running = False

        # Cancel background task
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Stop Rich Live display
        if self._live:
            # Final render before stopping
            self._live.update(self._render_tree())
            self._live.stop()

            # Print final tree state so it persists after Live stops
            # Debug: always print tree info
            self.console.print(f"\n[dim]Debug: {len(self._root_nodes)} root nodes, {len(self._node_map)} total nodes[/dim]")
            if self._root_nodes:
                self.console.print()
                self.console.print(self._render_tree())
                self.console.print()
            else:
                self.console.print("[yellow]No execution tree nodes were created[/yellow]")

    async def update(self) -> None:
        """Manually trigger a display update.

        This is called periodically to refresh the tree display.
        """
        if self._live:
            self._live.update(self._render_tree())

    def clear(self) -> None:
        """Clear the execution tree."""
        self._root_nodes.clear()
        self._node_map.clear()

    async def __aenter__(self) -> "ExecutionTreeDisplay":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
