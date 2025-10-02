"""
Global Configuration for Nova Sonic Golf Assistant

Centralized configuration management for all components of the golf assistant.
Update these values to customize the application for your specific setup.
"""

# =============================================================================
# AWS CONFIGURATION
# =============================================================================

# Bedrock Model Configuration for Knowledge Base
MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0'
KNOWLEDGE_BASE_ID = "YOUR_KB_ID_HERE"  # Replace with your actual Knowledge Base ID

# DynamoDB Configuration for Score Tracking
DYNAMODB_TABLE_ARN = "arn:aws:dynamodb:us-east-1:ACCOUNT:table/golf-scores" # Replace with your actual Table ARN

# =============================================================================
# LOCATION CONFIGURATION
# =============================================================================

# Default Golf Course Location
# Update these coordinates to match your actual golf course location
COURSE_LOCATION = {
    "name": "Pinehurst, NC",
    "latitude": 35.1898,
    "longitude": -79.4669,
    "timezone": "America/New_York"
}

# =============================================================================
# WEATHER API CONFIGURATION
# =============================================================================

# Open-Meteo Weather API
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_API_TIMEOUT = 10  # seconds

# =============================================================================
# GOLF COURSE API CONFIGURATION
# =============================================================================

# Golf Course API Settings (get your api key from the website)
GOLF_COURSE_API_URL = "https://api.golfcourseapi.com"
GOLF_COURSE_API_KEY = ""
GOLF_COURSE_API_TIMEOUT = 10  # seconds

# =============================================================================
# GEOLOCATION CONFIGURATION
# =============================================================================

# IP-based Geolocation API
IP_API_URL = "http://ip-api.com/json/"
IP_API_TIMEOUT = 5  # seconds

# Location Cache Settings
CACHE_DURATION_HOURS = 4  # Cache location for 4 hours (typical golf round duration)

# =============================================================================
# AUDIO CONFIGURATION
# =============================================================================

# Audio Stream Settings
INPUT_SAMPLE_RATE = 16000   # Microphone sample rate
OUTPUT_SAMPLE_RATE = 24000  # Speaker sample rate
CHANNELS = 1                # Mono audio
CHUNK_SIZE = 1024          # Audio buffer size

# =============================================================================
# SCORING CONFIGURATION
# =============================================================================

# Round Management Settings
ROUND_RESUME_CONFIG = {
    "max_resume_hours": 4,          # Don't offer resume after 4 hours
    "auto_abandon_hours": 24,       # Auto-mark as abandoned after 24 hours
    "same_day_only": True,          # Only resume rounds from same day
    "max_active_rounds": 2,         # Limit concurrent active rounds
    "ttl_days": 30                  # Auto-delete after 30 days
}

# =============================================================================
# DEBUG CONFIGURATION
# =============================================================================

# Per-file debug flags - set to True to enable debug logging for specific modules
# These flags only take effect when --debug command line argument is provided

NOVA_SONIC_DEBUG = False          # Main application (nova_sonic_tool_use.py)
WEATHER_HELPER_DEBUG = False      # Weather API operations (weather_helper.py)
GEOLOCATION_HELPER_DEBUG = False  # Location detection (geolocation_helper.py)
GOLFCOURSE_HELPER_DEBUG = False   # Golf Course API operations (golfcourse_helper.py)
SCORING_HELPER_DEBUG = False      # Score tracking and DynamoDB (scoring_helper.py)

def get_debug_flags():
    """
    Get all debug flags as a dictionary
    
    Returns:
        dict: Module name to debug flag mapping
    """
    return {
        'nova_sonic_tool_use': NOVA_SONIC_DEBUG,
        'weather_helper': WEATHER_HELPER_DEBUG,
        'geolocation_helper': GEOLOCATION_HELPER_DEBUG,
        'golfcourse_helper': GOLFCOURSE_HELPER_DEBUG,
        'scoring_helper': SCORING_HELPER_DEBUG
    }

def is_debug_enabled(module_name):
    """
    Check if debug is enabled for a specific module
    
    Args:
        module_name: Name of the module (e.g., 'weather_helper')
        
    Returns:
        bool: True if debug is enabled for the module
    """
    debug_flags = get_debug_flags()
    return debug_flags.get(module_name, False)

def validate_debug_config():
    """
    Validate debug configuration and provide helpful error messages
    
    Returns:
        tuple: (is_valid, error_messages)
    """
    errors = []
    debug_flags = get_debug_flags()
    
    # Check that all flags are boolean
    for module_name, flag_value in debug_flags.items():
        if not isinstance(flag_value, bool):
            errors.append(f"Debug flag {module_name.upper()}_DEBUG must be True or False")
    
    return len(errors) == 0, errors

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

# Application Metadata
APP_NAME = "Nova Sonic Golf Assistant"
APP_VERSION = "1.0.0"
GOLF_CLUB_NAME = "Sunny Hills Golf Club"

# System Prompt Configuration
SYSTEM_PROMPT_TEMPLATE = (
    "You are a friendly and knowledgeable golf caddy assistant for {club_name}. "
    "You help golfers with course information, real-time weather conditions, strategic advice, and score tracking for their round. "
    "You know every hole at {club_name} intimately and can provide detailed advice about course strategy, hazards, and club selection. "
    "For weather information, you provide comprehensive golf-specific advice including temperature effects on ball performance, wind strategy, equipment recommendations, and course conditions. "
    "You can also track scores throughout the round - when players mention their score, use the recordScoreTool. You understand golf terminology like birdie (1 under par), eagle (2 under par), bogey (1 over par), and can convert these to actual stroke counts. "
    "When players ask about their performance, use getScoreStatusTool to provide current totals, front nine, back nine, or overall round analysis. "
    "When someone introduces themselves or mentions their name, immediately use registerPlayerTool with their first name to set up score tracking. If they want to track scores but haven't given their name, ask them to introduce themselves first. "
    "Speak in a conversational, supportive tone as if you're walking alongside them on the course. "
    "When mentioning hole numbers, say them clearly, for example 'hole number five' or 'the fifth hole'. "
    "Provide practical, actionable advice that will help improve their game and enjoyment of golf at {club_name}. "
    "Celebrate good scores and offer encouragement for challenging holes."
)

# =============================================================================
# VALIDATION AND HELPERS
# =============================================================================

def validate_config():
    """
    Validate configuration values and provide helpful error messages
    
    Returns:
        tuple: (is_valid, errors, warnings)
            - is_valid: True if all critical configuration is correct
            - errors: List of critical errors that prevent the app from running
            - warnings: List of optional configuration issues (extensions won't work)
    """
    errors = []
    warnings = []
    
    # =========================================================================
    # CRITICAL VALIDATIONS - Required for core functionality
    # =========================================================================
    
    # Check required AWS configuration
    if not KNOWLEDGE_BASE_ID or KNOWLEDGE_BASE_ID == "YOUR_KB_ID_HERE":
        errors.append("KNOWLEDGE_BASE_ID must be set to your actual Bedrock Knowledge Base ID")
    
    if "ACCOUNT" in DYNAMODB_TABLE_ARN:
        errors.append("DYNAMODB_TABLE_ARN must be updated with your actual AWS account ID")
    
    # Check location configuration
    if not isinstance(COURSE_LOCATION.get("latitude"), (int, float)):
        errors.append("COURSE_LOCATION latitude must be a valid number")
    
    if not isinstance(COURSE_LOCATION.get("longitude"), (int, float)):
        errors.append("COURSE_LOCATION longitude must be a valid number")
    
    # Check cache duration
    if CACHE_DURATION_HOURS <= 0:
        errors.append("CACHE_DURATION_HOURS must be greater than 0")
    
    # Validate debug configuration
    debug_flags = get_debug_flags()
    for module_name, flag_value in debug_flags.items():
        if not isinstance(flag_value, bool):
            errors.append(f"Debug flag {module_name.upper()}_DEBUG must be True or False")
    
    # =========================================================================
    # OPTIONAL VALIDATIONS - Only needed for extension features
    # =========================================================================
    
    # Golf Course API (only needed if extending with multi-course support)
    if not GOLF_COURSE_API_KEY or len(GOLF_COURSE_API_KEY) < 10:
        warnings.append("GOLF_COURSE_API_KEY not configured - Golf course search extension unavailable (see README 'Extending This Sample' section)")
    
    if GOLF_COURSE_API_KEY and not GOLF_COURSE_API_URL.startswith("https://"):
        warnings.append("GOLF_COURSE_API_URL should be a valid HTTPS URL")
    
    return len(errors) == 0, errors, warnings

def get_system_prompt():
    """
    Get the formatted system prompt with club name substitution
    
    Returns:
        str: Formatted system prompt
    """
    return SYSTEM_PROMPT_TEMPLATE.format(club_name=GOLF_CLUB_NAME)

def get_config_summary():
    """
    Get a summary of current configuration for debugging
    
    Returns:
        dict: Configuration summary
    """
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "golf_club": GOLF_CLUB_NAME,
        "location": COURSE_LOCATION["name"],
        "knowledge_base_id": KNOWLEDGE_BASE_ID[:10] + "..." if len(KNOWLEDGE_BASE_ID) > 10 else KNOWLEDGE_BASE_ID,
        "cache_duration_hours": CACHE_DURATION_HOURS
    }