import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
import numpy as np
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
import re
from collections import Counter
import spacy
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import openai
from bs4 import BeautifulSoup
import hashlib

from ..base_agent import BaseAgent, AgentMessage, MessageType, MessagePriority


class ContentType(Enum):
    POST = "post"
    ARTICLE = "article"
    VIDEO = "video"
    IMAGE = "image"
    POLL = "poll"
    EVENT = "event"
    JOB = "job"
    SHARED = "shared"


class Industry(Enum):
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    MARKETING = "marketing"
    SALES = "sales"
    HR = "hr"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    CONSULTING = "consulting"
    REAL_ESTATE = "real_estate"
    LEGAL = "legal"
    NONPROFIT = "nonprofit"
    OTHER = "other"


class EngagementLevel(Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    VIRAL = "viral"


@dataclass
class ContentAnalysis:
    content_id: str
    content_type: ContentType
    text: str
    author: str
    author_headline: Optional[str]
    timestamp: datetime
    
    # Analysis results
    sentiment_score: float
    sentiment_label: str
    industries: List[Industry]
    topics: List[str]
    keywords: List[str]
    entities: Dict[str, List[str]]
    
    # Engagement predictions
    engagement_score: float
    engagement_level: EngagementLevel
    relevance_score: float
    quality_score: float
    
    # Interaction recommendations
    should_engage: bool
    engagement_priority: int
    suggested_action: str
    suggested_comment_topics: List[str]
    
    # Metadata
    hashtags: List[str]
    mentions: List[str]
    urls: List[str]
    language: str
    word_count: int
    reading_time: int
    
    # Embeddings
    text_embedding: Optional[List[float]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['content_type'] = self.content_type.value
        data['industries'] = [i.value for i in self.industries]
        data['engagement_level'] = self.engagement_level.value
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContentAnalysis':
        data['content_type'] = ContentType(data['content_type'])
        data['industries'] = [Industry(i) for i in data['industries']]
        data['engagement_level'] = EngagementLevel(data['engagement_level'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class ContentAnalysisAgent(BaseAgent):
    def __init__(self, agent_id: str, agent_type: str, config: Dict[str, Any]):
        super().__init__(agent_id, agent_type, config)
        
        # NLP models
        self.nlp = None  # Spacy model
        self.sentiment_analyzer = None  # NLTK sentiment
        self.bert_classifier = None  # BERT for classification
        self.sentence_transformer = None  # Sentence embeddings
        self.zero_shot_classifier = None  # Zero-shot classification
        
        # OpenAI configuration
        self.openai_api_key = config.get('openai_api_key')
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        
        # Analysis cache
        self.analysis_cache: Dict[str, ContentAnalysis] = {}
        self.cache_ttl = config.get('cache_ttl', 3600)  # 1 hour
        
        # Configuration
        self.min_relevance_score = config.get('min_relevance_score', 0.5)
        self.min_quality_score = config.get('min_quality_score', 0.4)
        self.target_industries = [Industry(i) for i in config.get('target_industries', [])]
        self.target_keywords = config.get('target_keywords', [])
        self.excluded_keywords = config.get('excluded_keywords', [])
        
        # Industry keywords mapping
        self.industry_keywords = {
            Industry.TECHNOLOGY: ['ai', 'ml', 'software', 'tech', 'data', 'cloud', 'automation', 'digital', 'innovation', 'startup', 'saas', 'api', 'coding', 'development'],
            Industry.FINANCE: ['finance', 'investment', 'banking', 'fintech', 'crypto', 'trading', 'portfolio', 'market', 'economy', 'wealth'],
            Industry.HEALTHCARE: ['health', 'medical', 'healthcare', 'patient', 'clinical', 'pharma', 'biotech', 'wellness', 'therapy', 'diagnosis'],
            Industry.EDUCATION: ['education', 'learning', 'training', 'school', 'university', 'course', 'student', 'teaching', 'edtech', 'certification'],
            Industry.MARKETING: ['marketing', 'branding', 'advertising', 'campaign', 'seo', 'content', 'social media', 'growth', 'analytics', 'engagement'],
            Industry.SALES: ['sales', 'revenue', 'customer', 'crm', 'lead', 'pipeline', 'conversion', 'quota', 'prospecting', 'closing'],
            Industry.HR: ['hr', 'human resources', 'recruitment', 'talent', 'hiring', 'employee', 'culture', 'benefits', 'onboarding', 'retention'],
        }

    async def _initialize_agent(self):
        # Load NLP models
        await self._load_nlp_models()
        
        # Download NLTK data if needed
        try:
            nltk.download('vader_lexicon', quiet=True)
            nltk.download('punkt', quiet=True)
            nltk.download('stopwords', quiet=True)
        except:
            pass
        
        # Register message handlers
        self.register_handler(MessageType.COMMAND, self._handle_command)
        self.register_handler(MessageType.QUERY, self._handle_query)

    async def _load_nlp_models(self):
        """Load all NLP models asynchronously"""
        try:
            # Load Spacy model
            self.nlp = spacy.load("en_core_web_sm")
            
            # Initialize NLTK sentiment analyzer
            self.sentiment_analyzer = SentimentIntensityAnalyzer()
            
            # Load transformer models
            self.bert_classifier = pipeline(
                "sentiment-analysis",
                model="nlptown/bert-base-multilingual-uncased-sentiment"
            )
            
            # Load sentence transformer for embeddings
            self.sentence_transformer = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Load zero-shot classifier
            self.zero_shot_classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli"
            )
            
            self.logger.info("NLP models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading NLP models: {e}")
            # Fallback to basic functionality
            self.nlp = None

    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        return [
            asyncio.create_task(self._cache_cleaner()),
            asyncio.create_task(self._model_updater())
        ]

    def _get_capabilities(self) -> List[str]:
        return [
            "content_analysis",
            "sentiment_analysis",
            "topic_classification",
            "engagement_prediction",
            "keyword_extraction",
            "entity_recognition",
            "industry_classification",
            "relevance_scoring",
            "quality_assessment",
            "comment_suggestion"
        ]

    async def _on_start(self):
        self.logger.info("Content Analysis Agent started")

    async def _on_stop(self):
        # Clear cache
        self.analysis_cache.clear()
        self.logger.info("Content Analysis Agent stopped")

    async def _handle_command(self, message: AgentMessage):
        command = message.payload.get('command')
        
        if command == 'analyze_content':
            await self._analyze_content_command(message)
        elif command == 'batch_analyze':
            await self._batch_analyze_command(message)
        elif command == 'update_preferences':
            await self._update_preferences_command(message)
        else:
            self.logger.warning(f"Unknown command: {command}")

    async def _handle_query(self, message: AgentMessage):
        query = message.payload.get('query')
        
        if query == 'get_analysis':
            await self._get_analysis_query(message)
        elif query == 'get_trending_topics':
            await self._get_trending_topics_query(message)
        elif query == 'get_industry_insights':
            await self._get_industry_insights_query(message)
        else:
            self.logger.warning(f"Unknown query: {query}")

    async def _analyze_content_command(self, message: AgentMessage):
        """Analyze a single piece of content"""
        try:
            content_data = message.payload['content']
            
            # Check cache first
            content_id = self._generate_content_id(content_data)
            if content_id in self.analysis_cache:
                cached_analysis = self.analysis_cache[content_id]
                response = AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    payload={
                        'success': True,
                        'analysis': cached_analysis.to_dict(),
                        'from_cache': True
                    },
                    correlation_id=message.correlation_id
                )
                await self.send_message(response)
                return
            
            # Perform analysis
            analysis = await self._analyze_content(content_data)
            
            # Cache result
            self.analysis_cache[content_id] = analysis
            
            # Send response
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'analysis': analysis.to_dict(),
                    'from_cache': False
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error analyzing content: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _analyze_content(self, content_data: Dict[str, Any]) -> ContentAnalysis:
        """Perform comprehensive content analysis"""
        
        # Extract basic information
        content_id = self._generate_content_id(content_data)
        text = self._extract_text(content_data)
        content_type = self._determine_content_type(content_data)
        
        # Clean and prepare text
        cleaned_text = self._clean_text(text)
        
        # Basic metadata
        word_count = len(cleaned_text.split())
        reading_time = max(1, word_count // 200)  # Assuming 200 words per minute
        
        # Extract features
        hashtags = self._extract_hashtags(text)
        mentions = self._extract_mentions(text)
        urls = self._extract_urls(text)
        
        # NLP analysis
        sentiment_score, sentiment_label = await self._analyze_sentiment(cleaned_text)
        entities = await self._extract_entities(cleaned_text)
        keywords = await self._extract_keywords(cleaned_text)
        topics = await self._extract_topics(cleaned_text)
        industries = await self._classify_industries(cleaned_text)
        
        # Advanced analysis
        quality_score = await self._assess_quality(content_data, cleaned_text)
        relevance_score = await self._calculate_relevance(cleaned_text, keywords, industries)
        engagement_score = await self._predict_engagement(content_data, sentiment_score, quality_score)
        engagement_level = self._determine_engagement_level(engagement_score)
        
        # Generate embeddings
        text_embedding = None
        if self.sentence_transformer:
            text_embedding = self.sentence_transformer.encode(cleaned_text).tolist()
        
        # Determine engagement strategy
        should_engage = self._should_engage(relevance_score, quality_score, engagement_score)
        engagement_priority = self._calculate_priority(relevance_score, engagement_score)
        suggested_action = self._suggest_action(content_type, engagement_level, sentiment_label)
        suggested_comment_topics = await self._suggest_comment_topics(cleaned_text, topics, industries)
        
        # Detect language
        language = self._detect_language(cleaned_text)
        
        return ContentAnalysis(
            content_id=content_id,
            content_type=content_type,
            text=text,
            author=content_data.get('author', 'Unknown'),
            author_headline=content_data.get('author_headline'),
            timestamp=datetime.fromisoformat(content_data.get('timestamp', datetime.utcnow().isoformat())),
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            industries=industries,
            topics=topics,
            keywords=keywords,
            entities=entities,
            engagement_score=engagement_score,
            engagement_level=engagement_level,
            relevance_score=relevance_score,
            quality_score=quality_score,
            should_engage=should_engage,
            engagement_priority=engagement_priority,
            suggested_action=suggested_action,
            suggested_comment_topics=suggested_comment_topics,
            hashtags=hashtags,
            mentions=mentions,
            urls=urls,
            language=language,
            word_count=word_count,
            reading_time=reading_time,
            text_embedding=text_embedding
        )

    def _generate_content_id(self, content_data: Dict[str, Any]) -> str:
        """Generate unique content ID"""
        unique_string = f"{content_data.get('url', '')}{content_data.get('text', '')}{content_data.get('author', '')}"
        return hashlib.md5(unique_string.encode()).hexdigest()

    def _extract_text(self, content_data: Dict[str, Any]) -> str:
        """Extract text from content data"""
        text = content_data.get('text', '')
        
        # If HTML content, extract text
        if content_data.get('html'):
            soup = BeautifulSoup(content_data['html'], 'html.parser')
            text = soup.get_text(separator=' ')
        
        return text.strip()

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Remove special LinkedIn markers
        text = re.sub(r'#[A-Za-z0-9]+', '', text)  # Remove hashtags for analysis
        text = re.sub(r'@[A-Za-z0-9]+', '', text)  # Remove mentions
        text = re.sub(r'http[s]?://\S+', '', text)  # Remove URLs
        
        # Clean up
        text = text.strip()
        
        return text

    def _determine_content_type(self, content_data: Dict[str, Any]) -> ContentType:
        """Determine the type of content"""
        content_type_str = content_data.get('content_type', '').lower()
        
        if 'article' in content_type_str:
            return ContentType.ARTICLE
        elif 'video' in content_type_str:
            return ContentType.VIDEO
        elif 'poll' in content_type_str:
            return ContentType.POLL
        elif 'event' in content_type_str:
            return ContentType.EVENT
        elif 'job' in content_type_str:
            return ContentType.JOB
        elif 'shared' in content_type_str:
            return ContentType.SHARED
        elif content_data.get('has_image'):
            return ContentType.IMAGE
        else:
            return ContentType.POST

    def _extract_hashtags(self, text: str) -> List[str]:
        """Extract hashtags from text"""
        return re.findall(r'#([A-Za-z0-9]+)', text)

    def _extract_mentions(self, text: str) -> List[str]:
        """Extract mentions from text"""
        return re.findall(r'@([A-Za-z0-9]+)', text)

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text"""
        return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

    async def _analyze_sentiment(self, text: str) -> Tuple[float, str]:
        """Analyze sentiment of text"""
        if not text:
            return 0.0, 'neutral'
        
        # Use VADER sentiment analyzer
        if self.sentiment_analyzer:
            scores = self.sentiment_analyzer.polarity_scores(text)
            compound_score = scores['compound']
            
            if compound_score >= 0.05:
                label = 'positive'
            elif compound_score <= -0.05:
                label = 'negative'
            else:
                label = 'neutral'
            
            return compound_score, label
        
        return 0.0, 'neutral'

    async def _extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text"""
        entities = {
            'PERSON': [],
            'ORG': [],
            'LOC': [],
            'PRODUCT': [],
            'EVENT': [],
            'MONEY': [],
            'DATE': []
        }
        
        if self.nlp and text:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ in entities:
                    entities[ent.label_].append(ent.text)
        
        return entities

    async def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        keywords = []
        
        if self.nlp and text:
            doc = self.nlp(text)
            
            # Extract noun phrases
            noun_phrases = [chunk.text.lower() for chunk in doc.noun_chunks]
            
            # Extract important single words (nouns and verbs)
            important_pos = {'NOUN', 'VERB', 'PROPN'}
            important_words = [
                token.lemma_.lower() 
                for token in doc 
                if token.pos_ in important_pos and not token.is_stop and len(token.text) > 2
            ]
            
            # Combine and rank
            all_keywords = noun_phrases + important_words
            keyword_freq = Counter(all_keywords)
            
            # Get top keywords
            keywords = [kw for kw, _ in keyword_freq.most_common(10)]
        
        return keywords

    async def _extract_topics(self, text: str) -> List[str]:
        """Extract topics from text using zero-shot classification"""
        if not text or not self.zero_shot_classifier:
            return []
        
        # Define candidate topics
        candidate_topics = [
            'technology', 'business', 'leadership', 'innovation', 'career',
            'marketing', 'sales', 'finance', 'healthcare', 'education',
            'sustainability', 'ai/ml', 'startup', 'productivity', 'networking'
        ]
        
        try:
            result = self.zero_shot_classifier(
                text[:512],  # Limit text length
                candidate_labels=candidate_topics,
                multi_label=True
            )
            
            # Get topics with score > 0.3
            topics = [
                label for label, score in zip(result['labels'], result['scores'])
                if score > 0.3
            ]
            
            return topics[:5]  # Return top 5 topics
            
        except Exception as e:
            self.logger.error(f"Error extracting topics: {e}")
            return []

    async def _classify_industries(self, text: str) -> List[Industry]:
        """Classify content into industries"""
        industries = []
        text_lower = text.lower()
        
        # Score each industry based on keyword matches
        industry_scores = {}
        
        for industry, keywords in self.industry_keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                industry_scores[industry] = score
        
        # Sort by score and return top industries
        sorted_industries = sorted(
            industry_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        industries = [industry for industry, score in sorted_industries[:3] if score >= 2]
        
        # If no strong matches, use 'other'
        if not industries:
            industries = [Industry.OTHER]
        
        return industries

    async def _assess_quality(self, content_data: Dict[str, Any], text: str) -> float:
        """Assess content quality"""
        quality_score = 0.5  # Base score
        
        # Length factor
        word_count = len(text.split())
        if 50 <= word_count <= 500:
            quality_score += 0.1
        elif word_count > 500:
            quality_score += 0.15
        
        # Structure factors
        if '\n' in text or '\n\n' in text:  # Has paragraphs
            quality_score += 0.05
        
        if any(indicator in text.lower() for indicator in ['1.', '2.', '•', '-']):  # Has lists
            quality_score += 0.05
        
        # Media factors
        if content_data.get('has_image'):
            quality_score += 0.1
        if content_data.get('has_video'):
            quality_score += 0.15
        
        # Author factors
        if content_data.get('author_headline'):
            quality_score += 0.05
        if content_data.get('author_followers', 0) > 1000:
            quality_score += 0.1
        
        # Grammar and spelling (simplified check)
        if self.nlp and text:
            doc = self.nlp(text)
            # Check for proper capitalization and punctuation
            sentences = [sent.text.strip() for sent in doc.sents]
            proper_sentences = sum(
                1 for sent in sentences 
                if sent and sent[0].isupper() and sent[-1] in '.!?'
            )
            if sentences:
                grammar_ratio = proper_sentences / len(sentences)
                quality_score += grammar_ratio * 0.1
        
        return min(1.0, quality_score)

    async def _calculate_relevance(self, text: str, keywords: List[str], industries: List[Industry]) -> float:
        """Calculate relevance score based on configuration"""
        relevance_score = 0.0
        
        # Check industry match
        if self.target_industries:
            industry_match = any(ind in self.target_industries for ind in industries)
            if industry_match:
                relevance_score += 0.4
        else:
            relevance_score += 0.2  # No specific industry preference
        
        # Check keyword matches
        text_lower = text.lower()
        if self.target_keywords:
            keyword_matches = sum(1 for kw in self.target_keywords if kw.lower() in text_lower)
            relevance_score += min(0.4, keyword_matches * 0.1)
        
        # Check for excluded keywords
        if self.excluded_keywords:
            excluded_matches = sum(1 for kw in self.excluded_keywords if kw.lower() in text_lower)
            relevance_score -= min(0.3, excluded_matches * 0.1)
        
        # Semantic similarity if embeddings available
        if self.sentence_transformer and self.target_keywords:
            target_embedding = self.sentence_transformer.encode(' '.join(self.target_keywords))
            text_embedding = self.sentence_transformer.encode(text)
            similarity = cosine_similarity([target_embedding], [text_embedding])[0][0]
            relevance_score += similarity * 0.2
        
        return max(0.0, min(1.0, relevance_score))

    async def _predict_engagement(self, content_data: Dict[str, Any], sentiment_score: float, quality_score: float) -> float:
        """Predict engagement potential"""
        engagement_score = 0.5  # Base score
        
        # Current engagement metrics
        likes = content_data.get('likes', 0)
        comments = content_data.get('comments', 0)
        shares = content_data.get('shares', 0)
        
        # Normalize engagement (assuming average post gets 50 likes)
        normalized_engagement = min(1.0, (likes + comments * 2 + shares * 3) / 100)
        engagement_score = normalized_engagement * 0.3
        
        # Quality factor
        engagement_score += quality_score * 0.2
        
        # Sentiment factor (positive content tends to get more engagement)
        if sentiment_score > 0:
            engagement_score += sentiment_score * 0.1
        
        # Content type factors
        content_type = self._determine_content_type(content_data)
        if content_type == ContentType.VIDEO:
            engagement_score += 0.15
        elif content_type == ContentType.POLL:
            engagement_score += 0.1
        elif content_type == ContentType.IMAGE:
            engagement_score += 0.05
        
        # Timing factor (if posted recently)
        if 'timestamp' in content_data:
            post_time = datetime.fromisoformat(content_data['timestamp'])
            hours_old = (datetime.utcnow() - post_time).total_seconds() / 3600
            if hours_old < 4:
                engagement_score += 0.1
            elif hours_old < 24:
                engagement_score += 0.05
        
        # Author influence
        author_followers = content_data.get('author_followers', 0)
        if author_followers > 10000:
            engagement_score += 0.15
        elif author_followers > 1000:
            engagement_score += 0.1
        
        return min(1.0, engagement_score)

    def _determine_engagement_level(self, engagement_score: float) -> EngagementLevel:
        """Determine engagement level from score"""
        if engagement_score >= 0.9:
            return EngagementLevel.VIRAL
        elif engagement_score >= 0.7:
            return EngagementLevel.VERY_HIGH
        elif engagement_score >= 0.5:
            return EngagementLevel.HIGH
        elif engagement_score >= 0.3:
            return EngagementLevel.MEDIUM
        elif engagement_score >= 0.15:
            return EngagementLevel.LOW
        else:
            return EngagementLevel.VERY_LOW

    def _should_engage(self, relevance_score: float, quality_score: float, engagement_score: float) -> bool:
        """Determine if we should engage with content"""
        # Must meet minimum thresholds
        if relevance_score < self.min_relevance_score:
            return False
        
        if quality_score < self.min_quality_score:
            return False
        
        # Combined score check
        combined_score = (relevance_score * 0.5 + quality_score * 0.3 + engagement_score * 0.2)
        
        return combined_score >= 0.5

    def _calculate_priority(self, relevance_score: float, engagement_score: float) -> int:
        """Calculate engagement priority (1-10)"""
        priority_score = (relevance_score * 0.7 + engagement_score * 0.3) * 10
        return max(1, min(10, int(priority_score)))

    def _suggest_action(self, content_type: ContentType, engagement_level: EngagementLevel, sentiment: str) -> str:
        """Suggest appropriate action"""
        if engagement_level in [EngagementLevel.VIRAL, EngagementLevel.VERY_HIGH]:
            if content_type == ContentType.POST:
                return "comment_and_share"
            else:
                return "comment"
        
        elif engagement_level in [EngagementLevel.HIGH, EngagementLevel.MEDIUM]:
            if sentiment == 'positive':
                return "comment"
            else:
                return "like"
        
        else:
            return "like"

    async def _suggest_comment_topics(self, text: str, topics: List[str], industries: List[Industry]) -> List[str]:
        """Suggest relevant comment topics"""
        suggestions = []
        
        # Based on content topics
        topic_suggestions = {
            'technology': ['innovation impact', 'technical implementation', 'future trends'],
            'business': ['business strategy', 'market insights', 'growth opportunities'],
            'leadership': ['leadership lessons', 'team building', 'organizational culture'],
            'ai/ml': ['AI applications', 'ethical considerations', 'technical challenges'],
            'startup': ['scaling challenges', 'funding insights', 'market validation'],
        }
        
        for topic in topics:
            if topic in topic_suggestions:
                suggestions.extend(topic_suggestions[topic])
        
        # Based on industries
        industry_suggestions = {
            Industry.TECHNOLOGY: ['technical perspective', 'implementation experience'],
            Industry.FINANCE: ['financial implications', 'ROI considerations'],
            Industry.HEALTHCARE: ['patient impact', 'healthcare innovation'],
            Industry.MARKETING: ['marketing strategy', 'audience engagement'],
        }
        
        for industry in industries:
            if industry in industry_suggestions:
                suggestions.extend(industry_suggestions[industry])
        
        # Remove duplicates and limit
        unique_suggestions = list(dict.fromkeys(suggestions))
        
        return unique_suggestions[:5]

    def _detect_language(self, text: str) -> str:
        """Detect language of text"""
        # Simple implementation - can be enhanced with langdetect
        if self.nlp and text:
            doc = self.nlp(text)
            return doc.lang_
        return 'en'

    async def _cache_cleaner(self):
        """Clean expired cache entries"""
        while self.running:
            try:
                current_time = datetime.utcnow()
                expired_keys = []
                
                for content_id, analysis in self.analysis_cache.items():
                    age = (current_time - analysis.timestamp).total_seconds()
                    if age > self.cache_ttl:
                        expired_keys.append(content_id)
                
                for key in expired_keys:
                    del self.analysis_cache[key]
                
                if expired_keys:
                    self.logger.info(f"Cleaned {len(expired_keys)} expired cache entries")
                
                await asyncio.sleep(300)  # Clean every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Cache cleaner error: {e}")
                await asyncio.sleep(60)

    async def _model_updater(self):
        """Periodically update ML models or configurations"""
        while self.running:
            try:
                # This could include:
                # - Reloading models with new weights
                # - Updating industry keywords based on trends
                # - Refreshing configuration from external source
                
                await asyncio.sleep(3600)  # Update every hour
                
            except Exception as e:
                self.logger.error(f"Model updater error: {e}")
                await asyncio.sleep(300)

    async def _batch_analyze_command(self, message: AgentMessage):
        """Analyze multiple pieces of content"""
        try:
            contents = message.payload['contents']
            analyses = []
            
            for content_data in contents:
                analysis = await self._analyze_content(content_data)
                analyses.append(analysis.to_dict())
            
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'analyses': analyses,
                    'count': len(analyses)
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error in batch analysis: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _update_preferences_command(self, message: AgentMessage):
        """Update analysis preferences"""
        preferences = message.payload.get('preferences', {})
        
        if 'target_industries' in preferences:
            self.target_industries = [Industry(i) for i in preferences['target_industries']]
        
        if 'target_keywords' in preferences:
            self.target_keywords = preferences['target_keywords']
        
        if 'excluded_keywords' in preferences:
            self.excluded_keywords = preferences['excluded_keywords']
        
        if 'min_relevance_score' in preferences:
            self.min_relevance_score = preferences['min_relevance_score']
        
        if 'min_quality_score' in preferences:
            self.min_quality_score = preferences['min_quality_score']
        
        # Save preferences
        await self.update_state({
            'preferences': {
                'target_industries': [i.value for i in self.target_industries],
                'target_keywords': self.target_keywords,
                'excluded_keywords': self.excluded_keywords,
                'min_relevance_score': self.min_relevance_score,
                'min_quality_score': self.min_quality_score
            }
        })
        
        response = AgentMessage(
            sender=self.agent_id,
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload={'success': True, 'message': 'Preferences updated'},
            correlation_id=message.correlation_id
        )
        await self.send_message(response)