#!/usr/bin/env python3
"""
GPGSV - GPS Satellites in View
Format: $GPGSV,num_sentences,sentence_num,num_sats,sat_id,elevation,azimuth,snr,...,checksum
"""

from datetime import datetime
import random
from typing import List, Dict
from .base import NMEABase


class GPGSV(NMEABase):
    """GPGSV sentence generator"""
    
    def __init__(self):
        super().__init__()
        self.sentence_id = "GPGSV"
        self.satellites = self._generate_satellite_data()
    
    def _generate_satellite_data(self) -> List[Dict]:
        """Generate realistic satellite data"""
        satellites = []
        
        # Generate 8-12 satellites with realistic PRN numbers
        num_sats = random.randint(8, 12)
        prn_numbers = random.sample(range(1, 32), num_sats)
        
        for prn in prn_numbers:
            satellite = {
                'prn': prn,
                'elevation': random.randint(10, 90),  # degrees above horizon
                'azimuth': random.randint(0, 359),    # degrees from north
                'snr': random.randint(20, 50) if random.random() > 0.1 else 0  # signal-to-noise ratio
            }
            satellites.append(satellite)
        
        return satellites
    
    def generate(self, timestamp: datetime) -> List[str]:
        """
        Generate GPGSV sentences (may be multiple sentences for all satellites)
        
        Args:
            timestamp: UTC timestamp
            
        Returns:
            List of GPGSV sentences
        """
        sentences = []
        
        # Update satellite positions slightly (simulate movement)
        self._update_satellite_positions()
        
        # Calculate number of sentences needed (4 satellites per sentence max)
        num_satellites = len(self.satellites)
        num_sentences = (num_satellites + 3) // 4  # Round up division
        
        for sentence_num in range(1, num_sentences + 1):
            # Get satellites for this sentence (4 per sentence)
            start_idx = (sentence_num - 1) * 4
            end_idx = min(start_idx + 4, num_satellites)
            sentence_satellites = self.satellites[start_idx:end_idx]
            
            # Build sentence fields
            fields = [
                self.sentence_id,
                str(num_sentences),
                str(sentence_num),
                f"{num_satellites:02d}"
            ]
            
            # Add satellite data (up to 4 satellites per sentence)
            for sat in sentence_satellites:
                fields.extend([
                    f"{sat['prn']:02d}",                    # PRN number
                    f"{sat['elevation']:02d}",              # Elevation
                    f"{sat['azimuth']:03d}",                # Azimuth
                    f"{sat['snr']:02d}" if sat['snr'] > 0 else ""  # SNR (empty if no signal)
                ])
            
            # Pad with empty fields if less than 4 satellites in this sentence
            while len(fields) < 4 + (4 * 4):  # 4 base fields + 4 fields per satellite
                fields.append("")
            
            sentences.append(self._build_sentence(fields))
        
        return sentences
    
    def _update_satellite_positions(self):
        """Slightly update satellite positions to simulate orbital movement"""
        for sat in self.satellites:
            # Small random changes to simulate satellite movement
            sat['elevation'] += random.randint(-2, 2)
            sat['elevation'] = max(0, min(90, sat['elevation']))  # Keep in valid range
            
            sat['azimuth'] += random.randint(-5, 5)
            sat['azimuth'] = sat['azimuth'] % 360  # Keep in 0-359 range
            
            # Occasionally change SNR
            if random.random() < 0.1:
                if sat['snr'] > 0:
                    sat['snr'] += random.randint(-5, 5)
                    sat['snr'] = max(0, min(50, sat['snr']))
                else:
                    # Sometimes a satellite comes back into view
                    if random.random() < 0.3:
                        sat['snr'] = random.randint(15, 25)
