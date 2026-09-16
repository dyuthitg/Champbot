import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import random
import re
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
import openai
from transformers import pipeline, GPT2LMHeadModel, GPT2Tokenizer
import torch
import spacy
from collections import Counter, defaultdict
import hashlib

from ..base_agent import BaseAgent, AgentMessage, MessageType, MessagePriority


class ConversationType(Enum):
    COMMENT = "comment"
    REPLY = "reply"
    MESSAGE = "message"
    CONNECTION_NOTE = "connection_note"
    ENDORSEMENT = "endorsement"


class ConversationStyle(Enum):
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    FRIENDLY = "friendly"
    THOUGHT_LEADER = "thought_leader"
    TECHNICAL = "technical"
    INSPIRATIONAL = "inspirational"
    ANALYTICAL = "analytical"


class ConversationTone(Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    SUPPORTIVE = "supportive"
    INQUISITIVE = "inquisitive"
    AGREEABLE = "agreeable"
    CHALLENGING = "challenging"


@dataclass
class ConversationContext:
    content_text: str
    content_author: str
    content_type: str
    content_topics: List[str]
    content_sentiment: str
    industry: str
    conversation_type: ConversationType
    target_style: ConversationStyle
    target_tone: ConversationTone
    user_profile: Dict[str, Any]
    existing_comments: List[str] = None
    character_limit: int = 280
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.existing_comments is None:
            self.existing_comments = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConversationResponse:
    response_id: str
    conversation_type: ConversationType
    generated_text: str
    confidence_score: float
    style: ConversationStyle
    tone: ConversationTone
    word_count: int
    character_count: int
    quality_score: float
    relevance_score: float
    uniqueness_score: float
    generated_at: datetime
    context_hash: str
    alternatives: List[str] = None
    
    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['conversation_type'] = self.conversation_type.value
        data['style'] = self.style.value
        data['tone'] = self.tone.value
        data['generated_at'] = self.generated_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationResponse':
        data['conversation_type'] = ConversationType(data['conversation_type'])
        data['style'] = ConversationStyle(data['style'])
        data['tone'] = ConversationTone(data['tone'])
        data['generated_at'] = datetime.fromisoformat(data['generated_at'])
        return cls(**data)


class ConversationAgent(BaseAgent):
    def __init__(self, agent_id: str, agent_type: str, config: Dict[str, Any]):
        super().__init__(agent_id, agent_type, config)
        
        # AI models configuration
        self.openai_api_key = config.get('openai_api_key')
        self.use_local_models = config.get('use_local_models', False)
        self.model_name = config.get('model_name', 'gpt-3.5-turbo')
        
        # Model instances
        self.gpt2_model = None
        self.gpt2_tokenizer = None
        self.nlp = None
        
        # Response cache
        self.response_cache: Dict[str, ConversationResponse] = {}
        self.cache_ttl = config.get('cache_ttl', 3600)  # 1 hour
        
        # User profiles and personalization
        self.user_profiles: Dict[str, Dict[str, Any]] = {}
        self.conversation_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        # Style and tone configurations
        self.style_templates = {
            ConversationStyle.PROFESSIONAL: {
                'patterns': [
                    "Thank you for sharing this insight about {topic}.",
                    "This is a valuable perspective on {topic}.",
                    "I appreciate your thoughts on {topic}.",
                    "Your analysis of {topic} resonates with my experience.",
                    "This aligns well with current trends in {industry}."
                ],
                'vocabulary': ['professional', 'insightful', 'valuable', 'comprehensive', 'strategic']
            },
            ConversationStyle.CASUAL: {
                'patterns': [
                    "Great point about {topic}!",
                    "Love this take on {topic}.",
                    "This really hits home about {topic}.",
                    "Totally agree with your view on {topic}.",
                    "Thanks for sharing this about {topic}!"
                ],
                'vocabulary': ['great', 'awesome', 'love', 'totally', 'really']
            },
            ConversationStyle.THOUGHT_LEADER: {
                'patterns': [
                    "This raises important questions about the future of {topic}.",
                    "Building on your point about {topic}, I believe...",
                    "Your perspective on {topic} highlights a critical trend.",
                    "This conversation about {topic} is exactly what our industry needs.",
                    "The implications of {topic} extend beyond what most realize."
                ],
                'vocabulary': ['strategic', 'forward-thinking', 'innovative', 'transformative', 'paradigm']
            },
            ConversationStyle.TECHNICAL: {
                'patterns': [
                    "The technical implementation of {topic} presents interesting challenges.",
                    "From an architectural perspective, {topic} requires careful consideration.",
                    "The scalability aspects of {topic} are particularly noteworthy.",
                    "Your approach to {topic} addresses key performance considerations.",
                    "The integration challenges around {topic} are significant."
                ],
                'vocabulary': ['implementation', 'architecture', 'scalability', 'optimization', 'integration']
            }
        }
        
        # Topic-specific knowledge bases
        self.topic_knowledge = {
            'technology': {
                'keywords': ['AI', 'ML', 'automation', 'digital transformation', 'innovation'],
                'talking_points': [
                    'impact on industry efficiency',
                    'future workforce implications',
                    'adoption challenges',
                    'competitive advantages',
                    'ethical considerations'
                ]
            },
            'leadership': {
                'keywords': ['team', 'culture', 'management', 'growth', 'strategy'],
                'talking_points': [
                    'building high-performing teams',
                    'organizational culture',
                    'change management',
                    'employee engagement',
                    'leadership development'
                ]
            },
            'business': {
                'keywords': ['growth', 'strategy', 'market', 'revenue', 'operations'],
                'talking_points': [
                    'market opportunities',
                    'operational efficiency',
                    'customer experience',
                    'competitive positioning',
                    'business model innovation'
                ]
            }
        }
        
        # Quality filters
        self.min_confidence_score = config.get('min_confidence_score', 0.7)
        self.min_quality_score = config.get('min_quality_score', 0.6)
        self.min_relevance_score = config.get('min_relevance_score', 0.6)
        
        # Generation parameters
        self.max_alternatives = config.get('max_alternatives', 3)
        self.diversity_threshold = config.get('diversity_threshold', 0.8)

    async def _initialize_agent(self):
        # Initialize OpenAI
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        
        # Load local models if configured
        if self.use_local_models:
            await self._load_local_models()
        
        # Load user profiles
        await self._load_user_profiles()
        
        # Register message handlers
        self.register_handler(MessageType.COMMAND, self._handle_command)
        self.register_handler(MessageType.QUERY, self._handle_query)

    async def _load_local_models(self):
        """Load local AI models"""
        try:
            # Load Spacy model
            self.nlp = spacy.load("en_core_web_sm")
            
            # Load GPT-2 model for text generation
            self.gpt2_tokenizer = GPT2Tokenizer.from_pretrained('gpt2-medium')
            self.gpt2_model = GPT2LMHeadModel.from_pretrained('gpt2-medium')
            self.gpt2_tokenizer.pad_token = self.gpt2_tokenizer.eos_token
            
            self.logger.info("Local models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading local models: {e}")
            self.use_local_models = False

    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        return [
            asyncio.create_task(self._cache_cleaner()),
            asyncio.create_task(self._profile_updater()),
            asyncio.create_task(self._quality_monitor())
        ]

    def _get_capabilities(self) -> List[str]:
        return [
            "generate_comments",
            "generate_replies",
            "generate_messages",
            "generate_connection_notes",
            "style_adaptation",
            "tone_matching",
            "context_awareness",
            "conversation_continuity",
            "quality_assessment",
            "alternative_generation"
        ]

    async def _on_start(self):
        self.logger.info("Conversation Agent started")

    async def _on_stop(self):
        # Save user profiles and cache
        await self._save_user_profiles()
        self.logger.info("Conversation Agent stopped")

    async def _handle_command(self, message: AgentMessage):
        command = message.payload.get('command')
        
        command_handlers = {
            'generate_response': self._generate_response_command,
            'generate_alternatives': self._generate_alternatives_command,
            'update_user_profile': self._update_user_profile_command,
            'learn_from_feedback': self._learn_from_feedback_command
        }
        
        handler = command_handlers.get(command)
        if handler:
            await handler(message)
        else:
            self.logger.warning(f"Unknown command: {command}")

    async def _handle_query(self, message: AgentMessage):
        query = message.payload.get('query')
        
        query_handlers = {
            'get_conversation_history': self._get_conversation_history_query,
            'get_style_options': self._get_style_options_query,
            'analyze_context': self._analyze_context_query
        }
        
        handler = query_handlers.get(query)
        if handler:
            await handler(message)
        else:
            self.logger.warning(f"Unknown query: {query}")

    async def _generate_response_command(self, message: AgentMessage):
        """Generate conversation response"""
        try:
            context_data = message.payload['context']
            
            # Create conversation context
            context = ConversationContext(
                content_text=context_data['content_text'],
                content_author=context_data['content_author'],
                content_type=context_data.get('content_type', 'post'),
                content_topics=context_data.get('content_topics', []),
                content_sentiment=context_data.get('content_sentiment', 'neutral'),
                industry=context_data.get('industry', 'general'),
                conversation_type=ConversationType(context_data.get('conversation_type', 'comment')),
                target_style=ConversationStyle(context_data.get('target_style', 'professional')),
                target_tone=ConversationTone(context_data.get('target_tone', 'positive')),
                user_profile=context_data.get('user_profile', {}),
                existing_comments=context_data.get('existing_comments', []),
                character_limit=context_data.get('character_limit', 280),
                metadata=context_data.get('metadata', {})
            )
            
            # Check cache first
            context_hash = self._generate_context_hash(context)
            if context_hash in self.response_cache:
                cached_response = self.response_cache[context_hash]
                
                response = AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    payload={
                        'success': True,
                        'response': cached_response.to_dict(),
                        'from_cache': True
                    },
                    correlation_id=message.correlation_id
                )
                await self.send_message(response)
                return
            
            # Generate new response
            conversation_response = await self._generate_conversation_response(context)
            
            if conversation_response:
                # Cache response
                self.response_cache[context_hash] = conversation_response
                
                # Send response
                response = AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    payload={
                        'success': True,
                        'response': conversation_response.to_dict(),
                        'from_cache': False
                    },
                    correlation_id=message.correlation_id
                )
                await self.send_message(response)
            else:
                raise Exception("Failed to generate response")
                
        except Exception as e:
            self.logger.error(f"Error generating response: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _generate_conversation_response(self, context: ConversationContext) -> Optional[ConversationResponse]:
        """Generate a conversation response based on context"""
        try:
            # Generate multiple candidates
            candidates = []
            
            # Try different generation methods
            if self.openai_api_key:
                openai_response = await self._generate_with_openai(context)
                if openai_response:
                    candidates.append(openai_response)
            
            if self.use_local_models and self.gpt2_model:
                local_response = await self._generate_with_local_model(context)
                if local_response:
                    candidates.append(local_response)
            
            # Template-based generation as fallback
            template_response = await self._generate_with_templates(context)
            if template_response:
                candidates.append(template_response)
            
            if not candidates:
                return None
            
            # Score and select best response
            best_response = await self._select_best_response(candidates, context)
            
            # Generate alternatives
            alternatives = [
                candidate['text'] for candidate in candidates 
                if candidate['text'] != best_response['text']
            ][:self.max_alternatives - 1]
            
            # Create response object
            response_id = f"resp_{datetime.utcnow().timestamp()}_{random.randint(1000, 9999)}"
            context_hash = self._generate_context_hash(context)
            
            conversation_response = ConversationResponse(
                response_id=response_id,
                conversation_type=context.conversation_type,
                generated_text=best_response['text'],
                confidence_score=best_response['confidence'],
                style=context.target_style,
                tone=context.target_tone,
                word_count=len(best_response['text'].split()),
                character_count=len(best_response['text']),
                quality_score=best_response['quality'],
                relevance_score=best_response['relevance'],
                uniqueness_score=await self._calculate_uniqueness(best_response['text'], context),
                generated_at=datetime.utcnow(),
                context_hash=context_hash,
                alternatives=alternatives
            )
            
            return conversation_response
            
        except Exception as e:
            self.logger.error(f"Error in conversation generation: {e}")
            return None

    async def _generate_with_openai(self, context: ConversationContext) -> Optional[Dict[str, Any]]:
        """Generate response using OpenAI API"""
        try:
            # Build prompt
            prompt = self._build_openai_prompt(context)
            
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": self._get_system_prompt(context)
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=150,
                temperature=0.7,
                top_p=0.9
            )
            
            generated_text = response.choices[0].message.content.strip()
            
            # Clean and validate
            cleaned_text = self._clean_response(generated_text, context)
            if not cleaned_text:
                return None
            
            # Calculate scores
            quality_score = await self._assess_response_quality(cleaned_text, context)
            relevance_score = await self._assess_relevance(cleaned_text, context)
            confidence_score = min(quality_score, relevance_score)
            
            return {
                'text': cleaned_text,
                'confidence': confidence_score,
                'quality': quality_score,
                'relevance': relevance_score,
                'method': 'openai'
            }
            
        except Exception as e:
            self.logger.error(f"OpenAI generation error: {e}")
            return None

    async def _generate_with_local_model(self, context: ConversationContext) -> Optional[Dict[str, Any]]:
        """Generate response using local GPT model"""
        try:
            # Build prompt
            prompt = self._build_local_prompt(context)
            
            # Tokenize
            inputs = self.gpt2_tokenizer.encode(prompt, return_tensors='pt')
            
            # Generate
            with torch.no_grad():
                outputs = self.gpt2_model.generate(
                    inputs,
                    max_length=inputs.size(1) + 50,
                    temperature=0.8,
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=self.gpt2_tokenizer.eos_token_id
                )
            
            # Decode and extract response
            generated_text = self.gpt2_tokenizer.decode(outputs[0], skip_special_tokens=True)
            response_text = generated_text[len(prompt):].strip()
            
            # Clean and validate
            cleaned_text = self._clean_response(response_text, context)
            if not cleaned_text:
                return None
            
            # Calculate scores
            quality_score = await self._assess_response_quality(cleaned_text, context)
            relevance_score = await self._assess_relevance(cleaned_text, context)
            confidence_score = min(quality_score, relevance_score) * 0.8  # Slightly lower confidence for local
            
            return {
                'text': cleaned_text,
                'confidence': confidence_score,
                'quality': quality_score,
                'relevance': relevance_score,
                'method': 'local'
            }
            
        except Exception as e:
            self.logger.error(f"Local model generation error: {e}")
            return None

    async def _generate_with_templates(self, context: ConversationContext) -> Optional[Dict[str, Any]]:
        """Generate response using templates and patterns"""
        try:
            style_config = self.style_templates.get(context.target_style)
            if not style_config:
                return None
            
            # Select appropriate template
            patterns = style_config['patterns']
            selected_pattern = random.choice(patterns)
            
            # Fill template with context
            main_topic = self._extract_main_topic(context.content_text, context.content_topics)
            
            response_text = selected_pattern.format(
                topic=main_topic,
                industry=context.industry,
                author=context.content_author
            )
            
            # Add contextual continuation
            continuation = await self._generate_contextual_continuation(context, main_topic)
            if continuation:
                response_text += f" {continuation}"
            
            # Clean and validate
            cleaned_text = self._clean_response(response_text, context)
            if not cleaned_text:
                return None
            
            # Calculate scores (templates generally have lower quality/confidence)
            quality_score = 0.6
            relevance_score = 0.7
            confidence_score = 0.6
            
            return {
                'text': cleaned_text,
                'confidence': confidence_score,
                'quality': quality_score,
                'relevance': relevance_score,
                'method': 'template'
            }
            
        except Exception as e:
            self.logger.error(f"Template generation error: {e}")
            return None

    def _build_openai_prompt(self, context: ConversationContext) -> str:
        """Build prompt for OpenAI"""
        prompt_parts = [
            f"Content: {context.content_text}",
            f"Author: {context.content_author}",
            f"Type: {context.conversation_type.value}",
            f"Style: {context.target_style.value}",
            f"Tone: {context.target_tone.value}",
            f"Industry: {context.industry}",
        ]
        
        if context.content_topics:
            prompt_parts.append(f"Topics: {', '.join(context.content_topics)}")
        
        if context.existing_comments:
            prompt_parts.append(f"Existing comments: {', '.join(context.existing_comments[:3])}")
        
        prompt_parts.append(f"Generate a {context.conversation_type.value} (max {context.character_limit} characters):")
        
        return "\n".join(prompt_parts)

    def _get_system_prompt(self, context: ConversationContext) -> str:
        """Get system prompt for OpenAI"""
        system_prompts = {
            ConversationStyle.PROFESSIONAL: "You are a professional LinkedIn user who writes thoughtful, industry-relevant comments that add value to conversations.",
            ConversationStyle.CASUAL: "You are a friendly LinkedIn user who writes casual, relatable comments that engage with others authentically.",
            ConversationStyle.THOUGHT_LEADER: "You are an industry thought leader who writes insightful comments that demonstrate deep expertise and forward-thinking.",
            ConversationStyle.TECHNICAL: "You are a technical expert who writes detailed, technically-oriented comments that showcase expertise.",
        }
        
        base_prompt = system_prompts.get(context.target_style, system_prompts[ConversationStyle.PROFESSIONAL])
        
        additional_instructions = [
            "Write naturally and avoid overly promotional language.",
            "Be authentic and add genuine value to the conversation.",
            "Keep responses concise and engaging.",
            "Match the tone of the original content appropriately.",
        ]
        
        if context.conversation_type == ConversationType.CONNECTION_NOTE:
            additional_instructions.append("Write a personalized connection request message that mentions mutual interests or reasons for connecting.")
        
        return f"{base_prompt} {' '.join(additional_instructions)}"

    def _build_local_prompt(self, context: ConversationContext) -> str:
        """Build prompt for local model"""
        # Simpler prompt for local model
        return f"LinkedIn {context.conversation_type.value} about {context.content_topics[0] if context.content_topics else 'business'}: "

    def _clean_response(self, text: str, context: ConversationContext) -> Optional[str]:
        """Clean and validate generated response"""
        if not text:
            return None
        
        # Remove quotes and extra whitespace
        text = re.sub(r'^["\']|["\']$', '', text.strip())
        text = ' '.join(text.split())
        
        # Check length constraints
        if len(text) > context.character_limit:
            # Truncate at last complete sentence
            sentences = text.split('. ')
            truncated = ''
            for sentence in sentences:
                if len(truncated + sentence + '. ') <= context.character_limit:
                    truncated += sentence + '. '
                else:
                    break
            text = truncated.strip()
            if text.endswith('.'):
                text = text[:-1]
        
        # Minimum length check
        if len(text) < 10:
            return None
        
        # Remove inappropriate content patterns
        inappropriate_patterns = [
            r'as an ai|i am an ai|artificial intelligence',
            r'i cannot|i can\'t|unable to',
            r'sorry|apologize|unfortunately',
        ]
        
        for pattern in inappropriate_patterns:
            if re.search(pattern, text.lower()):
                return None
        
        # Ensure proper capitalization
        text = text[0].upper() + text[1:] if text else text
        
        return text

    async def _assess_response_quality(self, text: str, context: ConversationContext) -> float:
        """Assess the quality of a generated response"""
        quality_score = 0.5  # Base score
        
        # Length appropriateness
        if 20 <= len(text) <= context.character_limit * 0.8:
            quality_score += 0.1
        
        # Sentence structure
        sentences = text.split('. ')
        if 1 <= len(sentences) <= 3:
            quality_score += 0.1
        
        # Vocabulary diversity (if using NLP)
        if self.nlp:
            doc = self.nlp(text)
            unique_words = set(token.lemma_.lower() for token in doc if not token.is_stop)
            if len(unique_words) > len(text.split()) * 0.6:
                quality_score += 0.1
        
        # Professional tone indicators
        professional_indicators = ['insight', 'perspective', 'experience', 'valuable', 'appreciate']
        if any(indicator in text.lower() for indicator in professional_indicators):
            quality_score += 0.1
        
        # Avoid generic responses
        generic_phrases = ['great post', 'thanks for sharing', 'very interesting']
        if not any(phrase in text.lower() for phrase in generic_phrases):
            quality_score += 0.1
        
        return min(1.0, quality_score)

    async def _assess_relevance(self, text: str, context: ConversationContext) -> float:
        """Assess relevance of response to content"""
        relevance_score = 0.5  # Base score
        
        # Topic keyword matching
        if context.content_topics:
            content_words = set(context.content_text.lower().split())
            response_words = set(text.lower().split())
            
            topic_words = set()
            for topic in context.content_topics:
                topic_words.update(topic.lower().split())
            
            # Check overlap with content topics
            topic_overlap = len(topic_words.intersection(response_words))
            if topic_overlap > 0:
                relevance_score += min(0.3, topic_overlap * 0.1)
        
        # Industry-specific vocabulary
        if context.industry in self.topic_knowledge:
            industry_keywords = self.topic_knowledge[context.industry]['keywords']
            industry_mentions = sum(1 for keyword in industry_keywords if keyword.lower() in text.lower())
            if industry_mentions > 0:
                relevance_score += min(0.2, industry_mentions * 0.1)
        
        return min(1.0, relevance_score)

    async def _calculate_uniqueness(self, text: str, context: ConversationContext) -> float:
        """Calculate uniqueness compared to existing comments"""
        if not context.existing_comments:
            return 1.0
        
        # Simple similarity check using word overlap
        text_words = set(text.lower().split())
        max_similarity = 0.0
        
        for existing_comment in context.existing_comments:
            existing_words = set(existing_comment.lower().split())
            if not text_words or not existing_words:
                continue
            
            overlap = len(text_words.intersection(existing_words))
            total = len(text_words.union(existing_words))
            similarity = overlap / total if total > 0 else 0
            
            max_similarity = max(max_similarity, similarity)
        
        return 1.0 - max_similarity

    async def _select_best_response(self, candidates: List[Dict[str, Any]], context: ConversationContext) -> Dict[str, Any]:
        """Select best response from candidates"""
        if not candidates:
            return None
        
        # Filter by minimum thresholds
        qualified_candidates = []
        for candidate in candidates:
            if (candidate['confidence'] >= self.min_confidence_score and
                candidate['quality'] >= self.min_quality_score and
                candidate['relevance'] >= self.min_relevance_score):
                qualified_candidates.append(candidate)
        
        if not qualified_candidates:
            qualified_candidates = candidates  # Use all if none meet threshold
        
        # Score candidates
        for candidate in qualified_candidates:
            # Weighted scoring
            candidate['final_score'] = (
                candidate['confidence'] * 0.4 +
                candidate['quality'] * 0.3 +
                candidate['relevance'] * 0.3
            )
        
        # Return best scoring candidate
        return max(qualified_candidates, key=lambda x: x['final_score'])

    def _extract_main_topic(self, content_text: str, content_topics: List[str]) -> str:
        """Extract main topic from content"""
        if content_topics:
            return content_topics[0]
        
        # Simple keyword extraction
        words = content_text.lower().split()
        word_freq = Counter(words)
        
        # Filter out common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        meaningful_words = [word for word, freq in word_freq.most_common(10) if word not in stop_words and len(word) > 3]
        
        return meaningful_words[0] if meaningful_words else 'business'

    async def _generate_contextual_continuation(self, context: ConversationContext, main_topic: str) -> Optional[str]:
        """Generate contextual continuation for template responses"""
        if context.industry in self.topic_knowledge:
            knowledge = self.topic_knowledge[context.industry]
            if main_topic.lower() in [kw.lower() for kw in knowledge['keywords']]:
                # Add relevant talking point
                talking_points = knowledge['talking_points']
                selected_point = random.choice(talking_points)
                
                continuations = [
                    f"The {selected_point} aspect is particularly relevant in today's market.",
                    f"I've seen similar trends around {selected_point} in my experience.",
                    f"What's your take on the {selected_point} implications?",
                    f"The {selected_point} dimension adds another layer to consider."
                ]
                
                return random.choice(continuations)
        
        return None

    def _generate_context_hash(self, context: ConversationContext) -> str:
        """Generate hash for context caching"""
        hash_components = [
            context.content_text[:100],  # First 100 chars
            context.content_author,
            context.conversation_type.value,
            context.target_style.value,
            context.target_tone.value,
            context.industry
        ]
        
        hash_string = '|'.join(hash_components)
        return hashlib.md5(hash_string.encode()).hexdigest()

    async def _cache_cleaner(self):
        """Clean expired cache entries"""
        while self.running:
            try:
                current_time = datetime.utcnow()
                expired_keys = []
                
                for response_id, response in self.response_cache.items():
                    age = (current_time - response.generated_at).total_seconds()
                    if age > self.cache_ttl:
                        expired_keys.append(response_id)
                
                for key in expired_keys:
                    del self.response_cache[key]
                
                if expired_keys:
                    self.logger.info(f"Cleaned {len(expired_keys)} expired cache entries")
                
                await asyncio.sleep(300)  # Clean every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Cache cleaner error: {e}")
                await asyncio.sleep(300)

    async def _profile_updater(self):
        """Update user profiles based on conversation patterns"""
        while self.running:
            try:
                # Analyze conversation patterns to improve personalization
                # This could include:
                # - Learning preferred styles and tones
                # - Identifying successful response patterns
                # - Updating industry knowledge
                
                await asyncio.sleep(3600)  # Update every hour
                
            except Exception as e:
                self.logger.error(f"Profile updater error: {e}")
                await asyncio.sleep(3600)

    async def _quality_monitor(self):
        """Monitor response quality and adjust parameters"""
        while self.running:
            try:
                # Track response quality metrics
                # Adjust generation parameters based on success rates
                
                await asyncio.sleep(1800)  # Check every 30 minutes
                
            except Exception as e:
                self.logger.error(f"Quality monitor error: {e}")
                await asyncio.sleep(1800)

    async def _load_user_profiles(self):
        """Load user profiles from storage"""
        try:
            profiles_data = await self.get_state('user_profiles')
            if profiles_data:
                self.user_profiles = profiles_data
                self.logger.info(f"Loaded {len(self.user_profiles)} user profiles")
        except Exception as e:
            self.logger.error(f"Error loading user profiles: {e}")

    async def _save_user_profiles(self):
        """Save user profiles to storage"""
        try:
            await self.update_state({'user_profiles': self.user_profiles})
            self.logger.info("User profiles saved")
        except Exception as e:
            self.logger.error(f"Error saving user profiles: {e}")

    async def _generate_alternatives_command(self, message: AgentMessage):
        """Generate alternative responses"""
        try:
            response_id = message.payload['response_id']
            count = message.payload.get('count', 3)
            
            # Find original response
            original_response = None
            for cached_response in self.response_cache.values():
                if cached_response.response_id == response_id:
                    original_response = cached_response
                    break
            
            if not original_response:
                raise Exception("Original response not found")
            
            # Generate alternatives with slight variations
            alternatives = []
            
            # This is a simplified version - in production, would regenerate with different parameters
            for i in range(count):
                alt_text = await self._create_variation(original_response.generated_text)
                if alt_text:
                    alternatives.append(alt_text)
            
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'alternatives': alternatives
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error generating alternatives: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _create_variation(self, original_text: str) -> Optional[str]:
        """Create variation of existing text"""
        # Simple variation techniques
        variations = [
            original_text.replace('This', 'That'),
            original_text.replace('great', 'excellent'),
            original_text.replace('interesting', 'fascinating'),
            original_text.replace('Thank you', 'Thanks'),
            original_text.replace('perspective', 'viewpoint')
        ]
        
        # Return a variation that's different from original
        for variation in variations:
            if variation != original_text:
                return variation
        
        return None