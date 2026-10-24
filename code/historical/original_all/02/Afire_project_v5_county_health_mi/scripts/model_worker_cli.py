from __future__ import annotations
import argparse, json, sys, traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_all as r

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--task',required=True); ap.add_argument('--output',required=True)
    args=ap.parse_args(); task=json.loads(args.task)
    try: result=r.fit_model_task(task)
    except Exception as e: result={'ok':False,'task':task,'error':repr(e),'traceback':traceback.format_exc()}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
if __name__=='__main__': main()
