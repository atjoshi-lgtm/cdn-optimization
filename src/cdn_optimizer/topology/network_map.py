"""
network_map.py

Resolves geographic and network topology relationships.
"""

from typing import Dict


class MetroResolver:
    """
    Resolves Metro Names to IDs (and vice versa) for database queries and logging.
    """

    def __init__(self, name_to_id_map: Dict[str, int], id_to_name_map: Dict[int, str]) -> None:
        """
        Initialize the resolver with a predefined mapping.
        
        Args:
            name_to_id_map: Dictionary mapping metro names to their integer IDs.
            id_to_name_map: Dictionary mapping metro IDs to their string names.
        """
        self._name_to_id = name_to_id_map
        self._id_to_name = id_to_name_map

    def get_id(self, metro_name: str) -> int:
        """
        Resolve a metro name to its ID.
        
        Args:
            metro_name: The string name of the metro (e.g., 'Seattle').
            
        Returns:
            The integer ID used in the database.
            
        Raises:
            KeyError: If the metro name is not found in the topology map.
        """
        if metro_name not in self._name_to_id:
            raise KeyError(f"Metro name '{metro_name}' not found in the topology map.")
        return self._name_to_id[metro_name]

    def get_name(self, metro_id: int) -> str:
        """
        Resolve a metro ID to its name.
        
        Args:
            metro_id: The integer ID of the metro.
            
        Returns:
            The string name of the metro.
            
        Raises:
            KeyError: If the metro ID is not found in the topology map.
        """
        if metro_id not in self._id_to_name:
            raise KeyError(f"Metro ID '{metro_id}' not found in the topology map.")
        return self._id_to_name[metro_id]