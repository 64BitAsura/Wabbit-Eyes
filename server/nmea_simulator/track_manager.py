#!/usr/bin/env python3
"""
Track Manager - Handles GPX track files and position simulation
"""

import xml.etree.ElementTree as ET
import math
import random
from typing import List, Dict, Optional
from datetime import datetime, timedelta


class TrackManager:
    """Manages track data from GPX files and simulated movement"""
    
    def __init__(self):
        self.track_points = []
        self.current_index = 0
        self.loop_track = True
        
        # Simulation parameters for when no GPX file is loaded
        self.sim_lat = 51.9225  # Rotterdam coordinates
        self.sim_lon = 4.47917
        self.sim_speed = 5.0    # knots
        self.sim_heading = 90.0  # degrees
        self.sim_time_step = 1.0  # seconds
        
    def load_gpx_file(self, gpx_file: str) -> bool:
        """
        Load GPX track file
        
        Args:
            gpx_file: Path to GPX file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            # Parse GPX file
            tree = ET.parse(gpx_file)
            root = tree.getroot()
            
            # Handle GPX namespace
            namespace = {'gpx': 'http://www.topografix.com/GPX/1/1'}
            if not root.tag.endswith('gpx'):
                # Try without namespace
                namespace = {'gpx': ''}
            
            self.track_points = []
            
            # Extract track points from <trk><trkseg><trkpt>
            for trk in root.findall('.//trk', namespace):
                for trkseg in trk.findall('.//trkseg', namespace):
                    for trkpt in trkseg.findall('.//trkpt', namespace):
                        try:
                            lat = float(trkpt.get('lat'))
                            lon = float(trkpt.get('lon'))
                            
                            # Try to get elevation
                            ele_elem = trkpt.find('.//ele', namespace)
                            elevation = float(ele_elem.text) if ele_elem is not None else 0.0
                            
                            # Try to get time
                            time_elem = trkpt.find('.//time', namespace)
                            timestamp = None
                            if time_elem is not None:
                                try:
                                    timestamp = datetime.fromisoformat(
                                        time_elem.text.replace('Z', '+00:00')
                                    )
                                except Exception:
                                    pass
                            
                            point = {
                                'lat': lat,
                                'lon': lon,
                                'elevation': elevation,
                                'timestamp': timestamp
                            }
                            
                            self.track_points.append(point)
                            
                        except (ValueError, TypeError):
                            continue
            
            # If no track points found, try waypoints
            if not self.track_points:
                for wpt in root.findall('.//wpt', namespace):
                    try:
                        lat = float(wpt.get('lat'))
                        lon = float(wpt.get('lon'))
                        
                        ele_elem = wpt.find('.//ele', namespace)
                        elevation = float(ele_elem.text) if ele_elem is not None else 0.0
                        
                        point = {
                            'lat': lat,
                            'lon': lon,
                            'elevation': elevation,
                            'timestamp': None
                        }
                        
                        self.track_points.append(point)
                        
                    except (ValueError, TypeError):
                        continue
            
            if self.track_points:
                # Calculate speed and course for each point
                self._calculate_movement_data()
                self.current_index = 0
                return True
            
            return False
            
        except Exception as e:
            print(f"Error loading GPX file: {e}")
            return False
    
    def _calculate_movement_data(self):
        """Calculate speed and course between track points"""
        for i in range(len(self.track_points)):
            if i < len(self.track_points) - 1:
                current = self.track_points[i]
                next_point = self.track_points[i + 1]
                
                # Calculate distance and bearing
                distance_m = self._calculate_distance(
                    current['lat'], current['lon'],
                    next_point['lat'], next_point['lon']
                )
                
                bearing = self._calculate_bearing(
                    current['lat'], current['lon'],
                    next_point['lat'], next_point['lon']
                )
                
                # Calculate time difference for speed calculation
                time_diff = 60.0  # Default 1 minute between points
                if (current.get('timestamp') and next_point.get('timestamp')):
                    time_diff = (next_point['timestamp'] - current['timestamp']).total_seconds()
                    time_diff = max(1.0, time_diff)  # Minimum 1 second
                
                # Calculate speed in knots
                speed_mps = distance_m / time_diff
                speed_knots = speed_mps * 1.94384  # Convert m/s to knots
                
                current['speed'] = speed_knots
                current['course'] = bearing
            else:
                # Last point - use previous point's data
                if i > 0:
                    self.track_points[i]['speed'] = self.track_points[i-1]['speed']
                    self.track_points[i]['course'] = self.track_points[i-1]['course']
                else:
                    self.track_points[i]['speed'] = 0.0
                    self.track_points[i]['course'] = 0.0
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using Haversine formula (meters)"""
        R = 6371000  # Earth's radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    def _calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing between two points (degrees)"""
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)
        
        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = (math.cos(lat1_rad) * math.sin(lat2_rad) - 
             math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))
        
        bearing = math.atan2(x, y)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        
        return bearing
    
    def get_current_position(self) -> Optional[Dict]:
        """Get current position from track"""
        if not self.track_points:
            return None
        
        return self.track_points[self.current_index].copy()
    
    def advance_position(self):
        """Advance to next position in track"""
        if not self.track_points:
            return
        
        self.current_index += 1
        
        if self.current_index >= len(self.track_points):
            if self.loop_track:
                self.current_index = 0
            else:
                self.current_index = len(self.track_points) - 1
    
    def get_simulated_position(self) -> Dict:
        """Generate simulated position when no GPX track is loaded"""
        # Add random speed variation (±20% of base speed)
        speed_variation = random.uniform(-0.2, 0.2)
        current_speed = self.sim_speed * (1 + speed_variation)
        current_speed = max(0.1, current_speed)  # Ensure minimum speed
        
        # Move based on current heading and speed
        distance_per_second = current_speed * 0.514444  # Convert knots to m/s
        
        # Calculate new position
        lat_change = (distance_per_second * math.cos(math.radians(self.sim_heading)) / 111320)
        lon_change = (distance_per_second * math.sin(math.radians(self.sim_heading)) / 
                     (111320 * math.cos(math.radians(self.sim_lat))))
        
        self.sim_lat += lat_change
        self.sim_lon += lon_change
        
        # Occasionally change heading to make it more interesting
        if random.random() < 0.01:  # 1% chance
            self.sim_heading += random.uniform(-30, 30)
            self.sim_heading = self.sim_heading % 360
        
        # Add small random variations
        self.sim_heading += random.uniform(-2, 2)
        self.sim_heading = self.sim_heading % 360
        
        return {
            'lat': self.sim_lat,
            'lon': self.sim_lon,
            'elevation': 0.0,
            'speed': current_speed,
            'course': self.sim_heading,
            'timestamp': datetime.utcnow()
        }
    
    def get_track_info(self) -> Dict:
        """Get information about the current track"""
        return {
            'total_points': len(self.track_points),
            'current_index': self.current_index,
            'has_track': len(self.track_points) > 0,
            'loop_enabled': self.loop_track
        }
    
    def set_loop_track(self, loop: bool):
        """Enable/disable track looping"""
        self.loop_track = loop
    
    def reset_position(self):
        """Reset to beginning of track"""
        self.current_index = 0
    
    def set_simulation_parameters(self, lat: float = None, lon: float = None, 
                                speed: float = None, heading: float = None):
        """Set parameters for position simulation"""
        if lat is not None:
            self.sim_lat = lat
        if lon is not None:
            self.sim_lon = lon
        if speed is not None:
            self.sim_speed = speed
        if heading is not None:
            self.sim_heading = heading
