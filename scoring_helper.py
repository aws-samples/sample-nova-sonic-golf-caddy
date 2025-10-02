"""
Scoring Helper for Golf Course Assistant

Handles persistent score tracking with session resilience and player management.
"""

import boto3
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
import uuid
from config import ROUND_RESUME_CONFIG, is_debug_enabled

logger = logging.getLogger(__name__)

def decimal_to_int(obj):
    """Convert Decimal objects to int for JSON serialization"""
    if isinstance(obj, Decimal):
        return int(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_int(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_int(v) for v in obj]
    return obj


class ScoringHelper:
    """Handles all DynamoDB operations for golf score tracking"""
    
    def __init__(self, table_arn):
        """
        Initialize scoring helper
        
        Args:
            table_arn: DynamoDB table ARN (required)
                      Format: arn:aws:dynamodb:region:account:table/table-name
        """
        # Configure debug logging based on config.py flag
        if is_debug_enabled('scoring_helper'):
            logger.setLevel(logging.DEBUG)
        
        logger.debug(f"Initializing scoring helper with ARN: {table_arn}")
        
        if not table_arn:
            raise ValueError("table_arn is required")
        
        self.table_arn = table_arn
        
        # Parse ARN to extract region and table name
        # ARN format: arn:aws:dynamodb:region:account:table/table-name
        arn_parts = table_arn.split(':')
        logger.debug(f"ARN parts: {arn_parts}")
        
        if len(arn_parts) < 6 or not arn_parts[5].startswith('table/'):
            raise ValueError(f"Invalid DynamoDB table ARN format: {table_arn}")
        
        self.region = arn_parts[3]
        self.table_name = arn_parts[5].split('/')[-1]
        
        logger.debug(f"Extracted region: {self.region}, table name: {self.table_name}")
        
        # Initialize DynamoDB client and table
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
            self.table = self.dynamodb.Table(self.table_name)
            logger.debug("DynamoDB client and table initialized successfully")
        except Exception as e:
            logger.debug(f"Failed to initialize DynamoDB: {str(e)}")
            raise
        
        # Current session state
        self.current_player = None
        self.current_session_id = None
        self.round_status = None
    
    async def register_player(self, first_name):
        """
        Register a player and check for active rounds
        
        Args:
            first_name: Player's first name
            
        Returns:
            dict: Registration result with resume options
        """
        logger.debug(f"Registering player: {first_name}")
        
        # Normalize player name
        player_name = first_name.strip().capitalize()
        self.current_player = player_name
        logger.debug(f"Normalized player name: {player_name}")
        
        try:
            # Check for active rounds
            logger.debug("Checking for active rounds...")
            active_rounds = await self._check_active_rounds(player_name)
            logger.debug(f"Found {len(active_rounds)} active rounds")
            
            if active_rounds:
                # Automatically resume the first active round
                first_round = active_rounds[0]
                resume_result = await self.resume_round(first_round['session_id'])
                
                result = {
                    "success": True,
                    "player": player_name,
                    "action": "resumed",
                    "session_id": first_round['session_id'],
                    "active_rounds": decimal_to_int(active_rounds),
                    "message": f"Welcome back, {player_name}! Resumed your round with {first_round['holes_played']} holes completed."
                }
                logger.debug(f"Registration result (resumed): {result}")
                return result
            else:
                # No active rounds, ready for new round
                result = {
                    "success": True,
                    "player": player_name,
                    "action": "start_new",
                    "message": f"Nice to meet you, {player_name}! Ready to start your round?"
                }
                logger.debug(f"Registration result (new): {result}")
                return result
                
        except Exception as e:
            logger.debug(f"Error registering player: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to register player: {str(e)}"
            }
    
    async def start_new_round(self, course_name="Sunny Hills Golf Club"):
        """
        Start a new round for the current player
        
        Args:
            course_name: Name of the golf course
            
        Returns:
            dict: New round information
        """
        if not self.current_player:
            return {"success": False, "error": "No player registered"}
        
        try:
            # Generate new session ID
            self.current_session_id = self._generate_session_id(self.current_player)
            self.round_status = "in_progress"
            
            # Create round metadata record
            await self._create_round_metadata(course_name)
            
            return {
                "success": True,
                "player": self.current_player,
                "session_id": self.current_session_id,
                "course_name": course_name,
                "message": f"Started new round for {self.current_player}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to start new round: {str(e)}"
            }
    
    async def resume_round(self, session_id):
        """
        Resume an existing round
        
        Args:
            session_id: Session ID to resume
            
        Returns:
            dict: Resume result
        """
        try:
            self.current_session_id = session_id
            self.round_status = "in_progress"
            
            # Update last activity
            await self._update_round_activity()
            
            # Get round summary
            round_summary = await self.get_round_summary(session_id)
            
            return {
                "success": True,
                "session_id": session_id,
                "round_summary": round_summary,
                "message": f"Resumed round {session_id}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to resume round: {str(e)}"
            }
    
    async def record_score(self, hole_number, strokes, par):
        """
        Record a score for a specific hole
        
        Args:
            hole_number: Hole number (1-18)
            strokes: Number of strokes taken
            par: Par for the hole
            
        Returns:
            dict: Score recording result
        """
        logger.debug(f"Recording score: hole {hole_number}, strokes {strokes}, par {par}")
        logger.debug(f"Current player: {self.current_player}, session: {self.current_session_id}")
        
        if not self.current_player or not self.current_session_id:
            logger.debug("No active round - missing player or session")
            return {"success": False, "error": "No active round"}
        
        try:
            # Calculate score to par
            score_to_par = strokes - par
            score_description = self._calculate_score_description(score_to_par)
            logger.debug(f"Score calculation: {score_to_par} ({score_description})")
            
            # Create score record
            current_time = datetime.now(timezone.utc)
            ttl = int((current_time + timedelta(days=ROUND_RESUME_CONFIG["ttl_days"])).timestamp())
            
            item = {
                "player_name": self.current_player,
                "session_hole": f"{self.current_session_id}#hole_{hole_number:02d}",
                "session_id": self.current_session_id,
                "hole_number": hole_number,
                "strokes": strokes,
                "par": par,
                "score_to_par": score_to_par,
                "score_description": score_description,
                "round_date": current_time.strftime("%Y-%m-%d"),
                "round_status": "in_progress",
                "last_activity": current_time.isoformat(),
                "course_name": "Sunny Hills Golf Club",
                "hole_timestamp": current_time.isoformat(),
                "ttl": ttl
            }
            
            logger.debug(f"DynamoDB item to save: {item}")
            
            # Save to DynamoDB
            logger.debug("Saving item to DynamoDB...")
            self.table.put_item(Item=item)
            logger.debug("Item saved successfully")
            
            # Update round metadata
            logger.debug("Updating round metadata...")
            await self._update_round_metadata(hole_number)
            
            # Check if round is complete
            if hole_number == 18:
                logger.debug("Round complete - marking as finished")
                await self._complete_round()
            
            result = {
                "success": True,
                "player": self.current_player,
                "session_id": self.current_session_id,
                "hole_number": hole_number,
                "strokes": strokes,
                "par": par,
                "score_description": score_description,
                "message": f"Recorded {strokes} strokes on hole {hole_number} - {score_description}!"
            }
            logger.debug(f"Score recording result: {result}")
            return result
            
        except Exception as e:
            logger.debug(f"Error recording score: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to record score: {str(e)}"
            }
    
    async def get_round_summary(self, session_id=None):
        """
        Get summary of current or specified round
        
        Args:
            session_id: Optional session ID, uses current if not provided
            
        Returns:
            dict: Round summary with statistics
        """
        logger.debug("get_round_summary called")
        session_id = session_id or self.current_session_id
        logger.debug(f"Using session_id: {session_id}, current_player: {self.current_player}")
        
        if not session_id or not self.current_player:
            logger.debug("No active round - missing session_id or current_player")
            return {"success": False, "error": "No active round"}
        
        try:
            # Query all holes for the session
            query_key = f"{session_id}#hole_"
            logger.debug(f"Querying DynamoDB with player: {self.current_player}, session prefix: {query_key}")
            
            response = self.table.query(
                KeyConditionExpression=Key('player_name').eq(self.current_player) & 
                                      Key('session_hole').begins_with(query_key)
            )
            
            logger.debug(f"DynamoDB query returned {len(response.get('Items', []))} items")
            
            holes = []
            total_strokes = 0
            total_par = 0
            
            for item in response['Items']:
                logger.debug(f"Processing item: {item}")
                if 'hole_number' in item:  # Skip metadata records
                    hole_data = {
                        'hole_number': item['hole_number'],
                        'strokes': item['strokes'],
                        'par': item['par'],
                        'score_to_par': item['score_to_par'],
                        'score_description': item['score_description']
                    }
                    holes.append(hole_data)
                    total_strokes += item['strokes']
                    total_par += item['par']
                    logger.debug(f"Added hole {item['hole_number']}: {item['strokes']} strokes, par {item['par']}")
                else:
                    logger.debug(f"Skipping metadata record: {item.get('session_hole', 'unknown')}")
            
            # Sort holes by number
            holes.sort(key=lambda x: x['hole_number'])
            
            # Calculate statistics
            holes_played = len(holes)
            total_score_to_par = total_strokes - total_par
            
            logger.debug(f"Summary: {holes_played} holes, {total_strokes} strokes, {total_par} par")
            
            result = {
                "success": True,
                "session_id": session_id,
                "player": self.current_player,
                "holes_played": holes_played,
                "total_strokes": total_strokes,
                "total_par": total_par,
                "score_to_par": total_score_to_par,
                "holes": holes,
                "par_status": self._format_par_status(total_score_to_par)
            }
            
            logger.debug(f"Returning summary result: {result}")
            return result
            
        except Exception as e:
            logger.debug(f"Error in get_round_summary: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get round summary: {str(e)}"
            }
    
    async def _check_active_rounds(self, player_name):
        """Check for active rounds for a player"""
        today = datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.now(timezone.utc)
        logger.debug(f"Checking active rounds for {player_name} on {today}")
        
        try:
            # Query today's rounds
            logger.debug(f"Querying DynamoDB for player: {player_name}, date prefix: {today}_")
            response = self.table.query(
                KeyConditionExpression=Key('player_name').eq(player_name) & 
                                      Key('session_hole').begins_with(f"{today}_")
            )
            logger.debug(f"DynamoDB query response: {len(response.get('Items', []))} items found")
        except Exception as e:
            logger.debug(f"Error querying DynamoDB: {str(e)}")
            return []
        
        # Group by session
        sessions = {}
        for item in response['Items']:
            session_id = item['session_id']
            if session_id not in sessions:
                sessions[session_id] = {
                    'session_id': session_id,
                    'holes': [],
                    'last_activity': item['last_activity'],
                    'status': item.get('round_status', 'in_progress'),
                    'total_strokes': 0,
                    'total_par': 0
                }
            
            if 'hole_number' in item:
                sessions[session_id]['holes'].append(item['hole_number'])
                sessions[session_id]['total_strokes'] += item['strokes']
                sessions[session_id]['total_par'] += item['par']
        
        # Filter active sessions
        active_rounds = []
        for session in sessions.values():
            if session['status'] == 'in_progress':
                last_activity = datetime.fromisoformat(session['last_activity'])
                hours_since = (current_time - last_activity).total_seconds() / 3600
                
                if hours_since < ROUND_RESUME_CONFIG["max_resume_hours"]:
                    session['holes_played'] = len(session['holes'])
                    session['score_to_par'] = session['total_strokes'] - session['total_par']
                    session['par_status'] = self._format_par_status(session['score_to_par'])
                    active_rounds.append(session)
        
        return active_rounds
    
    def _generate_session_id(self, player_name):
        """Generate unique session ID for the day"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Count existing rounds for today
        try:
            response = self.table.query(
                KeyConditionExpression=Key('player_name').eq(player_name) & 
                                      Key('session_hole').begins_with(f"{today}_")
            )
            
            # Count unique sessions
            sessions = set()
            for item in response['Items']:
                sessions.add(item['session_id'])
            
            round_number = len(sessions) + 1
            
        except Exception:
            round_number = 1
        
        return f"{today}_{player_name.lower()}_round{round_number}"
    
    async def _create_round_metadata(self, course_name):
        """Create metadata record for the round"""
        current_time = datetime.now(timezone.utc)
        ttl = int((current_time + timedelta(days=ROUND_RESUME_CONFIG["ttl_days"])).timestamp())
        
        metadata_item = {
            "player_name": self.current_player,
            "session_hole": f"{self.current_session_id}#metadata",
            "session_id": self.current_session_id,
            "round_date": current_time.strftime("%Y-%m-%d"),
            "round_start_time": current_time.isoformat(),
            "round_status": "in_progress",
            "last_activity": current_time.isoformat(),
            "course_name": course_name,
            "holes_completed": 0,
            "total_strokes": 0,
            "total_par": 0,
            "ttl": ttl
        }
        
        self.table.put_item(Item=metadata_item)
    
    async def _update_round_activity(self):
        """Update last activity timestamp"""
        current_time = datetime.now(timezone.utc)
        
        try:
            self.table.update_item(
                Key={
                    'player_name': self.current_player,
                    'session_hole': f"{self.current_session_id}#metadata"
                },
                UpdateExpression="SET last_activity = :time",
                ExpressionAttributeValues={
                    ':time': current_time.isoformat()
                }
            )
        except Exception:
            # Metadata record might not exist, create it
            await self._create_round_metadata("Sunny Hills Golf Club")
    
    async def _update_round_metadata(self, hole_number):
        """Update round metadata after scoring"""
        # Get current round summary
        summary = await self.get_round_summary()
        
        if summary['success']:
            try:
                self.table.update_item(
                    Key={
                        'player_name': self.current_player,
                        'session_hole': f"{self.current_session_id}#metadata"
                    },
                    UpdateExpression="SET holes_completed = :holes, total_strokes = :strokes, total_par = :par, last_activity = :time",
                    ExpressionAttributeValues={
                        ':holes': summary['holes_played'],
                        ':strokes': summary['total_strokes'],
                        ':par': summary['total_par'],
                        ':time': datetime.now(timezone.utc).isoformat()
                    }
                )
            except Exception as e:
                print(f"Failed to update metadata: {e}")
    
    async def _complete_round(self):
        """Mark round as completed"""
        self.round_status = "completed"
        
        try:
            self.table.update_item(
                Key={
                    'player_name': self.current_player,
                    'session_hole': f"{self.current_session_id}#metadata"
                },
                UpdateExpression="SET round_status = :status, round_end_time = :time",
                ExpressionAttributeValues={
                    ':status': 'completed',
                    ':time': datetime.now(timezone.utc).isoformat()
                }
            )
        except Exception as e:
            print(f"Failed to complete round: {e}")
    
    def _calculate_score_description(self, score_to_par):
        """Calculate golf score description"""
        if score_to_par == -3:
            return "albatross"
        elif score_to_par == -2:
            return "eagle"
        elif score_to_par == -1:
            return "birdie"
        elif score_to_par == 0:
            return "par"
        elif score_to_par == 1:
            return "bogey"
        elif score_to_par == 2:
            return "double bogey"
        elif score_to_par == 3:
            return "triple bogey"
        else:
            return f"{abs(score_to_par)} {'under' if score_to_par < 0 else 'over'} par"
    
    def _format_par_status(self, score_to_par):
        """Format par status for display"""
        if score_to_par == 0:
            return "even par"
        elif score_to_par < 0:
            return f"{abs(score_to_par)} under par"
        else:
            return f"{score_to_par} over par"


# Utility functions for integration
def create_scoring_helper(table_arn):
    """
    Factory function to create scoring helper
    
    Args:
        table_arn: DynamoDB table ARN (required)
    
    Returns:
        ScoringHelper: Configured scoring helper instance
    """
    return ScoringHelper(table_arn=table_arn)