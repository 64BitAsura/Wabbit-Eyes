#!/usr/bin/env python3
"""
Base class for NMEA sentence generators
Provides common functionality including checksum calculation
"""

from typing import List


class NMEABase:
    """Base class for NMEA sentence generators"""
    
    def __init__(self):
        self.sentence_id = ""
    
    def _calculate_checksum(self, sentence: str) -> str:
        """
        Calculate NMEA checksum
        XOR of all characters between $ and *
        """
        checksum = 0
        for char in sentence:
            checksum ^= ord(char)
        return f"{checksum:02X}"
    
    def _build_sentence(self, fields: List[str]) -> str:
        """
        Build complete NMEA sentence with checksum
        
        Args:
            fields: List of sentence fields
            
        Returns:
            Complete NMEA sentence with checksum and CRLF
        """
        # Join fields with comma
        sentence_body = ",".join(str(field) for field in fields)
        
        # Calculate checksum (exclude the $ prefix)
        checksum = self._calculate_checksum(sentence_body)
        
        # Build complete sentence
        complete_sentence = f"${sentence_body}*{checksum}\r\n"
        
        return complete_sentence
    
    def _knots_to_mps(self, knots: float) -> float:
        """Convert knots to meters per second"""
        return knots * 0.514444
    
    def _mps_to_knots(self, mps: float) -> float:
        """Convert meters per second to knots"""
        return mps / 0.514444
    
    def _feet_to_meters(self, feet: float) -> float:
        """Convert feet to meters"""
        return feet * 0.3048
    
    def _meters_to_feet(self, meters: float) -> float:
        """Convert meters to feet"""
        return meters / 0.3048
