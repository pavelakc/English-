import os
import json
import httpx
from http.server import HTTPServer, SimpleHTTPRequestHandler

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

class Handler(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        if self.path == '/ai':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            result = handle_ai(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # Quiet logs

def call_claude(prompt, max_tokens=500):
    if not ANTHROPIC_KEY:
        return None
    with httpx.Client(timeout=30) as client:
        r = client.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_KEY,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'claude-haiku-4-5-20251001',
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}]
            }
        )
        data = r.json()
        return data.get('content', [{}])[0].get('text', '')

def handle_ai(body):
    t = body.get('type', '')

    if t == 'association':
        en, ru = body.get('word_en',''), body.get('word_ru','')
        text = call_claude(
            f'Создай короткую смешную ассоциацию для запоминания слова "{en}" = "{ru}". '
            f'Ответь ТОЛЬКО JSON без лишнего: {{"association":"1-2 предложения на русском"}}',
            max_tokens=150
        )
        try:
            return json.loads(text.strip())
        except:
            return {'association': ''}

    elif t == 'story':
        level = body.get('level','A1')
        desc = body.get('levelDesc','simple')
        topic = body.get('topic','everyday life')
        words_ctx = body.get('wordsContext','')
        text = call_claude(
            f'Write a short English story for level {level} student.\n'
            f'Level requirements: {desc}.\n'
            f'Topic: {topic}.\n'
            f'{words_ctx}\n\n'
            f'Reply ONLY with valid JSON:\n'
            f'{{"title":"Story title","story":"Full story text...","questions":[{{"q":"Q1?","a":"A1"}},{{"q":"Q2?","a":"A2"}},{{"q":"Q3?","a":"A3"}}]}}',
            max_tokens=800
        )
        try:
            clean = text.strip().replace('```json','').replace('```','').strip()
            return json.loads(clean)
        except:
            return {'title':'Story','story': text or 'Error generating story.','questions':[]}

    elif t == 'translate':
        word = body.get('word','')
        text = call_claude(
            f'Translate English word "{word}" to Russian. Reply ONLY JSON: {{"ru":"перевод"}}',
            max_tokens=50
        )
        try:
            return json.loads(text.strip())
        except:
            return {'ru': word}

    return {'error': 'Unknown type'}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f'🚀 Server running on port {port}')
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
