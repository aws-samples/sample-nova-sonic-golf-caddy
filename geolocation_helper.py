"""
Geolocation Helper for Golf Course Assistant

Handles automatic location detection using IP-based geolocation with fallback support.
Includes in-memory caching to avoid repeated API calls during a golf round.
"""

import requests
import json
import logging
from datetime import datetime, timedelta
from config import COURSE_LOCATION, IP_API_URL, IP_API_TIMEOUT, CACHE_DURATION_HOURS, is_debug_enabled

logger = logging.getLogger(__name__)


class GeolocationHelper:
    """Handles automatic location detection with fallback support and caching"""
    
    def __init__(self):
        """
        Initialize geolocation helper
        """
        self.debug_enabled = is_debug_enabled('geolocation_helper')
        self.fallback_location = COURSE_LOCATION
        self.api_url = IP_API_URL
        self.timeout = IP_API_TIMEOUT
        
        # Configure debug logging
        if self.debug_enabled:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initializing GeolocationHelper")
        
        # In-memory cache
        self._cached_location = None
        self._cache_timestamp = None
        self._cache_duration = timedelta(hours=CACHE_DURATION_HOURS)
    
    async def get_current_location(self, force_refresh=False):
        """
        Get current location using IP-based geolocation with caching
        
        Args:
            force_refresh: If True, bypass cache and make fresh API call
        
        Returns:
            dict: Location result with success status and location data
        """
        if self.debug_enabled:
            logger.debug("Starting location detection...")
        
        # Check cache first (unless force refresh)
        if not force_refresh and self._is_cache_valid():
            if self.debug_enabled:
                logger.debug("Using cached location data")
            cached_result = self._cached_location.copy()
            cached_result["source"] = f"{cached_result['source']}_cached"
            cached_result["message"] = f"{cached_result['message']} (cached)"
            return cached_result
        
        try:
            # Try IP-based geolocation
            location_data = await self._get_ip_location()
            
            if location_data:
                if self.debug_enabled:
                    logger.debug(f"Successfully detected location: {location_data['name']}")
                result = {
                    "success": True,
                    "source": "ip_geolocation",
                    "location": location_data,
                    "message": f"Detected location: {location_data['name']}"
                }
                
                # Cache the successful result
                self._cache_location(result)
                return result
            else:
                if self.debug_enabled:
                    logger.debug("IP geolocation failed, using fallback location")
                fallback_result = self._get_fallback_location()
                
                # Cache fallback result too (to avoid repeated API failures)
                self._cache_location(fallback_result)
                return fallback_result
                
        except Exception as e:
            if self.debug_enabled:
                logger.debug(f"Error in location detection: {str(e)}")
            fallback_result = self._get_fallback_location()
            self._cache_location(fallback_result)
            return fallback_result
    
    async def _get_ip_location(self):
        """
        Get location from IP-based geolocation API
        
        Returns:
            dict: Location data or None if failed
        """
        if self.debug_enabled:
            logger.debug(f"Querying IP geolocation API: {self.api_url}")
        
        try:
            # Make request to IP-API
            response = requests.get(self.api_url, timeout=self.timeout)
            if self.debug_enabled:
                logger.debug(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if self.debug_enabled:
                    logger.debug(f"API response data: {data}")
                
                # Check if the request was successful
                if data.get('status') == 'success':
                    location_data = {
                        "name": f"{data.get('city', 'Unknown')}, {data.get('regionName', 'Unknown')}",
                        "latitude": data.get('lat'),
                        "longitude": data.get('lon'),
                        "timezone": data.get('timezone', 'America/New_York'),
                        "country": data.get('country', 'Unknown'),
                        "region": data.get('regionName', 'Unknown'),
                        "city": data.get('city', 'Unknown'),
                        "zip": data.get('zip', 'Unknown'),
                        "isp": data.get('isp', 'Unknown')
                    }
                    
                    # Validate required fields
                    if location_data['latitude'] and location_data['longitude']:
                        if self.debug_enabled:
                            logger.debug(f"Valid location data extracted: {location_data['name']}")
                        return location_data
                    else:
                        if self.debug_enabled:
                            logger.debug("Missing latitude/longitude in API response")
                        return None
                else:
                    if self.debug_enabled:
                        logger.debug(f"API returned error status: {data.get('message', 'Unknown error')}")
                    return None
            else:
                if self.debug_enabled:
                    logger.debug(f"HTTP error: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            if self.debug_enabled:
                logger.debug(f"API request timed out after {self.timeout} seconds")
            return None
        except requests.exceptions.RequestException as e:
            if self.debug_enabled:
                logger.debug(f"Request error: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            if self.debug_enabled:
                logger.debug(f"JSON decode error: {str(e)}")
            return None
        except Exception as e:
            if self.debug_enabled:
                logger.debug(f"Unexpected error in IP geolocation: {str(e)}")
            return None
    
    def _get_fallback_location(self):
        """
        Get fallback location when IP geolocation fails
        
        Returns:
            dict: Fallback location result
        """
        if self.debug_enabled:
            logger.debug(f"Using fallback location: {self.fallback_location['name']}")
        
        return {
            "success": True,
            "source": "fallback",
            "location": self.fallback_location.copy(),
            "message": f"Using fallback location: {self.fallback_location['name']}",
            "note": "IP geolocation unavailable, using default location"
        }
    
    def get_location_summary(self, location_result):
        """
        Generate a human-readable summary of location detection
        
        Args:
            location_result: Result from get_current_location()
            
        Returns:
            str: Human-readable location summary
        """
        if not location_result.get("success"):
            return "Location detection failed"
        
        location = location_result["location"]
        source = location_result["source"]
        
        if source == "ip_geolocation":
            return f"Detected your location as {location['name']} (via IP geolocation)"
        elif source == "fallback":
            return f"Using default location: {location['name']} (IP geolocation unavailable)"
        else:
            return f"Location: {location['name']}"
    
    def is_location_accurate(self, location_result):
        """
        Check if the detected location is likely accurate for golf course use
        
        Args:
            location_result: Result from get_current_location()
            
        Returns:
            bool: True if location seems accurate enough
        """
        if not location_result.get("success"):
            return False
        
        source = location_result["source"]
        
        # IP geolocation is city-level accurate, good enough for weather
        if source == "ip_geolocation" or source == "ip_geolocation_cached":
            return True
        
        # Fallback is always "accurate" since it's a known golf location
        if source == "fallback" or source == "fallback_cached":
            return True
        
        return False
    
    def _is_cache_valid(self):
        """
        Check if cached location is still valid
        
        Returns:
            bool: True if cache is valid and not expired
        """
        if not self._cached_location or not self._cache_timestamp:
            if self.debug_enabled:
                logger.debug("No cached location data")
            return False
        
        now = datetime.now()
        cache_age = now - self._cache_timestamp
        is_valid = cache_age < self._cache_duration
        
        if self.debug_enabled:
            logger.debug(f"Cache age: {cache_age}, valid: {is_valid}")
        return is_valid
    
    def _cache_location(self, location_result):
        """
        Cache location result in memory
        
        Args:
            location_result: Location result to cache
        """
        self._cached_location = location_result.copy()
        self._cache_timestamp = datetime.now()
        
        if self.debug_enabled:
            logger.debug(f"Cached location: {location_result['location']['name']}")
            logger.debug(f"Cache expires at: {self._cache_timestamp + self._cache_duration}")
    
    def clear_cache(self):
        """
        Clear cached location data (useful for testing or manual refresh)
        """
        if self.debug_enabled:
            logger.debug("Clearing location cache")
        self._cached_location = None
        self._cache_timestamp = None
    
    def get_cache_status(self):
        """
        Get information about cache status
        
        Returns:
            dict: Cache status information
        """
        if not self._cached_location:
            return {
                "cached": False,
                "message": "No cached location"
            }
        
        if self._is_cache_valid():
            cache_age = datetime.now() - self._cache_timestamp
            expires_in = self._cache_duration - cache_age
            
            return {
                "cached": True,
                "valid": True,
                "location": self._cached_location["location"]["name"],
                "cached_since": self._cache_timestamp.isoformat(),
                "expires_in_minutes": int(expires_in.total_seconds() / 60),
                "message": f"Cached location: {self._cached_location['location']['name']}"
            }
        else:
            return {
                "cached": True,
                "valid": False,
                "message": "Cached location expired"
            }


# Utility functions for integration
def create_geolocation_helper():
    """
    Factory function to create geolocation helper
    
    Returns:
        GeolocationHelper: Configured geolocation helper instance
    """
    return GeolocationHelper()

async def get_user_location():
    """
    Quick utility function to get user location
    
    Returns:
        dict: Location result
    """
    helper = create_geolocation_helper()
    return await helper.get_current_location()