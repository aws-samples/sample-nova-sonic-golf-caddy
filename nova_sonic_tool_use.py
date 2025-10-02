import os
import asyncio
import base64
import json
import uuid
import warnings
import pyaudio
import pytz
import random
import hashlib
import datetime
import time
import inspect
import csv
import logging
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver

# Import global configuration
from config import (
    MODEL_ARN, KNOWLEDGE_BASE_ID, DYNAMODB_TABLE_ARN,
    INPUT_SAMPLE_RATE, OUTPUT_SAMPLE_RATE, CHANNELS, CHUNK_SIZE,
    get_system_prompt, validate_config, get_config_summary, is_debug_enabled
)

# Import weather helper
from weather_helper import GolfWeatherHelper

# Import geolocation helper
from geolocation_helper import GeolocationHelper

# Import golf course helper
from golfcourse_helper import GolfCourseHelper

# Import scoring helper
from scoring_helper import ScoringHelper

# Import for Bedrock Agent Runtime (Knowledge Base)
try:
    import boto3
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    print("Warning: boto3 not available. Knowledge Base functionality will be disabled.")

# Suppress warnings
warnings.filterwarnings("ignore")

# Audio format configuration
FORMAT = pyaudio.paInt16

# Set up logger for this module
logger = logging.getLogger(__name__)

# Configure debug logging based on config.py flag
if is_debug_enabled('nova_sonic_tool_use'):
    logger.setLevel(logging.DEBUG)
    logger.debug("Nova Sonic main application initialized with debug logging enabled")
else:
    logger.setLevel(logging.WARNING)

def time_it(label, methodToRun):
    start_time = time.perf_counter()
    result = methodToRun()
    end_time = time.perf_counter()
    logger.debug(f"Execution time for {label}: {end_time - start_time:.4f} seconds")
    return result

async def time_it_async(label, methodToRun):
    start_time = time.perf_counter()
    result = await methodToRun()
    end_time = time.perf_counter()
    logger.debug(f"Execution time for {label}: {end_time - start_time:.4f} seconds")
    return result

class ToolProcessor:
    def __init__(self, region='us-east-1'):
        # ThreadPoolExecutor could be used for complex implementations
        self.tasks = {}
        self.region = region
        
        # Initialize Bedrock Agent Runtime client for Knowledge Base
        self.knowledge_base_id = KNOWLEDGE_BASE_ID
        self.bedrock_agent_client = None
        if BOTO3_AVAILABLE:
            self._initialize_knowledge_base_client()
        
        # Score tracking
        self.scorecard = {}  # {hole_number: {'strokes': int, 'par': int, 'score_to_par': int}}
        self.course_par = {}  # {hole_number: par_value}
        self.par_loaded = False
        self.round_start_time = None
        
        # Initialize helpers - they will read debug flags from config.py
        self.weather_helper = GolfWeatherHelper()
        self.geolocation_helper = GeolocationHelper()
        self.golfcourse_helper = GolfCourseHelper()
        self.scoring_helper = ScoringHelper(table_arn=DYNAMODB_TABLE_ARN)
        
        # MULTI-LAYER FALLBACK SYSTEM FOR NAME DETECTION
        # Layer 3: Session Storage - stores player name in memory for persistence
        # This ensures the name persists throughout the conversation even if Nova Sonic
        # doesn't call registerPlayerTool consistently
        self.session_player_name = None
    
    def _extract_name_from_text(self, text):
        """
        LAYER 2: Regex Name Extraction (Fallback)
        
        Extract first name from common introduction patterns when Nova Sonic
        fails to call registerPlayerTool. This is a backup mechanism to ensure
        name detection works even when the primary tool calling is inconsistent.
        
        Problem: Nova Sonic sometimes responds conversationally to "my name is benjamin"
        without calling registerPlayerTool, causing score tracking to fail.
        
        Solution: Automatically scan user text for name patterns and extract names
        using regex, then store them for later use in scoring tools.
        """
        import re
        text_lower = text.lower()
        
        # Common patterns for name introduction that users might say
        patterns = [
            r"my name is (\w+)",      # "my name is benjamin"
            r"i'm (\w+)",             # "i'm sarah"
            r"i am (\w+)",            # "i am mike"
            r"call me (\w+)",         # "call me john"
            r"name's (\w+)"           # "name's alex"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).capitalize()
                logger.debug(f"FALLBACK: Extracted name from text: {name}")
                return name
        
        return None
    
    def _initialize_knowledge_base_client(self):
        """Initialize the Bedrock Agent Runtime client for Knowledge Base operations"""
        try:
            self.bedrock_agent_client = boto3.client(
                'bedrock-agent-runtime',
                region_name=self.region
            )
            logger.debug("Knowledge Base client initialized successfully")
        except Exception as e:
            logger.debug(f"Failed to initialize Knowledge Base client: {e}")
            self.bedrock_agent_client = None
    
    async def process_tool_async(self, tool_name, tool_content):
        """Process a tool call asynchronously and return the result"""
        # Create a unique task ID
        task_id = str(uuid.uuid4())
        
        # Create and store the task
        task = asyncio.create_task(self._run_tool(tool_name, tool_content))
        self.tasks[task_id] = task
        
        try:
            # Wait for the task to complete
            result = await task
            return result
        finally:
            # Clean up the task reference
            if task_id in self.tasks:
                del self.tasks[task_id]
    
    async def _run_tool(self, tool_name, tool_content):
        """Internal method to execute the tool logic"""
        logger.debug(f"*** TOOL CALLED: {tool_name}")
        tool = tool_name.lower()
        
        if tool == "getweathertool":
            # Get real weather data with golf-specific advice
            content = tool_content.get("content", {})
            content_data = json.loads(content)
            location = content_data.get("location", None)
            
            # Get comprehensive weather advice
            weather_response = await self.weather_helper.get_golf_weather_advice(location)
            
            # Debug output for weather data
            logger.debug(f"Weather API Response: {json.dumps(weather_response, indent=2)}")
            
            return weather_response
        
        elif tool == "getholeinformationtool":
            # Get hole information using Bedrock Knowledge Base
            logger.debug(f"GetHoleInformationTool starting operation...")
            
            # Extract parameters from toolUseContent
            content = tool_content.get("content", {})
            content_data = json.loads(content)
            hole_number = content_data.get("holeNumber", 1)
            
            # Validate hole number
            if not isinstance(hole_number, int) or hole_number < 1 or hole_number > 18:
                return {
                    "error": "Invalid hole number. Please specify a hole between 1 and 18."
                }
            
            # Query Knowledge Base for hole information
            kb_response = await self._query_knowledge_base_for_hole(hole_number)
            
            if kb_response and kb_response.get("success"):
                hole_info = {
                    "holeNumber": hole_number,
                    "response": kb_response.get("response", ""),
                    "sources": kb_response.get("sources", []),
                    "sessionId": kb_response.get("sessionId", "")
                }
            else:
                hole_info = {
                    "error": f"Unable to retrieve information for hole {hole_number}.",
                    "details": kb_response.get("error", "Knowledge Base query failed") if kb_response else "Knowledge Base client not available"
                }
            
            return hole_info
        
        elif tool == "recordscoretool":
            # Record a golf score for a specific hole using DynamoDB
            logger.debug(f"RecordScoreTool: current_player = {self.scoring_helper.current_player if self.scoring_helper else 'None'}")
            logger.debug(f"RecordScoreTool: current_session_id = {self.scoring_helper.current_session_id if self.scoring_helper else 'None'}")
            
            # Check if player is registered and scoring helper is available
            if not self.scoring_helper or not self.scoring_helper.current_player:
                # Try to use session player name if available
                if self.session_player_name:
                    logger.debug(f"RecordScoreTool: Using session player name: {self.session_player_name}")
                    reg_result = await self.scoring_helper.register_player(self.session_player_name)
                    logger.debug(f"RecordScoreTool: Re-registration result: {reg_result}")
                    if not reg_result.get("success"):
                        return {"error": "Please introduce yourself first by saying your name (e.g., 'I'm Ben')"}
                else:
                    return {"error": "Please introduce yourself first by saying your name (e.g., 'I'm Ben')"}
            
            # Ensure we have an active session
            if not self.scoring_helper.current_session_id:
                logger.debug("No active session, starting new round...")
                start_result = await self.scoring_helper.start_new_round()
                logger.debug(f"Start round result: {start_result}")
                if not start_result["success"]:
                    return {"error": f"Failed to start round: {start_result.get('error')}"}
            
            # Ensure pars are loaded
            pars_loaded = await self._load_all_course_pars()
            if not pars_loaded:
                return {"error": "Unable to load course par information from Knowledge Base. Score tracking is not available."}
            
            # Extract parameters from toolUseContent
            content = tool_content.get("content", {})
            content_data = json.loads(content)
            hole_number = content_data.get("holeNumber")
            strokes = content_data.get("strokes")
            
            logger.debug(f"RecordScoreTool: hole_number = {hole_number}, strokes = {strokes}")
            
            # Validate inputs
            if not isinstance(hole_number, int) or hole_number < 1 or hole_number > 18:
                return {"error": "Invalid hole number. Please specify a hole between 1 and 18."}
            
            if not isinstance(strokes, int) or strokes < 1 or strokes > 15:
                return {"error": "Invalid stroke count. Please specify between 1 and 15 strokes."}
            
            # Get par for this hole
            hole_par = self.course_par.get(hole_number)
            if hole_par is None:
                return {"error": f"Par information not available for hole {hole_number}."}
            
            logger.debug(f"RecordScoreTool: hole_par = {hole_par}")
            
            # Record the score using DynamoDB helper
            score_result = await self.scoring_helper.record_score(hole_number, strokes, hole_par)
            logger.debug(f"RecordScoreTool: score_result = {score_result}")
            
            return score_result
        
        elif tool == "getscorestatustool":
            # Get current score status and analysis from DynamoDB
            logger.debug("GetScoreStatusTool: Starting...")
            logger.debug(f"GetScoreStatusTool: current_player = {self.scoring_helper.current_player if self.scoring_helper else 'None'}")
            logger.debug(f"GetScoreStatusTool: current_session_id = {self.scoring_helper.current_session_id if self.scoring_helper else 'None'}")
            
            # Check if player is registered
            if not self.scoring_helper or not self.scoring_helper.current_player:
                # Try to use session player name if available
                if self.session_player_name:
                    logger.debug(f"GetScoreStatusTool: Using session player name: {self.session_player_name}")
                    reg_result = await self.scoring_helper.register_player(self.session_player_name)
                    if not reg_result.get("success"):
                        logger.debug("GetScoreStatusTool: Failed to re-register player")
                        return {"error": "Please tell me your first name first. Say something like 'I'm Ben'"}
                else:
                    logger.debug("GetScoreStatusTool: No player registered")
                    return {"error": "Please tell me your first name first. Say something like 'I'm Ben'"}
            
            # Check if there's an active session
            if not self.scoring_helper.current_session_id:
                logger.debug("GetScoreStatusTool: No active session")
                return {"message": "No scores recorded yet. Start by recording a score for any hole!"}
            
            # Extract parameters for specific queries
            content = tool_content.get("content", {})
            content_data = json.loads(content)
            query = content_data.get("query", "current").lower()
            logger.debug(f"GetScoreStatusTool: query = {query}")
            
            # Get round summary from DynamoDB
            logger.debug("GetScoreStatusTool: Getting round summary...")
            try:
                summary = await self.scoring_helper.get_round_summary()
                logger.debug(f"GetScoreStatusTool: summary result = {summary}")
            except Exception as e:
                logger.debug(f"GetScoreStatusTool: Error getting summary: {str(e)}")
                return {"error": f"Failed to get score status: {str(e)}"}
            
            if not summary.get("success"):
                logger.debug(f"GetScoreStatusTool: Summary failed: {summary.get('error')}")
                return {"error": f"Failed to get score status: {summary.get('error')}"}
            
            if summary.get("holes_played", 0) == 0:
                logger.debug("GetScoreStatusTool: No holes played")
                return {"message": "No scores recorded yet. Start by recording a score for any hole!"}
            
            logger.debug(f"GetScoreStatusTool: Processing query '{query}' with {summary['holes_played']} holes played")
            
            if query in ["current", "total", "overall"]:
                result = {
                    "player": summary["player"],
                    "session": summary["session_id"],
                    "totalStrokes": summary["total_strokes"],
                    "totalPar": summary["total_par"],
                    "scoreTopar": summary["score_to_par"],
                    "parStatus": summary["par_status"],
                    "holesPlayed": summary["holes_played"],
                    "message": f"After {summary['holes_played']} holes: {summary['total_strokes']} strokes, {summary['par_status']}"
                }
                logger.debug(f"GetScoreStatusTool: Returning current/total result: {result}")
                return result
            
            elif query in ["front9", "front", "front_nine"]:
                logger.debug("GetScoreStatusTool: Processing front nine query")
                # Calculate front nine from holes data
                front_nine_holes = [h for h in summary["holes"] if h["hole_number"] <= 9]
                logger.debug(f"GetScoreStatusTool: Found {len(front_nine_holes)} front nine holes")
                
                if not front_nine_holes:
                    return {"message": "No scores recorded for the front nine yet."}
                
                front_strokes = sum(h["strokes"] for h in front_nine_holes)
                front_par = sum(h["par"] for h in front_nine_holes)
                front_score_to_par = front_strokes - front_par
                front_par_status = "even par" if front_score_to_par == 0 else f"{abs(front_score_to_par)} {'under' if front_score_to_par < 0 else 'over'} par"
                
                result = {
                    "frontNineStrokes": front_strokes,
                    "frontNinePar": front_par,
                    "frontNineTopar": front_score_to_par,
                    "holesPlayed": len(front_nine_holes),
                    "message": f"Front nine: {front_strokes} strokes ({len(front_nine_holes)} holes played), {front_par_status}"
                }
                logger.debug(f"GetScoreStatusTool: Returning front nine result: {result}")
                return result
            
            elif query in ["back9", "back", "back_nine"]:
                logger.debug("GetScoreStatusTool: Processing back nine query")
                # Calculate back nine from holes data
                back_nine_holes = [h for h in summary["holes"] if h["hole_number"] >= 10]
                logger.debug(f"GetScoreStatusTool: Found {len(back_nine_holes)} back nine holes")
                
                if not back_nine_holes:
                    return {"message": "No scores recorded for the back nine yet."}
                
                back_strokes = sum(h["strokes"] for h in back_nine_holes)
                back_par = sum(h["par"] for h in back_nine_holes)
                back_score_to_par = back_strokes - back_par
                back_par_status = "even par" if back_score_to_par == 0 else f"{abs(back_score_to_par)} {'under' if back_score_to_par < 0 else 'over'} par"
                
                result = {
                    "backNineStrokes": back_strokes,
                    "backNinePar": back_par,
                    "backNineTopar": back_score_to_par,
                    "holesPlayed": len(back_nine_holes),
                    "message": f"Back nine: {back_strokes} strokes ({len(back_nine_holes)} holes played), {back_par_status}"
                }
                logger.debug(f"GetScoreStatusTool: Returning back nine result: {result}")
                return result
            
            else:
                logger.debug(f"GetScoreStatusTool: Invalid query: {query}")
                return {"error": "Invalid query. Use 'current', 'front9', 'back9', or 'total'."}
        
        elif tool == "registerplayertool":
            # Register a player by their first name
            content = tool_content.get("content", {})
            content_data = json.loads(content)
            first_name = content_data.get("firstName", "")
            
            if not first_name:
                return {"error": "First name is required for registration"}
            
            # Register the player
            registration_result = await self.scoring_helper.register_player(first_name)
            
            # If registration successful, store the player name in session
            if registration_result.get("success"):
                self.session_player_name = first_name.strip().capitalize()
                logger.debug(f"Stored session player name: {self.session_player_name}")
                
                if registration_result.get("action") == "start_new":
                    start_result = await self.scoring_helper.start_new_round()
                    if start_result.get("success"):
                        registration_result["session_started"] = True
                        registration_result["session_id"] = start_result["session_id"]
                    else:
                        registration_result["session_error"] = start_result.get("error")
                elif registration_result.get("action") == "resumed":
                    # Session already resumed automatically
                    logger.debug(f"Session automatically resumed: {registration_result.get('session_id')}")
            
            return registration_result
        
        else:
            return {
                "error": f"Unsupported tool: {tool_name}"
            }
    
    async def _query_knowledge_base_for_hole(self, hole_number):
        """Query the Bedrock Knowledge Base for hole information"""
        if not self.bedrock_agent_client:
            return {"success": False, "error": "Knowledge Base client not initialized"}
        
        try:
            # Create a query for the specific hole
            query = f"Tell me about hole {hole_number} at Sunny Hills Golf Club. Include details about the hole layout, hazards, strategy, and any tips for playing this hole."
            
            logger.debug(f"Querying Knowledge Base for hole {hole_number}")
            
            # Use retrieve_and_generate API
            response = self.bedrock_agent_client.retrieve_and_generate(
                input={
                    'text': query
                },
                retrieveAndGenerateConfiguration={
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'knowledgeBaseId': self.knowledge_base_id,
                        'modelArn': MODEL_ARN
                    }
                }
            )
            
            # Extract the response
            generated_text = response.get('output', {}).get('text', '')
            citations = response.get('citations', [])
            
            # Extract source information from citations
            sources = []
            for citation in citations:
                for reference in citation.get('retrievedReferences', []):
                    location = reference.get('location', {})
                    source_info = {
                        'type': location.get('type', ''),
                        's3Location': location.get('s3Location', {}),
                        'content': reference.get('content', {}).get('text', '')[:200] + '...' if reference.get('content', {}).get('text', '') else ''
                    }
                    sources.append(source_info)
            
            logger.debug(f"Knowledge Base query successful for hole {hole_number}")
            
            return {
                "success": True,
                "response": generated_text,
                "sources": sources,
                "sessionId": response.get('sessionId', '')
            }
            
        except Exception as e:
            logger.debug(f"Knowledge Base query failed for hole {hole_number}: {str(e)}")
            return {
                "success": False,
                "error": f"Knowledge Base query failed: {str(e)}"
            }
    
    async def _load_all_course_pars(self):
        """Load par information using structured metadata from Knowledge Base"""
        if self.par_loaded:
            return True
        
        if not self.bedrock_agent_client:
            return False
        
        try:
            # Use retrieve API to get structured data with metadata
            response = self.bedrock_agent_client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={'text': 'golf course holes par information'},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': 18  # Get all holes
                    }
                }
            )
            
            # Extract par values directly from metadata
            for result in response.get('retrievalResults', []):
                metadata = result.get('metadata', {})
                hole_number = metadata.get('HoleNumber')
                par_value = metadata.get('Par')
                
                if hole_number and par_value:
                    try:
                        hole_int = int(hole_number)
                        par_int = int(par_value)
                        self.course_par[hole_int] = par_int
                    except (ValueError, TypeError):
                        continue
            
            if len(self.course_par) == 18:
                self.par_loaded = True
                return True
            else:
                return False
            
        except Exception:
            return False
    

    def _calculate_score_to_par(self, strokes, par):
        """Calculate score relative to par"""
        diff = strokes - par
        if diff == -2:
            return "eagle"
        elif diff == -1:
            return "birdie"
        elif diff == 0:
            return "par"
        elif diff == 1:
            return "bogey"
        elif diff == 2:
            return "double bogey"
        else:
            return f"{abs(diff)} {'under' if diff < 0 else 'over'} par"
    
    def _calculate_total_score(self):
        """Calculate total strokes and score to par"""
        total_strokes = sum(hole['strokes'] for hole in self.scorecard.values())
        total_par = sum(hole['par'] for hole in self.scorecard.values())
        holes_played = len(self.scorecard)
        
        return {
            'total_strokes': total_strokes,
            'total_par': total_par,
            'score_to_par': total_strokes - total_par,
            'holes_played': holes_played
        }
    
    def _get_nine_score(self, front_nine=True):
        """Calculate score for front 9 (holes 1-9) or back 9 (holes 10-18)"""
        holes = range(1, 10) if front_nine else range(10, 19)
        played_holes = {h: self.scorecard[h] for h in holes if h in self.scorecard}
        
        if not played_holes:
            return None
            
        total_strokes = sum(hole['strokes'] for hole in played_holes.values())
        total_par = sum(hole['par'] for hole in played_holes.values())
        
        return {
            'strokes': total_strokes,
            'par': total_par,
            'score_to_par': total_strokes - total_par,
            'holes_played': len(played_holes)
        }
    

class BedrockStreamManager:
    """Manages bidirectional streaming with AWS Bedrock using asyncio"""
    
    # Event templates
    START_SESSION_EVENT = '''{
        "event": {
            "sessionStart": {
            "inferenceConfiguration": {
                "maxTokens": 1024,
                "topP": 0.9,
                "temperature": 0.7
                }
            }
        }
    }'''

    CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
            "promptName": "%s",
            "contentName": "%s",
            "type": "AUDIO",
            "interactive": true,
            "role": "USER",
            "audioInputConfiguration": {
                "mediaType": "audio/lpcm",
                "sampleRateHertz": 16000,
                "sampleSizeBits": 16,
                "channelCount": 1,
                "audioType": "SPEECH",
                "encoding": "base64"
                }
            }
        }
    }'''

    AUDIO_EVENT_TEMPLATE = '''{
        "event": {
            "audioInput": {
            "promptName": "%s",
            "contentName": "%s",
            "content": "%s"
            }
        }
    }'''

    TEXT_CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
            "promptName": "%s",
            "contentName": "%s",
            "type": "TEXT",
            "role": "%s",
            "interactive": false,
                "textInputConfiguration": {
                    "mediaType": "text/plain"
                }
            }
        }
    }'''

    TEXT_INPUT_EVENT = '''{
        "event": {
            "textInput": {
            "promptName": "%s",
            "contentName": "%s",
            "content": "%s"
            }
        }
    }'''

    TOOL_CONTENT_START_EVENT = '''{
        "event": {
            "contentStart": {
                "promptName": "%s",
                "contentName": "%s",
                "interactive": false,
                "type": "TOOL",
                "role": "TOOL",
                "toolResultInputConfiguration": {
                    "toolUseId": "%s",
                    "type": "TEXT",
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        }
    }'''

    CONTENT_END_EVENT = '''{
        "event": {
            "contentEnd": {
            "promptName": "%s",
            "contentName": "%s"
            }
        }
    }'''

    PROMPT_END_EVENT = '''{
        "event": {
            "promptEnd": {
            "promptName": "%s"
            }
        }
    }'''

    SESSION_END_EVENT = '''{
        "event": {
            "sessionEnd": {}
        }
    }'''
    
    def start_prompt(self):
        """Create a promptStart event"""
        get_weather_schema = json.dumps({
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location to get weather information for (defaults to golf course if not specified)",
                    "default": "golf course"
                }
            },
            "required": []
        })

        get_hole_information_schema = json.dumps({
            "type": "object",
            "properties": {
                "holeNumber": {
                    "type": "integer",
                    "description": "The hole number to get information for (1-18)",
                    "minimum": 1,
                    "maximum": 18
                }
            },
            "required": ["holeNumber"]
        })

        record_score_schema = json.dumps({
            "type": "object",
            "properties": {
                "holeNumber": {
                    "type": "integer",
                    "description": "The hole number (1-18)",
                    "minimum": 1,
                    "maximum": 18
                },
                "strokes": {
                    "type": "integer",
                    "description": "Number of strokes taken on this hole",
                    "minimum": 1,
                    "maximum": 15
                }
            },
            "required": ["holeNumber", "strokes"]
        })

        get_score_status_schema = json.dumps({
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What score information to retrieve: 'current' (total score), 'front9', 'back9', or 'total'",
                    "enum": ["current", "total", "front9", "back9", "overall"]
                }
            },
            "required": []
        })

        register_player_schema = json.dumps({
            "type": "object",
            "properties": {
                "firstName": {
                    "type": "string",
                    "description": "The player's first name"
                }
            },
            "required": ["firstName"]
        })

        
        prompt_start_event = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    },
                    "toolUseOutputConfiguration": {
                        "mediaType": "application/json"
                    },
                    "toolConfiguration": {
                        "tools": [
                            {
                                "toolSpec": {
                                    "name": "getWeatherTool",
                                    "description": "Get current weather conditions and forecast for the golf course or specified location. Provides temperature, wind conditions, and golf-specific weather advice.",
                                    "inputSchema": {
                                        "json": get_weather_schema
                                    }
                                }
                            },
                            {
                                "toolSpec": {
                                    "name": "getHoleInformationTool",
                                    "description": "Get detailed information about a specific golf hole including par, distance, hazards, green conditions, and club recommendations. Use this when players ask about hole strategy or course layout.",
                                    "inputSchema": {
                                    "json": get_hole_information_schema
                                    }
                                }
                            },
                            {
                                "toolSpec": {
                                    "name": "recordScoreTool",
                                    "description": "Record a golf score for a specific hole. Use this when players mention their score, strokes taken, or golf terms like birdie, eagle, bogey. Convert golf terms to actual stroke counts based on par.",
                                    "inputSchema": {
                                        "json": record_score_schema
                                    }
                                }
                            },
                            {
                                "toolSpec": {
                                    "name": "getScoreStatusTool",
                                    "description": "Get current scoring status, total score, or performance analysis. Use when players ask about their score, how they're doing, front/back nine performance, or overall round status.",
                                    "inputSchema": {
                                        "json": get_score_status_schema
                                    }
                                }
                            },
                            {
                                "toolSpec": {
                                    "name": "registerPlayerTool",
                                    "description": "Register a player by their first name when they introduce themselves for score tracking purposes (e.g., 'I'm Ben', 'My name is Sarah', 'Call me Mike'). Use this when someone provides their name in the context of wanting to track scores.",
                                    "inputSchema": {
                                        "json": register_player_schema
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }
        
        return json.dumps(prompt_start_event)
    
    def tool_result_event(self, content_name, content, role):
        """Create a tool result event"""

        if isinstance(content, dict):
            content_json_string = json.dumps(content)
        else:
            content_json_string = content
            
        tool_result_event = {
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": content_json_string
                }
            }
        }
        return json.dumps(tool_result_event)
   
    def __init__(self, model_id='amazon.nova-sonic-v1:0', region='us-east-1'):
        """Initialize the stream manager."""
        self.model_id = model_id
        self.region = region
        
        # Replace RxPy subjects with asyncio queues
        self.audio_input_queue = asyncio.Queue()
        self.audio_output_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()
        
        self.response_task = None
        self.stream_response = None
        self.is_active = False
        self.barge_in = False
        self.bedrock_client = None
        
        # Audio playback components
        self.audio_player = None
        
        # Text response components
        self.display_assistant_text = False
        self.role = None

        # Session information
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""

        # Add a tool processor
        self.tool_processor = ToolProcessor(region=self.region)
        
        # Add tracking for in-progress tool calls
        self.pending_tool_tasks = {}

    def _initialize_client(self):
        """Initialize the Bedrock client."""
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
            http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()}
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)
    
    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        if not self.bedrock_client:
            self._initialize_client()
        
        try:
            self.stream_response = await time_it_async("invoke_model_with_bidirectional_stream", lambda : self.bedrock_client.invoke_model_with_bidirectional_stream( InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)))
            self.is_active = True
            default_system_prompt = get_system_prompt()
            
            # Send initialization events
            prompt_event = self.start_prompt()
            text_content_start = self.TEXT_CONTENT_START_EVENT % (self.prompt_name, self.content_name, "SYSTEM")
            text_content = self.TEXT_INPUT_EVENT % (self.prompt_name, self.content_name, default_system_prompt)
            text_content_end = self.CONTENT_END_EVENT % (self.prompt_name, self.content_name)
            
            init_events = [self.START_SESSION_EVENT, prompt_event, text_content_start, text_content, text_content_end]
            
            for event in init_events:
                await self.send_raw_event(event)
                # Small delay between init events
                await asyncio.sleep(0.1)
            
            # Start listening for responses
            self.response_task = asyncio.create_task(self._process_responses())
            
            # Start processing audio input
            asyncio.create_task(self._process_audio_input())
            
            # Wait a bit to ensure everything is set up
            await asyncio.sleep(0.1)
            
            logger.debug("Stream initialized successfully")
            return self
        except Exception as e:
            self.is_active = False
            print(f"Failed to initialize stream: {str(e)}")
            raise
    
    async def send_raw_event(self, event_json):
        """Send a raw event JSON to the Bedrock stream."""
        if not self.stream_response or not self.is_active:
            logger.debug("Stream not initialized or closed")
            return
       
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        
        try:
            await self.stream_response.input_stream.send(event)
            # Only log non-audio events to avoid flooding
            if len(event_json) > 200:
                event_type = json.loads(event_json).get("event", {}).keys()
                event_type_list = list(event_type)
                # Skip logging audioInput events as they flood the screen
                if 'audioInput' not in event_type_list:
                    logger.debug(f"Sent event type: {event_type_list}")
            else:
                # Skip logging audio events
                if '"audioInput"' not in event_json:
                    logger.debug(f"Sent event: {event_json}")
        except Exception as e:
            logger.debug(f"Error sending event: {str(e)}")
            if DEBUG:
                import traceback
                traceback.print_exc()
    
    async def send_audio_content_start_event(self):
        """Send a content start event to the Bedrock stream."""
        content_start_event = self.CONTENT_START_EVENT % (self.prompt_name, self.audio_content_name)
        await self.send_raw_event(content_start_event)
    
    async def _process_audio_input(self):
        """Process audio input from the queue and send to Bedrock."""
        while self.is_active:
            try:
                # Get audio data from the queue
                data = await self.audio_input_queue.get()
                
                audio_bytes = data.get('audio_bytes')
                if not audio_bytes:
                    logger.info("No audio bytes received")
                    continue
                
                # Base64 encode the audio data
                blob = base64.b64encode(audio_bytes)
                audio_event = self.AUDIO_EVENT_TEMPLATE % (
                    self.prompt_name, 
                    self.audio_content_name, 
                    blob.decode('utf-8')
                )
                
                # Send the event
                await self.send_raw_event(audio_event)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Error processing audio: {e}")
                # Log traceback for debugging
                import traceback
                logger.debug(f"Audio processing traceback: {traceback.format_exc()}")
    
    def add_audio_chunk(self, audio_bytes):
        """Add an audio chunk to the queue."""
        self.audio_input_queue.put_nowait({
            'audio_bytes': audio_bytes,
            'prompt_name': self.prompt_name,
            'content_name': self.audio_content_name
        })
    
    async def send_audio_content_end_event(self):
        """Send a content end event to the Bedrock stream."""
        if not self.is_active:
            logger.debug("Stream is not active")
            return
        
        content_end_event = self.CONTENT_END_EVENT % (self.prompt_name, self.audio_content_name)
        await self.send_raw_event(content_end_event)
        logger.debug("Audio ended")
    
    async def send_tool_start_event(self, content_name, tool_use_id):
        """Send a tool content start event to the Bedrock stream."""
        content_start_event = self.TOOL_CONTENT_START_EVENT % (self.prompt_name, content_name, tool_use_id)
        logger.debug(f"Sending tool start event: {content_start_event}")  
        await self.send_raw_event(content_start_event)

    async def send_tool_result_event(self, content_name, tool_result):
        """Send a tool content event to the Bedrock stream."""
        # Use the actual tool result from processToolUse
        tool_result_event = self.tool_result_event(content_name=content_name, content=tool_result, role="TOOL")
        logger.debug(f"Sending tool result event: {tool_result_event}")
        await self.send_raw_event(tool_result_event)
    
    async def send_tool_content_end_event(self, content_name):
        """Send a tool content end event to the Bedrock stream."""
        tool_content_end_event = self.CONTENT_END_EVENT % (self.prompt_name, content_name)
        logger.debug(f"Sending tool content event: {tool_content_end_event}")
        await self.send_raw_event(tool_content_end_event)
    
    async def send_prompt_end_event(self):
        """Close the stream and clean up resources."""
        if not self.is_active:
            logger.debug("Stream is not active")
            return
        
        prompt_end_event = self.PROMPT_END_EVENT % (self.prompt_name)
        await self.send_raw_event(prompt_end_event)
        logger.debug("Prompt ended")
        
    async def send_session_end_event(self):
        """Send a session end event to the Bedrock stream."""
        if not self.is_active:
            logger.debug("Stream is not active")
            return

        await self.send_raw_event(self.SESSION_END_EVENT)
        self.is_active = False
        logger.debug("Session ended")
    
    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        try:            
            while self.is_active:
                try:
                    output = await self.stream_response.await_output()
                    result = await output[1].receive()
                    if result.value and result.value.bytes_:
                        try:
                            response_data = result.value.bytes_.decode('utf-8')
                            json_data = json.loads(response_data)
                            
                            # Handle different response types
                            if 'event' in json_data:
                                if 'completionStart' in json_data['event']:
                                    logger.debug(f"completionStart: {json_data['event']}")
                                elif 'contentStart' in json_data['event']:
                                    content_start = json_data['event']['contentStart']
                                    # set role
                                    self.role = content_start['role']
                                    # Check for speculative content
                                    if 'additionalModelFields' in content_start:
                                        try:
                                            additional_fields = json.loads(content_start['additionalModelFields'])
                                            if additional_fields.get('generationStage') == 'SPECULATIVE':
                                                self.display_assistant_text = True
                                            else:
                                                self.display_assistant_text = False
                                        except json.JSONDecodeError:
                                            logger.info("Error parsing additionalModelFields")
                                elif 'textOutput' in json_data['event']:
                                    text_content = json_data['event']['textOutput']['content']
                                    role = json_data['event']['textOutput']['role']
                                    # Check if there is a barge-in
                                    if '{ "interrupted" : true }' in text_content:
                                        logger.debug("Barge-in detected. Stopping audio output.")
                                        self.barge_in = True

                                    if (self.role == "ASSISTANT" and self.display_assistant_text):
                                        print(f"Caddy: {text_content}")
                                    elif (self.role == "USER"):
                                        print(f"Golf Player: {text_content}")
                                        
                                        # LAYER 2 FALLBACK: Auto-extract names from user text
                                        # This runs when Nova Sonic processes user speech but doesn't call registerPlayerTool
                                        # If we don't already have a player name stored, try to extract one
                                        if not self.tool_processor.session_player_name:
                                            extracted_name = self.tool_processor._extract_name_from_text(text_content)
                                            if extracted_name:
                                                # LAYER 3: Store in session for later use
                                                self.tool_processor.session_player_name = extracted_name
                                                logger.debug(f"FALLBACK: Auto-extracted and stored player name: {extracted_name}")
                                elif 'audioOutput' in json_data['event']:
                                    audio_content = json_data['event']['audioOutput']['content']
                                    audio_bytes = base64.b64decode(audio_content)
                                    await self.audio_output_queue.put(audio_bytes)
                                elif 'toolUse' in json_data['event']:
                                    self.toolUseContent = json_data['event']['toolUse']
                                    self.toolName = json_data['event']['toolUse']['toolName']
                                    self.toolUseId = json_data['event']['toolUse']['toolUseId']
                                    logger.debug(f"Tool use detected: {self.toolName}, ID: {self.toolUseId}")
                                elif 'contentEnd' in json_data['event'] and json_data['event'].get('contentEnd', {}).get('type') == 'TOOL':
                                    logger.debug("Processing tool use and sending result")
                                     # Start asynchronous tool processing - non-blocking
                                    self.handle_tool_request(self.toolName, self.toolUseContent, self.toolUseId)
                                    logger.debug("Processing tool use asynchronously")
                                elif 'contentEnd' in json_data['event']:
                                    pass  # Skip logging content end events
                                elif 'completionEnd' in json_data['event']:
                                    # Handle end of conversation, no more response will be generated
                                    logger.debug("End of response sequence")
                                elif 'usageEvent' in json_data['event']:
                                    # Skip logging usage events as they flood the screen
                                    pass
                            # Put the response in the output queue for other components
                            await self.output_queue.put(json_data)
                        except json.JSONDecodeError:
                            await self.output_queue.put({"raw_data": response_data})
                except StopAsyncIteration:
                    # Stream has ended
                    break
                except Exception as e:
                   # Handle ValidationException properly
                    if "ValidationException" in str(e):
                        error_message = str(e)
                        print(f"Validation error: {error_message}")
                    else:
                        print(f"Error receiving response: {e}")
                    break
                    
        except Exception as e:
            print(f"Response processing error: {e}")
        finally:
            self.is_active = False

    def handle_tool_request(self, tool_name, tool_content, tool_use_id):
        """Handle a tool request asynchronously"""
        # Create a unique content name for this tool response
        tool_content_name = str(uuid.uuid4())
        
        # Create an asynchronous task for the tool execution
        task = asyncio.create_task(self._execute_tool_and_send_result(
            tool_name, tool_content, tool_use_id, tool_content_name))
        
        # Store the task
        self.pending_tool_tasks[tool_content_name] = task
        
        # Add error handling
        task.add_done_callback(
            lambda t: self._handle_tool_task_completion(t, tool_content_name))
    
    def _handle_tool_task_completion(self, task, content_name):
        """Handle the completion of a tool task"""
        # Remove task from pending tasks
        if content_name in self.pending_tool_tasks:
            del self.pending_tool_tasks[content_name]
        
        # Handle any exceptions
        if task.done() and not task.cancelled():
            exception = task.exception()
            if exception:
                logger.debug(f"Tool task failed: {str(exception)}")
    
    async def _execute_tool_and_send_result(self, tool_name, tool_content, tool_use_id, content_name):
        """Execute a tool and send the result"""
        try:
            logger.debug(f"Starting tool execution: {tool_name}")
            
            # Process the tool - this doesn't block the event loop
            tool_result = await self.tool_processor.process_tool_async(tool_name, tool_content)
            
            # Send the result sequence
            await self.send_tool_start_event(content_name, tool_use_id)
            await self.send_tool_result_event(content_name, tool_result)
            await self.send_tool_content_end_event(content_name)
            
            logger.debug(f"Tool execution complete: {tool_name}")
        except Exception as e:
            logger.debug(f"Error executing tool {tool_name}: {str(e)}")
            # Try to send an error response if possible
            try:
                error_result = {"error": f"Tool execution failed: {str(e)}"}
                
                await self.send_tool_start_event(content_name, tool_use_id)
                await self.send_tool_result_event(content_name, error_result)
                await self.send_tool_content_end_event(content_name)
            except Exception as send_error:
                logger.debug(f"Failed to send error response: {str(send_error)}")
    
    async def close(self):
        """Close the stream properly."""
        if not self.is_active:
            return
        
        # Cancel any pending tool tasks
        for task in self.pending_tool_tasks.values():
            task.cancel()

        if self.response_task and not self.response_task.done():
            self.response_task.cancel()

        await self.send_audio_content_end_event()
        await self.send_prompt_end_event()
        await self.send_session_end_event()

        if self.stream_response:
            await self.stream_response.input_stream.close()

class AudioStreamer:
    """Handles continuous microphone input and audio output using separate streams."""
    
    def __init__(self, stream_manager):
        self.stream_manager = stream_manager
        self.is_streaming = False
        self.loop = asyncio.get_event_loop()

        # Initialize PyAudio
        logger.debug("AudioStreamer Initializing PyAudio...")
        self.p = time_it("AudioStreamerInitPyAudio", pyaudio.PyAudio)
        logger.debug("AudioStreamer PyAudio initialized")

        # Initialize separate streams for input and output
        # Input stream with callback for microphone
        logger.debug("Opening input audio stream...")
        self.input_stream = time_it("AudioStreamerOpenAudio", lambda  : self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=self.input_callback
        ))
        logger.debug("input audio stream opened")

        # Output stream for direct writing (no callback)
        logger.debug("Opening output audio stream...")
        self.output_stream = time_it("AudioStreamerOpenAudio", lambda  : self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE
        ))

        logger.debug("output audio stream opened")

    def input_callback(self, in_data, frame_count, time_info, status):
        """Callback function that schedules audio processing in the asyncio event loop"""
        if self.is_streaming and in_data:
            # Schedule the task in the event loop
            asyncio.run_coroutine_threadsafe(
                self.process_input_audio(in_data), 
                self.loop
            )
        return (None, pyaudio.paContinue)

    async def process_input_audio(self, audio_data):
        """Process a single audio chunk directly"""
        try:
            # Send audio to Bedrock immediately
            self.stream_manager.add_audio_chunk(audio_data)
        except Exception as e:
            if self.is_streaming:
                print(f"Error processing input audio: {e}")
    
    async def play_output_audio(self):
        """Play audio responses from Nova Sonic"""
        while self.is_streaming:
            try:
                # Check for barge-in flag
                if self.stream_manager.barge_in:
                    # Clear the audio queue
                    while not self.stream_manager.audio_output_queue.empty():
                        try:
                            self.stream_manager.audio_output_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    self.stream_manager.barge_in = False
                    # Small sleep after clearing
                    await asyncio.sleep(0.05)
                    continue
                
                # Get audio data from the stream manager's queue
                audio_data = await asyncio.wait_for(
                    self.stream_manager.audio_output_queue.get(),
                    timeout=0.1
                )
                
                if audio_data and self.is_streaming:
                    # Write directly to the output stream in smaller chunks
                    chunk_size = CHUNK_SIZE  # Use the same chunk size as the stream
                    
                    # Write the audio data in chunks to avoid blocking too long
                    for i in range(0, len(audio_data), chunk_size):
                        if not self.is_streaming:
                            break
                        
                        end = min(i + chunk_size, len(audio_data))
                        chunk = audio_data[i:end]
                        
                        # Create a new function that captures the chunk by value
                        def write_chunk(data):
                            return self.output_stream.write(data)
                        
                        # Pass the chunk to the function
                        await asyncio.get_event_loop().run_in_executor(None, write_chunk, chunk)
                        
                        # Brief yield to allow other tasks to run
                        await asyncio.sleep(0.001)
                    
            except asyncio.TimeoutError:
                # No data available within timeout, just continue
                continue
            except Exception as e:
                if self.is_streaming:
                    print(f"Error playing output audio: {str(e)}")
                    import traceback
                    traceback.print_exc()
                await asyncio.sleep(0.05)
    
    async def start_streaming(self):
        """Start streaming audio."""
        if self.is_streaming:
            return
        
        print("Starting audio streaming. Speak into your microphone...")
        print("Press Enter to stop streaming...")
        
        # Send audio content start event
        await time_it_async("send_audio_content_start_event", lambda : self.stream_manager.send_audio_content_start_event())
        
        self.is_streaming = True
        
        # Start the input stream if not already started
        if not self.input_stream.is_active():
            self.input_stream.start_stream()
        
        # Start processing tasks
        #self.input_task = asyncio.create_task(self.process_input_audio())
        self.output_task = asyncio.create_task(self.play_output_audio())
        
        # Wait for user to press Enter to stop
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        # Once input() returns, stop streaming
        await self.stop_streaming()
    
    async def stop_streaming(self):
        """Stop streaming audio."""
        if not self.is_streaming:
            return
            
        self.is_streaming = False

        # Cancel the tasks
        tasks = []
        if hasattr(self, 'input_task') and not self.input_task.done():
            tasks.append(self.input_task)
        if hasattr(self, 'output_task') and not self.output_task.done():
            tasks.append(self.output_task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # Stop and close the streams
        if self.input_stream:
            if self.input_stream.is_active():
                self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            if self.output_stream.is_active():
                self.output_stream.stop_stream()
            self.output_stream.close()
        if self.p:
            self.p.terminate()
        
        await self.stream_manager.close() 

def configure_logging(debug_enabled):
    """
    Configure logging based on debug flag and config.py settings
    
    Args:
        debug_enabled: Whether --debug flag was provided
    """
    if debug_enabled:
        # Enable debug logging with detailed formatting
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        )
        
        # Configure each module based on config.py flags
        from config import get_debug_flags
        debug_flags = get_debug_flags()
        
        for module_name, is_enabled in debug_flags.items():
            logger = logging.getLogger(module_name)
            if is_enabled:
                logger.setLevel(logging.DEBUG)
            else:
                logger.setLevel(logging.WARNING)
    else:
        # Standard logging - warnings and above only
        logging.basicConfig(level=logging.WARNING)

async def main(debug=False):
    """Main function to run the application."""
    # Configure logging based on debug flag and config.py settings
    configure_logging(debug)
    
    # Validate configuration
    is_valid, errors, warnings = validate_config()
    
    # Show critical errors
    if not is_valid:
        print("❌ Configuration validation failed:")
        for error in errors:
            print(f"   • {error}")
        print("\nPlease update your configuration in config.py and try again.")
        return
    
    # Show warnings for optional features
    if warnings:
        print("⚠️  Optional features not configured:")
        for warning in warnings:
            print(f"   • {warning}")
        print()
    
    # Show configuration summary if debug mode
    if debug:
        config_summary = get_config_summary()
        print("📋 Configuration Summary:")
        print(f"   • App: {config_summary['app_name']} v{config_summary['app_version']}")
        print(f"   • Golf Club: {config_summary['golf_club']}")
        print(f"   • Location: {config_summary['location']}")
        print(f"   • Knowledge Base: {config_summary['knowledge_base_id']}")
        print(f"   • Cache Duration: {config_summary['cache_duration_hours']} hours")
        print()
    


    # Create stream manager
    stream_manager = BedrockStreamManager(model_id='amazon.nova-sonic-v1:0', region='us-east-1')

    # Create audio streamer
    audio_streamer = AudioStreamer(stream_manager)

    # Initialize the stream
    await time_it_async("initialize_stream", stream_manager.initialize_stream)

    try:
        # This will run until the user presses Enter
        await audio_streamer.start_streaming()
        
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        # Clean up
        await audio_streamer.stop_streaming()
        

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Nova Sonic Python Streaming')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with granular per-module control via config.py')
    args = parser.parse_args()
    
    # Run the main function
    try:
        asyncio.run(main(debug=args.debug))
    except Exception as e:
        print(f"Application error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
