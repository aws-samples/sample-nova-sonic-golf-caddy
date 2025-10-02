"""
Weather Helper for Golf Course Assistant

Provides real weather data and golf-specific interpretations.
Golf logic is separated for future migration to Bedrock Knowledge Base.
"""

import asyncio
import aiohttp
import json
import random
import hashlib
import logging
from datetime import datetime
from config import COURSE_LOCATION, WEATHER_API_URL, WEATHER_API_TIMEOUT, is_debug_enabled

# Configure logger
logger = logging.getLogger(__name__)


class GolfWeatherHelper:
    """Handles weather data retrieval and golf-specific interpretations"""
    
    def __init__(self):
        self.location = COURSE_LOCATION
        self.api_url = WEATHER_API_URL
        
        # Configure debug logging based on config.py flag
        self.debug_enabled = is_debug_enabled('weather_helper')
        if self.debug_enabled:
            logger.setLevel(logging.DEBUG)
            logger.debug("WeatherHelper initialized with debug logging enabled")
        else:
            logger.setLevel(logging.WARNING)
    
    async def get_golf_weather_advice(self, location_override=None):
        """
        Get comprehensive golf weather advice
        
        Args:
            location_override: Optional location string to override default
            
        Returns:
            dict: Weather data with golf-specific advice
        """
        location_name = location_override or self.location["name"]
        logger.debug(f"Getting golf weather advice for location: {location_name}")
        
        try:
            # Try to get real weather data
            logger.debug("Attempting to fetch real weather data from API")
            weather_data = await self._fetch_real_weather()
            logger.debug(f"Successfully retrieved real weather data: {weather_data}")
            
            # Add golf-specific interpretations
            logger.debug("Generating golf-specific advice based on weather data")
            golf_advice = self._generate_golf_advice(weather_data)
            
            result = {
                "success": True,
                "location": location_name,
                "weather": weather_data,
                "golfAdvice": golf_advice,
                "source": "real_api"
            }
            logger.debug("Successfully generated golf weather advice from real API data")
            return result
            
        except Exception as e:
            logger.debug(f"Failed to fetch real weather data: {str(e)}, falling back to mock data")
            # Fallback to mock data
            fallback_data = self._generate_fallback_weather(location_override)
            result = {
                "success": True,
                "location": location_name,
                "weather": fallback_data["weather"],
                "golfAdvice": fallback_data["golfAdvice"],
                "source": "fallback",
                "note": "Using simulated weather data"
            }
            logger.debug("Successfully generated golf weather advice from fallback data")
            return result
    
    async def _fetch_real_weather(self):
        """Fetch real weather data from Open-Meteo API"""
        params = {
            "latitude": self.location["latitude"],
            "longitude": self.location["longitude"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,uv_index",
            "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m",
            "timezone": self.location["timezone"],
            "forecast_days": 1,
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph"
        }
        
        logger.debug(f"Making weather API request to {self.api_url} with params: {params}")
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=WEATHER_API_TIMEOUT)) as session:
            async with session.get(self.api_url, params=params) as response:
                logger.debug(f"Weather API response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Raw weather API response: {json.dumps(data, indent=2)}")
                    parsed_data = self._parse_api_response(data)
                    logger.debug(f"Parsed weather data: {parsed_data}")
                    return parsed_data
                else:
                    error_msg = f"API request failed with status {response.status}"
                    logger.debug(error_msg)
                    raise Exception(error_msg)
    
    def _parse_api_response(self, api_data):
        """Parse Open-Meteo API response into standardized format"""
        current = api_data.get("current", {})
        logger.debug(f"Parsing current weather data: {current}")
        
        parsed_data = {
            "temperature": round(current.get("temperature_2m", 70)),
            "humidity": current.get("relative_humidity_2m", 60),
            "windSpeed": round(current.get("wind_speed_10m", 5)),
            "windDirection": self._wind_direction_to_text(current.get("wind_direction_10m", 180)),
            "uvIndex": current.get("uv_index", 5),
            "timestamp": current.get("time", datetime.now().isoformat())
        }
        
        logger.debug(f"Parsed weather data: {parsed_data}")
        return parsed_data
    
    def _wind_direction_to_text(self, degrees):
        """Convert wind direction degrees to text"""
        if degrees is None:
            return "Variable"
        
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = round(degrees / 22.5) % 16
        return directions[index]
    
    def _generate_fallback_weather(self, location_override=None):
        """Generate realistic fallback weather data"""
        location = location_override or self.location["name"]
        logger.debug(f"Generating fallback weather data for location: {location}")
        
        # Generate consistent mock data based on location
        seed = int(hashlib.md5(location.encode(), usedforsecurity=False).hexdigest(), 16) % 10000
        random.seed(seed)
        logger.debug(f"Using seed {seed} for consistent mock data generation")
        
        weather_data = {
            "temperature": random.randint(65, 82),
            "humidity": random.randint(45, 75),
            "windSpeed": random.randint(3, 15),
            "windDirection": random.choice(["N", "NE", "E", "SE", "S", "SW", "W", "NW"]),
            "uvIndex": random.randint(4, 8),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.debug(f"Generated fallback weather data: {weather_data}")
        
        golf_advice = self._generate_golf_advice(weather_data)
        logger.debug("Generated golf advice for fallback weather data")
        
        return {
            "weather": weather_data,
            "golfAdvice": golf_advice
        }
    
    def _generate_golf_advice(self, weather_data):
        """
        Generate golf-specific advice based on weather conditions
        
        This logic is separated for future migration to Bedrock Knowledge Base
        """
        logger.debug(f"Generating golf advice for weather data: {weather_data}")
        
        advice = {
            "overall": "",
            "temperature": "",
            "wind": "",
            "conditions": "",
            "recommendations": []
        }
        
        # Temperature advice
        temp = weather_data["temperature"]
        logger.debug(f"Generating temperature advice for {temp}°F")
        advice["temperature"] = GolfWeatherLogic.get_temperature_advice(temp)
        
        # Wind advice  
        wind_speed = weather_data["windSpeed"]
        wind_direction = weather_data["windDirection"]
        logger.debug(f"Generating wind advice for {wind_speed} mph from {wind_direction}")
        advice["wind"] = GolfWeatherLogic.get_wind_advice(wind_speed, wind_direction)
        
        # UV/Conditions advice
        uv_index = weather_data.get("uvIndex", 5)
        humidity = weather_data.get("humidity", 60)
        logger.debug(f"Generating conditions advice for UV index {uv_index} and humidity {humidity}%")
        advice["conditions"] = GolfWeatherLogic.get_conditions_advice(uv_index, humidity)
        
        # Overall assessment
        logger.debug("Generating overall golf conditions assessment")
        advice["overall"] = GolfWeatherLogic.get_overall_assessment(weather_data)
        
        # Equipment recommendations
        logger.debug("Generating equipment recommendations")
        advice["recommendations"] = GolfWeatherLogic.get_equipment_recommendations(weather_data)
        
        logger.debug(f"Generated complete golf advice: {advice}")
        return advice


class GolfWeatherLogic:
    """
    Separated golf weather logic for future migration to Bedrock Knowledge Base
    
    All methods are static to make KB migration easier
    """
    
    @staticmethod
    def get_temperature_advice(temperature):
        """Temperature-specific golf advice"""
        if temperature < 60:
            return "Cold conditions will reduce ball compression. Consider softer compression balls for better distance. Expect shorter drives and less spin control."
        elif temperature < 70:
            return "Cool but playable conditions. Ball performance will be slightly reduced. Good conditions for accuracy-focused play."
        elif temperature <= 80:
            return "Ideal golf temperature! Ball compression and performance are optimal. Perfect conditions for your best game."
        elif temperature <= 90:
            return "Warm conditions will increase ball compression for longer drives. Expect firmer, faster greens with more roll and less stopping power."
        else:
            return "Hot conditions - stay hydrated! Expect maximum ball distance but very firm, fast greens. Consider early morning or late afternoon play."
    
    @staticmethod
    def get_wind_advice(wind_speed, wind_direction):
        """Wind-specific golf advice"""
        if wind_speed <= 5:
            return f"Light breeze from the {wind_direction} - excellent conditions for accuracy and putting. Perfect day for working on your short game."
        elif wind_speed <= 12:
            return f"Moderate {wind_speed} mph wind from the {wind_direction}. Adjust club selection and aim accordingly. Focus on lower ball flight for better control."
        elif wind_speed <= 20:
            return f"Strong {wind_speed} mph wind from the {wind_direction}. Expect significant ball movement. Use one club up/down for headwind/tailwind. Grip control is crucial."
        else:
            return f"Very strong {wind_speed} mph wind from the {wind_direction}. Challenging conditions! Focus on course management and conservative play. Consider postponing if possible."
    
    @staticmethod
    def get_conditions_advice(uv_index, humidity):
        """UV and humidity advice"""
        advice_parts = []
        
        # UV advice
        if uv_index <= 2:
            advice_parts.append("Low UV - minimal sun protection needed.")
        elif uv_index <= 5:
            advice_parts.append("Moderate UV - consider sunscreen and a hat.")
        elif uv_index <= 7:
            advice_parts.append("High UV - sunscreen and protective clothing recommended.")
        else:
            advice_parts.append("Very high UV - essential to use strong sunscreen, hat, and seek shade when possible.")
        
        # Humidity advice
        if humidity < 40:
            advice_parts.append("Low humidity means firmer conditions and more ball roll.")
        elif humidity > 70:
            advice_parts.append("High humidity will make greens softer and more receptive to shots.")
        
        return " ".join(advice_parts)
    
    @staticmethod
    def get_overall_assessment(weather_data):
        """Overall golf conditions assessment"""
        temp = weather_data.get("temperature", 70)
        wind = weather_data.get("windSpeed", 5)
        
        # Calculate playability score
        score = 10
        
        # Temperature penalties
        if temp < 50 or temp > 95:
            score -= 3
        elif temp < 60 or temp > 85:
            score -= 1
        
        # Wind penalties
        if wind > 20:
            score -= 3
        elif wind > 12:
            score -= 1
        
        # Generate assessment
        if score >= 9:
            return "Excellent golf conditions! Perfect day to be on the course."
        elif score >= 7:
            return "Very good conditions with minor challenges. Great day for golf!"
        elif score >= 5:
            return "Good playable conditions. Some adjustments needed but enjoyable round expected."
        elif score >= 3:
            return "Challenging but manageable conditions. Focus on course management."
        else:
            return "Difficult conditions. Consider if you want to proceed or wait for better weather."
    
    @staticmethod
    def get_equipment_recommendations(weather_data):
        """Equipment and strategy recommendations"""
        recommendations = []
        
        temp = weather_data.get("temperature", 70)
        wind = weather_data.get("windSpeed", 5)
        humidity = weather_data.get("humidity", 60)
        
        # Temperature-based recommendations
        if temp < 60:
            recommendations.append("Bring extra layers and consider softer compression balls")
        elif temp > 85:
            recommendations.append("Bring plenty of water and electrolyte drinks")
        
        # Wind recommendations
        if wind > 12:
            recommendations.append("Focus on grip control and consider rain gloves for better hold")
            recommendations.append("Practice low ball flight shots on the range")
        
        # Humidity recommendations
        if humidity > 70:
            recommendations.append("Expect softer greens - be more aggressive with approach shots")
        elif humidity < 40:
            recommendations.append("Expect firm conditions - plan for extra roll on drives and approaches")
        
        return recommendations