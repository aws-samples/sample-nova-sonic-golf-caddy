"""
Golf Course API Helper

This module provides a helper class for interacting with the Golf Course API
to retrieve golf course information, search for courses, and get detailed
course data including tee boxes, ratings, and hole information.

API Documentation: https://api.golfcourseapi.com/docs/api/
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
import logging
from config import GOLF_COURSE_API_URL, GOLF_COURSE_API_KEY, GOLF_COURSE_API_TIMEOUT, is_debug_enabled

logger = logging.getLogger(__name__)


class GolfCourseAPIError(Exception):
    """Custom exception for Golf Course API errors"""
    pass


class GolfCourseHelper:
    """Helper class for interacting with the Golf Course API"""
    
    def __init__(self, api_key: str = None, base_url: str = None):
        """
        Initialize the Golf Course API helper
        
        Args:
            api_key: Your Golf Course API key (defaults to config value)
            base_url: Base URL for the API (defaults to config value)
        """
        self.api_key = api_key or GOLF_COURSE_API_KEY
        self.base_url = (base_url or GOLF_COURSE_API_URL).rstrip('/')
        self.timeout = GOLF_COURSE_API_TIMEOUT
        self.debug_enabled = is_debug_enabled('golfcourse_helper')
        self.headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Configure debug logging based on config flag
        if self.debug_enabled:
            logger.setLevel(logging.DEBUG)
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make an async HTTP request to the Golf Course API
        
        Args:
            endpoint: API endpoint (e.g., '/v1/search')
            params: Query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            GolfCourseAPIError: If the API request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 401:
                        raise GolfCourseAPIError("API key is missing or invalid")
                    elif response.status != 200:
                        error_text = await response.text()
                        raise GolfCourseAPIError(f"API request failed with status {response.status}: {error_text}")
                    
                    return await response.json()
                    
        except aiohttp.ClientError as e:
            raise GolfCourseAPIError(f"Network error: {str(e)}")
        except asyncio.TimeoutError:
            raise GolfCourseAPIError(f"Request timed out after {self.timeout} seconds")
        except Exception as e:
            raise GolfCourseAPIError(f"Unexpected error: {str(e)}")
    
    async def search_courses(self, search_query: str) -> List[Dict[str, Any]]:
        """
        Search for golf courses by name or club name
        
        Args:
            search_query: The search term (e.g., "pinehurst", "pebble beach")
            
        Returns:
            List of course dictionaries with basic information
            
        Raises:
            GolfCourseAPIError: If the search fails
        """
        if self.debug_enabled:
            logger.debug(f"Searching for courses with query: {search_query}")
        
        params = {"search_query": search_query}
        response = await self._make_request("/v1/search", params)
        
        courses = response.get("courses", [])
        if self.debug_enabled:
            logger.debug(f"Found {len(courses)} courses matching '{search_query}'")
        
        return courses
    
    async def get_course_details(self, course_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific golf course
        
        Args:
            course_id: The numeric ID of the golf course
            
        Returns:
            Detailed course information including tees, holes, ratings
            
        Raises:
            GolfCourseAPIError: If the course lookup fails
        """
        if self.debug_enabled:
            logger.debug(f"Getting details for course ID: {course_id}")
        
        response = await self._make_request(f"/v1/courses/{course_id}")
        
        if self.debug_enabled:
            logger.debug(f"Retrieved details for course: {response.get('course_name', 'Unknown')}")
        
        return response
    
    async def healthcheck(self) -> Dict[str, Any]:
        """
        Check the API service status
        
        Returns:
            API status and system information
            
        Raises:
            GolfCourseAPIError: If the healthcheck fails
        """
        if self.debug_enabled:
            logger.debug("Performing API healthcheck")
        
        response = await self._make_request("/v1/healthcheck")
        
        if self.debug_enabled:
            logger.debug(f"API status: {response.get('status', 'unknown')}")
        
        return response
    
    # Convenience methods for common operations
    
    async def find_course_by_name(self, course_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a specific course by name and return its full details
        
        Args:
            course_name: Name of the course to find
            
        Returns:
            Full course details if found, None otherwise
        """
        try:
            courses = await self.search_courses(course_name)
            
            if not courses:
                if self.debug_enabled:
                    logger.debug(f"No courses found matching '{course_name}'")
                return None
            
            # Get the first match (most relevant)
            first_course = courses[0]
            course_id = first_course.get("id")
            
            if course_id:
                return await self.get_course_details(course_id)
            
            return first_course
            
        except GolfCourseAPIError as e:
            if self.debug_enabled:
                logger.debug(f"Error finding course '{course_name}': {str(e)}")
            return None
    
    async def get_course_tees(self, course_id: int, gender: str = "male") -> List[Dict[str, Any]]:
        """
        Get tee information for a specific course and gender
        
        Args:
            course_id: The numeric ID of the golf course
            gender: "male" or "female" tees
            
        Returns:
            List of tee box information
        """
        course_details = await self.get_course_details(course_id)
        tees = course_details.get("tees", {})
        
        return tees.get(gender, [])
    
    async def get_hole_info(self, course_id: int, tee_name: str = None) -> List[Dict[str, Any]]:
        """
        Get hole-by-hole information for a course
        
        Args:
            course_id: The numeric ID of the golf course
            tee_name: Specific tee to get hole info for (e.g., "Blue", "White")
            
        Returns:
            List of hole information with par, yardage, handicap
        """
        course_details = await self.get_course_details(course_id)
        tees = course_details.get("tees", {})
        
        # Try to find the specified tee, or use the first available
        target_tees = []
        for gender in ["male", "female"]:
            gender_tees = tees.get(gender, [])
            if tee_name:
                target_tees = [t for t in gender_tees if t.get("tee_name", "").lower() == tee_name.lower()]
                if target_tees:
                    break
            else:
                target_tees = gender_tees
                if target_tees:
                    break
        
        if target_tees:
            return target_tees[0].get("holes", [])
        
        return []
    
    def format_course_summary(self, course_data: Dict[str, Any]) -> str:
        """
        Format course data into a readable summary
        
        Args:
            course_data: Course data from the API
            
        Returns:
            Formatted string summary of the course
        """
        if not course_data:
            return "No course data available"
        
        club_name = course_data.get("club_name", "Unknown Club")
        course_name = course_data.get("course_name", "Unknown Course")
        location = course_data.get("location", {})
        
        summary = f"{club_name}"
        if course_name != club_name:
            summary += f" - {course_name}"
        
        if location.get("city") and location.get("state"):
            summary += f"\nLocation: {location['city']}, {location['state']}"
        
        # Add tee information if available
        tees = course_data.get("tees", {})
        male_tees = tees.get("male", [])
        if male_tees:
            tee_names = [t.get("tee_name", "Unknown") for t in male_tees]
            summary += f"\nTees Available: {', '.join(tee_names)}"
            
            # Add yardage info for first tee
            first_tee = male_tees[0]
            total_yards = first_tee.get("total_yards")
            par_total = first_tee.get("par_total")
            if total_yards and par_total:
                summary += f"\nYardage: {total_yards} yards, Par {par_total}"
        
        return summary


# Convenience function for quick testing
async def test_golf_course_api():
    """Test function to verify API connectivity"""
    helper = GolfCourseHelper()
    
    try:
        # Test healthcheck
        health = await helper.healthcheck()
        print(f"API Status: {health.get('status')}")
        
        # Test search
        courses = await helper.search_courses("pinehurst")
        print(f"Found {len(courses)} courses for 'pinehurst'")
        
        if courses:
            # Test course details
            first_course = courses[0]
            course_id = first_course.get("id")
            if course_id:
                details = await helper.get_course_details(course_id)
                print(f"Course details: {helper.format_course_summary(details)}")
        
        return True
        
    except GolfCourseAPIError as e:
        print(f"API Error: {str(e)}")
        return False


if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_golf_course_api())