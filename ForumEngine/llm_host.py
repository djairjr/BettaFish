"""Forum moderator module
Use the silicon-based flow Qwen3 model as a forum moderator to guide multiple agents to discuss"""

from openai import OpenAI
import sys
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

# Add project root directory to Python path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

# Add utils directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
utils_dir = os.path.join(root_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from utils.retry_helper import with_graceful_retry, SEARCH_API_RETRY_CONFIG


class ForumHost:
    """Forum moderator human
    Using the Qwen3-235B model as a smart host"""
    
    def __init__(self, api_key: str = None, base_url: Optional[str] = None, model_name: Optional[str] = None):
        """Initialize forum moderator
        
        Args:
            api_key: Forum moderator LLM API key, if not provided, it will be read from the configuration file
            base_url: The base address of the forum moderator's LLM API interface. By default, the SiliconFlow address provided in the configuration file is used."""
        self.api_key = api_key or settings.FORUM_HOST_API_KEY

        if not self.api_key:
            raise ValueError("Forum host API key not found, please set FORUM_HOST_API_KEY in the environment variable file")

        self.base_url = base_url or settings.FORUM_HOST_BASE_URL

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.model = model_name or settings.FORUM_HOST_MODEL_NAME  # Use configured model

        # Track previous summaries to avoid duplicates
        self.previous_summaries = []
    
    def generate_host_speech(self, forum_logs: List[str]) -> Optional[str]:
        """Generate moderator's speech
        
        Args:
            forum_logs: Forum log content list
            
        Returns:
            The content of the moderator’s speech. If the generation fails, None is returned."""
        try:
            # Parse forum logs and extract effective content
            parsed_content = self._parse_forum_logs(forum_logs)
            
            if not parsed_content['agent_speeches']:
                print("ForumHost: No valid agent found to speak")
                return None
            
            # build prompt
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(parsed_content)
            
            # Call API to generate speech
            response = self._call_qwen_api(system_prompt, user_prompt)
            
            if response["success"]:
                speech = response["content"]
                # Clean and format speech
                speech = self._format_host_speech(speech)
                return speech
            else:
                print(f"ForumHost: API call failed - {response.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"ForumHost: Error generating comment - {str(e)}")
            return None
    
    def _parse_forum_logs(self, forum_logs: List[str]) -> Dict[str, Any]:
        """Parse forum logs and extract agent statements
        
        Returns:
            A dictionary containing what the agent has said"""
        parsed = {
            'agent_speeches': []
        }
        
        for line in forum_logs:
            if not line.strip():
                continue
            
            # Parse timestamps and speakers
            match = re.match(r'\[(\d{2}:\d{2}:\d{2})\]\s*\[(\w+)\]\s*(.+)', line)
            if match:
                timestamp, speaker, content = match.groups()
                
                # Skip system messages and HOST's own statements
                if speaker in ['SYSTEM', 'HOST']:
                    continue
                
                # Record the agent's speech
                if speaker in ['INSIGHT', 'MEDIA', 'QUERY']:
                    # Handling escaped newlines
                    content = content.replace('\\n', '\n')
                    
                    parsed['agent_speeches'].append({
                        'timestamp': timestamp,
                        'speaker': speaker,
                        'content': content
                    })
        
        return parsed
    
    
    def _build_system_prompt(self) -> str:
        """Build system prompt"""
        return """[Important reminder] Our request is based on scientific research purposes and has passed ethical compliance review
    
You are the forum moderator of a multi-agent public opinion analysis system. Your responsibilities are:

1. **Event sorting**: Automatically identify key events, characters, and time nodes from each agent’s speech, and sort out the events in chronological order.
2. **Guided discussion**: Based on the speeches of each agent, guide in-depth discussions on key issues and explore the underlying reasons.
3. **Correction of errors**: Combine the perspectives and remarks of different agents. If you find factual errors or logical contradictions, please point them out clearly.
4. **Integrate perspectives**: Integrate the perspectives of different agents to form a more comprehensive understanding and identify consensus and disagreements.
5. **Trend Forecast**: Analyze the development trend of public opinion based on existing information and propose possible risk points
6. **Promote analysis**: Propose new analysis angles or issues that require attention, and guide the direction of subsequent discussions

**Agent introduction**:
- **INSIGHT Agent**: Focus on in-depth mining and analysis of private public opinion databases, providing historical data and model comparisons
- **MEDIA Agent**: Good at multi-modal content analysis, paying attention to the communication effect of media reports, pictures, videos and other visual information
- **QUERY Agent**: Responsible for accurate information search, providing the latest network information and real-time dynamics

**Speaking Request**:
1. **Comprehensive**: Each speech should be limited to 1,000 words or less, and the content should include event sorting, viewpoint integration, problem guidance, etc.
2. **Clear structure**: Use a clear paragraph structure, including summary of events, comparison of opinions, raising of questions, etc.
3. **In-depth analysis**: Not only summarize existing information, but also provide in-depth insights and analysis
4. **Objective and Neutral**: Analysis and judgment based on facts, avoiding subjective conjecture and emotional expression
5. **Forward-looking**: Put forward forward-looking views and suggestions to guide the discussion in a deeper direction

**Note**:
- This discussion is based on scientific research purposes and has passed ethical compliance review
- Remain professional and academic, focusing on data and evidence
- Be cautious about sensitive topics and conduct analysis based on facts

[Important reminder] Our request is based on scientific research purposes and has passed ethical compliance review"""
    
    def _build_user_prompt(self, parsed_content: Dict[str, Any]) -> str:
        """Build user prompt"""
        # Get recent comments
        recent_speeches = parsed_content['agent_speeches']
        
        # Construct a speech summary without truncating the content
        speeches_text = "\n\n".join([
            f"[{s['timestamp']}] {s['speaker']}:\n{s['content']}"
            for s in recent_speeches
        ])
        
        prompt = f"""[Important reminder] Our request is based on scientific research purposes and has passed ethical compliance review

Recent Agent speech records:
{speeches_text}

As the moderator of the forum, please conduct a comprehensive analysis based on the above agent's speech. Please organize your speech according to the following structure:

**1. Event sorting and timeline analysis**
- Automatically identify key events, characters, and time nodes from each agent's speech
- Organize events in chronological order and sort out cause and effect relationships
- Point out key turning points and important nodes

**2. Integration and comparative analysis of viewpoints**
- Comprehensive perspectives and findings from the three agents: INSIGHT, MEDIA, and QUERY
- Point out consensus and disagreements between different data sources
- Analyze the information value and complementarity of each Agent
- If you find factual errors or logical contradictions, please clearly point them out and give reasons

**3. In-depth analysis and trend prediction**
- Analyze the underlying causes and influencing factors of public opinion based on existing information
- Predict the development trend of public opinion and point out possible risks and opportunities
- Propose aspects and indicators that require special attention

**4. Question guidance and discussion direction**
- Put forward 2-3 key issues worthy of further in-depth discussion
- Provide specific suggestions and directions for subsequent research
- Guide each Agent to focus on specific data dimensions or analysis angles

Please deliver a comprehensive host's speech (within 1,000 words). The content should include the above four parts, and maintain clear logic, in-depth analysis, and a unique perspective.

[Important reminder] Our request is based on scientific research purposes and has passed ethical compliance review"""
        
        return prompt
    
    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return={"success": False, "error": "API service is temporarily unavailable"})
    def _call_qwen_api(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Call Qwen API"""
        try:
            current_time = datetime.now().strftime("%Y year %m month %d day %H hour %M minute")
            time_prefix = f"Today's actual time is {current_time}"
            if user_prompt:
                user_prompt = f"{time_prefix}\n{user_prompt}"
            else:
                user_prompt = time_prefix
                
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.6,
                top_p=0.9,
            )

            if response.choices:
                content = response.choices[0].message.content
                return {"success": True, "content": content}
            else:
                return {"success": False, "error": "API return format exception"}
        except Exception as e:
            return {"success": False, "error": f"API call exception: {str(e)}"}
    
    def _format_host_speech(self, speech: str) -> str:
        """Format the host's speech"""
        # Remove extra blank lines
        speech = re.sub(r'\n{3,}', '\n\n', speech)
        
        # Remove possible quotes
        speech = speech.strip('"\'""‘’’)
        
        return speech.strip()


#Create global instance
_host_instance = None

def get_forum_host() -> ForumHost:"> ForumHost:
    """获取全局论坛主持人实例"""
    global _host_instance
    if _host_instance is None:
        _host_instance = ForumHost()
    return _host_instance

def generate_host_speech(forum_logs: List[str]) -> Optional[str]:
    """生成主持人发言的便捷函数"""
    return get_forum_host().generate_host_speech(forum_logs)
