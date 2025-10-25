"""Hierarchical execution tree display using Rich Live."""

import asyncio
from datetime import datetime
from enum import Enum
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


class DisplayMode(Enum):
    """Display mode for execution tree.

    MINIMAL: Only show active phase (results-focused, default)
    DEFAULT: Show active phase + completed phase count
    VERBOSE: Show all phases with full details
    """
    MINIMAL = "minimal"
    DEFAULT = "default"
    VERBOSE = "verbose"


# Symbol constants (minimal, Betty-themed)
SYMBOL_QUERY = "◉"       # Session/query (Betty's eye)
SYMBOL_COMPLETE = "•"    # Completed item
SYMBOL_ACTIVE = "●"      # Active/running
SYMBOL_TOOL = "→"        # Tool executing
SYMBOL_SUCCESS = "◎"     # Complete session
SYMBOL_ERROR = "✗"       # Error
SYMBOL_BRANCH = "└─"     # Tree branch

# Colors
COLOR_QUERY = "cyan"
COLOR_COMPLETE = "dim white"
COLOR_ACTIVE = "yellow"
COLOR_SUCCESS = "green"
COLOR_ERROR = "red"


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


class ExecutionPhase:
    """Represents a reasoning phase (LLM thinking + associated tool calls).

    A phase groups together:
    - One LLM request/response pair
    - Zero or more tool calls made during that thinking cycle

    Attributes:
        phase_number: Sequential phase number
        llm_node: LLM thinking node (optional)
        tool_nodes: Tool nodes executed in this phase
        start_time: When phase started
        end_time: When phase completed
        status: Phase status (in_progress, completed, error)
    """

    def __init__(self, phase_number: int):
        """Initialize execution phase.

        Args:
            phase_number: Sequential number for this phase
        """
        self.phase_number = phase_number
        self.llm_node: Optional[TreeNode] = None
        self.tool_nodes: List[TreeNode] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        self.status = "in_progress"

    def add_llm_node(self, node: TreeNode) -> None:
        """Add LLM thinking node to this phase."""
        self.llm_node = node

    def add_tool_node(self, node: TreeNode) -> None:
        """Add tool execution node to this phase."""
        self.tool_nodes.append(node)

    def complete(self) -> None:
        """Mark phase as completed."""
        self.status = "completed"
        self.end_time = datetime.now()

    def mark_error(self) -> None:
        """Mark phase as error."""
        self.status = "error"
        self.end_time = datetime.now()

    @property
    def duration(self) -> float:
        """Get phase duration in seconds."""
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def summary(self) -> str:
        """Get phase summary description."""
        tool_count = len(self.tool_nodes)
        if tool_count == 0:
            return f"Phase {self.phase_number}: Initial thinking"
        elif tool_count == 1:
            tool_name = self.tool_nodes[0].label.replace(SYMBOL_TOOL + " ", "").split(" ")[0]
            return f"Phase {self.phase_number}: {tool_name}"
        else:
            return f"Phase {self.phase_number}: {tool_count} tool calls"

    @property
    def has_nodes(self) -> bool:
        """Check if phase has any nodes."""
        return self.llm_node is not None or len(self.tool_nodes) > 0


class ExecutionTreeDisplay:
    """Hierarchical execution tree display using Rich Live.

    This class manages a tree of execution events and renders them
    in real-time using Rich's Live display with visual hierarchy.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        display_mode: DisplayMode = DisplayMode.MINIMAL,
    ):
        """Initialize execution tree display.

        Args:
            console: Rich console to use (creates new one if not provided)
            display_mode: Display verbosity level (MINIMAL, DEFAULT, VERBOSE)
        """
        self.console = console or Console()
        self.display_mode = display_mode
        self._live: Optional[Live] = None
        self._root_nodes: List[TreeNode] = []
        self._node_map: Dict[str, TreeNode] = {}
        self._event_emitter: EventEmitter = get_event_emitter()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._is_rich_supported = self.console.is_terminal

        # Phase tracking for grouping
        self._phases: List[ExecutionPhase] = []
        self._current_phase: Optional[ExecutionPhase] = None
        self._session_start_time = datetime.now()

        # Display configuration based on mode
        self._auto_collapse_completed = (display_mode == DisplayMode.MINIMAL)
        self._show_llm_details = (display_mode == DisplayMode.VERBOSE)

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

    def _render_phases(self) -> RenderableType:
        """Render execution using phase-based view.

        Returns:
            Rich renderable with phase-grouped display
        """
        if not self._phases:
            return Text(f"{SYMBOL_ACTIVE} Thinking...", style=COLOR_ACTIVE)

        renderables = []

        # Calculate session progress
        completed_count = sum(1 for p in self._phases if p.status == "completed")
        total_phases = len(self._phases)
        session_duration = (datetime.now() - self._session_start_time).total_seconds()

        # Display mode: MINIMAL (only show active phase)
        if self.display_mode == DisplayMode.MINIMAL:
            # Only show current phase if one exists
            if self._current_phase and self._current_phase.status == "in_progress":
                phase_label = Text(f"{SYMBOL_ACTIVE} {self._current_phase.summary}", style=COLOR_ACTIVE)
                phase_tree = Tree(phase_label)

                # Show LLM details if verbose
                if self._show_llm_details and self._current_phase.llm_node:
                    phase_tree.add(self._render_node_rich(self._current_phase.llm_node))

                # Show tool calls
                for tool_node in self._current_phase.tool_nodes:
                    phase_tree.add(self._render_node_rich(tool_node))

                renderables.append(phase_tree)

                # Progress line
                if completed_count > 0:
                    progress_text = Text(
                        f"\n{completed_count}/{total_phases} phases complete",
                        style="dim"
                    )
                    renderables.append(progress_text)

            elif completed_count == total_phases and total_phases > 0:
                # All done - show minimal summary
                summary_text = Text(
                    f"{SYMBOL_SUCCESS} Complete ({session_duration:.1f}s)",
                    style=COLOR_SUCCESS
                )
                renderables.append(summary_text)

        # Display mode: DEFAULT (show active + completed summary)
        elif self.display_mode == DisplayMode.DEFAULT:
            # Show completed phases (condensed)
            for phase in self._phases[:-1]:  # All but current
                if phase.status == "completed":
                    phase_text = Text(
                        f"{SYMBOL_COMPLETE} {phase.summary} ({phase.duration:.1f}s)",
                        style=COLOR_COMPLETE
                    )
                    renderables.append(phase_text)

            # Show current phase (expanded)
            if self._current_phase and self._current_phase.status == "in_progress":
                phase_label = Text(f"{SYMBOL_ACTIVE} {self._current_phase.summary}", style=COLOR_ACTIVE)
                phase_tree = Tree(phase_label)

                for tool_node in self._current_phase.tool_nodes:
                    phase_tree.add(self._render_node_rich(tool_node))

                renderables.append(phase_tree)

        # Display mode: VERBOSE (show all details)
        else:  # VERBOSE
            for phase in self._phases:
                # Phase header
                if phase.status == "in_progress":
                    symbol = SYMBOL_ACTIVE
                    style = COLOR_ACTIVE
                elif phase.status == "completed":
                    symbol = SYMBOL_COMPLETE
                    style = COLOR_COMPLETE
                else:
                    symbol = SYMBOL_ERROR
                    style = COLOR_ERROR

                phase_label = Text(
                    f"{symbol} {phase.summary} ({phase.duration:.1f}s)",
                    style=style
                )
                phase_tree = Tree(phase_label)

                # LLM details
                if self._show_llm_details and phase.llm_node:
                    phase_tree.add(self._render_node_rich(phase.llm_node))

                # Tool calls
                for tool_node in phase.tool_nodes:
                    phase_tree.add(self._render_node_rich(tool_node))

                renderables.append(phase_tree)

        return Group(*renderables) if renderables else Text(f"{SYMBOL_ACTIVE} Thinking...", style=COLOR_ACTIVE)

    def _render_tree(self) -> RenderableType:
        """Render the execution tree.

        Returns:
            Rich renderable tree
        """
        # Use phase-based rendering if phases exist
        if self._phases:
            return self._render_phases()

        # Fallback to node-based rendering (for non-phase events)
        if not self._is_rich_supported:
            # Fallback to simple text rendering
            lines = []
            for node in self._root_nodes:
                lines.extend(self._render_node_simple(node, indent=0))
            return Text("\n".join(lines))

        # Create Rich tree for hierarchical display
        if not self._root_nodes:
            return Text(f"{SYMBOL_ACTIVE} Thinking...", style=COLOR_ACTIVE)

        # Render all root nodes
        renderables = []
        for root_node in self._root_nodes:
            renderables.append(self._render_node_rich(root_node))

        return Group(*renderables) if renderables else Text(f"{SYMBOL_ACTIVE} Thinking...", style=COLOR_ACTIVE)

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
            symbol = SYMBOL_ACTIVE
        elif node.status == "completed":
            symbol = SYMBOL_COMPLETE
        else:  # error
            symbol = SYMBOL_ERROR

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
            symbol = SYMBOL_ACTIVE
            style = COLOR_ACTIVE
        elif node.status == "completed":
            symbol = SYMBOL_COMPLETE
            style = COLOR_COMPLETE
        else:  # error
            symbol = SYMBOL_ERROR
            style = COLOR_ERROR

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
            label = f"{SYMBOL_TOOL} {event.tool_name}"
            if event.arguments:
                # Add key arguments to label
                if "repo" in event.arguments:
                    label += f" ({event.arguments['repo']})"
                elif "repository" in event.arguments:
                    label += f" ({event.arguments['repository']})"
                elif "service" in event.arguments:
                    label += f" ({event.arguments['service']})"
            node = self._create_node(event, label)

            # Add tool to current phase
            if self._current_phase:
                self._current_phase.add_tool_node(node)

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
                label = f"{SYMBOL_ACTIVE} {event.step_name}"
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
            label = f"{SYMBOL_TOOL} {event.command}"
            if event.event_id not in self._node_map:
                node = self._create_node(event, label)
                node.metadata["output_lines"] = [event.output_line]
            else:
                node = self._node_map[event.event_id]
                node.metadata.setdefault("output_lines", []).append(event.output_line)

        elif isinstance(event, LLMRequestEvent):
            # Start a new reasoning phase
            if self._current_phase and self._current_phase.has_nodes:
                # Complete previous phase before starting new one
                self._current_phase.complete()

            # Create new phase
            phase_num = len(self._phases) + 1
            self._current_phase = ExecutionPhase(phase_num)
            self._phases.append(self._current_phase)

            # Create LLM node
            label = f"Thinking ({event.message_count} messages)"
            node = self._create_node(event, label)
            self._current_phase.add_llm_node(node)

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

        # Complete any active phase
        if self._current_phase and self._current_phase.status == "in_progress":
            self._current_phase.complete()

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
            # Final render before stopping (Live will show this)
            self._live.update(self._render_tree())
            self._live.stop()

            # In MINIMAL mode, print a clean completion message after Live stops
            # (Live display is transient and disappears, so we print a final state)
            if self.display_mode == DisplayMode.MINIMAL and self._phases:
                completed_count = len([p for p in self._phases if p.status == "completed"])
                total_duration = (datetime.now() - self._session_start_time).total_seconds()
                self.console.print(
                    f"\n[{COLOR_SUCCESS}]{SYMBOL_SUCCESS} Complete ({total_duration:.1f}s) - "
                    f"{completed_count} phases[/{COLOR_SUCCESS}]\n"
                )

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
