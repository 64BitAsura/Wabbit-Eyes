#!/usr/bin/env python3
"""
GPRMC - Recommended Minimum Specific GPS/Transit Data
Format: $GPRMC,time,status,lat,lat_dir,lon,lon_dir,speed,course,date,mag_var,mag_var_dir,checksum
"""

from datetime import datetime
from typing import Optional
from .base import NMEABase


class GPRMC(NMEABase):
    """GPRMC sentence generator"""
    
    def __init__(self):
        super().__init__()
        self.sentence_id = "GPRMC"
    
    def generate(self, 
                timestamp: datetime,
                latitude: float,
                longitude: float,
                speed: float = 0.0,
                course: float = 0.0,
                status: str = "A") -> str:
        """
        Generate GPRMC sentence
        
        Args:
            timestamp: UTC timestamp
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            speed: Speed over ground in knots
            course: Course over ground in degrees
            status: A=Active, V=Void
        """
        
        # Format time as HHMMSS.SS
        time_str = timestamp.strftime("%H%M%S.%f")[:-4]  # Remove last 4 digits for .SS
        
        # Format date as DDMMYY
        date_str = timestamp.strftime("%d%m%y")
        
        # Convert coordinates to NMEA format
        lat_nmea, lat_dir = self._decimal_to_nmea_lat(latitude)
        lon_nmea, lon_dir = self._decimal_to_nmea_lon(longitude)
        
        # Format speed (knots) and course
        speed_str = f"{speed:.1f}" if speed > 0 else ""
        course_str = f"{course:.1f}" if course > 0 else ""
        
        # Magnetic variation (empty for now)
        mag_var = ""
        mag_var_dir = ""
        
        # Build sentence
        fields = [
            self.sentence_id,
            time_str,
            status,
            lat_nmea,
            lat_dir,
            lon_nmea,
            lon_dir,
            speed_str,
            course_str,
            date_str,
            mag_var,
            mag_var_dir
        ]
        
        return self._build_sentence(fields)
    
    def _decimal_to_nmea_lat(self, decimal_degrees: float) -> tuple:
        """Convert decimal degrees latitude to NMEA format"""
        direction = "N" if decimal_degrees >= 0 else "S"
        abs_degrees = abs(decimal_degrees)
        degrees = int(abs_degrees)
        minutes = (abs_degrees - degrees) * 60
        return f"{degrees:02d}{minutes:07.4f}", direction
    
    def _decimal_to_nmea_lon(self, decimal_degrees: float) -> tuple:
        """Convert decimal degrees longitude to NMEA format"""
        direction = "E" if decimal_degrees >= 0 else "W"
        abs_degrees = abs(decimal_degrees)
        degrees = int(abs_degrees)
        minutes = (abs_degrees - degrees) * 60
        return f"{degrees:03d}{minutes:07.4f}", direction
