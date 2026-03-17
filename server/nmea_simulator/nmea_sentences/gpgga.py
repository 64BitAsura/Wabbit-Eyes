#!/usr/bin/env python3
"""
GPGGA - Global Positioning System Fix Data
Format: $GPGGA,time,lat,lat_dir,lon,lon_dir,quality,num_sats,hdop,alt,alt_unit,geoid_height,geoid_unit,dgps_time,dgps_id,checksum
"""

from datetime import datetime
import random
from .base import NMEABase


class GPGGA(NMEABase):
    """GPGGA sentence generator"""
    
    def __init__(self):
        super().__init__()
        self.sentence_id = "GPGGA"
    
    def generate(self,
                timestamp: datetime,
                latitude: float,
                longitude: float,
                altitude: float = 0.0,
                quality: int = 1,
                num_satellites: int = None,
                hdop: float = None) -> str:
        """
        Generate GPGGA sentence
        
        Args:
            timestamp: UTC timestamp
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            altitude: Altitude above mean sea level in meters
            quality: GPS quality indicator (0=invalid, 1=GPS fix, 2=DGPS fix)
            num_satellites: Number of satellites in use
            hdop: Horizontal dilution of precision
        """
        
        # Format time as HHMMSS.SS
        time_str = timestamp.strftime("%H%M%S.%f")[:-4]
        
        # Convert coordinates to NMEA format
        lat_nmea, lat_dir = self._decimal_to_nmea_lat(latitude)
        lon_nmea, lon_dir = self._decimal_to_nmea_lon(longitude)
        
        # Generate realistic satellite count if not provided
        if num_satellites is None:
            num_satellites = random.randint(6, 12)
        
        # Generate realistic HDOP if not provided
        if hdop is None:
            hdop = random.uniform(0.8, 2.5)
        
        # Format altitude
        alt_str = f"{altitude:.1f}"
        alt_unit = "M"
        
        # Geoid height (simplified - using a typical value)
        geoid_height = random.uniform(-50, 50)
        geoid_height_str = f"{geoid_height:.1f}"
        geoid_unit = "M"
        
        # DGPS fields (empty for standard GPS)
        dgps_time = ""
        dgps_id = ""
        
        # Build sentence
        fields = [
            self.sentence_id,
            time_str,
            lat_nmea,
            lat_dir,
            lon_nmea,
            lon_dir,
            str(quality),
            f"{num_satellites:02d}",
            f"{hdop:.1f}",
            alt_str,
            alt_unit,
            geoid_height_str,
            geoid_unit,
            dgps_time,
            dgps_id
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
