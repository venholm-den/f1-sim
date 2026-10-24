"""Register/capture/score the independent form research cohort; no uploads."""
import argparse
import json
from pathlib import Path

from portable_app.instance_lock import workspace_lock
from src.app_services.form_shadow import register,read_suite,capture,score


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--register',type=Path,metavar='BENCHMARK_FOLDER')
    parser.add_argument('--capture',type=Path,metavar='FROZEN_FORECAST')
    parser.add_argument('--score',action='store_true')
    parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args();root=args.workspace.resolve();result={}
    if args.verify_only:
        if args.register or args.capture or args.score:parser.error('Verification cannot mutate evidence.')
        suite=read_suite(root)
        print(json.dumps({'status':'verified' if suite else 'disabled','suite_sha256':suite[2] if suite else None}));return
    with workspace_lock(root):
        if args.register:result['registered']=register(root,(root/args.register).resolve())
        if args.capture:result['capture']=capture(root,(root/args.capture).resolve())
        if args.score:result['scoring']=score(root)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
