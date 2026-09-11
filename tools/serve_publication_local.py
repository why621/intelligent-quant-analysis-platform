"""Serve an explicit local publication with persistent isolated jobs and built UI."""
import argparse
import os
from pathlib import Path
from flask import send_from_directory

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publication',required=True,type=Path)
    parser.add_argument('--jobs',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args()
    root=Path('artifacts').resolve()
    if not args.jobs.resolve().is_relative_to(root) or not args.publication.resolve().is_relative_to(root):
        parser.error('local artifact paths required')
    args.jobs.parent.mkdir(parents=True,exist_ok=True)
    os.environ['QUANT_PUBLICATION_ROOT']=str(args.publication.resolve())
    os.environ['BACKTEST_DB_PATH']=str(args.jobs.resolve())
    from app import create_app
    application=create_app()
    dist=Path('apps/frontend/dist').resolve()
    @application.get('/')
    def index():
        return send_from_directory(dist,'index.html')
    @application.get('/assets/<path:name>')
    def assets(name):
        return send_from_directory(dist/'assets',name)
    application.run(host='127.0.0.1',port=args.port,threaded=True,use_reloader=False)


if __name__ == "__main__":
    main()
