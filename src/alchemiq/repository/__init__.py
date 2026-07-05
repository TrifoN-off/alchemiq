"""Public data-access objects: Repository faсade and pagination containers."""

from alchemiq.repository.base import Repository
from alchemiq.repository.pagination import Page

__all__ = ["Page", "Repository"]
