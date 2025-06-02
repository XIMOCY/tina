import argparse
from tina.tina import Tina



def main():
    parser = argparse.ArgumentParser(description='tina 命令行工具')
    subparsers = parser.add_subparsers(dest="command",required=True)

    run_parser = subparsers.add_parser("run",help="运行tina示例程序")
    args = parser.parse_args()

    if args.command == "run":
         tina = Tina()
         tina.run()