from flask import Flask, request
import json
import redis
import requests
import urllib

app = Flask(__name__)

if __name__ == '__main__':
    r = redis.StrictRedis(host='localhost', port=6379, db=0)
    tg_bot_token = open("tg_bot_token.txt").read().strip()
else:
    r = redis.StrictRedis(host='redis', port=6379, db=0)
    tg_bot_token = open("/run/secrets/tg_bot_token").read().strip()

def get_status(nodes):
    status = []
    for node in nodes:
        status.append({'info':{},'gpus':{}})
        last_active = json.loads(r.get(node+b"/info"))['last_active']
        status[-1]['info']['last_active'] = last_active
        gpus = r.smembers(node)
        for gpu in gpus:
            card = {}
            card['info'] = json.loads(r.get(gpu+b"/info"))
            card['procs'] = []
            for pid in r.smembers(gpu):
                card['procs'].append(json.loads(r.get(pid)))
            status[-1]['gpus'][gpu.decode()] = card

    return status

def status_strings(status):
    msgs = []
    for node in status:
        msg = '<pre>'
        for gpu in node['gpus']:
            if node['gpus'][gpu]['procs']:
                msg += f"{gpu}:  {node['gpus'][gpu]['info']['util']}%  {node['gpus'][gpu]['info']['temp']}°C  ({node['gpus'][gpu]['info']['free']} free):\n"
                for proc in node['gpus'][gpu]['procs']:
                    msg += f"{proc['pid'] :<6} {proc['user'] :^8} {proc['since'] :^15} {proc['usage']}  {proc['cmd']}\n"
            else:
                msg += f"</pre><b>{gpu}:  {node['gpus'][gpu]['info']['util']}%  {node['gpus'][gpu]['info']['temp']}°C  ({node['gpus'][gpu]['info']['free']} free):</b><pre>\n"
            msg += "\n"
        last_active = node['info']['last_active']
        msg += f"</pre>\nLast active user: {last_active['user']} {last_active['last']} {last_active['what']}"
        msgs.append(msg)
    return msgs

@app.route('/', methods=['GET', 'POST'])
def index():
    msg = ''
    if request.method == 'POST':
        data = request.json['gpus']
        node = request.json['info']['node']
        r.set(node+"/info", json.dumps(request.json['info']))
        cards = set()
        if r.sadd("nodes", node):
            msg += f"New node {node}\n"
        for card in data:
            gpu = f"{node}-{card['id']}-{card['gpu']}"
            cards.add(gpu.encode())

        nodegpus = r.smembers(node)
        if cards - nodegpus:
            for gpu in cards - nodegpus:
                msg += f"New GPU {gpu.decode()}\n"
                r.sadd(node, gpu)
        if nodegpus - cards:
            for gpu in nodegpus - cards:
                msg += f"{gpu.decode()} not reported. removed\n"
                r.srem(node, gpu)
                r.delete(gpu)
                r.delete(gpu+b"/info")

        procs = {}
        removed = set()
        for card in data:
            gpu = f"{node}-{card['id']}-{card['gpu']}"
            r.set(gpu+"/info", json.dumps({key: card[key] for key in ['util','temp','free']}))
            sgpu = set()
            for proc in card['procs']:
                pid = f"{node}/{proc['pid']}".encode()
                sgpu.add(pid)
                procs[pid] = proc

            gpuprocs = r.smembers(gpu)
            if sgpu - gpuprocs:
                for pid in sgpu - gpuprocs:
                    msg += f"{procs[pid]['user']} create process(pid {procs[pid]['pid']}) on {gpu}\n"
                    r.sadd(gpu,pid)
            for pid in sgpu:
                r.set(pid,json.dumps(procs[pid]))
            if gpuprocs - sgpu:
                for pid in gpuprocs - sgpu:
                    temp = json.loads(r.get(pid))
                    msg += f"process(pid {temp['pid']} by {temp['user']}) on {gpu} exited\n"
                    r.srem(gpu,pid)
                    removed.add(pid)

        for card in data:
            for proc in card['procs']:
                pid = f"{node}/{proc['pid']}".encode()
                if pid in removed:
                    removed.remove(pid)

        for pid in removed:
            r.delete(pid)

    if request.method == 'POST':
        if msg:
            status = get_status(set([node.encode()]))
            r.set('last_event', msg)
            msgs = status_strings(status) + ["<b>" + msg + '</b>\n<a href="http://jp.xydustc.me:12340">View full status</a>']
            for m in msgs:
                if __name__ == '__main__':
                    requests.get("https://api.telegram.org/"+tg_bot_token+"/sendMessage?chat_id=-1001221829815&parse_mode=HTML&text="
                                + urllib.parse.quote_plus(m), proxies={'https':'socks5://172.27.80.1:2088'})
                else:
                    requests.get("https://api.telegram.org/"+tg_bot_token+"/sendMessage?chat_id=-1001221829815&parse_mode=HTML&text="
                                + urllib.parse.quote_plus(m))
        return ""
    if request.method == 'GET':
        status = get_status(r.smembers("nodes"))
        msg = r.get('last_event').decode().replace('\n', "<br>")
        msg += "<pre>---------------------------------------------</pre>".join(status_strings(status))
        return msg

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=12340, debug=True)