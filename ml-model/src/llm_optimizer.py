# """
# LLM Query Optimizer
# Supports: Groq (free), Gemini (free), OpenAI, Mistral, Together AI
# Auto-detects provider from API key format.
# """
# import os, re, json, urllib.request, urllib.error
# from pathlib import Path


# def _load_env():
#     env_path = Path(__file__).parent.parent / '.env'
#     if not env_path.exists():
#         return
#     with open(env_path) as f:
#         for line in f:
#             line = line.strip()
#             if not line or line.startswith('#') or '=' not in line:
#                 continue
#             key, _, val = line.partition('=')
#             key = key.strip()
#             val = val.strip().strip('"').strip("'")
#             if key and val and key not in os.environ:
#                 os.environ[key] = val

# _load_env()


# class LLMOptimizer:
#     def __init__(self):
#         self.api_key  = os.getenv('OPENAI_API_KEY', '').strip()
#         self.model    = os.getenv('LLM_MODEL', '').strip()
#         self.base_url = os.getenv('LLM_BASE_URL', '').strip()

#         # Auto-detect provider from key format
#         self.provider = self._detect_provider()

#         # Set defaults per provider if not specified
#         if not self.model:
#             self.model = self._default_model()
#         if not self.base_url:
#             self.base_url = self._default_base_url()

#         self.enabled = bool(
#             self.api_key and
#             len(self.api_key) > 10 and
#             self.api_key not in ('your-api-key-here', 'sk-...')
#         )

#     def _detect_provider(self) -> str:
#         key = self.api_key.lower()
#         url = self.base_url.lower()
#         if key.startswith('gsk_'):                        return 'Groq'
#         if key.startswith('aiz') or 'gemini' in url:      return 'Gemini'
#         if key.startswith('sk-') and 'openai' in url:     return 'OpenAI'
#         if 'mistral' in url:                              return 'Mistral'
#         if 'together' in url:                             return 'Together AI'
#         if key.startswith('sk-'):                         return 'OpenAI'
#         if 'groq' in url:                                 return 'Groq'
#         return 'Unknown'

#     # def _default_model(self) -> str:
#     #     return {
#     #         'Groq':       'llama3-8b-8192',
#     #         'Gemini':     'gemini-1.5-flash',
#     #         'OpenAI':     'gpt-4o-mini',
#     #         'Mistral':    'mistral-small-latest',
#     #         'Together AI':'meta-llama/Llama-3-8b-chat-hf',
#     #     }.get(self.provider, 'gpt-4o-mini')


#     def _default_model(self) -> str:
#         return {
#         'Groq':       'llama3-8b-8192',
#         'Gemini':     'gemini-2.0-flash',
#         'OpenAI':     'gpt-4o-mini',
#         'Mistral':    'mistral-small-latest',
#         'Together AI':'meta-llama/Llama-3-8b-chat-hf',
#     }.get(self.provider, 'gpt-4o-mini')

#     def _default_base_url(self) -> str:
#         return {
#             'Groq':       'https://api.groq.com/openai/v1',
#             'Gemini':     'https://generativelanguage.googleapis.com/v1beta',
#             'OpenAI':     'https://api.openai.com/v1',
#             'Mistral':    'https://api.mistral.ai/v1',
#             'Together AI':'https://api.together.xyz/v1',
#         }.get(self.provider, 'https://api.openai.com/v1')

#     def get_status(self) -> dict:
#         return {
#             'enabled':  self.enabled,
#             'provider': self.provider if self.enabled else None,
#             'model':    self.model    if self.enabled else None,
#             'message':  (f'LLM active — {self.provider} ({self.model})'
#                          if self.enabled else
#                          'LLM disabled — add API key to ml-model/.env'),
#         }

#     def optimize(self, query: str, schema: dict,
#                  strategy: str = None, context: dict = None) -> dict:
#         if not self.enabled:
#             return {'success': False,
#                     'error': 'LLM not configured. Add API key to ml-model/.env',
#                     'query': query, 'llm_available': False}

#         if self.provider == 'Gemini':
#             return self._call_gemini(query, schema, strategy)
#         else:
#             return self._call_openai_compat(query, schema, strategy)

#     # ── OpenAI-compatible (Groq, OpenAI, Mistral, Together) ──────
#     def _call_openai_compat(self, query: str, schema: dict, strategy: str) -> dict:
#         prompt = self._build_prompt(query, schema, strategy)

#         # Keep payload small — Groq has 6000 token limit on free tier
#         payload = json.dumps({
#             'model':       self.model,
#             'messages':    [
#                 {'role': 'system', 'content':
#                     'You are a SQL optimizer. Respond ONLY with JSON, no markdown.'},
#                 {'role': 'user', 'content': prompt}
#             ],
#             'temperature': 0.1,
#             'max_tokens':  600,
#         }).encode('utf-8')

#         req = urllib.request.Request(
#             f'{self.base_url}/chat/completions',
#             data=payload,
#             headers={
#                 'Content-Type':  'application/json',
#                 'Authorization': f'Bearer {self.api_key}',
#             }
#         )
#         try:
#             with urllib.request.urlopen(req, timeout=30) as r:
#                 data = json.loads(r.read().decode())
#             raw = data['choices'][0]['message']['content']
#             return self._parse(raw, query)
#         except urllib.error.HTTPError as e:
#             body = e.read().decode('utf-8', errors='ignore')
#             return {'success': False, 'error': self._http_error(e.code, body),
#                     'query': query, 'llm_available': True}
#         except Exception as e:
#             return {'success': False, 'error': str(e),
#                     'query': query, 'llm_available': True}

#     # ── Gemini native API ─────────────────────────────────────────
#     def _call_gemini(self, query: str, schema: dict, strategy: str) -> dict:
#         prompt = self._build_prompt(query, schema, strategy)
#         url = (f'https://generativelanguage.googleapis.com/v1beta/models/'
#                f'{self.model}:generateContent?key={self.api_key}')

#         payload = json.dumps({
#             'contents': [{'parts': [{'text': prompt}]}],
#             'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 600}
#         }).encode('utf-8')

#         req = urllib.request.Request(url, data=payload,
#             headers={'Content-Type': 'application/json'})
#         try:
#             with urllib.request.urlopen(req, timeout=30) as r:
#                 data = json.loads(r.read().decode())
#             # raw = data['candidates'][0]['content']['parts'][0]['text']
#             # return self._parse(raw, query)

#             raw = data['candidates'][0]['content']['parts'][0]['text']

#             print("\n===== GEMINI RESPONSE =====")
#             print(raw)
#             print("===========================\n")

#             return self._parse(raw, query)

#         except urllib.error.HTTPError as e:
#             body = e.read().decode('utf-8', errors='ignore')
#             return {'success': False, 'error': self._http_error(e.code, body),
#                     'query': query, 'llm_available': True}
#         except Exception as e:
#             return {'success': False, 'error': str(e),
#                     'query': query, 'llm_available': True}

#     # ── Prompt — kept SHORT to avoid 413 ─────────────────────────
#     def _build_prompt(self, query: str, schema: dict, strategy: str) -> str:
#         # Only send table name + column names + row count (no extra detail)
#         schema_lines = []
#         for tbl, info in (schema or {}).items():
#             cols = info.get('columns', [])
#             col_names = [c if isinstance(c, str) else c.get('name', c) for c in cols[:10]]
#             rows = info.get('row_count', 0)
#             schema_lines.append(f'{tbl}({rows} rows): {", ".join(col_names)}')
#         schema_str = '\n'.join(schema_lines[:5])  # max 5 tables

#         # Trim long queries
#         q = query.strip()
#         # if len(q) > 500:
#         #     q = q[:500] + '...'

#         if len(q) > 200:
#             q = q[:200] + '...'

#         hint = f'\nFocus: {strategy.replace("_"," ")}' if strategy else ''

#         return f"""Optimize this SQL query. Keep exact same result set.{hint}

# QUERY:
# {q}

# SCHEMA:
# {schema_str}

# Rules: replace SELECT * with columns, use EXISTS instead of IN subquery, push WHERE early, remove redundant ORDER BY in subqueries.

# Reply ONLY this JSON (no markdown):
# {{"optimized_query":"<sql>","changes":["change1"],"explanation":"brief reason","confidence":0.8}}"""

#     def _parse(self, content: str, original: str) -> dict:
#         content = re.sub(r'```(?:json)?', '', content).strip().strip('`').strip()
#         parsed  = None
#         try:
#             parsed = json.loads(content)
#         except json.JSONDecodeError:
#             m = re.search(r'\{.*\}', content, re.DOTALL)
#             if m:
#                 try: parsed = json.loads(m.group(0))
#                 except: pass

#         if not parsed:
#             return {'success': False, 'error': 'Could not parse LLM response',
#                     'query': original, 'llm_available': True}

#         optimized = parsed.get('optimized_query', '').strip()
#         if not optimized or not optimized.upper().startswith(('SELECT','WITH')):
#             return {'success': False, 'error': 'LLM returned invalid SQL',
#                     'query': original, 'llm_available': True}

#         if re.sub(r'\s+', ' ', optimized.lower()) == re.sub(r'\s+', ' ', original.lower()):
#             return {'success': False, 'error': 'LLM found no improvement',
#                     'query': original, 'llm_available': True}

#         return {
#             'success':       True,
#             'query':         optimized,
#             'changes':       parsed.get('changes', []),
#             'explanation':   parsed.get('explanation', ''),
#             'confidence':    float(parsed.get('confidence', 0.8)),
#             'llm_available': True,
#             'provider':      self.provider,
#             'model':         self.model,
#         }

#     def _http_error(self, code: int, body: str) -> str:
#         if code == 413:
#             return ('Request too large for API. Try a shorter query or simpler schema. '
#                     f'(HTTP 413)')
#         if code == 403:
#             return (f'Access denied (403). '
#                     f'For Groq: create a new API key at console.groq.com/keys with no restrictions. '
#                     f'Body: {body[:100]}')
#         if code == 401:
#             return 'Invalid API key. Check OPENAI_API_KEY in ml-model/.env'
#         if code == 429:
#             return 'Rate limit hit. Wait a moment and try again.'
#         if code == 400:
#             return f'Bad request: {body[:150]}'
#         return f'HTTP {code}: {body[:150]}'














"""
LLM Query Optimizer - minimal prompt to avoid rate limits
"""
import os, re, json, urllib.request, urllib.error
from pathlib import Path

def _load_env():
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists(): return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, _, v = line.partition('=')
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ: os.environ[k] = v
_load_env()

class LLMOptimizer:
    def __init__(self):
        self.api_key  = os.getenv('OPENAI_API_KEY', '').strip()
        self.model    = os.getenv('LLM_MODEL', '').strip()
        self.base_url = os.getenv('LLM_BASE_URL', '').strip()
        self.provider = self._detect_provider()
        if not self.model:    self.model    = self._default_model()
        if not self.base_url: self.base_url = self._default_base_url()
        self.enabled = bool(self.api_key and len(self.api_key) > 10
                            and self.api_key not in ('your-api-key-here','sk-...'))

    def _detect_provider(self):
        k = self.api_key; u = self.base_url.lower()
        if k.startswith('gsk_'):                    return 'Groq'
        if k.startswith('AIz') or 'gemini' in u:    return 'Gemini'
        if 'mistral' in u:                          return 'Mistral'
        if 'together' in u:                         return 'Together AI'
        if k.startswith('sk-'):                     return 'OpenAI'
        if 'groq' in u:                             return 'Groq'
        return 'Unknown'

    def _default_model(self):
        return {'Groq':'llama3-8b-8192','Gemini':'gemini-2.5-flash',
                'OpenAI':'gpt-4o-mini','Mistral':'mistral-small-latest'
                }.get(self.provider, 'gpt-4o-mini')

    def _default_base_url(self):
        return {'Groq':       'https://api.groq.com/openai/v1',
                'Gemini':     'https://generativelanguage.googleapis.com/v1beta',
                'OpenAI':     'https://api.openai.com/v1',
                'Mistral':    'https://api.mistral.ai/v1',
                'Together AI':'https://api.together.xyz/v1',
                }.get(self.provider, 'https://api.openai.com/v1')

    def get_status(self):
        return {'enabled': self.enabled,
                'provider': self.provider if self.enabled else None,
                'model':    self.model    if self.enabled else None,
                'message':  (f'LLM active — {self.provider} ({self.model})'
                             if self.enabled else
                             'Add API key to ml-model/.env')}

    def optimize(self, query, schema, strategy=None, context=None):
        if not self.enabled:
            return {'success':False,'error':'LLM not configured','query':query,'llm_available':False}
        if self.provider == 'Gemini':
            return self._call_gemini(query, schema, strategy)
        return self._call_openai_compat(query, schema, strategy)

    def _build_prompt(self, query, schema, strategy):
        # Ultra-minimal prompt — max ~300 tokens total
        tables = []
        for tbl, info in list((schema or {}).items())[:3]:  # max 3 tables
            cols = info.get('columns', [])[:6]              # max 6 cols
            col_names = [c if isinstance(c,str) else c.get('name',c) for c in cols]
            tables.append(f'{tbl}: {", ".join(col_names)}')
        schema_str = ' | '.join(tables)

        q = query.strip()[:300]  # max 300 chars
        hint = strategy.replace('_',' ') if strategy else ''

        return (f'Optimize SQL (same results). Hint: {hint}\n'
                f'Schema: {schema_str}\n'
                f'Query: {q}\n'
                f'Reply JSON only: {{"optimized_query":"...","changes":["..."],"explanation":"...","confidence":0.8}}')

    def _call_openai_compat(self, query, schema, strategy):
        payload = json.dumps({
            'model': self.model,
            'messages': [
                {'role':'system','content':'SQL optimizer. JSON only, no markdown.'},
                {'role':'user',  'content': self._build_prompt(query, schema, strategy)}
            ],
            'temperature': 0.1, 'max_tokens': 1024,
        }).encode('utf-8')

        req = urllib.request.Request(
            f'{self.base_url}/chat/completions', data=payload,
            headers={'Content-Type':'application/json',
                     'Authorization':f'Bearer {self.api_key}'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())

            print("\n========== FULL GEMINI RESPONSE ==========")
            print(json.dumps(data, indent=2))
            print("==========================================\n")

            return self._parse(data['choices'][0]['message']['content'], query)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            return {'success':False,'error':self._http_err(e.code,body),'query':query,'llm_available':True}
        except Exception as e:
            return {'success':False,'error':str(e),'query':query,'llm_available':True}

    def _call_gemini(self, query, schema, strategy):
        prompt = self._build_prompt(query, schema, strategy)
        url = (f'https://generativelanguage.googleapis.com/v1beta/models/'
               f'{self.model}:generateContent?key={self.api_key}')
        payload = json.dumps({
            'contents':[{'parts':[{'text':prompt}]}],
            'generationConfig':{'temperature':0.1,'maxOutputTokens':400}
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload,
                                     headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())


            # raw = data['candidates'][0]['content']['parts'][0]['text']
            # return self._parse(raw, query)
        
            raw = data['candidates'][0]['content']['parts'][0]['text']

            print("\n========== GEMINI RAW RESPONSE ==========")
            print(raw)
            print("=========================================\n")

            return self._parse(raw, query)

        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            return {'success':False,'error':self._http_err(e.code,body),'query':query,'llm_available':True}
        except Exception as e:
            return {'success':False,'error':str(e),'query':query,'llm_available':True}

    def _parse(self, content, original):
        content = re.sub(r'```(?:json)?','',content).strip().strip('`').strip()
        parsed = None
        try: parsed = json.loads(content)
        except:
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                try: parsed = json.loads(m.group(0))
                except: pass
        if not parsed:
            return {'success':False,'error':'Could not parse LLM response','query':original,'llm_available':True}
        opt = parsed.get('optimized_query','').strip()
        if not opt or not opt.upper().startswith(('SELECT','WITH')):
            return {'success':False,'error':'LLM returned invalid SQL','query':original,'llm_available':True}
        if re.sub(r'\s+',' ',opt.lower()) == re.sub(r'\s+',' ',original.lower()):
            return {'success':False,'error':'LLM found no improvement','query':original,'llm_available':True}
        return {'success':True,'query':opt,'changes':parsed.get('changes',[]),
                'explanation':parsed.get('explanation',''),'confidence':float(parsed.get('confidence',0.8)),
                'llm_available':True,'provider':self.provider,'model':self.model}

    def _http_err(self, code, body):
        if code == 413: return f'Prompt too large (413). Try shorter query.'
        if code == 429: return 'Rate limit hit. Wait 30 seconds and retry.'
        if code == 403: return f'Access denied (403). Create new API key with no restrictions.'
        if code == 401: return 'Invalid API key. Check ml-model/.env'
        return f'HTTP {code}: {body[:100]}'
    


