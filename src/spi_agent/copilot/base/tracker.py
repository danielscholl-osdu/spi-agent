"""Abstract base class for all status trackers."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any

from rich.table import Table


class BaseTracker(ABC):
    """Abstract base class for all status trackers."""

    def __init__(self, services: List[str]):
        """Initialize base tracker.

        Args:
            services: List of service names to track
        """
        self.services = self._initialize_services(services)

    @abstractmethod
    def _initialize_services(self, services: List[str]) -> Dict[str, Dict[str, Any]]:
        """Initialize service tracking dictionary.

        Args:
            services: List of service names

        Returns:
            Dictionary mapping service names to status data
        """
        pass

    def update(self, service: str, status: str, details: str = "", **kwargs) -> None:
        """Update service status.

        Args:
            service: Service name to update
            status: New status value
            details: Optional status details
            **kwargs: Additional status fields specific to tracker type
        """
        if service in self.services:
            self._update_service(service, status, details, **kwargs)

    @abstractmethod
    def _update_service(self, service: str, status: str, details: str, **kwargs) -> None:
        """Internal method to update service status.

        Args:
            service: Service name to update
            status: New status value
            details: Optional status details
            **kwargs: Additional status fields specific to tracker type
        """
        pass

    @abstractmethod
    def get_table(self) -> Table:
        """Generate Rich table of status.

        Returns:
            Rich Table with current status display
        """
        pass

    @property
    @abstractmethod
    def table_title(self) -> str:
        """Return the title for the status table.

        Returns:
            Title string for the table
        """
        pass

    @property
    @abstractmethod
    def status_icons(self) -> Dict[str, str]:
        """Return status icon mapping.

        Returns:
            Dictionary mapping status values to icon strings
        """
        pass

    def get_icon(self, status: str) -> str:
        """Get icon for a given status.

        Args:
            status: Status value

        Returns:
            Icon string for the status
        """
        return self.status_icons.get(status, "•")