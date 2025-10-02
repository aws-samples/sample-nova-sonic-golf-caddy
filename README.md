# Nova Sonic Golf Assistant

A voice-enabled golf caddy assistant powered by Amazon Nova Sonic and Bedrock Knowledge Base. This sample application demonstrates real-time conversational AI for golfers, featuring weather information, hole-by-hole guidance, and persistent score tracking.

## What This Sample Demonstrates

This sample showcases:

- **Amazon Nova Sonic**: Bidirectional audio streaming for natural voice conversations
- **Bedrock Knowledge Base**: Semantic search over structured golf course data with metadata
- **Tool Use Pattern**: How to implement custom tools that Nova Sonic can call during conversations
- **DynamoDB Integration**: Persistent state management with session resumption, used for player registration and score tracking
- **External API Integration**: Real-time weather data with fallback mechanisms
- **Extensible Architecture**: Modular design with ready-to-use helper modules for expansion

The application is specialized for Sunny Hills Golf Club but includes additional helper modules (`geolocation_helper.py` and `golfcourse_helper.py`) that demonstrate how to extend it for multi-course support and automatic location detection.

## Features

### ✅ Actively Implemented & Used

- **Voice Interaction**: Real-time bidirectional audio streaming with Amazon Nova Sonic
- **Real Weather Information**: Live weather data from Open-Meteo API with golf-specific advice and conditions analysis
- **Hole Information**: Detailed course knowledge powered by Bedrock Knowledge Base with semantic search
- **Player Registration**: Simple voice-based registration with first names and session management
- **Score Tracking**: Persistent DynamoDB-based score and player recording with automatic par lookup from Knowledge Base
- **Round Resumption**: Automatic detection and resumption of interrupted rounds within configurable time window
- **Performance Analytics**: Front nine, back nine, and total round statistics with score-to-par calculations
- **Centralized Configuration**: Global config system with validation and easy customization

### 🔧 Ready to Use (Implemented but Not Integrated)

These features are fully implemented with ready to use code but not currently connected to the voice assistant. They're included as building blocks for extending this sample:

- **Automatic Location Detection** (`geolocation_helper.py`): IP-based geolocation with intelligent caching and fallback support
  - Currently: Weather uses static location from `config.py`
  - Ready: Can auto-detect user location for personalized weather data
  
- **Golf Course Search** (`golfcourse_helper.py`): Comprehensive course database access via Golf Course API
  - Currently: Application is specialized for Sunny Hills Golf Club only
  - Ready: Can potentially provide access to 20,000+ courses worldwide if you have the required level of access to the API, retrieve tee information, and get hole-by-hole data.

### 💡 Extension Ideas

This sample can be extended in many ways. Here are some ideas to inspire your own implementations:

1. **Multi-Course Support**: Integrate `golfcourse_helper` to let users search and get information about any course
2. **Dynamic Location**: Use `geolocation_helper` to automatically detect user location for accurate weather
3. **Course Comparison**: Compare multiple courses using the Golf Course API data
4. **Tee Selection**: Let users choose their tee box and get appropriate yardages
5. **Handicap Tracking**: Extend score tracking to calculate and track player handicaps over time
6. **Playing Partners**: Support multiple players in a round with individual scorecards
7. **Shot Tracking**: Record not just scores but individual shots (driver, approach, putts)
8. **Course Conditions**: Add real-time course condition updates (wet, dry, fast greens)
9. **Tournament Mode**: Support stroke play, match play, and other tournament formats
10. **Historical Analysis**: Query past rounds and provide performance trends

## Prerequisites

- Python 3.13+
- AWS Account with appropriate permissions
- Microphone and speakers for audio interaction
- AWS CLI configured with credentials

## Required Python Packages

All dependencies are listed in `requirements.txt`. Install them with:

```bash
pip install -r requirements.txt
```

## AWS Setup

### 1. Create S3 Bucket for Knowledge Base Data

```bash
# Create an S3 bucket for your golf course documents
aws s3 mb s3://your-golf-course-kb-bucket --region us-east-1

# Upload the sample golf course data from this repository
aws s3 cp sample_moc_data_golf_course/ s3://your-golf-course-kb-bucket/ --recursive
```

#### Understanding the Sample Mock Dataset

The `sample_moc_data_golf_course/` directory contains sample course data that serves as the knowledge source for the Bedrock Knowledge Base:

**File Structure:**
- `sunny_hills_moc_full18.cs_` - CSV file containing detailed information for all 18 holes at Sunny Hills Golf Club
- `sunny_hills_full18.csv.metadata.json` - Bedrock Knowledge Base metadata configuration file that defines how to parse the CSV

**Metadata Configuration (`sunny_hills_full18.csv.metadata.json`):**
This file tells Bedrock Knowledge Base how to structure the CSV data for optimal retrieval:
```json
{
  "documentStructureConfiguration": {
    "type": "RECORD_BASED_STRUCTURE_METADATA",
    "recordBasedStructureMetadata": {
      "contentFields": [{"fieldName": "Content"}],
      "metadataFieldsSpecification": {
        "fieldsToInclude": [
          {"fieldName": "CourseName"},
          {"fieldName": "HoleNumber"},
          {"fieldName": "Par"},
          {"fieldName": "Yardage"},
          {"fieldName": "Handicap"}
        ]
      }
    }
  }
}
```

**Metadata Purpose:**
- `contentFields`: Specifies which CSV column contains the main searchable text (the "Content" field)
- `fieldsToInclude`: Defines structured metadata fields that can be directly accessed for filtering and retrieval
- This structure enables both semantic search on hole descriptions AND direct access to par values for score calculations

**CSV Data Format (`sunny_hills_moc_full18.cs_`):**
```csv
CourseName,HoleNumber,Par,Yardage,Handicap,Content
Sunny Hills Golf Club,1,4,375,7,"Hole 1 — Par 4 — 375 yards — HCP 7. Description: Straight opening hole with a wide fairway, bunkers right of green. Advice: Aim left; beginners use a 3-wood."
```

**Data Fields:**
- `CourseName`: Name of the golf course (Sunny Hills Golf Club)
- `HoleNumber`: Hole number (1-18)
- `Par`: Par value for the hole (3, 4, or 5)
- `Yardage`: Distance in yards from the main tees
- `Handicap`: Hole handicap rating (1-18, where 1 is most difficult)
- `Content`: Rich text description including hole layout, hazards, and strategic advice

**How the Data is Used:**
1. **Knowledge Base Source**: The CSV file is uploaded to S3 and indexed by Bedrock Knowledge Base
2. **Semantic Search**: When users ask about holes, the Knowledge Base performs semantic search on the Content field
3. **Structured Retrieval**: The metadata JSON file enables direct par lookups for score calculations
4. **Voice Responses**: Nova Sonic uses this data to provide detailed hole descriptions and strategic advice

**Customizing for Your Course:**
To adapt this system for a different golf course:
1. Replace the CSV data with your course's hole information
2. Update the `CourseName` field throughout
3. Maintain the same CSV structure for compatibility
4. Update the `GOLF_CLUB_NAME` in `config.py` to match your course name
5. Re-upload to S3 and re-index the Knowledge Base

### 2. Create Bedrock Knowledge Base

#### Step 1: Create the Knowledge Base
1. Navigate to Amazon Bedrock console
2. Go to "Knowledge Bases" in the left sidebar
3. Click "Create knowledge base"

#### Step 2: Configure Knowledge Base Settings
- **Name**: `sunny-hills-golf-kb` (or your preferred name)
- **Description**: `Knowledge base for Sunny Hills Golf Club course information`
- **IAM Role**: Create a new service role or use existing with Bedrock permissions

#### Step 3: Configure Data Source
- **Data source type**: Amazon S3
- **S3 URI**: `s3://your-golf-course-kb-bucket/`
- **Chunking strategy**: Default chunking
- **Chunking configuration**: Use default settings

#### Step 4: Configure Embeddings Model
- **Embeddings model**: Amazon Titan Text Embeddings V2
- **Vector dimensions**: 1024 (default for Titan V2)

#### Step 5: Configure Vector Database
- **Vector database**: Amazon S3 Vectors

#### Step 6: Review and Create
- Review all settings
- Click "Create knowledge base"
- Wait for the knowledge base to be created and indexed

#### Step 7: Note the Knowledge Base ID
After creation, copy the Knowledge Base ID (format: `XXXXXXXXXX`) - you'll need this for configuration.

### 3. Create DynamoDB Table

Create a DynamoDB table for persistent score tracking with the following schema:

**Table Schema:**
- **Primary Key (Partition Key)**: `player_name` (String) - The player's first name
- **Sort Key (Range Key)**: `session_hole` (String) - Format: `{session_id}#hole_{hole_number}` or `{session_id}#metadata`
- **Billing Mode**: On-Demand (recommended for variable usage)

```bash
# Create DynamoDB table with correct schema
aws dynamodb create-table \
    --table-name golf-scores \
    --attribute-definitions \
        AttributeName=player_name,AttributeType=S \
        AttributeName=session_hole,AttributeType=S \
    --key-schema \
        AttributeName=player_name,KeyType=HASH \
        AttributeName=session_hole,KeyType=RANGE \
    --billing-mode ON_DEMAND \
    --region us-east-1

# Note the table ARN from the output - you'll need it for configuration
```

**Important Schema Details:**
- The `session_hole` sort key uses a composite format to store both individual hole scores and round metadata
- Individual hole records: `2024-12-19_ben_round1#hole_03` (for hole 3)
- Round metadata records: `2024-12-19_ben_round1#metadata` (for round summary)
- This design enables efficient querying of all holes in a round and automatic round resumption

### 4. Update Configuration

All configuration is centralized in `config.py`. Edit the following values:

**AWS Configuration:**
```python
# Bedrock Model Configuration for Knowledge Base
MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0'
KNOWLEDGE_BASE_ID = "YOUR_KB_ID_HERE"  # Replace with your actual Knowledge Base ID

# DynamoDB Configuration for Score Tracking
DYNAMODB_TABLE_ARN = "arn:aws:dynamodb:us-east-1:ACCOUNT:table/golf-scores"
```

**Golf Course API Configuration (for extending the sample):**

The Golf Course API helper is implemented but not currently used. If you want to extend this sample to support multi-course search:

```python
# Golf Course API Settings (get your api key from the website)
GOLF_COURSE_API_URL = "https://api.golfcourseapi.com"
GOLF_COURSE_API_KEY = ""  # Get your API key from https://api.golfcourseapi.com
GOLF_COURSE_API_TIMEOUT = 10  # seconds
```

See the "Extension Ideas" section for how to integrate this feature.

**Location Configuration:**
```python
# Default Golf Course Location
COURSE_LOCATION = {
    "name": "Pinehurst, NC",        # Display name for the location
    "latitude": 35.1898,            # Latitude for weather API
    "longitude": -79.4669,          # Longitude for weather API  
    "timezone": "America/New_York"  # Timezone for weather data
}
```

**Application Configuration:**
```python
# Golf Club Name (used in system prompt)
GOLF_CLUB_NAME = "Sunny Hills Golf Club"

# Cache Settings
CACHE_DURATION_HOURS = 4  # Location cache duration

# Audio Settings
INPUT_SAMPLE_RATE = 16000   # Microphone sample rate
OUTPUT_SAMPLE_RATE = 24000  # Speaker sample rate
CHANNELS = 1                # Mono audio
CHUNK_SIZE = 1024          # Audio buffer size
```

**Configuration Validation:**
The application automatically validates your configuration on startup and provides helpful error messages if anything needs to be updated.

### 5. Required AWS Permissions

Ensure your AWS credentials have the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithBidirectionalStream",
                "bedrock-agent-runtime:RetrieveAndGenerate",
                "bedrock-agent-runtime:Retrieve",
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:UpdateItem"
            ],
            "Resource": "*"
        }
    ]
}
```

## Installation

1. **Clone the repository**
```bash
git clone <this-repo-url>
cd nova-sonic-golf
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure AWS credentials**
```bash
aws configure
# Or set environment variables:
# export AWS_ACCESS_KEY_ID=your_access_key
# export AWS_SECRET_ACCESS_KEY=your_secret_key
# export AWS_DEFAULT_REGION=us-east-1
```

4. **Test audio setup**
Ensure your microphone and speakers are working properly.

## Usage

### Basic Usage

```bash
# Run the golf assistant
python nova_sonic_tool_use.py

# Run with debug mode (uses config.py debug flags)
python nova_sonic_tool_use.py --debug
```

### Voice Commands

Once running, you can ask questions like:

**Weather Information:**
- "What's the weather like?"
- "How are the conditions for golf today?"
- "What's the wind doing?"

**Hole Information:**
- "Tell me about hole 8"
- "What's the strategy for hole 13?"
- "How should I play the par 5s?"
- "What are the hazards on hole 3?"

**Player Registration:**
- "I'm Ben"
- "My name is Sarah"
- "Call me Mike"

**Score Tracking:**
- "I got a 4 on hole 3"
- "Record a birdie on hole 7"
- "I shot a 6 on the par 4"
- "What's my current score?"
- "How am I doing on the front nine?"
- "What's my total for the round?"
- "Am I over or under par?"

### Stopping the Application

Press `Enter` in the terminal to stop the audio streaming and exit the application.

## Architecture

```
                    ┌───────────────────────────────────────────────────────────┐
                    │                 Nova Sonic Golf Assistant                 │
                    │                                                           │
┌─────────────────┐ │  ┌──────────────────┐     ┌─────────────────────────────┐ │
│   Microphone    │─┼─>│   Nova Sonic     │───> │      Tool Processor         │ │
│                 │ │  │   (Streaming)    │     │   - Weather Tool            │ │
└─────────────────┘ │  └──────────────────┘     │   - Hole Info Tool          │ │
                    │           │               │   - Golf Course Search Tool │ │
┌─────────────────┐ │           │               │   - Score Recording Tool    │ │
│    Speakers     │<┼───────────┘               │  - Score Status Tool        │ │
│                 │ │                           │   - Player Registration     │ │
└─────────────────┘ │                           └─────────────────────────────┘ │
                    │                                       │                   │
                    └───────────────────────────────────────┼───────────────────┘
                                                            │
                              ┌─────────────────────────────┼─────────────────────────────────┐
                              │                             │                                 │
                              ▼                             ▼                                 ▼
                    ┌─────────────────┐           ┌─────────────────┐           ┌─────────────────┐
                    │ Bedrock KB      │           │   DynamoDB      │           │  Open-Meteo     │
                    │ (Nova Micro)    │           │ Score Tracking  │           │  Weather API    │
                    │                 │           │                 │           │                 │
                    │ • Course Info   │           │ • Player Names  │           │ • Live Weather  │
                    │ • Hole Details  │           │ • Round Scores  │           │ • Golf Advice   │
                    │ • Strategy Tips │           │ • Session Data  │           │ • Conditions    │
                    │ • Hazard Info   │           │ • Round Resume  │           │ • Fallback Data │
                    └─────────────────┘           └─────────────────┘           └─────────────────┘
                              │                             │                                 
                              ▼                             ▼                               
                    ┌─────────────────┐             ┌─────────────────┐             
                    │   Amazon S3     │             │  Session Store  │             
                    │ Golf Course     │             │ Player Registry │             
                    │ Documents       │             │ Round Metadata  │             
                    └─────────────────┘             └─────────────────┘             

                    ┌──────────────────────────────────────────────────────────────┐
                    │         Ready-to-Use Extensions (Not Yet Integrated)         │
                    │                                                              │
                    │  ┌─────────────────┐              ┌─────────────────┐        │
                    │  │ Golf Course API │              │  IP Geolocation │        │
                    │  │ (golfcourseapi) │              │   (ip-api.com)  │        │
                    │  │                 │              │                 │        │
                    │  │ • Course Search │              │ • Auto Location │        │
                    │  │ • Course Details│              │ • City/Region   │        │
                    │  │ • Tee Info      │              │ • Smart Caching │        │
                    │  │ • 20K+ Courses  │              │ • Fallback      │        │
                    │  └─────────────────┘              └─────────────────┘        │
                    │                                                              │
                    │  See "Extension Ideas" section for integration examples      │
                    └──────────────────────────────────────────────────────────────┘
```

## Configuration

### Audio Settings
```python
INPUT_SAMPLE_RATE = 16000   # Microphone sample rate
OUTPUT_SAMPLE_RATE = 24000  # Speaker sample rate
CHANNELS = 1                # Mono audio
CHUNK_SIZE = 1024          # Audio buffer size
```

### Debug Mode
Enable debug logging by running with the single `--debug` command line flag:
```bash
# Clean run - no debug output
python nova_sonic_tool_use.py

# Enable debug output based on config.py settings
python nova_sonic_tool_use.py --debug
```

The debug system uses centralized per-file configuration in `config.py`. When `--debug` is provided, only modules with their debug flags set to `True` in config.py will output debug information.

#### Debug Configuration in config.py

Add the following debug configuration section to your `config.py`:

```python
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
```

#### Debug Usage Examples

```bash
# Example 1: Enable debug for all modules
# Set all debug flags to True in config.py, then run:
python nova_sonic_tool_use.py --debug

# Example 2: Enable debug for specific modules only
# Set only WEATHER_HELPER_DEBUG = True and SCORING_HELPER_DEBUG = True in config.py, then run:
python nova_sonic_tool_use.py --debug

# Example 3: No debug output (default)
# All debug flags False in config.py (or no --debug flag):
python nova_sonic_tool_use.py
```

## Troubleshooting

### Common Issues

1. **Audio not working**
   - Check microphone/speaker permissions
   - Verify PyAudio installation
   - Test with different audio devices

2. **Knowledge Base errors**
   - Verify Knowledge Base ID is correct
   - Check AWS permissions
   - Ensure Knowledge Base is fully indexed

3. **DynamoDB errors**
   - Verify DynamoDB table exists and ARN is correct
   - Check DynamoDB permissions
   - Ensure table has correct schema:
     - Primary Key: `player_name` (String)
     - Sort Key: `session_hole` (String)
     - Billing Mode: On-Demand recommended

4. **Weather API issues**
   - Check internet connectivity
   - Verify Open-Meteo API is accessible
   - Application will fallback to mock data if API fails

5. **AWS credential issues**
   - Verify AWS CLI configuration
   - Check environment variables
   - Ensure proper IAM permissions

### Debug Options

The application uses a single `--debug` flag with granular per-module control via config.py:

```bash
# Clean run - no debug output
python nova_sonic_tool_use.py

# Enable debug output based on config.py debug flags
python nova_sonic_tool_use.py --debug
```

**Debug Configuration:**
- Debug behavior is controlled by per-module flags in `config.py`
- Only modules with `True` debug flags will output debug information when `--debug` is used
- All debug flags default to `False` for quiet operation
- No verbose or dual debug modes - single, simple debug system

## Extending This Sample

This sample includes two fully-implemented helper modules that are ready to use but not currently integrated. They're included to demonstrate best practices and inspire your own extensions.

### Using the Geolocation Helper

The `geolocation_helper.py` module provides automatic location detection with caching. Here's how to integrate it:

**Current Implementation:**
```python
# Weather uses static location from config.py
weather_response = await self.weather_helper.get_golf_weather_advice(location=None)
```

**Extended Implementation:**
```python
# Add a new tool for location detection
async def _run_tool(self, tool_name, tool_content):
    if tool == "getlocationtool":
        # Detect user's location automatically
        location_result = await self.geolocation_helper.get_current_location()
        
        if location_result.get("success"):
            location = location_result["location"]
            # Use detected location for weather
            weather_response = await self.weather_helper.get_golf_weather_advice(
                location_override=location["name"]
            )
            return {
                "location": location["name"],
                "weather": weather_response,
                "detection_method": location_result["source"]
            }
```

**Benefits:**
- Automatic location detection without user input
- Intelligent caching (4-hour default) to avoid repeated API calls
- Graceful fallback to configured location if detection fails
- City-level accuracy sufficient for weather data

### Using the Golf Course Helper

The `golfcourse_helper.py` module provides access to 20,000+ golf courses worldwide. Here's how to integrate it:

**Example Integration:**
```python
# Add a new tool for course search
async def _run_tool(self, tool_name, tool_content):
    if tool == "searchcoursestool":
        content = tool_content.get("content", {})
        content_data = json.loads(content)
        search_query = content_data.get("query", "")
        
        # Search for courses
        courses = await self.golfcourse_helper.search_courses(search_query)
        
        if courses:
            # Get detailed info for first result
            course_id = courses[0].get("id")
            details = await self.golfcourse_helper.get_course_details(course_id)
            
            return {
                "success": True,
                "course_name": details.get("course_name"),
                "location": details.get("location"),
                "tees": details.get("tees"),
                "summary": self.golfcourse_helper.format_course_summary(details)
            }
```

**Use Cases:**
- Multi-course support: Let users switch between courses
- Course discovery: Help users find courses near their location
- Tee selection: Provide yardages for different tee boxes
- Course comparison: Compare difficulty, length, and ratings

**API Key Required:**
Get your free API key from [https://api.golfcourseapi.com](https://api.golfcourseapi.com) and add it to `config.py`.

### Combining Both Helpers

For a powerful extension, combine both helpers:

```python
# 1. Detect user location
location_result = await self.geolocation_helper.get_current_location()

# 2. Search for nearby courses using detected location
if location_result.get("success"):
    city = location_result["location"]["city"]
    courses = await self.golfcourse_helper.search_courses(city)
    
    # 3. Get weather for the detected location
    weather = await self.weather_helper.get_golf_weather_advice(
        location_override=location_result["location"]["name"]
    )
    
    return {
        "your_location": city,
        "nearby_courses": courses,
        "weather_conditions": weather
    }
```

This creates a fully dynamic golf assistant that adapts to any user's location and course preferences.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Support

For issues and questions:
- Check the troubleshooting section
- Review AWS Bedrock documentation
- Open an issue in the repository
## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
