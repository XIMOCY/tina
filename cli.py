import argparse
from tina.tina import Tina
from tina.LLM import llama
import tempfile
import os
import shutil

def main():
    parser = argparse.ArgumentParser(description='tina 命令行工具')
    subparsers = parser.add_subparsers(dest="command",required=True)

    run_parser = subparsers.add_parser("run",help="Run a model")
    run_parser.add_argument("--model",type=str,help="模型路径",required=True)
    run_parser.add_argument("--context",type=int,default=2024,help="上下文长度")

    args = parser.parse_args()

    if args.command == "run":
        llm = llama(path=args.model,context_length=args.context)
        llm.chat()