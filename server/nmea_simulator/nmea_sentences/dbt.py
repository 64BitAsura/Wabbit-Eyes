#!/usr/bin/env python3
"""
DBT - Depth Below Transducer
Format: $DBT,depth_feet,f,depth_meters,M,depth_fathoms,F,checksum
"""

from datetime import datetime
import random
import math
from .base import NMEABase


class DBT(NMEABase):
    """DBT sentence generator"""
    
    def __init__(self):
        super().__init__()
        self.sentence_id = "DBT"
        self.base_depth = random.uniform(5.0, 50.0)  # Base depth in meters
        self.depth_variation = 0.0
        self.time_offset = random.uniform(0, 2 * math.pi)
    
    def generate(self, timestamp: datetime, depth_meters: float = None) -> str:
        """
        Generate DBT sentence
        
        Args:
            timestamp: UTC timestamp
            depth_meters: Depth in meters (if None, generates realistic varying depth)
            
        Returns:
            DBT NMEA sentence
        """
        
        if depth_meters is None:
            # Generate realistic varying depth
            depth_meters = self._generate_realistic_depth(timestamp)
        
        # Convert to different units
        depth_feet = self._meters_to_feet(depth_meters)
        depth_fathoms = depth_meters / 1.8288  # 1 fathom = 1.8288 meters
        
        # Build sentence
        fields = [
            self.sentence_id,
            f"{depth_feet:.1f}",
            "f",
            f"{depth_meters:.1f}",
            "M",
            f"{depth_fathoms:.1f}",
            "F"
        ]
        
        return self._build_sentence(fields)
    
    def _generate_realistic_depth(self, timestamp: datetime) -> float:
        """
        Generate realistic depth that varies over time
        Simulates movement over varying bottom topography
        """
        # Use timestamp to create consistent but varying depth
        time_factor = timestamp.timestamp()
        
        # Create depth variation using sine waves of different frequencies
        variation = (
            math.sin(time_factor / 60 + self.time_offset) * 2.0 +      # Slow variation
            math.sin(time_factor / 20 + self.time_offset) * 1.0 +      # Medium variation
            math.sin(time_factor / 5 + self.time_offset) * 0.5         # Fast variation
        )
        
        # Apply variation to base depth
        current_depth = self.base_depth + variation
        
        # Ensure depth stays within reasonable bounds
        current_depth = max(1.0, min(100.0, current_depth))
        
        # Add small random noise
        current_depth += random.uniform(-0.1, 0.1)
        
        return current_depth
    
    def set_base_depth(self, depth_meters: float):
        """Set the base depth for simulation"""
        self.base_depth = max(1.0, depth_meters)
