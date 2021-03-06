#!/usr/bin/env python3
# __author__ klzsysy

from flask import Flask, send_file, make_response, redirect, Response
import requests
import logging
import os
import shutil
import threading
import re
import gzip

class Share(object):
    def __init__(self):
        self.PROXY_URL_PREFIX = os.getenv('PROXY_URL_PREFIX', 'zipcache')
        self.DOWNLOAD_PREFIX = 'public/' + os.getenv('DOWNLOAD_PREFIX', self.PROXY_URL_PREFIX)
        self.JSON_UPSTREAM_URL = os.getenv('MAIN_MIRROR', "https://packagist.laravel-china.org")
        self.UPSTREAM_URL = os.getenv('UPSTREAM_URL', 'https://dl.laravel-china.org')
        self.header = {"User-Agent": os.getenv("USER_AGENT", "Composer/1.6.5 (Darwin; 17.7.0; PHP 7.1.16)")}


class Logging(object):
    def __init__(self, level=logging.DEBUG, name='app'):
        self.level = level
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)

    def get_logger(self):
        ch = logging.StreamHandler()
        fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setLevel(self.level)
        ch.setFormatter(fmt)
        self.logger.addHandler(ch)
        return self.logger


S = Share()
Log = Logging(os.getenv('LOGGING_LEVEL', 10))
logger = Log.get_logger()
app = Flask(__name__)


def download(origin, folder, file, enable_gzip=False):
    try:
        logger.info("start download %s" % origin)
        logger.debug("origin:%s folder:%s file:%s enable_gzip:%s" %(origin, folder, file, enable_gzip))
        r = requests.get(origin, stream=True, headers=S.header)
        if r.status_code == 200:
            r.raw.decode_content = True
            if not os.path.isdir(folder):
                try:
                    os.makedirs(folder)
                    logger.debug("create %s" % folder)
                except BaseException as err:
                    logger.error('create %s failure!!\n%s' % (folder, str(err)))
                    return "", 500
            if enable_gzip:
                with gzip.open(file + '.gz', 'wb') as f:
                    logger.debug("gzip file %s" % file)
                    shutil.copyfileobj(r.raw, f)
                    os.chdir(folder)
                    filename = os.path.split(file)[-1]
                    os.symlink(filename + '.gz', filename)
                    logger.info("created symlink file {filename} --> {filename}.gz".format(filename=filename))
            else:
                with open(file, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
        else:
            return "", r.status_code

    except Exception as err:
        return str(err), 500
    else:
        logger.debug('Cache %s Succeeded ' % file)
        return "Cache Succeeded", 201


@app.route('/%s/<path:url>' % S.PROXY_URL_PREFIX)
def proxy(url):
    # headers = dict(request.headers)
    origin_download_url = S.UPSTREAM_URL + '/' + url
    local_file_path = os.path.join(S.DOWNLOAD_PREFIX, url)
    local_file_dir = os.path.dirname(local_file_path)
    local_file_name = os.path.basename(local_file_path)

    if os.path.isfile(local_file_path):
        response = make_response(send_file(local_file_path))
        response.headers["Content-Disposition"] = "attachment; filename={};".format(local_file_name)
        return response

    # python3 -m timeit -s "import re; re.search('\.(zip|tar\.gz|gz)$', 'zipcache/symfony/event-dispatcher/bfb30c2ad377615a463ebbc875eba64a99f6aa3e.zip')"
    # 100000000 loops, best of 3: 0.0102 usec per loop

    # python3 -m timeit -s "import re; re.match('.*\.(zip|tar\.gz|gz)$', 'zipcache/symfony/event-dispatcher/bfb30c2ad377615a463ebbc875eba64a99f6aa3e.zip')"
    # 100000000 loops, best of 3: 0.0102 usec per loop

    # python3 -m timeit "'zip' in 'zipcache/symfony/event-dispatcher/bfb30c2ad377615a463ebbc875eba64a99f6aa3e.zip'"
    # 10000000 loops, best of 3: 0.0471 usec per loop

    # fast verify url
    if not re.match('.*\.(zip|tar\.gz|gz)$', url):
        return "invalid url", 403

    dl = threading.Thread(target=download, args=(origin_download_url, local_file_dir, local_file_path))
    dl.start()

    return redirect(origin_download_url, code=302)

@app.route('/p/<path:url>')
def proxy_json(url):
    local_json_path = os.path.join("/repo/public/p", url)
    if os.path.isfile(local_json_path):
        with gzip.open(local_json_path, 'rb') as f:
            return Response(f.read(), mimetype='application/json')
    else:
        upstream_json_url = S.JSON_UPSTREAM_URL + '/p/' + url.rstrip('.gz')
        logger.warning("lost cache file %s, redirect to upstream %s" % (local_json_path, upstream_json_url))

        dl = threading.Thread(target=download, args=(upstream_json_url, os.path.dirname(local_json_path), local_json_path, True))
        dl.start()

        return redirect(upstream_json_url, code=302)

def main():
    logger.debug('debug start')
    # app.debug = True
    app.run(host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
