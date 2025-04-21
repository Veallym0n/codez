#!/usr/bin/env python3
import argparse, json, os, sqlite3, sys, httpx, base64, configparser, asyncio
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, Callable, AsyncGenerator, Optional
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

class Settings:
    def __init__(self):
        self.endpoint = 'http://porky.toai.chat/to/polli'
        self.model, self.api_key, self.system_prompt = 'openai', None, None
        self.chat_db, self.files, self.no_stream = None, None, False,
        self.printable, self.functions = True, None
        self.opts = {}
        self.prompt = []
    
    def get_api_key(self): return os.environ.get('OPENAI_API_KEY') or self.api_key
    
    def parse_args(self):
        parser = argparse.ArgumentParser(description='OpenAI API 聊天工具')
        parser.add_argument('-e', dest='endpoint', help='API 端点')
        parser.add_argument('-c', dest='chat_db', help='SQLite 聊天记录文件', default=':memory:')
        parser.add_argument('-F', dest='files', action='append', help='上传图片，格式: image=@file_path')
        parser.add_argument('-m', dest='model', help='指定使用的模型')
        parser.add_argument('-i', '--interactive', dest='interactive', action='store_true', help='交互模式', default=False)
        parser.add_argument('--no-stream', dest='no_stream', action='store_true', help='禁用流式输出')
        parser.add_argument('--sp', dest='system_prompt', help='指定系统提示')
        parser.add_argument('--func', dest='function', help='指定函数调用')
        parser.add_argument('--print', dest='printable', action='store_true', help='打印输出')
        parser.add_argument('prompt', nargs='*', help='聊天提示')

        return parser.parse_args()
    
    def _apply_args(self, args):
        if not args: return self
        if args.endpoint: self.endpoint = args.endpoint
        self.chat_db, self.files = args.chat_db, args.files
        if args.model: self.model = args.model
        self.no_stream = args.no_stream
        if args.system_prompt: self.system_prompt = args.system_prompt
        self.prompt = args.prompt
        if args.function:
            module, clz = args.function.split(':',1)
            if '.' in module: fromlist = module.split('.')
            else: fromlist = [module]
            module = __import__(fromlist[0], fromlist=fromlist[1:])
            tools = getattr(module, clz)
            self.functions = tools
        return self
    
    def getall(self, args=None):
        args = args or self.parse_args()
        self._args = args
        config_paths = [Path.home() / '.airc', Path.cwd() / '.airc']
        config_values = {}
        for config_path in config_paths:
            if config_path.exists():
                config = configparser.ConfigParser()
                config.read(config_path)
                if 'ai' in config:
                    for k in ['endpoint', 'model', 'api_key', 'system_prompt']:
                        if k in config['ai']: config_values[k] = config['ai'][k]
        for k, v in config_values.items(): setattr(self, k, v)
        return self._apply_args(args)

class DatabaseManager:
    def __init__(self, db_path=None):
        self.conn = None
        if db_path: self.setup_db(db_path)
    
    def setup_db(self, db_path):
        logging.debug(f'连接数据库: {db_path}')
        self.conn = sqlite3.connect(db_path)
        self.conn.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)')
        self.conn.commit()
        return self.conn
    
    def get_previous_messages(self):
        if not self.conn: return []
        cursor = self.conn.cursor()
        cursor.execute("SELECT role, content FROM messages ORDER BY id desc limit 500")
        return [{"role": r, "content": c} for r, c in cursor.fetchall()[::-1]]
    
    def save_message(self, role, content):
        if not self.conn: return
        self.conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
        self.conn.commit()

class AIChat:
    def __init__(self, settings: Settings = None):
        self.settings = settings or Settings().getall()
        self.db_manager = DatabaseManager(self.settings.chat_db) if self.settings.chat_db else None
        self.fn_calls = self.settings.functions or None
        self._message_queues = defaultdict(deque)
        self._filters = {}
    
    def process_file_argument(self, file_arg):
        if not file_arg.startswith('image=@'):
            logging.error(f"文件参数格式不正确: {file_arg}"); sys.exit(1)
        image_path = file_arg[7:]
        if not os.path.exists(image_path):
            logging.error(f"图片文件不存在: {image_path}"); sys.exit(1)
        with open(image_path, "rb") as img_file:
            b64 = base64.b64encode(img_file.read()).decode('utf-8')
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    
    def add_filter(self, queue_name: str, filter_fn: Callable[[Dict], bool]):
        self._filters[queue_name] = filter_fn
        return self
    
    def _apply_filters(self, data: Dict):
        for queue_name, filter_fn in self._filters.items():
            try:
                if filter_fn(data): self._message_queues[queue_name].append(data)
            except Exception as e: logging.error(f"过滤器错误: {e}")
    
    async def queue(self, queue_name: str) -> AsyncGenerator[Dict, None]:
        q = self._message_queues[queue_name]
        while True:
            if q: yield q.popleft()
            else: await asyncio.sleep(0.1)
    
    async def handle_stream(self, response):
        txt, tc_map = "", {}
        async for line in response.aiter_lines():
            if not line or not line.startswith('data: '): continue
            line_json = line[6:]
            if line_json.strip() == '[DONE]': break
            try:
                data = json.loads(line_json)
                self._apply_filters(data)
                if 'choices' not in data or not data['choices']: continue
                delta = data['choices'][0].get('delta', {})
                if c := delta.get('content'): 
                    txt += c
                    if self.settings.printable: print(c, end='', flush=True)
                #if c := delta.get('content'): print(c, end='', flush=True); txt += c
                if tcd := delta.get('tool_calls'):
                    for tc in tcd:
                        idx, tid = tc.get('index', 0), tc.get('id')
                        if tid and tid not in tc_map:
                            tc_map[tid] = {'id': tid, 'type': 'function', 'function': {'name': '', 'arguments': ''}, 'index': idx}
                        elif tid is None and idx is not None:
                            matches = [i for i, t in tc_map.items() if t.get('index') == idx]
                            tid = matches[0] if matches else None
                        if tid and tc.get('function'):
                            fd = tc['function']
                            if n := fd.get('name'): tc_map[tid]['function']['name'] += n
                            if a := fd.get('arguments'): tc_map[tid]['function']['arguments'] += a
            except Exception as e: logging.error(f"解析错误: {e}")
        if txt and self.settings.printable: print()
        if not tc_map: return None, txt
        tool_calls = sorted(tc_map.values(), key=lambda x: x.get('index', 0))
        for tc in tool_calls: tc.pop('index', None)
        valid_tc = []
        for tc in tool_calls:
            if tc['function']['name'] and tc['function']['arguments'].strip():
                try:
                    json.loads(tc['function']['arguments'])
                    valid_tc.append(tc)
                except: logging.debug(f"工具调用参数解析失败")
        return valid_tc if valid_tc else None, txt
    
    async def talk(self, prompt: str = None, stream: Optional[bool] = None):
        use_stream = not self.settings.no_stream if stream is None else stream
        content_parts = []
        if prompt: content_parts.append({"type": "text", "text": prompt})
        elif self.settings.prompt: content_parts.append({"type": "text", "text": " ".join(self.settings.prompt)})
        if self.settings.files:
            for f in self.settings.files: content_parts.append(self.process_file_argument(f))
        
        messages = []
        if self.settings.system_prompt: messages.append({"role": "system", "content": self.settings.system_prompt})
        if self.db_manager: messages.extend(self.db_manager.get_previous_messages())
        messages.append({"role": "user", "content": content_parts})
        
        headers = {"Content-Type": "application/json"}
        if api_key := self.settings.api_key or self.settings.get_api_key(): headers["Authorization"] = f"Bearer {api_key}"
        final_content, iteration = "", 0
        
        async with httpx.AsyncClient() as client:
            while iteration < 10:
                iteration += 1
                payload = {
                    "model": self.settings.model,
                    "messages": messages,
                    "temperature": self.settings.opts.get('temperature', 0.7),
                    "top_p": self.settings.opts.get('top_p', 1.0),
                    "n": self.settings.opts.get('n', 1),
                    "reasoning_effort": ['low','medium', 'high'][self.settings.opts.get('reasoning_effort', 2)],    # Reasoning Effort High by default
                    "max_tokens": 8192,
                    "stream": use_stream
                }
                if self.fn_calls and self.fn_calls.tools:
                    payload["tools"] = self.fn_calls.tools
                    payload["tool_choice"] = "auto"
                resp = await client.post(self.settings.endpoint, headers=headers, json=payload, timeout=60.0)
                if resp.status_code != 200:
                    logging.error(f"API Request Failed: {resp.status_code}")
                    logging.error(f"Server Error Information: {resp.text}")
                    sys.exit(1)
                if use_stream: tool_calls, assistant_content = await self.handle_stream(resp)
                else:
                    data = resp.json()
                    self._apply_filters(data)
                    assistant_message = data['choices'][0]['message']
                    assistant_content = assistant_message.get('content', '')
                    tool_calls = assistant_message.get('tool_calls')
                    if assistant_content: logging.info(assistant_content)
                
                final_content = assistant_content
                if self.fn_calls and tool_calls:
                    messages.append({"role": "assistant", "content": assistant_content, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        fn = tc['function']['name']
                        try: args = json.loads(tc['function']['arguments'])
                        except: args = {}
                        logging.info(f'tool_calling: {fn}({args})')
                        result = await self.fn_calls.execute(fn, args)
                        messages.append({"role": "tool", "tool_call_id": tc['id'], "name": fn, "content": str(result)})
                    continue
                break
        if self.db_manager:
            self.db_manager.save_message("user", json.dumps(content_parts))
            self.db_manager.save_message("assistant", final_content)
        return final_content
    
    def ttyrun(self):
        stdin_content = None if sys.stdin.isatty() else sys.stdin.read()
        prompt = " ".join(self.settings.prompt) if self.settings.prompt else ""
        if stdin_content: prompt = stdin_content + "\n" + prompt
        
        if self.settings._args.interactive:
            import readline
            while True:
                prompt = input(" > ")
                if prompt.lower() in ['exit', 'quit']: break
                elif prompt.strip():
                    print()
                    asyncio.run(self.talk(prompt))
                    print()
            return
        if not prompt and not self.settings.files:
            logging.error("错误: 请提供 prompt 或文件"); sys.exit(1)
        return asyncio.run(self.talk(prompt))

if __name__ == "__main__":
    aiai = AIChat()
    aiai.ttyrun()

