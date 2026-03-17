#!/usr/bin/env python3
"""
VHW - Water Speed and Heading
Format: $VHW,heading_true,T,heading_magnetic,M,speed_knots,N,speed_kmh,K,checksum
"""

from datetime import datetime
import random
import math
from .base import NMEABase


class VHW(NMEABase):
    """VHW sentence generator"""
    
    def __init__(self):
        super().__init__()
        self.sentence_id = "VHW"
        self.base_speed = random.uniform(2.0, 8.0)  # Base speed in knots
        self.heading_drift = random.uniform(-1.0, 1.0)  # Heading drift per update
        self.current_heading = random.uniform(0, 360)
        self.time_offset = random.uniform(0, 2 * math.pi)
    
    def generate(self, 
                timestamp: datetime, 
                speed: float = None, 
                heading: float = None,
                magnetic_declination: float = 0.0) -> str:
        """
        Generate VHW sentence
        
        Args:
            timestamp: UTC timestamp
            speed: Speed through water in knots (if None, generates realistic varying speed)
            heading: True heading in degrees (if None, generates realistic varying heading)
            magnetic_declination: Magnetic declination in degrees (+ East, - West)
            
        Returns:
            VHW NMEA sentence
        """
        
        if speed is None:
            speed = self._generate_realistic_speed(timestamp)
        
        if heading is None:
            heading = self._generate_realistic_heading(timestamp)
        
        # Calculate magnetic heading
        magnetic_heading = (heading - magnetic_declination) % 360
        
        # Convert speed to km/h
        speed_kmh = speed * 1.852  # 1 knot = 1.852 km/h
        
        # Build sentence
        fields = [
            self.sentence_id,
            f"{heading:.1f}",
            "T",
            f"{magnetic_heading:.1f}",
            "M",
            f"{speed:.1f}",
            "N",
            f"{speed_kmh:.1f}",
            "K"
        ]
        
        return self._build_sentence(fields)
    
    def _generate_realistic_speed(self, timestamp: datetime) -> float:
        """
        Generate realistic speed that varies over time
        Simulates varying throttle and sea conditions
        """
        time_factor = timestamp.timestamp()
        
        # Create speed variation using sine waves
        variation = (
            math.sin(time_factor / 120 + self.time_offset) * 1.5 +     # Slow variation (throttle changes)
            math.sin(time_factor / 30 + self.time_offset) * 0.8 +      # Medium variation (waves)
            math.sin(time_factor / 8 + self.time_offset) * 0.3         # Fast variation (turbulence)
        )
        
        current_speed = self.base_speed + variation
        
        # Ensure speed stays within reasonable bounds
        current_speed = max(0.0, min(25.0, current_speed))
        
        # Add small random noise
        current_speed += random.uniform(-0.1, 0.1)
        
        return current_speed
    
    def _generate_realistic_heading(self, timestamp: datetime) -> float:
        """
        Generate realistic heading that changes gradually
        Simulates course corrections and wind/current effects
        """
        # Gradual heading changes
        self.current_heading += self.heading_drift + random.uniform(-0.5, 0.5)
        
        # Normalize heading to 0-360 range
        self.current_heading = self.current_heading % 360
        
        # Occasionally make larger course corrections
        if random.random() < 0.01:  # 1% chance per update
            self.current_heading += random.uniform(-20, 20)
            self.current_heading = self.current_heading % 360
        
        return self.current_heading
    
    def set_base_speed(self, speed_knots: float):
        """Set the base speed for simulation"""
        self.base_speed = max(0.0, speed_knots)
    
    def set_heading(self, heading: float):
        """Set the current heading"""
        self.current_heading = heading % 360
