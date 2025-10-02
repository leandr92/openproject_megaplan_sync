"""Клиенты REST API."""

from .megaplan import MegaplanClient
from .openproject import OpenProjectClient

__all__ = ["MegaplanClient", "OpenProjectClient"]
