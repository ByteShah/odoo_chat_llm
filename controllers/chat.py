import re
import logging
import json
import numpy as np
from odoo import http
from odoo.http import request
from groq import Groq
from sentence_transformers import SentenceTransformer

_logger = logging.getLogger(__name__)

client = Groq(api_key="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")

class WebsiteChat(http.Controller):
    
    RAG_EXAMPLES = [
        {
            "question": "How many active users?",
            "code": "env['res.users'].search_count([('active', '=', True)])",
            "embedding": None
        },
        {
            "question": "Show confirmed sales orders",
            "code": "env['sale.order'].search([('state', '=', 'sale')])",
            "embedding": None
        }
    ]

    def __init__(self):
        self._init_embeddings()

    def _init_embeddings(self):
        """Initialize embeddings safely"""
        try:
            # Explicitly use CPU and disable meta tensors
            self.encoder = SentenceTransformer(
                'all-MiniLM-L6-v2', 
                device='cpu',
                trust_remote_code=True
            )
            
            for example in self.RAG_EXAMPLES:
                example["embedding"] = self.encoder.encode(
                    example["question"],
                    convert_to_tensor=False,
                    device='cpu'
                )
                
        except Exception as e:
            _logger.error("Embedding init failed: %s", str(e))
            self.encoder = None

    @http.route(['/llm/chat'], type='http', auth='public', website=True)
    def chat_page(self, **kw):
        return request.render('odoo_chat_llm.website_chat_page', {})

    @http.route('/llm/chat/message', type='json', auth='public', methods=['POST'], csrf=False)
    def process_chat_message(self, **post):
        try:
            data = json.loads(request.httprequest.data)
            user_message = data.get('message', '').strip()
            
            if not user_message:
                return {'error': 'Please enter a message.'}

            generated_query = self._generate_orm_query(user_message)
            if not generated_query:
                return {'error': 'Could not generate query.'}

            query_result = self._execute_orm_query(generated_query)
            final_response = self._generate_final_response(user_message, query_result)
            
            return {'response': final_response}

        except Exception as e:
            _logger.error("Error: %s", str(e), exc_info=True)
            return {'error': 'An error occurred.'}

    def _find_similar(self, query):
        """Find similar queries safely"""
        if not self.encoder:
            return []
            
        try:
            query_embed = self.encoder.encode(
                query,
                convert_to_tensor=False,
                device='cpu'
            )
            
            similarities = []
            for ex in self.RAG_EXAMPLES:
                if ex["embedding"] is None:
                    continue
                sim = np.dot(query_embed, ex["embedding"])
                similarities.append((sim, ex))
                
            return sorted(similarities, reverse=True)[:2]
            
        except Exception as e:
            _logger.warning("Similarity search failed: %s", str(e))
            return []

    def _generate_orm_query(self, user_message):
        """Generate ORM query with improved prompt"""
        prompt = f"""Translate this natural language query into valid Odoo ORM code:
        {user_message}
        
        Rules:
        1. Use only 'env' variable (no request)
        2. Return only Python code without comments
        3. Example: env['res.users'].search_count([('active','=',True)])
        4. Never use 'request' or 'browse' methods
        5. Only use search() or search_count() methods
        """
        
        try:
            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            raw_code = response.choices[0].message.content.strip()
            return self._extract_python_code(raw_code)
        except Exception as e:
            _logger.error("Query generation failed: %s", str(e))
            return None

    def _extract_code(self, text):
        match = re.search(r"```(?:python)?(.*?)```", text, re.DOTALL)
        return match.group(1).strip() if match else text

    def _execute_orm_query(self, generated_code):
        """Safer execution with request validation"""
        # Block dangerous patterns
        forbidden_patterns = [
            r'request\.',
            r'exec\(',
            r'eval\(',
            r'env\[.*\]\.browse'
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, generated_code):
                _logger.error("Blocked dangerous code: %s", generated_code)
                return None

        local_vars = {'env': request.env, 'query_result': None}
        safe_globals = {
            '__builtins__': {
                'super': super,
                'float': float,
                'int': int,
                'str': str,
                'bool': bool,
                'None': None,
                'list': list,
                'dict': dict,
                'tuple': tuple
            }
        }

        try:
            # Add safe assignment if missing
            if not generated_code.strip().startswith('query_result'):
                generated_code = f"query_result = {generated_code.strip().rstrip(';')}"

            # Validate model access
            allowed_models = ['res.users', 'sale.order', 'product.product']
            model_matches = re.findall(r"env\['(.*?)'\]", generated_code)
            for model in model_matches:
                if model not in allowed_models:
                    raise ValueError(f"Access to model {model} denied")

            exec(generated_code, safe_globals, local_vars)
            return local_vars.get('query_result')
        
        except Exception as e:
            _logger.error("Execution error: %s\nCode: %s", str(e), generated_code)
            return None

    def _generate_final_response(self, question, result):
        try:
            prompt = f"""User asked: {question}
            Result: {result}
            Create a helpful response."""
            
            response = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
            
        except Exception as e:
            return f"Result: {str(result)}"